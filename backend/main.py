import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from observability import (
    flush_traces,
    init_sentry,
    is_tracing_enabled,
)
from orchestrator import (
    AGENTS_CONFIG,
    ensure_report_for_session,
    generate_fact_check,
    generate_rebuttal_response,
    get_scoring_radar,
    handle_verdict_pushback,
    sessions,
    stream_echochamber,
)
from persistence import get_repository, init_repository_schema
from persistence.database import dispose_engine
from persistence.sync import SessionPersistenceBridge
from prompts import ANSWER_COACH_PROMPT
from pydantic import BaseModel, Field
from rate_limit import install_rate_limiter
from services.llm import llm_provider
from sse_starlette.sse import EventSourceResponse

# ─── Logging configuration (Tier 0f) ─────────────────────────────
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Rate limiting (Tier 0f). Default: 60 req/min per IP, in-memory storage.
# Set RATE_LIMIT_ENABLED=false to disable. Wire per-endpoint limits in Tier 1.
if os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes"):
    install_rate_limiter(app)
    logger.info("Rate limiting installed (default: 60 req/min per IP).")
else:
    logger.info("Rate limiting disabled via RATE_LIMIT_ENABLED=false.")

# Persistence bridge (Tier 0c). Mirrors writes to the legacy `sessions`
# dict into the durable SessionRepository. Defaults to the in-memory
# implementation, which means the bridge is effectively a no-op in dev.
# Set PANELMIND_REPOSITORY=sqlalchemy to enable durable storage.
_persistence_bridge: SessionPersistenceBridge | None = None


def _bridge() -> SessionPersistenceBridge:
    """Lazy accessor so tests can swap the repository before the first call."""
    global _persistence_bridge
    if _persistence_bridge is None:
        _persistence_bridge = SessionPersistenceBridge(get_repository())
    return _persistence_bridge


# ─── CORS lockdown (Tier 0f) ───────────────────────────────────────
# Read the allowed origins from the ALLOWED_ORIGINS env var. Default
# to localhost dev origins. In production, set this to your real domain.
# Setting `allow_credentials=True` together with `allow_origins=["*"]`
# is a security hazard — always be explicit.
_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Lifecycle hooks (Tier 0c) ─────────────────────────────────────
# On startup we initialise the persistence layer. On shutdown we close
# any open DB connections cleanly. Both are no-ops for the in-memory
# repository.


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        await init_repository_schema()
        logger.info("Persistence schema ready.")
    except Exception as e:
        # Don't crash the app if the DB is unavailable in dev — log and
        # continue. Production deployments should fail fast at this step.
        logger.warning("Persistence schema init skipped: %s", e)
    # Tier 1a: Langfuse LLM tracing (no-op in dev)
    try:
        if is_tracing_enabled():
            logger.info("Langfuse tracing ENABLED.")
        else:
            logger.info("Langfuse tracing disabled (no LANGFUSE_PUBLIC_KEY set).")
    except Exception:
        pass
    # Tier 1b: Sentry error tracking (no-op in dev)
    try:
        init_sentry()
    except Exception as e:
        logger.warning("Sentry init skipped: %s", e)
    yield
    # Shutdown
    try:
        await dispose_engine()
    except Exception as e:
        logger.warning("Engine dispose skipped: %s", e)
    try:
        flush_traces()
    except Exception as e:
        logger.debug("Trace flush skipped: %s", e)


# Replace the default lifespan handler. We assign explicitly so we don't
# lose the CORS middleware behavior.
app.router.lifespan_context = lifespan


def _utcnow() -> datetime:
    """Current UTC time. Used for API key expiry, etc."""
    return datetime.now(UTC)


