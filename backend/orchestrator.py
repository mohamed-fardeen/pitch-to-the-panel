import json
import asyncio
import os
from typing import AsyncGenerator, Tuple, Dict, List, Optional
from prompts import (
    HOST_PAIR_SELECTION_PROMPT,
    CONVERSATION_ORCHESTRATOR_PROMPT,
    HOST_UTTERANCE_PROMPT,
    OBSERVER_UTTERANCE_PROMPT,
    PITCHER_INTERRUPT_ACK_PROMPT,
    JUDGE_CONVERSATION_PROMPT,
    DIFFICULTY_MODIFIERS,
    PERSONA_ANCHORS
)
from services.llm import llm_provider
# Feature 4: Firecrawl MCP Setup
try:
    from firecrawl import FirecrawlApp
    firecrawl = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY")) if os.getenv("FIRECRAWL_API_KEY") else None
except ImportError:
    firecrawl = None
except Exception:
    firecrawl = None

async def search_competitors(domain_info: dict) -> str:
    if not firecrawl: return ""
    query = f"{domain_info.get('sub_domain', '')} competitors India 2026 pricing"
    try:
        # Run synchronous operation in an executor thread
        results = await asyncio.to_thread(firecrawl.search, query, params={"limit": 3})
        competitor_context = "LIVE COMPETITOR RESEARCH (searched just now):\n"
        for r in results.get("data", [])[:3]:
            competitor_context += f"- {r.get('title', '')}: {r.get('snippet', '')}\n"
        return competitor_context
    except Exception:
        return ""

# Feature 5: Memory MCP Setup
MEMORY_FILE = "pitcher_memory.json"

def load_pitcher_memory(pitcher_id: str) -> dict | None:
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f).get(pitcher_id)
    except Exception:
        return None

def save_pitcher_memory(pitcher_id: str, session_data: dict, verdict: str = ""):
    if not pitcher_id: return
    try:
        try:
            with open(MEMORY_FILE, "r") as f: memory = json.load(f)
        except Exception: memory = {}
        memory[pitcher_id] = {
            "last_pitch_summary": session_data.get("summary", session_data.get("hitl_data", {}).get("corrected_summary", "")),
            "domain": session_data.get("domain", {}),
            "weaknesses": "Check Verdict for Weaknesses", # Simplified since we don't have parts parser
            "verdict": verdict,
            "pitch_count": memory.get(pitcher_id, {}).get("pitch_count", 0) + 1
        }
        with open(MEMORY_FILE, "w") as f: json.dump(memory, f, indent=2)
    except Exception: pass

# Feature 7: Sketch-to-3D (Meshy)
MESHY_API_URL = "https://api.meshy.ai/v1/image-to-3d"

async def generate_3d_from_sketch(image_url: str) -> dict:
    api_key = os.getenv("MESHY_API_KEY")
    if not api_key: return {"error": "No Meshy API key"}
    
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "image_url": image_url,
        "enable_pbr": True,
    }
    
    try:
        # 1. Create task
        import requests
        response = await asyncio.to_thread(requests.post, MESHY_API_URL, headers=headers, json=payload)
        task_data = response.json()
        task_id = task_data.get("result")
        
        if not task_id: return {"error": f"Task creation failed: {task_data}"}
        
        # 2. Poll for completion
        for _ in range(30): # Poll for 3 minutes max
            await asyncio.sleep(6)
            status_res = await asyncio.to_thread(requests.get, f"{MESHY_API_URL}/{task_id}", headers=headers)
            status_data = status_res.json()
            if status_data.get("status") == "SUCCEEDED":
                return {
                    "thumbnail_url": status_data.get("thumbnail_url"),
                    "model_url": status_data.get("model_url"),
                    "task_id": task_id
                }
            if status_data.get("status") == "FAILED":
                return {"error": "Meshy generation failed"}
        
        return {"error": "Timeout waiting for 3D model"}
    except Exception as e:
        return {"error": str(e)}

# The standard agents
PANEL_AGENTS_STANDARD = ["vc", "enthusiastic", "hostile", "expert", "competitor", "beginner"]
PANEL_AGENTS_DESIGN = ["vc", "enthusiastic", "hostile", "expert", "competitor", "design_critic"]
PANEL_AGENTS_NON_TECH = ["vc", "enthusiastic", "hostile", "expert", "competitor", "suresh"]

async def generate_radar_chart_image(scores: dict) -> str:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        import io
        import base64

        labels = list(scores.keys())
        # Remove 'reasoning' if present
        if "reasoning" in labels: labels.remove("reasoning")
        
        values = [scores[l] for l in labels]
        num_vars = len(labels)

        angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
        values += values[:1]
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
        ax.fill(angles, values, color='red', alpha=0.25)
        ax.plot(angles, values, color='red', linewidth=2)
        ax.set_yticklabels([])
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', transparent=True)
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig)
        return img_str
    except Exception:
        return ""

