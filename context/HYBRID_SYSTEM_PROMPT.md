# Pitch to the Panel — Hybrid Conversation System
# Implementation prompt for Claude Code
# Paste this entire file as your first message

---

## CONTEXT — WHAT EXISTS NOW

The current system has this flow:
1. Pitch submitted
2. Extract summary
3. Round 1 — all 6 agents each write a long paragraph (no pitcher interaction)
4. Question selector picks ONE agent to ask ONE question
5. Pitcher answers once
6. Round 2 — all 6 agents each write a short reaction paragraph
7. Judge verdict

The current session object has: pitch_summary, round1{}, round2{},
question{}, pitcher_answer, verdict, phase

The current routes are:
- POST /pitch/start      → streams Round 1 then waits
- POST /pitch/answer     → streams Round 2 + verdict

The current orchestration functions are:
- stream_round1()
- select_question()
- stream_round2()
- QUESTION_SELECTOR_PROMPT constant

---

## WHAT YOU ARE REPLACING

DELETE these entirely:
- stream_round1()
- select_question()
- stream_round2()
- QUESTION_SELECTOR_PROMPT constant
- POST /pitch/answer route

KEEP everything else exactly as-is:
- All 6 entries in the AGENTS dict with their full system prompts — do not touch
- JUDGE_SYSTEM_PROMPT — unchanged
- AGENT_ORDER list — unchanged
- extract_pitch_summary() — unchanged
- compute_sentiment() — unchanged
- parse_verdict() — unchanged
- stream_verdict() — unchanged
- GET /session/{session_id} — unchanged
- GET /agents — unchanged
- GET /health — unchanged
- POST /session/create — unchanged
- All imports, FastAPI setup, CORS, client, MODEL — unchanged

---

## THE NEW FLOW

Replace the deleted functions with this hybrid conversation system:

```
Pitch submitted
→ Extract + summarise
→ HITL: pitcher approves or corrects summary
→ For each agent in order (1 through 6):
    - Agent generates ONE sharp question (reads all previous exchanges)
    - SSE streams question to frontend
    - System pauses — waits for pitcher's answer
    - Pitcher submits answer via new endpoint
    - Agent generates reaction to answer (1-2 sentences)
    - Interrupt check: should another agent jump in?
      → If yes: one agent asks a short follow-up, pitcher answers
    - Move to next agent
→ Judge reads full conversation transcript
→ Judge generates verdict
→ HITL: pitcher can push back on verdict once
→ Final verdict stored
```

---

## NEW SESSION OBJECT

Replace the old session structure with this:

```python
{
    "id": str,
    "pitch_summary": str,
    "pitch_summary_approved": bool,
    "conversation": [
        # grows throughout the session — this is the source of truth
        {
            "turn": int,               # sequential turn number
            "type": "question"         # "question" | "answer" | "reaction" | "interrupt_q" | "interrupt_a"
            "agent_id": str,           # which agent (or "pitcher")
            "agent_name": str,
            "content": str,
            "timestamp": str
        }
    ],
    "current_agent_index": int,        # which agent's turn (0-5)
    "current_agent_id": str,
    "waiting_for": "summary_approval" | "answer" | "pushback" | None,
    "verdict": str,
    "verdict_parts": dict,
    "phase": str,
    # asyncio events for pausing/resuming the stream
    "answer_event": asyncio.Event,
    "pending_answer": str,
    "summary_event": asyncio.Event,
    "pending_summary_correction": str | None,
    "pushback_event": asyncio.Event,
    "pending_pushback": str | None
}
```

---

## NEW CONSTANTS

Add these two new prompts:

```python
QUESTION_GENERATOR_PROMPT = """
You are {agent_name}, evaluating a startup pitch.

You have read the pitch summary and the full conversation so far
(all previous agents' questions and the pitcher's answers).

Your job: ask ONE sharp question. Not a long paragraph. Not an assessment.
One question — the single most important thing you need answered
given everything said so far.

FORMAT RULES:
- Maximum 2 sentences total
- First sentence (optional): one-line setup explaining WHY you're asking
- Second sentence: the actual question
- Do not repeat what other agents already asked
- Do not give your opinion yet — that comes after the pitcher answers
- Stay completely in character as {agent_name}

GOOD EXAMPLE:
"You mentioned hospitals as your distribution channel, but hospital
procurement cycles are 18-24 months minimum. Have you spoken to any
hospital administrator who has actually committed to a trial?"

BAD EXAMPLE:
"This is an interesting idea but I have some concerns about the market
size and competitive landscape. Medisafe already has millions of users
and I'm wondering what your differentiation strategy is and whether
you've considered the regulatory environment in India."
[Too long. Opinion included. Multiple questions packed in.]

Keep your question under 50 words total.
"""

REACTION_GENERATOR_PROMPT = """
You are {agent_name}, reacting to the pitcher's answer.

You asked: "{question}"
The pitcher answered: "{answer}"

Give your honest reaction in 1-2 sentences ONLY.
Did the answer satisfy your concern? Partially? Not at all?
Be specific — reference something they actually said.
Stay completely in character.
Do NOT ask another question here — just react.
Keep under 40 words.
"""

INTERRUPT_CHECK_PROMPT = """
You are a debate moderator. Read this exchange:

Agent: {agent_name}
Question: {question}
Pitcher's answer: {answer}
Agent's reaction: {reaction}

Full conversation so far:
{conversation_so_far}

Should another agent interrupt RIGHT NOW with a follow-up?
Only interrupt if the pitcher's answer opened a NEW angle that
a DIFFERENT agent is specifically positioned to address.
Do not interrupt just to be active. Most exchanges should NOT be interrupted.

Output ONLY valid JSON:
{
  "should_interrupt": true | false,
  "agent_id": "vc|enthusiastic|hostile|expert|competitor|first_timer" | null,
  "followup_question": "one sharp question under 30 words" | null,
  "reason": "one sentence why this agent should jump in now" | null
}

If should_interrupt is false, set agent_id, followup_question, reason all to null.
"""

JUDGE_CONVERSATION_PROMPT = """
You are the Judge. You have read the complete conversation between
the pitcher and all 6 panel agents — every question, every answer,
every reaction, every interrupt.

This is richer than a report. You saw how the pitcher handled pressure,
which objections they answered well, which ones they dodged, and where
they surprised the panel.

YOUR VERDICT MUST CONTAIN EXACTLY THREE PARTS:

PART 1 — STRONGEST POINT (one sentence):
The single best moment in the conversation — the answer that most
impressed the panel or changed their position.
Format: 'Your strongest point: [specific thing they said or did]'

PART 2 — BIGGEST WEAKNESS (one sentence):
The objection that appeared most across agents AND was not convincingly
answered. Must reference a specific exchange.
Format: 'Your biggest weakness: [specific unresolved objection]'

PART 3 — ONE THING TO FIX (one sentence):
The single most important action before the next pitch.
Must be specific. Not generic advice.
Format: 'Before your next pitch: [specific action]'

RULES:
- No preamble. Start directly with 'Your strongest point:'
- No softening. No 'great pitch overall.'
- Reference specific quotes or moments from the conversation
- Three sentences maximum
- Be honest. A weak conversation gets a tough verdict.
"""
```

---

## NEW FUNCTIONS TO ADD

### 1. build_conversation_context()

```python
def build_conversation_context(session: dict) -> str:
    """Build a readable transcript of the conversation so far."""
    if not session["conversation"]:
        return "No exchanges yet."
    
    lines = []
    for turn in session["conversation"]:
        if turn["type"] == "question":
            lines.append(f"{turn['agent_name']} asked: {turn['content']}")
        elif turn["type"] == "answer":
            lines.append(f"Pitcher answered: {turn['content']}")
        elif turn["type"] == "reaction":
            lines.append(f"{turn['agent_name']} reacted: {turn['content']}")
        elif turn["type"] == "interrupt_q":
            lines.append(f"{turn['agent_name']} jumped in: {turn['content']}")
        elif turn["type"] == "interrupt_a":
            lines.append(f"Pitcher replied: {turn['content']}")
    
    return "\n".join(lines)
```