def sanitize_pitch_input(text: str) -> str:
    """
    Cleans user pitch input before it enters any prompt.

    - Strips HTML tags
    - Removes prompt injection patterns
    - Normalizes whitespace
    - Truncates to safe length

    Note: this is best-effort sanitization, not a security boundary. Never
    rely on it for actual safety — always run user input through a
    secondary validation layer before letting it near sensitive tools.
    """
    if not text or not isinstance(text, str):
        raise ValueError("Pitch must be a non-empty string")

    # Strip HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Remove common prompt injection patterns.
    # Each pattern is matched case-insensitively and replaced with [removed].
    injection_patterns = [
        # Direct instruction overrides — match "ignore" followed by anything
        # up to 3 intervening words before "instructions".
        r"ignore\s+(?:[\w]+\s+){0,3}instructions?",
        r"disregard\s+(?:[\w]+\s+){0,3}instructions?",
        r"forget\s+(?:[\w]+\s+){0,3}(?:everything|all|instructions?)",
        # Persona-override attempts
        r"you are now",
        r"new persona",
        r"act as",
        r"pretend to be",
        # System-prompt markers
        r"system prompt",
        r"###\s*instructions",
        # ChatML / Anthropic-style markers
        r"\\n\\n(human|assistant|system):",
        r"<\|im_start\|>",
        r"<\|im_end\|>",
    ]
    for pattern in injection_patterns:
        text = re.sub(pattern, "[removed]", text, flags=re.IGNORECASE)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Truncate to 1500 characters — enough for any real pitch
    if len(text) > 1500:
        text = text[:1500] + "..."

    return text

class PitchRequest(BaseModel):
    pitch_transcript: str
    session_id: str | None = None
    difficulty: str = "standard"

class EvaluationRequest(BaseModel):
    pitch: str
    provider: str = "ollama"
    pitcher_id: str | None = None

class ConversationAnswer(BaseModel):
    session_id: str
    message: str
    interrupt: bool = False
    provider: str = "groq"

class SummaryApproval(BaseModel):
    session_id: str
    approved: bool
    corrected_summary: str | None = None

class ChallengeRequest(BaseModel):
    session_id: str
    agent_id: str
    agent_claim: str
    challenge_text: str
    provider: str = "groq"

class RebuttalRequest(BaseModel):
    session_id: str
    agent_id: str
    agent_claim: str
    rebuttal_text: str
    provider: str = "groq"

class PitcherInterruptRequest(BaseModel):
    session_id: str
    message: str = ""  # empty string is valid — means pitcher clicked button without typing

class PushbackRequest(BaseModel):
    session_id: str
    pushback: str
    provider: str = "ollama"

class AnswerCoachRequest(BaseModel):
    session_id: str
    agent_id: str
    question: str

class RetryAnswerRequest(BaseModel):
    session_id: str
    agent_id: str

@app.post("/api/pitch/approve-summary")
async def approve_summary(req: SummaryApproval):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if "hitl_data" not in session:
        session["hitl_data"] = {}

    session["hitl_data"]["corrected_summary"] = req.corrected_summary
    if "events" not in session:
        session["events"] = {
            "answer_event": asyncio.Event(),
            "interrupt_event": asyncio.Event(),
            "summary_approved": asyncio.Event(),
            "speech_complete_event": asyncio.Event(),
        }

    session["events"]["summary_approved"].set()
    return {"status": "ok"}

@app.post("/api/conversation/message")
async def post_message(req: ConversationAnswer):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    message = (req.message or "").strip()[:800]

    if "events" not in session:
        session["events"] = {
            "answer_event": asyncio.Event(),
            "interrupt_event": asyncio.Event(),
            "summary_approved": asyncio.Event(),
            "speech_complete_event": asyncio.Event(),
        }

    session["pending_answer"] = message

    # ✅ FLOW 1: SYSTEM QUESTION → USER ANSWER
    if req.interrupt is False and session.get("awaiting_user_input"):
        session["pending_answer"] = message
        session["awaiting_user_input"] = False

        print(f"[API] answer_event triggered: {message[:50]}...")
        if "events" in session and "answer_event" in session["events"]:
            session["events"]["answer_event"].set()

        return {"status": "answer_received"}

    # ✅ FLOW 2: MANUAL INTERRUPTION (JUMP IN)
    if req.interrupt is True:
        session["interrupt_message"] = message

        print(f"[API] interrupt_event triggered: {message[:50]}...")
        if "events" in session and "interrupt_event" in session["events"]:
            session["events"]["interrupt_event"].set()

        return {"status": "interrupt_received"}

    print(f"[API] Unexpected message format or state. Awaiting: {session.get('awaiting_user_input')}, Interrupt: {req.interrupt}")
    return {"status": "ignored"}