async def get_scoring_radar(pitch: str, round1: dict, provider: str) -> dict:
    prompt = """You are a startup pitch evaluator. Score this pitch on 5 dimensions based on the pitch and the panel's reactions. Output ONLY valid JSON:
    
    {
      "problem_clarity": 7,
      "market_size": 6,
      "differentiation": 8,
      "feasibility": 5,
      "founder_credibility": 7,
      "reasoning": { "problem_clarity": "...", "market_size": "...", "differentiation": "...", "feasibility": "...", "founder_credibility": "..." }
    }"""
    r1_text = "\n\n".join([f"[{k.upper()}]\n{v}" for k, v in round1.items()])
    user_prompt = f"PITCH:\n{pitch}\n\nPANEL REACTIONS:\n{r1_text}"
    try:
        response = await llm_provider.generate_response(prompt, user_prompt, provider, stream=False)
        start = response.find("{")
        end = response.rfind("}") + 1
        scores = json.loads(response[start:end])
    except Exception:
        scores = {"problem_clarity":5, "market_size":5, "differentiation":5, "feasibility":5, "founder_credibility":5}
    
    try:
        b64 = await generate_radar_chart_image(scores)
    except Exception:
        b64 = None
        
    return {"scores": scores, "image": b64}

# Helper to emit SSE events
def sse_event(event_type: str, data: dict) -> dict:
    return {"event": event_type, "data": json.dumps(data)}

def build_conversation_context(session: dict) -> str:
    """Build a readable transcript of the conversation so far."""
    if not session.get("conversation"):
        return "No exchanges yet."
    
    lines = []
    for turn in session["conversation"]:
        t = turn["type"]
        name = turn.get("agent_name", "Unknown")
        content = turn.get("content", "")

        if t == "question":
            lines.append(f"{name} asked: {content}")
        elif t == "answer":
            lines.append(f"Pitcher answered: {content}")
        elif t == "reaction":
            lines.append(f"{name} reacted: {content}")
        elif t == "interrupt_q":
            lines.append(f"{name} jumped in: {content}")
        elif t == "interrupt_a":
            lines.append(f"Pitcher replied: {content}")
        elif t == "host_utterance":
            lines.append(f"{name}: {content}")
        elif t == "observer_utterance":
            lines.append(f"{name} (Observer): {content}")
        elif t == "pitcher_interrupt":
            lines.append(f"Pitcher (Interruption): {content}")
        elif t == "interrupt_ack":
            lines.append(f"{name} (Acknowledging): {content}")
    
    return "\n".join(lines)

async def select_host_pair(
    session: dict, 
    provider: str
) -> Tuple[str, str]:
    """
    Select the two best host agents for this pitch.
    Returns (host_a_id, host_b_id).
    host_a is the more skeptical host.
    """
    active_panel = session["active_panel"]
    panel_names = ", ".join([
        f"{aid} ({AGENTS_CONFIG[aid]['name']})" 
        for aid in active_panel
    ])
    
    prompt = HOST_PAIR_SELECTION_PROMPT.format(
        active_panel_names=panel_names,
        domain=session.get("domain", {}).get(
            "sub_domain", "general"
        ),
        pitch_summary=session["pitch_summary"]
    )
    
    try:
        raw = await llm_provider.generate_response(
            "Select two host agents. Output only valid JSON.",
            prompt,
            provider,
            stream=False
        )
        start = raw.find("{")
        end = raw.rfind("}") + 1
        result = json.loads(raw[start:end])
        host_a = result.get("host_a", active_panel[0])
        host_b = result.get("host_b", active_panel[1])
        # Validate both are in active panel
        if host_a not in active_panel:
            host_a = active_panel[0]
        if host_b not in active_panel:
            host_b = active_panel[1]
        if host_a == host_b:
            host_b = active_panel[1] if host_a != active_panel[1] \
                     else active_panel[2]
        return host_a, host_b
    except Exception:
        # Fallback: vc as host_a, hostile as host_b
        # (most contrasting pair by default)
        fallbacks = [a for a in ["vc", "hostile", "expert",
                                  "enthusiastic", "competitor",
                                  "beginner"] 
                     if a in active_panel]
        return fallbacks[0], fallbacks[1]

