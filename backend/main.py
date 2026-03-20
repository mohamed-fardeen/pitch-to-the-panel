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
    generate_fact_check
)

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

class EvaluationRequest(BaseModel):
    pitch: str
    provider: str = "anthropic"
    pitcher_id: str | None = None

class ConversationAnswer(BaseModel):
    session_id: str
    answer: str
    provider: str = "anthropic"

class SummaryApproval(BaseModel):
    session_id: str
    approved: bool
    corrected_summary: str | None = None

class ChallengeRequest(BaseModel):
    session_id: str
    agent_id: str
    agent_claim: str
    challenge_text: str
    provider: str = "anthropic"

class PushbackRequest(BaseModel):
    session_id: str
    pushback: str
    provider: str = "anthropic"

class Sketch3DRequest(BaseModel):
    image_url: str

@app.post("/api/pitch/approve-summary")
async def approve_summary(req: SummaryApproval):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session["hitl_data"]["corrected_summary"] = req.corrected_summary
    session["events"]["summary_approved"].set()
    return {"status": "ok"}

@app.post("/api/conversation/answer")
async def submit_answer(req: ConversationAnswer):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session["pending_answer"] = req.answer
    session["events"]["answer_event"].set()
    return {"status": "ok"}

@app.post("/api/pitch/challenge")
async def challenge_claim(req: ChallengeRequest):
    result = await generate_fact_check(req.agent_claim, req.challenge_text, req.provider)
    return {"fact_check_result": result}

@app.get("/api/stream/main")
async def main_stream(request: Request, session_id: str, pitch: str, provider: str = "anthropic", pitcher_id: str = None, difficulty: str = "standard"):
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
            "difficulty": difficulty
        }
    
    async def event_generator():
        async for event in run_round1(session_id, sessions[session_id], pitch, provider, pitcher_id, difficulty):
            if await request.is_disconnected():
                break
            yield event
    return EventSourceResponse(event_generator())

@app.get("/api/stream/pushback")
async def stream_pushback(request: Request, session_id: str, pushback: str, provider: str = "anthropic"):
    async def event_generator():
        async for event in handle_verdict_pushback(session_id, pushback, provider):
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