@app.get("/api/agents")
async def get_agents():
    """Returns the active agent configuration for the frontend to consume."""
    return {
        agent_id: {
            "id": agent_id,
            "name": config["name"],
            "role": config["role"]
        }
        for agent_id, config in AGENTS_CONFIG.items()
        if agent_id != "interviewer"  # exclude internal agents if desired
    }


@app.get("/api/session/{session_id}/blackswan")
async def get_black_swan_report(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.get("black_swan", {"error": "Report not ready"})

@app.post("/api/pitch/challenge")
async def challenge_claim(req: ChallengeRequest):
    result = await generate_fact_check(req.agent_id, req.agent_claim, req.challenge_text, req.provider)
    return {"fact_check_result": result}

@app.post("/api/conversation/rebuttal")
async def submit_rebuttal(req: RebuttalRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    response = await generate_rebuttal_response(
        session, req.agent_id, req.agent_claim, req.rebuttal_text, req.provider
    )
    return {"agent_response": response}

@app.post("/api/conversation/speech_complete")
async def speech_complete(request: Request):
    data = await request.json()
    session_id = data.get("session_id")
    session = sessions.get(session_id)
    if session:
        session["is_speaking"] = False
        if "events" in session and "speech_complete_event" in session["events"]:
            session["events"]["speech_complete_event"].set()
    return {"status": "ok"}

@app.get("/api/stream/main")
async def main_stream(request: Request, session_id: str, pitch: str, provider: str = "groq", pitcher_id: str = None, mode: str = "venture", aggressiveness: int = 5):
    # FIXED: Enforce valid session_id
    if not session_id or not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required")

    # Validate inputs before anything else
    if not pitch or not pitch.strip():
        async def empty_error():
            yield json.dumps({"event": "error", "data": "Pitch cannot be empty"})
        return EventSourceResponse(empty_error())

    try:
        pitch = sanitize_pitch_input(pitch)
    except ValueError as e:
        _val_err = str(e)
        async def validation_error():
            yield json.dumps({"event": "error", "data": _val_err})
        return EventSourceResponse(validation_error())

    # FIXED: Mandatory mode validation (Fix 6)
    if mode not in ["spark", "venture", "reality"]:
        raise HTTPException(status_code=400, detail="Invalid mode")

    if provider not in ["groq", "anthropic", "gemini", "ollama"]:
        provider = "ollama"

    """The core unified stream calling the LangGraph orchestrator."""
    if session_id not in sessions:
        sessions[session_id] = {
            "session_id": session_id,
            "pitch_summary": pitch,
            "domain": {},
            "hitl_data": {},
            "events": {
                "answer_event": asyncio.Event(),
                "interrupt_event": asyncio.Event(),
                "summary_approved": asyncio.Event(),
                "speech_complete_event": asyncio.Event()
            },
            "pending_answer": "",
            "interrupt_message": "",
            "input_type": "confirmation", # FIXED: Standardized (Fix 5)
            "conversation": [],
            "mode": mode,
            "aggressiveness": aggressiveness,
            "provider": provider,
            "awaiting_pitch_confirmation": False,
            "awaiting_user_input": False,
            "refined_pitch": ""
        }
        # Tier 0c: mirror the new session into the durable repository.
        # Fire-and-forget — failures are logged but never block the request.
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(_bridge().session_created(
                session_id=session_id,
                pitch=pitch,
                mode=mode,
                provider=provider,
                aggressiveness=aggressiveness,
            ))
        except RuntimeError:
            # No running loop (shouldn't happen in a FastAPI handler, but
            # be defensive). The in-process cache still works.
            pass

    async def event_generator():
        try:
            async for event in stream_echochamber(session_id, sessions[session_id], provider, mode):
                if await request.is_disconnected() or sessions[session_id].get("cancelled"):
                    if "graph_task" in sessions[session_id]:
                        sessions[session_id]["graph_task"].cancel()
                    break

                yield event
        except Exception as e:
            yield json.dumps({"event": "error", "data": str(e)})

    return EventSourceResponse(event_generator())

@app.get("/api/stream/pushback")
async def stream_pushback(request: Request, session_id: str, pushback: str, provider: str = "groq"):
    async def event_generator():
        async for event in handle_verdict_pushback(session_id, pushback, provider, sessions):
            if await request.is_disconnected():
                break
            yield event
    return EventSourceResponse(event_generator())

class EndConversationRequest(BaseModel):
    session_id: str

@app.post("/api/conversation/end")
async def end_conversation(req: EndConversationRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    # Ask the graph to finish at the next safe point. Do not mark the
    # session cancelled here: cancellation makes the SSE generator stop
    # before final_node can create the report.
    session["force_end"] = True
    session["action"] = "end_session"

    # Trigger interrupt to stop current execution
    if "events" in session and "interrupt_event" in session["events"]:
        session["events"]["interrupt_event"].set()

    if "events" in session and "answer_event" in session["events"]:
        session["events"]["answer_event"].set()

    return {"status": "ending"}

@app.post("/api/pitch/score")
async def score_pitch(request: Request):
    data = await request.json()
    session_id = data.get("session_id")
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Simple transcript-based scoring
    transcript = ""
    for turn in session.get("conversation", []):
        transcript += f"{turn['agent_name']}: {turn['content']}\n"

    return await get_scoring_radar(session["pitch_summary"], {}, data.get("provider", session.get("provider", "ollama")))


# ─── Tier-1e: Multi-language pitch translation ───────────────────────


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    target_language: str  # ISO code: "en", "es", "hi", "zh", "fr", "de"
    provider: str = "groq"


# Languages we explicitly support. The LLM can handle others but we
# only validate against this list to keep the UI predictable.
SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "hi": "Hindi",
    "zh": "Mandarin Chinese",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ja": "Japanese",
}


@app.post("/api/translate")
async def translate_text(req: TranslateRequest):
    """Translate a pitch (or any text) into the target language.

    Returns the translated text and the detected source language.
    Uses the configured LLM provider — no translation-specific key
    is required. Best-effort; may fall back to returning the input
    if the LLM is unavailable.
    """
    target = req.target_language.lower().strip()
    if target not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language: {target!r}. Supported: "
                   f"{', '.join(sorted(SUPPORTED_LANGUAGES.keys()))}",
        )

    if target == "en":
        # No translation needed
        return {
            "translated_text": req.text,
            "source_language": "en",
            "target_language": "en",
            "model": "passthrough",
        }

    target_name = SUPPORTED_LANGUAGES[target]

    prompt = (
        f"Translate the following pitch into {target_name}. "
        "Preserve the original tone, technical terms, and brand names. "
        "Return ONLY the translated text, no preamble, no quotes, no notes.\n\n"
        f"---\n{req.text}\n---"
    )

    try:
        translated = await llm_provider.generate_response(
            system_prompt=(
                f"You are a professional pitch translator. "
                f"Translate into {target_name} while preserving meaning."
            ),
            user_prompt=prompt,
            provider=req.provider,
            stream=False,
        )
        # Heuristic: try to extract a "source language" if the model
        # didn't include it. For now, just report "auto".
        return {
            "translated_text": translated.strip(),
            "source_language": "auto",
            "target_language": target,
            "model": req.provider,
        }
    except Exception as e:
        logger.warning("Translation failed: %s", e)
        # Best-effort fallback: return the original text
        return {
            "translated_text": req.text,
            "source_language": "auto",
            "target_language": target,
            "model": "fallback",
            "error": str(e),
        }


@app.get("/api/languages")
async def list_supported_languages():
    """Return the list of languages we support for translation."""
    return {
        "languages": [
            {"code": code, "name": name}
            for code, name in sorted(SUPPORTED_LANGUAGES.items())
        ]
    }

# ─── Removed in Tier 0f ────────────────────────────────────────────
# The Meshy 3D endpoint was a hackathon-era leftover that contributed
# nothing to the pitch evaluation flow. /api/pitch/generate-3d and
# Sketch3DRequest are gone. See git history if you want to bring it back.

@app.post("/api/conversation/coach")
async def get_answer_coach(req: AnswerCoachRequest):
    """
    Returns 3 thinking prompts to help the pitcher
    answer the current agent's question.
    Called when pitcher clicks 'Help me answer this'
    OR when a weak answer is auto-detected.
    Does not stream — returns immediately.
    """
    if req.session_id not in sessions:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    session = sessions[req.session_id]
    agent = AGENTS_CONFIG[req.agent_id]

    prompt = ANSWER_COACH_PROMPT.format(
        question=req.question,
        agent_name=agent["name"],
        agent_role=agent["role"],
        pitch_summary=session["pitch_summary"]
    )

    response = await llm_provider.generate_response(
        system_prompt="You are a pitch coach. Output EXACTLY 3 bullet points, each on a new line. "
               "Each bullet must start with 'Think about: '. No preamble, no conclusion.",
        user_prompt=prompt,
        provider=session.get("provider", "groq"),
        stream=False
    )

    return {
        "coach_hints": response,
        "agent_name": agent["name"],
        "session_id": req.session_id
    }

@app.post("/api/conversation/retry")
async def retry_answer(req: RetryAnswerRequest):
    """
    Pitcher wants to redo their answer to the current
    agent's question. Removes their last answer from
    the conversation log.
    # FIXED: Removed legacy waiting_for logic and simplified types.
    """
    if req.session_id not in sessions:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    session = sessions[req.session_id]

    # Remove the last pitcher answer from conversation log
    # if one exists for this agent exchange
    conversation = session.get("conversation", [])
    if conversation and conversation[-1]["type"] == "pitcher_response":
        session["conversation"] = conversation[:-1]

    # Also remove the agent reaction if it already fired
    conversation = session.get("conversation", [])
    if conversation and conversation[-1]["type"] == "reaction":
        session["conversation"] = conversation[:-1]

    # Clear any pending answer
    session["pending_answer"] = ""

    # Clear coach hints if any
    session["coach_hints_shown"] = False

    return {
        "status": "retried",
        "session_id": req.session_id,
        "agent_id": req.agent_id,
        "message": "Response cleared. You can respond again."
    }


@app.get("/api/session/{session_id}/report")
async def get_report_data(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Return the structured report data
    report_data = session.get("final_report")
    if not report_data:
        verdict_text = session.get("verdict")
        if verdict_text:
            report_data = ensure_report_for_session(session, verdict_text)
        else:
            raise HTTPException(status_code=404, detail="Report not yet generated")

    return report_data


def _hash_api_key(raw_key: str) -> str:
    """SHA-256 hash an API key for storage. Raw keys are never stored."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (raw_key, key_hash, key_prefix).

    Format: pm_live_<32 random chars>. The prefix `pm_live_` is
    shown to the user for identification.
    """
    random_part = secrets.token_urlsafe(24)
    raw = f"pm_live_{random_part}"
    return raw, _hash_api_key(raw), f"pm_live_{random_part[:8]}"


async def _authenticate_api_key_async(authorization: str | None):
    """Async version: extract and validate the API key from the
    Authorization header. Returns the ApiKey row if valid, None if not.

    Return type is intentionally not annotated to avoid Pydantic
    v2 forward-ref resolution issues at request time.
    """
    if not authorization:
        return None
    # Accept both "Bearer pm_live_..." and "pm_live_..." (raw)
    raw = authorization.strip()
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    if not raw.startswith("pm_live_"):
        return None
    key_hash = _hash_api_key(raw)
    repo = get_repository()
    return await repo.get_api_key_by_hash(key_hash)


def _authenticate_api_key(authorization: str | None = Header(None)):
    """Sync wrapper for non-async callers (e.g. tests).

    In FastAPI handlers, prefer awaiting _authenticate_api_key_async
    directly. This sync version uses asyncio.run() which is fine in
    a non-async context but will fail in an already-running loop.

    Return type is intentionally not annotated to avoid Pydantic
    v2 forward-ref resolution issues at request time.
    """
    if not authorization:
        return None
    raw = authorization.strip()
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    if not raw.startswith("pm_live_"):
        return None
    key_hash = _hash_api_key(raw)
    try:
        return asyncio.run(_lookup_coro(key_hash))
    except RuntimeError:
        # Already in an event loop — return None and let the caller
        # use the async version.
        return None


async def _lookup_coro(key_hash: str):
    repo = get_repository()
    return await repo.get_api_key_by_hash(key_hash)


class CreateKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] = []
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=10000)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class CreateKeyResponse(BaseModel):
    id: str
    name: str
    key: str
    key_prefix: str
    scopes: list[str]
    rate_limit_per_minute: int | None = None
    created_at: str
    expires_at: str | None = None