async def get_next_orchestration_decision(
    session: dict,
    provider: str,
    difficulty: str = "standard"
) -> dict:
    """
    Ask the orchestrator what happens next in the 
    conversation. Returns a decision dict.
    """
    host_a_id = session["host_a"]
    host_b_id = session["host_b"]
    observers = [
        aid for aid in session["active_panel"]
        if aid not in [host_a_id, host_b_id]
        and aid not in session.get("called_observers", [])
    ]
    observer_list = "\n".join([
        f"- {aid}: {AGENTS_CONFIG[aid]['name']} "
        f"({AGENTS_CONFIG[aid]['role']})"
        for aid in observers
    ]) or "None remaining"

    difficulty_instruction = DIFFICULTY_MODIFIERS.get(
        difficulty, DIFFICULTY_MODIFIERS["standard"]
    )["question"]

    prompt = CONVERSATION_ORCHESTRATOR_PROMPT.format(
        host_a_id=host_a_id,
        host_a_name=AGENTS_CONFIG[host_a_id]["name"],
        host_a_role=AGENTS_CONFIG[host_a_id]["role"],
        host_b_id=host_b_id,
        host_b_name=AGENTS_CONFIG[host_b_id]["name"],
        host_b_role=AGENTS_CONFIG[host_b_id]["role"],
        observer_list=observer_list,
        pitch_summary=session["pitch_summary"],
        conversation_so_far=build_conversation_context(session),
        exchange_count=session.get("exchange_count", 0),
        pitcher_intervention_count=session.get(
            "pitcher_intervention_count", 0
        ),
        difficulty_instruction=difficulty_instruction
    )

    try:
        raw = await llm_provider.generate_response(
            "You are a debate orchestrator. "
            "Output only valid JSON.",
            prompt,
            provider,
            stream=False
        )
        start = raw.find("{")
        end = raw.rfind("}") + 1
        decision = json.loads(raw[start:end])
        speaker_id = decision.get("speaker_id")
        next_speaker = decision.get("next_speaker")
        
        # Normalize speaker_id if LLM returned a name instead of ID
        name_to_id = {v["name"]: k for k, v in AGENTS_CONFIG.items()}
        if speaker_id in name_to_id:
            speaker_id = name_to_id[speaker_id]
        
        # Also handle partial names or shortcuts if host_a/b
        if speaker_id == "host_a": speaker_id = host_a_id
        if speaker_id == "host_b": speaker_id = host_b_id
        
        decision["speaker_id"] = speaker_id
        return decision
    except Exception:
        # Fallback: alternate between hosts
        exchange_count = session.get("exchange_count", 0)
        next_host = host_a_id if exchange_count % 2 == 0 \
                    else host_b_id
        return {
            "next_speaker": "host_a" if next_host == host_a_id 
                            else "host_b",
            "speaker_id": next_host,
            "instruction": "Continue the conversation about "
                           "the pitch. Make your key point.",
            "should_ask_pitcher": exchange_count > 0 
                                  and exchange_count % 4 == 0,
            "pitcher_question": "What do you think about "
                                "the concern we just raised?",
            "observer_to_call": None,
            "observer_reason": None,
            "conversation_should_end": exchange_count >= 16
        }

async def stream_host_utterance(
    session: dict,
    agent_id: str,
    instruction: str,
    should_ask_pitcher: bool,
    pitcher_question: str,
    provider: str,
    difficulty: str = "standard"
) -> AsyncGenerator[dict, None]:
    """
    Stream a host's natural conversational utterance.
    Short bursts — 1-3 sentences.
    """
    agent = AGENTS_CONFIG[agent_id]
    difficulty_instruction = DIFFICULTY_MODIFIERS.get(
        difficulty, DIFFICULTY_MODIFIERS["standard"]
    )["question"]

    pitcher_instruction = (
        f"End your message with this direct question "
        f"to the pitcher: {pitcher_question}"
        if should_ask_pitcher
        else "Do not ask the pitcher anything this turn. "
             "Talk to the other host."
    )

    system = HOST_UTTERANCE_PROMPT.format(
        persona_anchor=PERSONA_ANCHORS.get(agent_id, ""),
        pitch_summary=session["pitch_summary"],
        conversation_so_far=build_conversation_context(session),
        instruction=instruction,
        difficulty_instruction=difficulty_instruction,
        pitcher_instruction=pitcher_instruction
    )

    user_message = (
        f"Speak now as {agent['name']}. "
        f"1-2 sentences. Natural and conversational."
    )

    yield sse_event("agent_utterance_start", {
        "agent_id": agent_id,
        "name": agent["name"],
        "role": agent["role"],
        "type": "host",
        "asks_pitcher": should_ask_pitcher,
        "pitcher_question": pitcher_question 
                            if should_ask_pitcher else None
    })

    full_text = ""
    try:
        stream = await llm_provider.generate_response(
            system, user_message, provider, stream=True, max_tokens=80
        )
        async for text in stream:
            # Check for immediate interrupt
            if session.get("waiting_for") == "pitcher_interrupt":
                break
                
            full_text += text
            yield sse_event("agent_token", {
                "agent_id": agent_id,
                "name": agent["name"],
                "token": text,
                "type": "host_utterance"
            })
    except Exception as e:
        full_text = f"Error: {str(e)}"

    session["conversation"].append({
        "turn": len(session["conversation"]),
        "type": "host_utterance",
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "content": full_text,
        "asks_pitcher": should_ask_pitcher,
        "timestamp": str(asyncio.get_event_loop().time())
    })

    session["exchange_count"] = \
        session.get("exchange_count", 0) + 1

    yield sse_event("agent_utterance_done", {
        "agent_id": agent_id,
        "name": agent["name"],
        "content": full_text,
        "asks_pitcher": should_ask_pitcher
    })

    if should_ask_pitcher and session.get("waiting_for") != "pitcher_interrupt":
        session["waiting_for"] = "answer"