---

### 2. generate_agent_question()

```python
async def generate_agent_question(
    session: dict,
    agent_id: str
) -> AsyncGenerator[str, None]:
    """Stream one sharp question from the current agent."""
    
    agent = AGENTS[agent_id]
    conversation_context = build_conversation_context(session)
    
    system = QUESTION_GENERATOR_PROMPT.format(
        agent_name=agent["name"]
    )
    
    user_message = f"""PITCH SUMMARY:
{session['pitch_summary']}

CONVERSATION SO FAR:
{conversation_context}

Now ask your one sharp question as {agent['name']}.
Remember: read what others asked. Don't repeat their angles.
Find YOUR most important unanswered question."""

    full_question = ""
    yield sse_event("agent_question_start", {
        "agent_id": agent_id,
        "name": agent["name"],
        "role": agent["role"],
        "agent_index": session["current_agent_index"]
    })
    
    with client.messages.stream(
        model=MODEL,
        max_tokens=80,
        system=system,
        messages=[{"role": "user", "content": user_message}]
    ) as stream:
        for text in stream.text_stream:
            full_question += text
            yield sse_event("agent_token", {
                "agent_id": agent_id,
                "token": text,
                "type": "question"
            })
    
    # Store in conversation log
    session["conversation"].append({
        "turn": len(session["conversation"]),
        "type": "question",
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "content": full_question,
        "timestamp": str(asyncio.get_event_loop().time())
    })
    
    yield sse_event("agent_question_done", {
        "agent_id": agent_id,
        "question": full_question
    })
    
    session["waiting_for"] = "answer"
```

---

### 3. generate_agent_reaction()

```python
async def generate_agent_reaction(
    session: dict,
    agent_id: str,
    question: str,
    answer: str
) -> AsyncGenerator[str, None]:
    """Stream agent's reaction after pitcher answers."""
    
    agent = AGENTS[agent_id]
    
    system = REACTION_GENERATOR_PROMPT.format(
        agent_name=agent["name"],
        question=question,
        answer=answer
    )
    
    user_message = f"""Stay completely in character as {agent['name']}.
React honestly to what the pitcher just said.
1-2 sentences only. No new question. Pure reaction."""

    full_reaction = ""
    yield sse_event("agent_reaction_start", {
        "agent_id": agent_id,
        "name": agent["name"]
    })
    
    with client.messages.stream(
        model=MODEL,
        max_tokens=70,
        system=system,
        messages=[{"role": "user", "content": user_message}]
    ) as stream:
        for text in stream.text_stream:
            full_reaction += text
            yield sse_event("agent_token", {
                "agent_id": agent_id,
                "token": text,
                "type": "reaction"
            })
    
    # Store reaction in conversation log
    session["conversation"].append({
        "turn": len(session["conversation"]),
        "type": "reaction",
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "content": full_reaction,
        "timestamp": str(asyncio.get_event_loop().time())
    })
    
    # Update sentiment based on reaction
    sentiment = compute_sentiment(full_reaction)
    yield sse_event("sentiment_update", {
        "agent_id": agent_id,
        "sentiment": sentiment
    })
    
    yield sse_event("agent_reaction_done", {
        "agent_id": agent_id,
        "reaction": full_reaction
    })
```

---

### 4. check_interrupt()

