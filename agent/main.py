"""FastAPI app. Endpoints: /health, /chat. Static demo UI at /."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.config import Config, get_config
from agent.orchestrator import run_turn


_client: anthropic.AsyncAnthropic | None = None
_config: Config | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client, _config
    _config = get_config()
    logging.basicConfig(
        level=getattr(logging, _config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    _client = anthropic.AsyncAnthropic(api_key=_config.anthropic_api_key)
    yield


app = FastAPI(title="Clinical Co-Pilot Agent", version="0.1.0", lifespan=lifespan)


class ChatRequest(BaseModel):
    patient_id: str = Field(..., description="Patient identifier locked to this conversation")
    message: str = Field(..., description="The clinician's natural-language question")


class ChatResponse(BaseModel):
    response: str
    verified: bool
    trace: dict


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": _config.model if _config else None}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if _client is None or _config is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    result = await run_turn(
        client=_client,
        model=_config.model,
        patient_id=req.patient_id,
        user_message=req.message,
    )

    trace = {
        "plan_tool_calls": [
            {"name": tc["name"], "input": tc["input"]}
            for tc in result.trace.plan_tool_calls
        ],
        "retrieved_source_ids": result.trace.retrieved_source_ids,
        "verification": (
            {
                "passed": result.trace.verification.passed,
                "note": result.trace.verification.note,
                "cited_ids": result.trace.verification.cited_ids,
                "unknown_ids": result.trace.verification.unknown_ids,
            }
            if result.trace.verification
            else None
        ),
        "refused": result.trace.refused,
        "refusal_reason": result.trace.refusal_reason,
        "usage": {
            "plan": result.trace.plan_usage,
            "reason": result.trace.reason_usage,
        },
    }

    return ChatResponse(response=result.response, verified=result.verified, trace=trace)


# Mount the static demo UI at root. Registered AFTER the API routes so /health
# and /chat take precedence; everything else (/, /index.html, /styles.css, etc.)
# falls through to the static directory.
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="ui")