async def stream_observer_utterance(
    session: dict,
    agent_id: str,
    observer_reason: str,
    provider: str,
    difficulty: str = "standard"
) -> AsyncGenerator[dict, None]:
    """
    Stream a called-in observer agent's single contribution.
    They speak once then step back.
    """
    agent = AGENTS_CONFIG[agent_id]
    difficulty_instruction = DIFFICULTY_MODIFIERS.get(
        difficulty, DIFFICULTY_MODIFIERS["standard"]
    )["question"]

    system = OBSERVER_UTTERANCE_PROMPT.format(
        persona_anchor=PERSONA_ANCHORS.get(agent_id, ""),
        pitch_summary=session["pitch_summary"],
        conversation_so_far=build_conversation_context(session),
        observer_reason=observer_reason,
        difficulty_instruction=difficulty_instruction
    )

    user_message = (
        f"Speak now as {agent['name']}. "
        f"2-3 sentences. Make your key point."
    )

    yield sse_event("agent_utterance_start", {
        "agent_id": agent_id,
        "name": agent["name"],
        "role": agent["role"],
        "type": "observer",
        "reason": observer_reason
    })

    full_text = ""
    try:
        stream = await llm_provider.generate_response(
            system, user_message, provider, stream=True
        )
        async for text in stream:
            # Check for immediate interrupt
            if session.get("waiting_for") == "pitcher_interrupt":
                full_text += "... [INTERRUPTED]"
                break

            full_text += text
            yield sse_event("agent_token", {
                "agent_id": agent_id,
                "name": agent["name"],
                "token": text,
                "type": "observer_utterance"
            })
    except Exception as e:
        full_text = f"Error: {str(e)}"

    session["conversation"].append({
        "turn": len(session["conversation"]),
        "type": "observer_utterance",
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "content": full_text,
        "timestamp": str(asyncio.get_event_loop().time())
    })

    # Mark this observer as called — they can't be 
    # called again this session
    if "called_observers" not in session:
        session["called_observers"] = []
    session["called_observers"].append(agent_id)

    session["exchange_count"] = \
        session.get("exchange_count", 0) + 1

    yield sse_event("agent_utterance_done", {
        "agent_id": agent_id,
        "name": agent["name"],
        "content": full_text,
        "type": "observer"
    })

async def stream_pitcher_interrupt_ack(
    session: dict,
    pitcher_message: str,
    provider: str,
    difficulty: str = "standard",
    respondent_id: Optional[str] = None
) -> AsyncGenerator[dict, None]:
    """
    Stream the chosen host's acknowledgement of 
    a pitcher interrupt.
    """
    intervention_count = session.get(
        "pitcher_intervention_count", 0
    )
    if not respondent_id:
        host_a = session["host_a"]
        host_b = session["host_b"]
        respondent_id = host_a if intervention_count % 2 == 0 \
                             else host_b

    agent = AGENTS_CONFIG[respondent_id]
    difficulty_instruction = DIFFICULTY_MODIFIERS.get(
        difficulty, DIFFICULTY_MODIFIERS["standard"]
    )["reaction"]

    # Detect if pitcher sent actual content or just clicked the button
    is_signal_only = (
        not pitcher_message.strip() or
        pitcher_message.strip() == "[interrupt_signal]"
    )

    # Get pitcher name from session if available
    pitcher_name = session.get("pitcher_name", "our pitcher")
    if not pitcher_name or pitcher_name.strip() == "":
        pitcher_name = "our pitcher"
        
    import random
    responses = [
        f"Oh, looks like {pitcher_name} wants to jump in. Go ahead.",
        f"Actually, {pitcher_name} looks like they have something to add. What's on your mind?",
        f"Wait, let's hear what {pitcher_name} has to say. Go ahead!"
    ]
    full_text = random.choice(responses)

    yield sse_event("agent_utterance_start", {
        "agent_id": respondent_id,
        "name": agent["name"],
        "role": agent["role"],
        "type": "interrupt_ack"
    })

    # Give the frontend TTS engine a split second to reset after cancelling
    # the previous speech, avoiding a notorious Chrome bug.
    await asyncio.sleep(0.5)

    yield sse_event("agent_token", {
        "agent_id": respondent_id,
        "name": agent["name"],
        "token": full_text,
        "type": "interrupt_ack"
    })

    session["conversation"].append({
        "turn": len(session["conversation"]),
        "type": "interrupt_ack",
        "agent_id": respondent_id,
        "agent_name": agent["name"],
        "content": full_text,
        "timestamp": str(asyncio.get_event_loop().time())
    })

    session["pitcher_intervention_count"] = \
        intervention_count + 1
    session["exchange_count"] = \
        session.get("exchange_count", 0) + 1

    yield sse_event("agent_utterance_done", {
        "agent_id": respondent_id,
        "name": agent["name"],
        "content": full_text,
        "type": "interrupt_ack"
    })