```python
async def check_interrupt(
    session: dict,
    current_agent_id: str,
    question: str,
    answer: str,
    reaction: str
) -> dict | None:
    """Check if another agent should interrupt. Returns interrupt data or None."""
    
    # Don't interrupt on last agent — no point
    current_index = AGENT_ORDER.index(current_agent_id)
    if current_index >= len(AGENT_ORDER) - 1:
        return None
    
    # Don't interrupt too often — check only every other exchange
    # Count existing interrupts
    interrupt_count = sum(
        1 for t in session["conversation"]
        if t["type"] == "interrupt_q"
    )
    if interrupt_count >= 2:  # max 2 interrupts per session
        return None
    
    conversation_so_far = build_conversation_context(session)
    
    prompt = INTERRUPT_CHECK_PROMPT.format(
        agent_name=AGENTS[current_agent_id]["name"],
        question=question,
        answer=answer,
        reaction=reaction,
        conversation_so_far=conversation_so_far
    )
    
    response = client.messages.create(
        model=MODEL,
        max_tokens=150,
        system="You are a debate moderator. Output only valid JSON.",
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    
    try:
        result = json.loads(raw)
        if result.get("should_interrupt") and result.get("agent_id"):
            # Don't interrupt with an agent that already had their turn
            interrupting_agent_index = AGENT_ORDER.index(result["agent_id"])
            if interrupting_agent_index > current_index:
                return result  # Only future agents can interrupt
        return None
    except (json.JSONDecodeError, ValueError):
        return None
```

---

### 5. stream_interrupt()

```python
async def stream_interrupt(
    session: dict,
    interrupt_data: dict
) -> AsyncGenerator[str, None]:
    """Stream an interrupt question from a jumping-in agent."""
    
    agent_id = interrupt_data["agent_id"]
    agent = AGENTS[agent_id]
    followup = interrupt_data["followup_question"]
    
    # Store interrupt question
    session["conversation"].append({
        "turn": len(session["conversation"]),
        "type": "interrupt_q",
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "content": followup,
        "timestamp": str(asyncio.get_event_loop().time())
    })
    
    yield sse_event("interrupt_start", {
        "agent_id": agent_id,
        "name": agent["name"],
        "role": agent["role"],
        "question": followup,
        "reason": interrupt_data.get("reason", "")
    })
    
    session["waiting_for"] = "interrupt_answer"
```

---

### 6. stream_full_conversation()

This is the main orchestrator. It replaces stream_round1() and stream_round2().

```python
async def stream_full_conversation(
    session_id: str
) -> AsyncGenerator[str, None]:
    """
    Main hybrid conversation orchestrator.
    Streams the full 6-agent conversation with pitcher answering each agent.
    Pauses at each question waiting for pitcher input via asyncio.Event.
    """
    
    session = sessions[session_id]
    
    yield sse_event("status", {
        "message": "Panel is ready. First question coming...",
        "phase": "conversation_start"
    })
    
    for agent_index, agent_id in enumerate(AGENT_ORDER):
        session["current_agent_index"] = agent_index
        session["current_agent_id"] = agent_id
        
        # ── STEP A: Agent asks question ──────────────────────────────
        async for event in generate_agent_question(session, agent_id):
            yield event
        
        # Get the question just stored
        question = session["conversation"][-1]["content"]
        
        # ── STEP B: Wait for pitcher's answer ────────────────────────
        session["answer_event"].clear()
        session["waiting_for"] = "answer"
        
        yield sse_event("waiting_for_answer", {
            "agent_id": agent_id,
            "agent_name": AGENTS[agent_id]["name"],
            "question": question,
            "agent_index": agent_index,
            "total_agents": len(AGENT_ORDER),
            "session_id": session_id
        })
        
        # Block until answer arrives via /conversation/answer endpoint
        await session["answer_event"].wait()
        answer = session["pending_answer"]
        session["pending_answer"] = ""
        session["waiting_for"] = None
        
        # Store pitcher's answer
        session["conversation"].append({
            "turn": len(session["conversation"]),
            "type": "answer",
            "agent_id": "pitcher",
            "agent_name": "Pitcher",
            "content": answer,
            "timestamp": str(asyncio.get_event_loop().time())
        })
        
        yield sse_event("pitcher_answer_received", {
            "answer": answer,
            "agent_id": agent_id
        })
        
        # ── STEP C: Agent reacts to answer ───────────────────────────
        async for event in generate_agent_reaction(session, agent_id, question, answer):
            yield event
        
        reaction = session["conversation"][-1]["content"]
        
        # ── STEP D: Interrupt check ───────────────────────────────────
        interrupt = await check_interrupt(session, agent_id, question, answer, reaction)
        
        if interrupt:
            async for event in stream_interrupt(session, interrupt):
                yield event
            
            interrupt_question = interrupt["followup_question"]
            interrupting_agent_id = interrupt["agent_id"]
            
            # Wait for pitcher's answer to the interrupt
            session["answer_event"].clear()
            session["waiting_for"] = "interrupt_answer"
            
            yield sse_event("waiting_for_answer", {
                "agent_id": interrupting_agent_id,
                "agent_name": AGENTS[interrupting_agent_id]["name"],
                "question": interrupt_question,
                "is_interrupt": True,
                "session_id": session_id
            })
            
            await session["answer_event"].wait()
            interrupt_answer = session["pending_answer"]
            session["pending_answer"] = ""
            session["waiting_for"] = None
            
            # Store interrupt answer
            session["conversation"].append({
                "turn": len(session["conversation"]),
                "type": "interrupt_a",
                "agent_id": "pitcher",
                "agent_name": "Pitcher",
                "content": interrupt_answer,
                "timestamp": str(asyncio.get_event_loop().time())
            })
            
            yield sse_event("interrupt_answer_received", {
                "answer": interrupt_answer,
                "agent_id": interrupting_agent_id
            })
        
        # Small pause between agents
        await asyncio.sleep(0.4)
    
    # ── All agents done — move to verdict ────────────────────────────
    session["phase"] = "verdict"
    yield sse_event("conversation_complete", {
        "total_turns": len(session["conversation"]),
        "session_id": session_id
    })
    
    # Generate verdict from full conversation
    async for event in stream_verdict_from_conversation(session_id):
        yield event
    
    # ── HITL: Verdict pushback ────────────────────────────────────────
    session["waiting_for"] = "pushback"
    yield sse_event("verdict_pushback_available", {
        "session_id": session_id,
        "message": "You can push back on one part of this verdict."
    })
```

