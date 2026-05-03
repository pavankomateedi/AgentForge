"""FastAPI app. Endpoints: /health, /chat (auth-protected), /auth/*. Static UI at /."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from agent import audit, auth, budget, observability, rbac
from agent.auth import ABSOLUTE_TIMEOUT_SECONDS, User, get_current_user
from agent.config import Config, get_config
from agent.db import connect, init_db
from agent.orchestrator import run_turn
from agent.tools import TOOLS


# Cap on history forwarded to the LLM. Eight turns = four user/
# assistant pairs, plenty for follow-ups like "what changed since last
# visit?" without inflating token cost or context window past Plan +
# Reason headroom. Server enforces; clients can send more but only the
# tail wins.
MAX_HISTORY_TURNS = 8


log = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None
_config: Config | None = None


def _bootstrap_default_user_if_empty(config: Config) -> None:
    """Seed a single user from env vars when (a) the DB is empty and
    (b) all three DEFAULT_USER_* vars are set. Lets Railway redeploys
    self-recover from filesystem ephemerality without a manual CLI step.

    Also seeds patient assignments for the bootstrap user so the demo
    flow works without a separate CLI step. RBAC on /chat refuses any
    user without an assignment for the requested patient."""
    if not (
        config.default_user_username
        and config.default_user_email
        and config.default_user_password
    ):
        return
    with connect(config.database_url) as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if count > 0:
        return
    log.info(
        "bootstrap: creating default user %r from env vars",
        config.default_user_username,
    )
    user = auth.create_user(
        config.database_url,
        username=config.default_user_username,
        email=config.default_user_email,
        password=config.default_user_password,
        role="physician",
    )
    # Seed assignments for every shipped demo patient; idempotent.
    from agent.demo_data import DEMO_PATIENTS

    for demo_patient_id in DEMO_PATIENTS.keys():
        rbac.assign_patient(
            config.database_url,
            user_id=user.id,
            patient_id=demo_patient_id,
        )
    log.info(
        "bootstrap: assigned %r to %d demo patient(s): %s",
        config.default_user_username,
        len(DEMO_PATIENTS),
        list(DEMO_PATIENTS.keys()),
    )


def _bootstrap_extra_users(config: Config) -> None:
    """Seed any users listed in EXTRA_USERS_JSON. Idempotent: existing
    usernames are skipped, existing patient assignments are no-ops.

    Survives Railway-style ephemeral filesystems — every cold start
    re-seeds whatever the env var declares, so demo accounts (nurse,
    resident, second physician) persist across redeploys without manual
    CLI intervention.

    Schema (JSON list):
        [
          {
            "username":     "nurse.adams",
            "email":        "nurse.adams@example.com",
            "password":     "NurseDemo!2026",
            "role":         "nurse",
            "patients":     ["demo-001"],
            "totp_secret":  "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
          }
        ]

    Optional `totp_secret` pre-enrolls MFA with the given base32 secret
    so a known TOTP code can be generated externally — the only safe
    way to hand graders a working credential without per-grader
    enrollment ceremony. The secret MUST be valid base32; an invalid
    secret leaves the account un-enrolled (forces in-app enrollment on
    first login). This pattern is acceptable for synthetic-data demos
    only — see HIPAA_COMPLIANCE.md.

    Optional `bypass_mfa: true` opts the account out of the MFA
    challenge entirely — password is enough to land in the workspace.
    Independent of `totp_secret`. Audit log records LOGIN_MFA_BYPASSED
    on every such login so the carve-out is observable. NEVER set on
    a real-PHI account.

    Validation: missing keys, unknown roles, malformed JSON → log and
    skip the offending entry. Other entries still process. We never
    crash the lifespan over a bad env var."""
    if not config.extra_users_json:
        return
    try:
        entries = json.loads(config.extra_users_json)
    except json.JSONDecodeError as e:
        log.error("EXTRA_USERS_JSON is not valid JSON; skipping. Error: %s", e)
        return
    if not isinstance(entries, list):
        log.error("EXTRA_USERS_JSON must be a JSON list; got %s. Skipping.", type(entries).__name__)
        return

    for entry in entries:
        if not isinstance(entry, dict):
            log.warning("EXTRA_USERS_JSON entry not an object; skipping: %r", entry)
            continue
        username = entry.get("username")
        email = entry.get("email")
        password = entry.get("password")
        role = entry.get("role", "physician")
        patients = entry.get("patients", []) or []

        if not (username and email and password):
            log.warning(
                "EXTRA_USERS_JSON entry missing username/email/password; skipping: %r",
                entry,
            )
            continue
        if not rbac.is_valid_role(role):
            log.warning(
                "EXTRA_USERS_JSON entry has unknown role %r; skipping: %s",
                role, username,
            )
            continue

        existing = auth.get_user_by_username(config.database_url, username)
        if existing is None:
            user = auth.create_user(
                config.database_url,
                username=username,
                email=email,
                password=password,
                role=role,
            )
            log.info(
                "bootstrap: extra user %r created (id=%d, role=%s)",
                user.username, user.id, user.role,
            )
            user_id = user.id
        else:
            log.info(
                "bootstrap: extra user %r already exists (id=%d); ensuring assignments",
                existing.username, existing.id,
            )
            user_id = existing.id

        for pid in patients:
            if not isinstance(pid, str):
                log.warning(
                    "EXTRA_USERS_JSON: non-string patient id for %r; skipping: %r",
                    username, pid,
                )
                continue
            rbac.assign_patient(config.database_url, user_id=user_id, patient_id=pid)
        if patients:
            log.info(
                "bootstrap: extra user %r assigned to %d patient(s): %s",
                username, len(patients), patients,
            )

        totp_secret = entry.get("totp_secret")
        if totp_secret:
            _pre_enroll_totp(config.database_url, user_id, username, totp_secret)

        # bypass_mfa is independent of totp_secret. Honored on every
        # cold start so flipping the flag in EXTRA_USERS_JSON takes
        # effect after a redeploy without manual DB poking.
        if entry.get("bypass_mfa") is True:
            auth._set_bypass_mfa(config.database_url, user_id, True)
            log.info(
                "bootstrap: %r flagged bypass_mfa=true (synthetic-data only)",
                username,
            )
        elif entry.get("bypass_mfa") is False:
            # Explicit False reconciles a previously-flagged account
            # back to mandatory MFA on the next cold start.
            auth._set_bypass_mfa(config.database_url, user_id, False)


def _pre_enroll_totp(
    database_url: str, user_id: int, username: str, secret: str
) -> None:
    """Pre-enroll a user's TOTP with a known base32 secret. Idempotent —
    running twice with the same secret is a no-op. Invalid base32 logs
    and skips (the user simply isn't pre-enrolled and will go through
    the normal enrollment flow on first login)."""
    import pyotp

    if not isinstance(secret, str) or not secret.strip():
        log.warning(
            "EXTRA_USERS_JSON: totp_secret for %r is empty; skipping pre-enroll",
            username,
        )
        return
    try:
        # pyotp accepts the secret silently and validates lazily on .now().
        pyotp.TOTP(secret).now()
    except Exception as e:
        log.warning(
            "EXTRA_USERS_JSON: totp_secret for %r is not valid base32 "
            "(%s); skipping pre-enroll",
            username, e,
        )
        return
    auth._save_totp_secret(database_url, user_id, secret)
    log.info("bootstrap: pre-enrolled TOTP for %r", username)


def _backfill_assignments_for_legacy_users(config: Config) -> None:
    """Any existing physician with zero patient assignments gets default
    assignments to every shipped demo patient. Keeps pre-RBAC users
    working after the schema change without manual intervention.
    Nurses and residents are required to have assignments granted
    explicitly — no auto-backfill for those roles."""
    from agent.demo_data import DEMO_PATIENTS

    with connect(config.database_url) as conn:
        unassigned = conn.execute(
            "SELECT u.id, u.username FROM users u "
            "WHERE u.role = 'physician' AND NOT EXISTS ("
            "  SELECT 1 FROM patient_assignments a WHERE a.user_id = u.id"
            ")"
        ).fetchall()
    for row in unassigned:
        for demo_patient_id in DEMO_PATIENTS.keys():
            rbac.assign_patient(
                config.database_url,
                user_id=row["id"],
                patient_id=demo_patient_id,
            )
        log.info(
            "rbac backfill: assigned %r (id=%d) to %d demo patient(s)",
            row["username"],
            row["id"],
            len(DEMO_PATIENTS),
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client, _config
    _config = get_config()
    logging.basicConfig(
        level=getattr(logging, _config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    init_db(_config.database_url)
    _bootstrap_default_user_if_empty(_config)
    _bootstrap_extra_users(_config)
    _backfill_assignments_for_legacy_users(_config)
    _client = anthropic.AsyncAnthropic(api_key=_config.anthropic_api_key)
    observability.init(
        public_key=_config.langfuse_public_key,
        secret_key=_config.langfuse_secret_key,
        host=_config.langfuse_host,
    )
    try:
        yield
    finally:
        observability.shutdown()


app = FastAPI(title="Clinical Co-Pilot Agent", version="0.2.0", lifespan=lifespan)

# Session middleware MUST be added before route handlers run. The cookie's
# absolute max-age is the upper bound; idle-timeout enforcement happens in
# auth.get_current_user (5 min idle).
_config_for_middleware = get_config()
if (
    not _config_for_middleware.session_secret
    or len(_config_for_middleware.session_secret) < 16
):
    raise RuntimeError(
        "SESSION_SECRET is not set or too short. "
        "Generate one with: "
        'python -c "import secrets; print(secrets.token_urlsafe(32))"'
    )
app.add_middleware(
    SessionMiddleware,
    secret_key=_config_for_middleware.session_secret,
    max_age=ABSOLUTE_TIMEOUT_SECONDS,
    https_only=_config_for_middleware.session_https_only,
    same_site="lax",
)

app.include_router(auth.router)


class ChatTurn(BaseModel):
    """One prior exchange the client wants the agent to consider for
    context. The role mirrors Anthropic's API roles. Content is plain
    text — `<source/>` tags from prior assistant turns are kept (the
    Reason model uses them for follow-up coherence) but the verifier
    still only validates the CURRENT turn's output against the current
    turn's retrieval bundle."""

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    patient_id: str = Field(
        ..., description="Patient identifier locked to this conversation"
    )
    message: str = Field(
        ..., description="The clinician's natural-language question"
    )
    # Optional prior turns for follow-up coherence. The server caps to
    # MAX_HISTORY_TURNS regardless of what the client sends, both to
    # bound LLM cost and to defend against a malicious client trying
    # to blow up the context window. Default empty preserves single-
    # turn behavior.
    history: list[ChatTurn] = Field(
        default_factory=list,
        max_length=64,
        description=(
            "Prior turns in this conversation. Server keeps the last "
            f"{MAX_HISTORY_TURNS} entries."
        ),
    )