async def get_interrupt_respondent(session: dict, pitcher_message: str, provider: str) -> str:
    host_a = session["host_a"]
    host_b = session["host_b"]
    
    agent_a = AGENTS_CONFIG[host_a]
    agent_b = AGENTS_CONFIG[host_b]
    
    prompt = f"""
    You are a conversation orchestrator for a pitch panel.
    Pitcher interrupted: "{pitcher_message}"
    
    Hosts:
    - {host_a}: {agent_a['name']} ({agent_a['role']})
    - {host_b}: {agent_b['name']} ({agent_b['role']})
    
    Which host should respond? 
    - Use 'vc' or 'hostile' for pressure/skepticism.
    - Use 'enthusiastic' or 'expert' for technical or positive points.
    
    Output ONLY the agent_id.
    """
    try:
        resp = await llm_provider.generate_response(prompt, pitcher_message, provider, stream=False)
        chosen = resp.strip().lower()
        if chosen in [host_a, host_b]:
            return chosen
    except Exception:
        pass
    return host_a

async def stream_notebooklm_conversation(
    session_id: str,
    session: dict,
    provider: str,
    difficulty: str = "standard"
) -> AsyncGenerator[dict, None]:
    """
    NotebookLM-style conversation orchestrator.
    Two hosts are discussing the pitch:
Host A: {host_a_id} ({host_a_name}, {host_a_role})
Host B: {host_b_id} ({host_b_name}, {host_b_role})

Observer agents available to call in:
{observer_list}
    """

    # ── SETUP ────────────────────────────────────────
    host_a, host_b = await select_host_pair(
        session, provider
    )
    session["host_a"] = host_a
    session["host_b"] = host_b
    session["called_observers"] = []
    session["exchange_count"] = 0
    session["pitcher_intervention_count"] = 0
    session["waiting_for"] = None

    yield sse_event("hosts_selected", {
        "host_a": {
            "agent_id": host_a,
            "name": AGENTS_CONFIG[host_a]["name"],
            "role": AGENTS_CONFIG[host_a]["role"]
        },
        "host_b": {
            "agent_id": host_b,
            "name": AGENTS_CONFIG[host_b]["name"],
            "role": AGENTS_CONFIG[host_b]["role"]
        },
        "observers": [
            {
                "agent_id": aid,
                "name": AGENTS_CONFIG[aid]["name"],
                "role": AGENTS_CONFIG[aid]["role"]
            }
            for aid in session["active_panel"]
            if aid not in [host_a, host_b]
        ],
        "session_id": session_id
    })

    yield sse_event("status", {
        "message": "Panel is live. The hosts are discussing "
                   "your pitch...",
        "phase": "conversation_start"
    })

    # ── MAIN CONVERSATION LOOP ────────────────────────
    last_active_agent = None
    while True:

        # Check for pitcher interrupt first
        if session.get("waiting_for") == "pitcher_interrupt":
            session["events"]["answer_event"].clear()
            
            # 1. SHOW INPUT BOX AND INVITE IMMEDIATELY
            yield sse_event("waiting_for_pitcher_interrupt", {
                "session_id": session_id,
                "message": "You interrupted — go ahead"
            })

            # 2. ACKNOWLEDGMENT (Intent to speak)
            # Use whoever was just speaking as the one to acknowledge
            respondent_id = last_active_agent or session["host_a"]
            
            async for event in stream_pitcher_interrupt_ack(
                session, "", provider, difficulty, respondent_id
            ):
                yield event

            # 3. WAIT (User is already typing)
            await session["events"]["answer_event"].wait()
            pitcher_msg = session["pending_answer"]
            session["pending_answer"] = ""
            session["waiting_for"] = None
            
            yield sse_event("pitcher_interrupted", {
                "content": pitcher_msg,
                "session_id": session_id
            })

            # Log the pitcher interrupt
            session["conversation"].append({
                "turn": len(session["conversation"]),
                "type": "pitcher_interrupt",
                "agent_id": "pitcher",
                "agent_name": "Pitcher",
                "content": pitcher_msg,
                "timestamp": str(asyncio.get_event_loop().time())
            })

            await asyncio.sleep(0.3)
            continue

        # Ensure answer_event is clean before setting up the race condition
        session["events"]["answer_event"].clear()

        # Get orchestrator decision asynchronously so it can be interrupted
        decision_task = asyncio.create_task(
            get_next_orchestration_decision(session, provider, difficulty)
        )
        interrupt_task = asyncio.create_task(session["events"]["answer_event"].wait())
        
        done, pending = await asyncio.wait(
            [decision_task, interrupt_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        if session.get("waiting_for") == "pitcher_interrupt":
            if decision_task in pending:
                decision_task.cancel()
            continue
            
        if interrupt_task in pending:
            interrupt_task.cancel()

        if not decision_task.done():
            # In case the event fired for some other unknown reason, avoid the state crash
            decision_task.cancel()
            continue
            
        decision = decision_task.result()

        # Check if conversation should end
        if decision.get("conversation_should_end"):
            break

        next_speaker = decision.get("next_speaker", "")
        speaker_id = decision.get("speaker_id")
        instruction = decision.get(
            "instruction", "Continue the discussion."
        )
        should_ask_pitcher = decision.get(
            "should_ask_pitcher", False
        ) or (next_speaker == "ask_pitcher")
        
        pitcher_question = decision.get(
            "pitcher_question", ""
        )
        observer_to_call = decision.get("observer_to_call")
        observer_reason = decision.get("observer_reason", "")

        # ── OBSERVER CALLED IN ────────────────────────
        if (next_speaker == "call_observer" or observer_to_call) and observer_to_call:
            session["called_observers"] = session.get("called_observers", []) + [observer_to_call]
            last_active_agent = observer_to_call
            async for event in stream_observer_utterance(
                session, observer_to_call,
                observer_reason, provider, difficulty
            ):
                yield event
            
            session["exchange_count"] = session.get("exchange_count", 0) + 1
            await asyncio.sleep(0.4)

            # If observer asked the pitcher something,
            # wait for answer
            last_turn = session["conversation"][-1]
            if "?" in last_turn.get("content", ""):
                session["events"]["answer_event"].clear()
                session["waiting_for"] = "answer"

                yield sse_event("waiting_for_answer", {
                    "agent_id": observer_to_call,
                    "agent_name": AGENTS_CONFIG[
                        observer_to_call
                    ]["name"],
                    "question": last_turn["content"],
                    "is_observer": True,
                    "session_id": session_id
                })

                await session["events"]["answer_event"].wait()
                obs_answer = session["pending_answer"]
                session["pending_answer"] = ""
                session["waiting_for"] = None

                session["conversation"].append({
                    "turn": len(session["conversation"]),
                    "type": "answer",
                    "agent_id": "pitcher",
                    "agent_name": "Pitcher",
                    "content": obs_answer,
                    "timestamp": str(
                        asyncio.get_event_loop().time()
                    )
                })

                yield sse_event("pitcher_answer_received", {
                    "answer": obs_answer,
                    "agent_id": observer_to_call
                })

            continue

        # ── HOST SPEAKS ───────────────────────────────
        if (next_speaker in ("host_a", "host_b", "ask_pitcher") or next_speaker.startswith("host")) \
                and speaker_id:
            last_active_agent = speaker_id
            async for event in stream_host_utterance(
                session, speaker_id, instruction,
                should_ask_pitcher, pitcher_question,
                provider, difficulty
            ):
                yield event

            session["exchange_count"] = session.get("exchange_count", 0) + 1
            await asyncio.sleep(0.3)

            # If host asked the pitcher, wait for answer
            if should_ask_pitcher:
                session["events"]["answer_event"].clear()
                session["waiting_for"] = "answer"

                yield sse_event("waiting_for_answer", {
                    "agent_id": speaker_id,
                    "agent_name": AGENTS_CONFIG[
                        speaker_id
                    ]["name"],
                    "question": pitcher_question,
                    "session_id": session_id
                })

                await session["events"]["answer_event"].wait()
                answer = session["pending_answer"]
                session["pending_answer"] = ""
                session["waiting_for"] = None

                session["conversation"].append({
                    "turn": len(session["conversation"]),
                    "type": "answer",
                    "agent_id": "pitcher",
                    "agent_name": "Pitcher",
                    "content": answer,
                    "timestamp": str(
                        asyncio.get_event_loop().time()
                    )
                })

                session["pitcher_intervention_count"] = session.get("pitcher_intervention_count", 0) + 1
                yield sse_event("pitcher_answer_received", {
                    "answer": answer,
                    "agent_id": speaker_id
                })

            continue

        # If we got here and didn't match host or observer, 
        # let's just use the fallback next time instead of breaking
        session["exchange_count"] = session.get("exchange_count", 0) + 1
        await asyncio.sleep(0.1)
        continue

        # Safety: if decision is unclear, break
        break
    
    # Complete
    session["phase"] = "verdict"
    yield sse_event("conversation_complete", {
        "total_turns": len(session["conversation"]),
        "session_id": session_id
    })
    
    async for event in stream_verdict_from_conversation(session_id, session, provider):
        yield event

async def stream_verdict_from_conversation(session_id: str, session: dict, provider: str):
    """Generate verdict from transcript."""
    yield sse_event("status", {"message": "Judge is reading the conversation...", "phase": "verdict_start"})
    await asyncio.sleep(0.8)
    
    transcript = build_conversation_context(session)
    user_input = f"PITCH SUMMARY:\n{session['pitch_summary']}\n\nFULL CONVERSATION TRANSCRIPT:\n{transcript}"
    
    difficulty_instruction = DIFFICULTY_MODIFIERS.get(
        session.get("difficulty", "standard"),
        DIFFICULTY_MODIFIERS["standard"]
    )["verdict"]

    system = JUDGE_CONVERSATION_PROMPT.format(
        difficulty_instruction=difficulty_instruction
    )

    yield sse_event("agent_start", {"agent_id": "judge", "name": "The Judge", "role": "Verdict"})
    
    full_verdict = ""
    try:
        stream = await llm_provider.generate_response(system, user_input, provider, stream=True)
        async for text in stream:
            full_verdict += text
            yield sse_event("agent_token", {"agent_id": "judge", "token": text})
    except Exception as e:
        full_verdict = f"Error: {str(e)}"
    
    session["verdict"] = full_verdict
    
    # Basic parsing for strengths/weakness/action
    parts = {"strongest": "", "weakness": "", "fix": ""}
    if "Your strongest point:" in full_verdict:
        parts["strongest"] = full_verdict.split("Your strongest point:")[1].split("Your biggest weakness:")[0].strip()
    if "Your biggest weakness:" in full_verdict:
        parts["weakness"] = full_verdict.split("Your biggest weakness:")[1].split("Before your next pitch:")[0].strip()
    if "Before your next pitch:" in full_verdict:
        parts["fix"] = full_verdict.split("Before your next pitch:")[1].strip()
    
    session["verdict_parts"] = parts
    yield sse_event("verdict_complete", {"verdict": full_verdict, "parts": parts, "session_id": session_id})
    
    yield sse_event("verdict_pushback_available", {"session_id": session_id, "message": "You can push back on one part."})

async def handle_verdict_pushback(session_id: str, pushback: str, provider: str, sessions: dict):
    """Judge responds to pushback."""
    session = sessions.get(session_id) # Note: sessions needs to be accessible, usually passed or global
    if not session: return

    prompt = f"Original Verdict:\n{session['verdict']}\n\nPushback:\n{pushback}\n\nRespond in 2 sentences."
    yield sse_event("pushback_response_start", {"session_id": session_id})
    
    full_resp = ""
    try:
        stream = await llm_provider.generate_response("You are the Judge. Respond to pushback.", prompt, provider, stream=True)
        async for text in stream:
            full_resp += text
            yield sse_event("agent_token", {"agent_id": "judge", "token": text, "type": "pushback_response"})
    except Exception: pass
    
    session["verdict_final"] = session["verdict"] + "\n\nJudge Response: " + full_resp
    yield sse_event("session_complete", {"session_id": session_id, "verdict": session["verdict_final"]})

# Mapping for agent IDs to names/roles (since we deleted AGENTS config usage here)
AGENTS_CONFIG = {
    "vc": {"name": "Arjun Mehta", "role": "Venture Capitalist"},
    "enthusiastic": {"name": "Priya Sharma", "role": "Product Manager"},
    "hostile": {"name": "Ravi Kumar", "role": "Operations Manager"},
    "expert": {"name": "Dr. Ananya Iyer", "role": "Industry Expert"},
    "competitor": {"name": "Meera Pillai", "role": "Marketing Manager"},
    "beginner": {"name": "Kiran", "role": "Student"},
    "suresh": {"name": "Suresh Nair", "role": "Experienced Operator"},
    "design_critic": {"name": "Aisha Thomas", "role": "Design Critic"}
}

# The initial round 1 flow which now incorporates HITL
async def run_round1(session_id: str, session: dict, pitch: str, provider: str, pitcher_id: Optional[str] = None, difficulty: str = "standard"):
    # EXTRACT SUMMARY
    summary_prompt = "Summarize this startup pitch in 2-3 clear sentences focusing on the core problem, solution, and business model. Never use pleasantries."
    try:
        summary = await llm_provider.generate_response(summary_prompt, pitch, provider, stream=False)
    except Exception:
        summary = pitch[:200] + "..."

    # CLASSIFY DOMAIN
    domain_prompt = """
    Read this pitch summary and classify it. Output ONLY valid JSON, no other text:
    
    {
      "domain": "tech|food_beverage|retail|services|agriculture|education|healthcare|manufacturing|creative|physical_product|other",
      "sub_domain": "specific one-line description",
      "is_tech_primary": true,
      "is_physical_product": false,
      "business_model": "b2c|b2b|b2b2c|marketplace|franchise|subscription|other",
      "target_customer": "one sentence",
      "key_metrics": ["3 metrics"],
      "likely_competitors": ["2-3 competitors"],
      "panel_mode": "standard|design|physical_product|non_tech"
    }
    """
    
    try:
        domain_json_str = await llm_provider.generate_response(domain_prompt, summary, provider, stream=False)
        start_idx = domain_json_str.find("{")
        end_idx = domain_json_str.rfind("}") + 1
        domain_data = json.loads(domain_json_str[start_idx:end_idx])
    except Exception:
        domain_data = {"sub_domain": "General Tech", "is_tech_primary": True, "panel_mode": "standard"}
    
    yield sse_event("hitl_summary_approval", {
        "summary": summary,
        "domain": domain_data,
        "session_id": session_id,
        "message": "Is this what you meant?"
    })

    # Wait for approval
    await session["events"]["summary_approved"].wait()

    final_summary = session["hitl_data"].get("corrected_summary") or summary
    session["pitcher_name"] = pitcher_id or "our pitcher"
    session["pitch_summary"] = final_summary
    session["domain"] = domain_data

    # Panel Selection
    panel_mode = domain_data.get("panel_mode", "standard")
    if panel_mode == "design":
        active_panel = PANEL_AGENTS_DESIGN
    elif panel_mode in ["non_tech", "physical_product"]:
        active_panel = PANEL_AGENTS_NON_TECH
    else:
        active_panel = PANEL_AGENTS_STANDARD
    
    session["active_panel"] = active_panel
    session["conversation"] = []

    if pitcher_id:
        memory = load_pitcher_memory(pitcher_id)
        if memory:
            session["pitcher_memory"] = memory
            yield sse_event("returning_pitcher", {"memory": memory, "message": f"Welcome back. You pitched {memory.get('pitch_count')} times before."})

    yield sse_event("domain_classified", {**domain_data, "active_panel": active_panel})
    
    # Instead of running all agents at once, we move to the conversation orchestrator
    async for event in stream_notebooklm_conversation(session_id, session, provider, difficulty):
        yield event
        
    if pitcher_id:
        save_pitcher_memory(pitcher_id, session, session.get("verdict_final") or session.get("verdict", ""))

async def generate_rebuttal_response(session: dict, agent_id: str, agent_claim: str, user_text: str, provider: str) -> str:
    agent = AGENTS_CONFIG.get(agent_id, {"name": "Agent", "role": "Panelist"})
    
    # Initialize history if it doesn't exist
    if "rebuttals" not in session:
        session["rebuttals"] = {}
    if agent_id not in session["rebuttals"]:
        session["rebuttals"][agent_id] = []
        
    history = session["rebuttals"][agent_id]
    history_context = "\n".join([f"{'Pitcher' if m['role'] == 'user' else agent['name']}: {m['content']}" for m in history])
    
    PROMPT = f"""
    You are {agent['name']} ({agent['role']}). 
    You recently made this claim: "{agent_claim}"
    
    Current Sub-Conversation History:
    {history_context}
    
    The pitcher just said: "{user_text}"
    
    Your task:
    1. Respond naturally in your own voice.
    2. Stick to your specific perspective (Skeptical VC, Expert, etc.).
    3. Be brief — 1-2 sentences maximum.
    4. You can admit you were wrong if the evidence is sound, or double-down if you are unconvinced.
    
    If the user references something you do not recognise or that may not exist, respond honestly and simply. Say something like: 'I'm not familiar with that — could you tell me more about what it is?' Never be dismissive or sarcastic about it. Treat the gap as an opportunity to learn more from the pitcher, not as a mistake to call out.
    
    Output ONLY your response.
    """
    
    response = await llm_provider.generate_response(PROMPT, user_text, provider, stream=False)
    
    # Update history
    history.append({"role": "user", "content": user_text})
    history.append({"role": "agent", "content": response})
    
    return response

async def generate_fact_check(agent_id: str, agent_claim: str, challenge: str, provider: str) -> str:
    # We can reuse the same logic for one-shot challenges
    agent = AGENTS_CONFIG.get(agent_id, {"name": "Agent", "role": "Panelist"})
    PROMPT = f"You are {agent['name']} ({agent['role']}). You made this claim: {agent_claim}. Pitcher challenged: {challenge}. Respond in 2 sentences."
    return await llm_provider.generate_response(PROMPT, challenge, provider, stream=False)