---

### 7. stream_verdict_from_conversation()

Replace stream_verdict() with this version that reads the full conversation:

```python
async def stream_verdict_from_conversation(
    session_id: str
) -> AsyncGenerator[str, None]:
    """Generate verdict from the full conversation transcript."""
    
    session = sessions[session_id]
    
    yield sse_event("status", {
        "message": "Judge is reading the full conversation...",
        "phase": "verdict_start"
    })
    await asyncio.sleep(0.8)
    
    conversation_transcript = build_conversation_context(session)
    
    full_verdict_input = f"""PITCH SUMMARY:
{session['pitch_summary']}

FULL CONVERSATION TRANSCRIPT:
{conversation_transcript}"""
    
    yield sse_event("agent_start", {
        "agent_id": "judge",
        "name": "The Judge",
        "role": "Verdict"
    })
    
    full_verdict = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=200,
        system=JUDGE_CONVERSATION_PROMPT,
        messages=[{"role": "user", "content": full_verdict_input}]
    ) as stream:
        for text in stream.text_stream:
            full_verdict += text
            yield sse_event("agent_token", {
                "agent_id": "judge",
                "token": text
            })
    
    session["verdict"] = full_verdict
    parts = parse_verdict(full_verdict)
    session["verdict_parts"] = parts
    
    yield sse_event("verdict_complete", {
        "verdict": full_verdict,
        "parts": parts,
        "session_id": session_id
    })
```

---

### 8. handle_verdict_pushback()