class ChatResponse(BaseModel):
    response: str
    verified: bool
    trace: dict


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": _config.model if _config else None}


@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    if _client is None or _config is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # ---- Cost guard: per-user daily token budget ----
    # Hard cap on tokens per user per UTC day. Refuses with 429
    # before invoking the agent so a runaway client cannot keep
    # accruing cost; current usage and the cap are surfaced in the
    # response detail so the user knows what happened.
    if budget.is_over_budget(
        _config.database_url,
        user_id=current_user.id,
        budget=_config.daily_token_budget,
    ):
        used = budget.get_today_usage(
            _config.database_url, user_id=current_user.id
        )
        audit.record(
            _config.database_url,
            audit.AuditEvent.BUDGET_EXCEEDED,
            user_id=current_user.id,
            ip_address=_client_ip(request),
            details={
                "tokens_used_today": used,
                "daily_budget": _config.daily_token_budget,
                "patient_id": req.patient_id,
            },
        )
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily token budget exceeded "
                f"({used}/{_config.daily_token_budget}). "
                f"Resets at UTC midnight."
            ),
        )

    # ---- RBAC: assignment gate ----
    # Refuse before invoking the agent if the user isn't assigned to
    # this patient. This is the v0 stand-in for OpenEMR's acl_check()
    # and it's enforced upstream of the orchestrator so an unauthorized
    # request never reaches the LLM or the FHIR layer.
    if not rbac.is_assigned(
        _config.database_url,
        user_id=current_user.id,
        patient_id=req.patient_id,
    ):
        audit.record(
            _config.database_url,
            audit.AuditEvent.CHAT_REFUSED_UNASSIGNED,
            user_id=current_user.id,
            ip_address=_client_ip(request),
            details={
                "patient_id": req.patient_id,
                "user_role": current_user.role,
            },
        )
        raise HTTPException(
            status_code=403,
            detail=(
                f"You are not assigned to patient {req.patient_id!r}. "
                f"Ask an administrator to grant access."
            ),
        )

    # ---- Role-aware tool filtering ----
    available_tools = rbac.filter_tools_for_role(current_user.role, TOOLS)

    # ---- Conversation history (capped) ----
    # Trim BEFORE handing to the orchestrator so an oversized client
    # request can't accidentally inflate token cost or trip the per-
    # call context limit. We keep the tail because the most recent
    # turns disambiguate the current question best.
    history_payload = [
        {"role": h.role, "content": h.content}
        for h in req.history[-MAX_HISTORY_TURNS:]
    ]

    result = await run_turn(
        client=_client,
        model=_config.model,
        patient_id=req.patient_id,
        user_message=req.message,
        user_id=str(current_user.id),
        user_role=current_user.role,
        available_tools=available_tools,
        history=history_payload,
    )

    # ---- Resident watermark ----
    # Residents see physician-equivalent tools but every response is
    # marked so downstream consumers know the briefing is from a
    # trainee. Watermark is appended so it survives even if the LLM
    # ignores formatting hints.
    if rbac.is_resident(current_user.role) and result.response.strip():
        result.response = (
            f"{result.response}\n\n"
            f"— Supervised review recommended (resident response)."
        )

    # Record token usage for the cost guard. We accrue usage even on
    # refusals/regenerations because they cost real tokens; the user
    # sees the cap creep up correspondingly.
    turn_tokens = budget.total_tokens_in_turn(
        result.trace.plan_usage, result.trace.reason_usage
    )
    if turn_tokens > 0 and _config.daily_token_budget > 0:
        budget.record_usage(
            _config.database_url,
            user_id=current_user.id,
            tokens=turn_tokens,
        )

    # Audit AFTER the turn so the trace_id can be joined to the request.
    # The /chat call has already been authenticated; an audit record on a
    # request whose orchestrator never finished isn't more useful than
    # one keyed on trace_id with the verification outcome attached.
    audit.record(
        _config.database_url,
        audit.AuditEvent.CHAT_REQUEST,
        user_id=current_user.id,
        ip_address=_client_ip(request),
        details={
            "patient_id": req.patient_id,
            "message_len": len(req.message),
            "history_len": len(history_payload),
            "trace_id": result.trace.trace_id,
            "verified": result.verified,
            "regenerated": result.trace.regenerated,
            "refused": result.trace.refused,
            "timings_ms": result.trace.timings_ms,
            "tokens_used_this_turn": turn_tokens,
        },
    )

    verification = result.trace.verification
    trace = {
        "trace_id": result.trace.trace_id,
        "trace_url": observability.trace_url(result.trace.trace_id),
        "plan_tool_calls": [
            {"name": tc["name"], "input": tc["input"]}
            for tc in result.trace.plan_tool_calls
        ],
        "retrieved_source_ids": result.trace.retrieved_source_ids,
        "verification": (
            {
                "passed": verification.passed,
                "note": verification.note,
                "cited_ids": verification.cited_ids,
                "unknown_ids": verification.unknown_ids,
                "value_mismatches": [
                    {
                        "source_id": mm.source_id,
                        "cited_value": mm.cited_value,
                        "record_value": mm.record_value,
                    }
                    for mm in verification.value_mismatches
                ],
            }
            if verification
            else None
        ),
        "rule_findings": [
            {
                "rule_id": f.rule_id,
                "category": f.category,
                "severity": f.severity,
                "message": f.message,
                "evidence_source_ids": list(f.evidence_source_ids),
            }
            for f in result.trace.rule_findings
        ],
        "regenerated": result.trace.regenerated,
        "refused": result.trace.refused,
        "refusal_reason": result.trace.refusal_reason,
        "timings_ms": result.trace.timings_ms,
        "usage": {
            "plan": result.trace.plan_usage,
            "reason": result.trace.reason_usage,
        },
    }

    return ChatResponse(
        response=result.response, verified=result.verified, trace=trace
    )


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


# Static UI mounted last so /auth/* and /chat take precedence.
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="ui")