class ListKeysResponse(BaseModel):
    keys: list = []


class PublicPitchResponse(BaseModel):
    """Response shape for /api/v1/pitches/{id}."""
    session_id: str
    is_public: bool
    mode: str
    created_at: str
    pitch_excerpt: str
    verdict: dict
    confidence_score: int
    investment_signal: str


@app.post("/api/v1/keys", response_model=CreateKeyResponse, status_code=201)
async def create_api_key(req: CreateKeyRequest):
    """Create a new API key. The raw key is returned ONCE — store it securely."""

    raw, key_hash, key_prefix = _generate_api_key()
    expires_at = None
    if req.expires_in_days is not None:
        expires_at = _utcnow() + timedelta(days=req.expires_in_days)

    repo = get_repository()
    key = await repo.create_api_key(
        name=req.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=req.scopes,
        expires_at=expires_at,
        rate_limit_per_minute=req.rate_limit_per_minute,
    )
    return CreateKeyResponse(
        id=key.id,
        name=key.name,
        key=raw,  # only returned here
        key_prefix=key.key_prefix,
        scopes=key.scopes,
        rate_limit_per_minute=key.rate_limit_per_minute,
        created_at=key.created_at.isoformat() if key.created_at else "",
        expires_at=key.expires_at.isoformat() if key.expires_at else None,
    )


