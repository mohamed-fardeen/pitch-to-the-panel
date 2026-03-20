from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import json
import asyncio

from orchestrator import run_round1, generate_question_selection, run_round2, generate_verdict, generate_fact_check, generate_pushback_verdict, get_scoring_radar, save_pitcher_memory, generate_3d_from_sketch

app = FastAPI()

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

class AnswerRequest(BaseModel):
    pitch: str
    round1_responses: dict
    question: str
    answer: str
    provider: str = "anthropic"

class SummaryApproval(BaseModel):
    session_id: str
    approved: bool
    corrected_summary: str | None = None

class SteerRequest(BaseModel):
    session_id: str
    choice: str
    clarification: str | None = None
    target_agent_id: str | None = None

class ChallengeRequest(BaseModel):
    session_id: str
    agent_id: str
    agent_claim: str
    challenge_text: str
    provider: str = "anthropic"

class PushbackRequest(BaseModel):
    session_id: str
    pushback: str
    pitch: str
    answer: str
    round1_responses: dict
    round2_responses: dict
    provider: str = "anthropic"

class ScoreRequest(BaseModel):
    pitch: str
    round1_responses: dict
    provider: str = "anthropic"

class ReportRequest(BaseModel):
    pitch: str
    round1_responses: dict
    round2_responses: dict
    verdict: str
    radar_chart_b64: str | None = None

class Sketch3DRequest(BaseModel):
    image_url: str
    
@app.post("/api/intake")
async def process_intake(request: EvaluationRequest):
    return {"status": "ok"}

@app.post("/api/pitch/approve-summary")
async def approve_summary(req: SummaryApproval):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session["hitl_data"]["corrected_summary"] = req.corrected_summary
    session["events"]["summary_approved"].set()
    return {"status": "ok"}

@app.post("/api/pitch/steer")
async def steer_debate(req: SteerRequest):
    session = sessions.get(req.session_id)
    if session:
        session["hitl_data"]["steer"] = req.dict()
    return {"status": "ok"}

@app.post("/api/pitch/challenge")
async def challenge_claim(req: ChallengeRequest):
    result = await generate_fact_check(req.agent_claim, req.challenge_text, req.provider)
    return {"fact_check_result": result}

@app.post("/api/pitch/pushback")
async def pushback_verdict(req: PushbackRequest):
    result = await generate_pushback_verdict(req.pitch, req.answer, req.round1_responses, req.round2_responses, req.pushback, req.provider)
    if req.session_id in sessions:
        save_pitcher_memory(sessions[req.session_id].get("pitcher_id"), sessions[req.session_id], result)
    return {"verdict": result}

@app.post("/api/pitch/score")
async def score_pitch(req: ScoreRequest):
    return await get_scoring_radar(req.pitch, req.round1_responses, req.provider)

@app.post("/api/pitch/generate-3d")
async def meshy_3d(req: Sketch3DRequest):
    return await generate_3d_from_sketch(req.image_url)

@app.post("/api/pitch/report")
async def generate_report(req: ReportRequest):
    import os
    from fastapi.responses import FileResponse
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    
    filename = "pitch_report_tmp.pdf"
    if os.path.exists(filename): os.remove(filename)
    
    c = canvas.Canvas(filename, pagesize=letter)
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 750, "AI Pitch Panel - Formal Report")
    
    c.setFont("Helvetica", 12)
    c.drawString(50, 720, "Pitch:")
    c.setFont("Helvetica", 10)
    c.drawString(50, 705, req.pitch[:200] + "..." if len(req.pitch)>200 else req.pitch)
    
    y = 660
    for agent, text in req.round1_responses.items():
        if y < 100:
            c.showPage()
            y = 750
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, f"{agent.upper()} FEEDBACK:")
        y -= 20
        c.setFont("Helvetica", 10)
        safe_text = str(text).replace('\n', ' ')
        c.drawString(50, y, safe_text[:120] + "...")
        y -= 30
    
    y -= 20
    if y < 150:
        c.showPage()
        y = 750
        
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Final Verdict:")
    y -= 20
    c.setFont("Helvetica", 10)
    
    lines = req.verdict.split("\n")
    for l in lines:
        if y < 100:
            c.showPage()
            y = 750
        c.drawString(50, y, l[:120])
        y -= 15
        
    c.save()
    return FileResponse(filename, filename="AI_Pitch_Report.pdf", media_type='application/pdf')

@app.get("/api/stream/round1")
async def stream_round1(request: Request, session_id: str, pitch: str, provider: str = "anthropic", pitcher_id: str = None):
    if session_id not in sessions:
        sessions[session_id] = {
            "events": {
                "summary_approved": asyncio.Event(),
                "steer_decided": asyncio.Event()
            },
            "hitl_data": {},
            "pitcher_id": pitcher_id
        }
    else:
        sessions[session_id]["pitcher_id"] = pitcher_id
    
    async def event_generator():
        async for event in run_round1(session_id, sessions[session_id], pitch, provider, pitcher_id):
            if await request.is_disconnected():
                break
            yield event
    return EventSourceResponse(event_generator())

@app.post("/api/question")
async def get_question(request: Request):
    data = await request.json()
    pitch = data.get("pitch")
    round1_responses = data.get("round1_responses", {})
    provider = data.get("provider", "anthropic")
    session_id = data.get("session_id")
    
    # Inject steering clarification if applicable
    if session_id and session_id in sessions:
        steer_data = sessions[session_id].get("hitl_data", {}).get("steer", {})
        if steer_data.get("choice") in ["clarify", "address"] and steer_data.get("clarification"):
            pitch = pitch + "\n\n[PITCHER CLARIFICATION POST-ROUND 1]:\n" + steer_data["clarification"]
    
    question_data = await generate_question_selection(pitch, round1_responses, provider)
    
    # Force target agent if steer address was used
    if session_id and session_id in sessions:
        steer_data = sessions[session_id].get("hitl_data", {}).get("steer", {})
        if steer_data.get("choice") == "address" and steer_data.get("target_agent_id"):
            question_data["selected_agent"] = steer_data["target_agent_id"]

    return question_data

@app.get("/api/stream/round2")
async def stream_round2(request: Request, pitch: str, answer: str, round1_responses: str, provider: str = "anthropic"):
    try:
        responses_dict = json.loads(round1_responses)
    except Exception:
        responses_dict = {}
        
    async def event_generator():
        async for event in run_round2(pitch, answer, responses_dict, provider):
            if await request.is_disconnected():
                break
            yield event
    return EventSourceResponse(event_generator())

@app.post("/api/verdict")
async def get_verdict(request: Request):
    data = await request.json()
    pitch = data.get("pitch")
    answer = data.get("answer")
    round1_responses = data.get("round1_responses", {})
    round2_responses = data.get("round2_responses", {})
    provider = data.get("provider", "anthropic")
    session_id = data.get("session_id")
    
    verdict_text = await generate_verdict(pitch, answer, round1_responses, round2_responses, provider)
    if session_id and session_id in sessions:
        save_pitcher_memory(sessions[session_id].get("pitcher_id"), sessions[session_id], verdict_text)

    return {"verdict": verdict_text}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
