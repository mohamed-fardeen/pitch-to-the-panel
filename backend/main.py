from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import json
import asyncio

from orchestrator import (
    run_round1, 
    handle_verdict_pushback,
    get_scoring_radar, 
    save_pitcher_memory, 
    generate_3d_from_sketch,
    generate_fact_check,
    generate_rebuttal_response,
    AGENTS_CONFIG
)
from services.llm import llm_provider

app = FastAPI()

# Global session storage
sessions = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PitchRequest(BaseModel):
    pitch_transcript: str
    session_id: str | None = None
    difficulty: str = "standard"

class EvaluationRequest(BaseModel):
    pitch: str
    provider: str = "anthropic"
    pitcher_id: str | None = None

class ConversationAnswer(BaseModel):
    session_id: str
    answer: str
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
    provider: str = "anthropic"

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
    session["hitl_data"]["corrected_summary"] = req.corrected_summary
    session["events"]["summary_approved"].set()
    return {"status": "ok"}

class SkipRequest(BaseModel):
    session_id: str

@app.post("/api/conversation/answer")
async def submit_answer(req: ConversationAnswer):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session["pending_answer"] = req.answer
    session["events"]["answer_event"].set()
    return {"status": "ok"}

@app.post("/api/conversation/skip")
async def skip_turn(req: SkipRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session["pending_answer"] = "[Skipped by user - Interaction handled via Challenge Mode]"
    session["events"]["answer_event"].set()
    return {"status": "ok"}

@app.post("/api/conversation/interrupt")
async def interrupt_conversation(req: PitcherInterruptRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session["pending_answer"] = (
        req.message.strip()
        if req.message.strip()
        else "[interrupt_signal]"
    )
    session["waiting_for"] = "pitcher_interrupt"
    session["events"]["answer_event"].set()
    return {"status": "ok"}

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
async def main_stream(request: Request, session_id: str, pitch: str, provider: str = "groq", pitcher_id: str = None, difficulty: str = "standard"):
    """The core unified stream for v1 hybrid conversation."""
    if session_id not in sessions:
        sessions[session_id] = {
            "events": {
                "summary_approved": asyncio.Event(),
                "answer_event": asyncio.Event()
            },
            "hitl_data": {},
            "pitcher_id": pitcher_id,
            "conversation": [],
            "pending_answer": "",
            "waiting_for": None,
            "phase": "setup",
            "difficulty": difficulty or "standard",
            "provider": provider or "groq"
        }
    
    async def event_generator():
        async for event in run_round1(session_id, sessions[session_id], pitch, provider, pitcher_id, difficulty):
            if await request.is_disconnected():
                break
            yield event
    return EventSourceResponse(event_generator())

@app.get("/api/stream/pushback")
async def stream_pushback(request: Request, session_id: str, pushback: str, provider: str = "groq"):
    async def event_generator():
        async for event in handle_verdict_pushback(session_id, pushback, provider, sessions):
            if await request.is_disconnected():
                break
            yield event
    return EventSourceResponse(event_generator())

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
    
    return await get_scoring_radar(session["pitch_summary"], {}, data.get("provider", "anthropic"))

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
    the conversation log and resets waiting state.
    Does not re-ask the question — just clears the answer
    so the pitcher can try again.
    """
    if req.session_id not in sessions:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    session = sessions[req.session_id]

    # Only allow retry if we are waiting for an answer
    # or if the last thing in the conversation was
    # an answer from the pitcher
    if session.get("waiting_for") not in (
        "answer", "interrupt_answer", None
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry in current state: "
                   f"{session.get('waiting_for')}"
        )

    # Remove the last pitcher answer from conversation log
    # if one exists for this agent exchange
    conversation = session.get("conversation", [])
    if conversation and conversation[-1]["type"] == "answer":
        session["conversation"] = conversation[:-1]

    # Also remove the agent reaction if it already fired
    conversation = session.get("conversation", [])
    if conversation and conversation[-1]["type"] == "reaction":
        session["conversation"] = conversation[:-1]

    # Reset waiting state back to waiting for answer
    session["waiting_for"] = "answer"

    # Clear any pending answer
    session["pending_answer"] = ""

    # Clear coach hints if any
    session["coach_hints_shown"] = False

    return {
        "status": "retried",
        "session_id": req.session_id,
        "agent_id": req.agent_id,
        "message": "Answer cleared. You can respond again."
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