```python
async def handle_verdict_pushback(
    session_id: str,
    pushback: str
) -> AsyncGenerator[str, None]:
    """Judge responds to pitcher's pushback on verdict. One time only."""
    
    session = sessions[session_id]
    
    pushback_prompt = f"""The pitcher has pushed back on your verdict.

Your original verdict:
{session['verdict']}

The pitcher's pushback:
{pushback}

Respond in exactly 2 sentences:
1. Acknowledge what is valid in their pushback if anything is.
2. Either modify your verdict or explain why it stands as-is.

Be honest. If they made a fair point, say so and update.
If they're deflecting, say so clearly.
Start with either 'Fair point —' or 'The verdict stands —'"""
    
    yield sse_event("pushback_response_start", {"session_id": session_id})
    
    full_response = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=100,
        system="You are the Judge. Respond to the pitcher's pushback on your verdict.",
        messages=[{"role": "user", "content": pushback_prompt}]
    ) as stream:
        for text in stream.text_stream:
            full_response += text
            yield sse_event("agent_token", {
                "agent_id": "judge",
                "token": text,
                "type": "pushback_response"
            })
    
    session["verdict_final"] = session["verdict"] + "\n\nJudge's response to pushback: " + full_response
    session["waiting_for"] = None
    session["phase"] = "complete"
    
    yield sse_event("session_complete", {
        "session_id": session_id,
        "verdict": session["verdict_final"]
    })
```

---

## MODIFIED ROUTES

### Replace POST /pitch/start

```python
@app.post("/pitch/start")
async def start_pitch(req: PitchRequest):
    """Start pitch — extract summary and pause for HITL approval."""
    
    session_id = req.session_id or str(uuid.uuid4())
    sessions[session_id] = {
        "id": session_id,
        "pitch_summary": "",
        "pitch_summary_approved": False,
        "conversation": [],
        "current_agent_index": 0,
        "current_agent_id": AGENT_ORDER[0],
        "waiting_for": "summary_approval",
        "verdict": "",
        "verdict_parts": {},
        "verdict_final": "",
        "phase": "extracting",
        # asyncio primitives for pausing/resuming
        "answer_event": asyncio.Event(),
        "summary_event": asyncio.Event(),
        "pushback_event": asyncio.Event(),
        "pending_answer": "",
        "pending_summary_correction": None,
        "pending_pushback": None,
        "stream_generator": None  # stores reference to active stream
    }
    
    async def event_stream():
        session = sessions[session_id]
        
        # Step 1: Extract pitch summary
        yield sse_event("status", {
            "message": "Understanding your pitch...",
            "phase": "extracting"
        })
        
        summary = await extract_pitch_summary(req.pitch_transcript)
        session["pitch_summary"] = summary
        session["phase"] = "awaiting_summary_approval"
        
        yield sse_event("summary_ready", {
            "summary": summary,
            "session_id": session_id,
            "message": "Is this what you meant?"
        })
        
        # HITL PAUSE 1: Wait for summary approval
        session["summary_event"].clear()
        await session["summary_event"].wait()
        
        # Apply correction if any
        if session["pending_summary_correction"]:
            session["pitch_summary"] = session["pending_summary_correction"]
            session["pending_summary_correction"] = None
            yield sse_event("summary_corrected", {
                "summary": session["pitch_summary"]
            })
        
        session["pitch_summary_approved"] = True
        session["phase"] = "conversation"
        
        yield sse_event("conversation_starting", {
            "session_id": session_id,
            "agent_count": len(AGENT_ORDER)
        })
        
        # Step 2: Run full hybrid conversation
        async for event in stream_full_conversation(session_id):
            yield event
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )
```

---

## NEW ROUTES TO ADD

### POST /pitch/approve-summary

```python
class SummaryApprovalRequest(BaseModel):
    session_id: str
    approved: bool
    corrected_summary: str | None = None

@app.post("/pitch/approve-summary")
async def approve_summary(req: SummaryApprovalRequest):
    if req.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[req.session_id]
    
    if req.corrected_summary:
        session["pending_summary_correction"] = req.corrected_summary
    
    session["summary_event"].set()  # unblocks the stream
    return {"status": "ok", "session_id": req.session_id}
```

---

### POST /conversation/answer