@app.get("/api/v1/keys", response_model=ListKeysResponse)
async def list_api_keys(authorization: str | None = Header(None)):
    """List API keys. Requires a valid key in the Authorization header."""
    key = await _authenticate_api_key_async(authorization)
    if key is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    repo = get_repository()
    keys = await repo.list_api_keys()
    # Strip key_hash from the response
    return ListKeysResponse(
        keys=[k.to_dict(include_hash=False) for k in keys]
    )


@app.delete("/api/v1/keys/{key_id}", status_code=204)
async def revoke_api_key(key_id: str, authorization: str | None = Header(None)):
    """Revoke an API key. Future requests with this key return 401."""
    auth_key = await _authenticate_api_key_async(authorization)
    if auth_key is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    repo = get_repository()
    revoked = await repo.revoke_api_key(key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")
    return


@app.get("/api/v1/pitches/{session_id}", response_model=PublicPitchResponse)
async def api_v1_get_pitch(session_id: str, authorization: str | None = Header(None)):
    """Public API: get a sanitized pitch verdict by session ID.

    Requires a valid API key. Rate-limited per-key.
    """
    api_key = await _authenticate_api_key_async(authorization)
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    if not api_key.is_active or api_key.revoked_at is not None:
        raise HTTPException(status_code=401, detail="API key revoked")
    # Record usage
    repo = get_repository()
    await repo.record_api_key_usage(api_key.id)
    # Return the same sanitized verdict shape as the /v/<id>/public endpoint
    session = await repo.get_session(session_id)
    if session is None or not session.is_public or session.status != "completed":
        raise HTTPException(status_code=404, detail="Verdict not found")
    verdict = await repo.get_verdict(session_id)
    if verdict is None:
        raise HTTPException(status_code=404, detail="Verdict not found")
    pitch_excerpt = (session.pitch_summary or "")[:200]
    if len(session.pitch_summary or "") > 200:
        pitch_excerpt += "..."
    return PublicPitchResponse(
        session_id=session_id,
        is_public=session.is_public,
        mode=session.mode,
        created_at=session.created_at.isoformat() if session.created_at else "",
        pitch_excerpt=pitch_excerpt,
        verdict={
            "strongest": verdict.strongest or "",
            "weakness": verdict.weakness or "",
            "fix": verdict.fix or "",
            "recommendation": verdict.recommendation or "",
            "investment_score": verdict.investment_score,
            "verdict_text": (verdict.verdict_text or "")[:1000],
        },
        confidence_score=verdict.confidence_score,
        investment_signal=verdict.signal or "MEDIUM",
    )


@app.get("/api/v1/health")
async def api_v1_health():
    """Public API: liveness probe. No auth required."""
    return {"status": "ok", "tier": "v1"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
