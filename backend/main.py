from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import json
from orchestrator import sessions
import asyncio

from orchestrator import (
    handle_verdict_pushback,
    get_scoring_radar, 
    save_pitcher_memory, 
    generate_3d_from_sketch,
    generate_fact_check,
    generate_rebuttal_response,
    stream_echochamber,
    AGENTS_CONFIG
)
from services.llm import llm_provider

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import re

def sanitize_pitch_input(text: str) -> str:
    """
    Cleans user pitch input before it enters any prompt.
    - Strips HTML tags
    - Removes prompt injection patterns
    - Normalizes whitespace
    - Truncates to safe length
    """
    if not text or not isinstance(text, str):
        raise ValueError("Pitch must be a non-empty string")

    # Strip HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Remove common prompt injection patterns
    injection_patterns = [
        r'ignore (all |previous |above )?instructions?',
        r'you are now',
        r'new persona',
        r'forget (everything|all)',
        r'system prompt',
        r'\\n\\n(human|assistant|system):',
        r'<|im_start|>',
        r'<|im_end|>',
    ]
    for pattern in injection_patterns:
        text = re.sub(pattern, '[removed]', text, flags=re.IGNORECASE)

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

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

class Sketch3DRequest(BaseModel):
    image_url: str

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
            "summary_approved": asyncio.Event()
        }

    session["pending_answer"] = message

    # ✅ NORMAL ANSWER FLOW
    if session.get("awaiting_user_input"):
        session["awaiting_user_input"] = False
        session["input_type"] = "pitcher_response" # FIXED: Standardized type

        print(f"[API] answer received: {message}")

        # FIXED: Always trigger event (no conditional check) to avoid race condition/deadlock (Fix 1)
        event = session["events"]["answer_event"]
        event.set()

        return {"status": "pitcher_response_received"}

    # ✅ INTERRUPT FLOW
    session["pitcher_interrupt"] = True
    session["pitcher_message"] = message
    session["input_type"] = "interrupt"

    # FIXED: Wake graph on interrupt
    if "events" in session and "answer_event" in session["events"]:
        session["events"]["answer_event"].set()

    print(f"[API] interrupt: {message}")

    return {"status": "interrupt_triggered"}

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

@app.get("/api/stream/main")
async def main_stream(request: Request, session_id: str, pitch: str, provider: str = "groq", pitcher_id: str = None, mode: str = "venture"):
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
        async def validation_error():
            yield json.dumps({"event": "error", "data": str(e)})
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
                "summary_approved": asyncio.Event()
            },
            "pending_answer": "",
            "pitcher_interrupt": False,
            "pitcher_message": "",
            "input_type": "confirmation", # FIXED: Standardized (Fix 5)
            "conversation": [],
            "mode": mode,
            "provider": provider,
            "awaiting_pitch_confirmation": False,
            "awaiting_user_input": False,
            "refined_pitch": ""
        }
    
    async def event_generator():
        try:
            async for event in stream_echochamber(session_id, sessions[session_id], provider, mode):
                if await request.is_disconnected():
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
    
    # In agentic v4, we signal the controller to end the session
    session["action"] = "end_session"
    
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

@app.post("/api/pitch/generate-3d")
async def meshy_3d(req: Sketch3DRequest):
    return await generate_3d_from_sketch(req.image_url)

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
    
    from prompts import ANSWER_COACH_PROMPT
    
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

from pdf_export import generate_pdf_report
from fastapi import Response

@app.get("/api/session/{session_id}/report")
async def download_report(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    pdf_bytes = await generate_pdf_report(session)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=pitch-report.pdf"}
    )

@app.get("/api/memory")
async def list_memory():
    """List all pitcher memory entries."""
    try:
        with open("pitcher_memory.json", "r") as f:
            memory = json.load(f)
        return {"pitchers": memory, "count": len(memory)}
    except FileNotFoundError:
        return {"pitchers": {}, "count": 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/memory/{pitcher_id}")
async def delete_memory(pitcher_id: str):
    """Delete a specific pitcher's memory."""
    try:
        with open("pitcher_memory.json", "r") as f:
            memory = json.load(f)
        if pitcher_id not in memory:
            raise HTTPException(status_code=404, detail=f"No memory found for '{pitcher_id}'")
        del memory[pitcher_id]
        with open("pitcher_memory.json", "w") as f:
            json.dump(memory, f, indent=2)
        return {"status": "deleted", "pitcher_id": pitcher_id, "remaining": len(memory)}
    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No memory file exists yet")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/memory")
async def clear_all_memory():
    """Clear ALL pitcher memory."""
    try:
        with open("pitcher_memory.json", "w") as f:
            json.dump({}, f)
        return {"status": "cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