```python
class ConversationAnswerRequest(BaseModel):
    session_id: str
    answer: str

@app.post("/conversation/answer")
async def submit_conversation_answer(req: ConversationAnswerRequest):
    """Submit pitcher's answer to current agent's question."""
    
    if req.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[req.session_id]
    
    if session["waiting_for"] not in ("answer", "interrupt_answer"):
        raise HTTPException(
            status_code=400,
            detail=f"Not waiting for an answer. Current state: {session['waiting_for']}"
        )
    
    if not req.answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty")
    
    session["pending_answer"] = req.answer.strip()
    session["answer_event"].set()   # unblocks the stream
    session["answer_event"].clear() # reset immediately for next use
    
    return {
        "status": "ok",
        "session_id": req.session_id,
        "agent_index": session["current_agent_index"],
        "agents_remaining": len(AGENT_ORDER) - session["current_agent_index"] - 1
    }
```

---

### POST /verdict/pushback

```python
class PushbackRequest(BaseModel):
    session_id: str
    pushback: str

@app.post("/verdict/pushback")
async def submit_pushback(req: PushbackRequest):
    """Pitcher pushes back on one part of the verdict. One time only."""
    
    if req.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[req.session_id]
    
    if session["waiting_for"] != "pushback":
        raise HTTPException(status_code=400, detail="Not in pushback phase")
    
    async def pushback_stream():
        async for event in handle_verdict_pushback(req.session_id, req.pushback):
            yield event
    
    return StreamingResponse(
        pushback_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )
```

---

### POST /verdict/skip-pushback

```python
@app.post("/verdict/skip-pushback")
async def skip_pushback(session_id: str):
    """Pitcher accepts verdict without pushing back."""
    
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    session["waiting_for"] = None
    session["phase"] = "complete"
    session["verdict_final"] = session["verdict"]
    
    return {"status": "complete", "session_id": session_id}
```

---

### GET /session/{session_id}/conversation

```python
@app.get("/session/{session_id}/conversation")
async def get_conversation(session_id: str):
    """Get full conversation transcript for current session."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "conversation": sessions[session_id]["conversation"],
        "current_agent_index": sessions[session_id]["current_agent_index"],
        "waiting_for": sessions[session_id]["waiting_for"],
        "phase": sessions[session_id]["phase"]
    }
```

---

## UPDATED SESSION OBJECT FOR GET /session/{id}

The existing GET /session/{session_id} route is unchanged.
But update it to exclude asyncio.Event objects from the JSON response
(they are not JSON-serialisable). Add this helper:

```python
def serialise_session(session: dict) -> dict:
    """Return session dict without asyncio primitives."""
    excluded = {"answer_event", "summary_event", "pushback_event", "stream_generator"}
    return {k: v for k, v in session.items() if k not in excluded}
```

Then in the GET /session/{session_id} route:
```python
return serialise_session(sessions[session_id])
```

---

## UPDATED SSE EVENTS — FULL LIST

Frontend must handle these new events:

```
# Existing (keep handling these)
status                      → show status message
agent_token                 → append token to current agent display
session_complete            → session finished

# New — summary approval
summary_ready               → show editable summary + approve/correct UI
summary_corrected           → update displayed summary

# New — conversation flow
conversation_starting       → show "Panel ready" state, display all 6 agent slots
agent_question_start        → highlight the active agent card
agent_question_done         → lock the question display for this agent
pitcher_answer_received     → show pitcher's answer under the question
agent_reaction_start        → agent card enters "reacting" state
agent_reaction_done         → lock reaction display
sentiment_update            → update single agent's sentiment meter
waiting_for_answer          → show answer input box, highlight active agent

# New — interrupts
interrupt_start             → full-width interrupt card appears (same as old question interrupt)
interrupt_answer_received   → show answer to interrupt

# New — verdict
conversation_complete       → show "Conversation done" state
verdict_complete            → show verdict card
verdict_pushback_available  → show pushback input + skip button

# New — pushback
pushback_response_start     → judge card activates again
```

---

## FRONTEND UI CHANGES

The existing page.js needs these UI state changes:

### Replace the 3x2 agent card grid

Instead of a static 6-card grid where all agents show long paragraphs:

