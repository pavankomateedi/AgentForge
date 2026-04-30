"""FastAPI app. Endpoints: /health, /chat (auth-protected), /auth/*. Static UI at /."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from agent import audit, auth, observability
from agent.auth import ABSOLUTE_TIMEOUT_SECONDS, User, get_current_user
from agent.config import Config, get_config
from agent.db import connect, init_db
from agent.orchestrator import run_turn


log = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None
_config: Config | None = None


def _bootstrap_default_user_if_empty(config: Config) -> None:
    """Seed a single user from env vars when (a) the DB is empty and
    (b) all three DEFAULT_USER_* vars are set. Lets Railway redeploys
    self-recover from filesystem ephemerality without a manual CLI step."""
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
    auth.create_user(
        config.database_url,
        username=config.default_user_username,
        email=config.default_user_email,
        password=config.default_user_password,
        role="physician",
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


class ChatRequest(BaseModel):
    patient_id: str = Field(
        ..., description="Patient identifier locked to this conversation"
    )
    message: str = Field(
        ..., description="The clinician's natural-language question"
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

    result = await run_turn(
        client=_client,
        model=_config.model,
        patient_id=req.patient_id,
        user_message=req.message,
        user_id=str(current_user.id),
        user_role=current_user.role,
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
            "trace_id": result.trace.trace_id,
            "verified": result.verified,
            "regenerated": result.trace.regenerated,
            "refused": result.trace.refused,
            "timings_ms": result.trace.timings_ms,
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