Use a CHAT-STYLE layout with a PROGRESS STRIP at the top:
```
[AM] → [PS] → [RK] → [AI] → [MP] → [K]
 ●       ○       ○       ○       ○      ○
Done  Active  Waiting...
```

Each agent slot shows:
- Before their turn: name + avatar, dimmed
- During question: question streaming in, highlighted border
- Awaiting answer: answer input box appears below the question
- After answer: pitcher's answer shown, then agent's reaction streams in
- Interrupt: different styling — orange border, "jumped in" label
- Complete: question + answer + reaction locked, sentiment pill visible

### Answer input

Show a text input + submit button ONLY when `waiting_for_answer` event arrives.
Position it directly below the active agent's card.
Include: voice input button, text input, submit button, agent index counter ("2 of 6")

### Summary approval screen

Full-screen modal before conversation starts:
- Shows the extracted pitch summary
- Editable text area (pre-filled with summary)
- "Looks right →" button
- "Let me correct this" button → makes summary editable

### Verdict pushback

Below the verdict card:
- "Push back on this verdict" text input
- "I accept this verdict" button
- Both visible simultaneously
- Pushback response streams below the original verdict

### Room Temperature meter

Keep this — update it after EACH agent reaction, not just after full rounds.
Sentiment updates one agent at a time now.

---

## AGENT SYSTEM PROMPT ADDITIONS

Add these lines to the end of EVERY agent's existing system_prompt.
Do not change anything else in the prompts — just append:

```
HYBRID CONVERSATION RULES:
In this system you will:
1. Ask ONE sharp question first (your opening move)
2. React briefly after the pitcher answers (1-2 sentences)
These are separate calls — stay in character for both.
For your question: no long preamble, no opinion, just ask.
For your reaction: reference what they actually said, be specific.
```

---

## IMPORTANT IMPLEMENTATION NOTES

1. asyncio.Event() objects must be created fresh for each session.
   The answer_event is reused across all 6 agents — it clears and sets
   for each exchange. Do not create a new event per agent.

2. The stream stays open for the entire session duration.
   POST /pitch/start returns a StreamingResponse that doesn't close
   until session_complete fires. This is intentional.

3. If the SSE connection drops mid-conversation, the session state
   is preserved in the sessions dict. The frontend can reconnect
   and call GET /session/{id}/conversation to recover state.

4. Max interrupts per session is 2 (hardcoded in check_interrupt).
   This prevents the conversation from becoming chaotic.
   Adjust this constant if needed after testing.

5. The answer_event.clear() in /conversation/answer must happen
   AFTER set() — otherwise the next wait() will fire immediately.
   The order is: set() → clear() → function returns.
   The asyncio loop in stream_full_conversation handles the timing.

6. AGENT_ORDER controls speaking order.
   Current order: vc → enthusiastic → hostile → expert → competitor → first_timer
   Interrupts can only come from agents LATER in the order than current speaker.
   This prevents agents who already spoke from jumping back in.

7. Token limits per call:
   - Question generation: max_tokens=80  (short question)
   - Reaction generation: max_tokens=70  (short reaction)
   - Interrupt check: max_tokens=150    (JSON output)
   - Verdict: max_tokens=200            (3 sentences)
   - Pushback response: max_tokens=100  (2 sentences)

8. Use claude-haiku-4-5-20251001 for interrupt check only
   (it's a yes/no routing decision — Sonnet is overkill).
   Use claude-sonnet-4-5 for everything else.
   Add FAST_MODEL = "claude-haiku-4-5-20251001" constant.
   Use FAST_MODEL in check_interrupt(), FAST_MODEL in extract_pitch_summary().

---

## WHAT THIS ACHIEVES

Old system:   6 long paragraphs → 1 question → 6 short reactions → verdict
              Pitcher speaks: ONCE
              Pitcher is passive: ~7 minutes

New system:   6 questions → 6 answers → 6 reactions → up to 2 interrupts → verdict
              Pitcher speaks: 6-8 times
              Pitcher is active: entire session
              Every agent's reaction is grounded in what the pitcher actually said
              Verdict is based on real conversation not simulated monologues
