import json
import asyncio
import os
from typing import AsyncGenerator, Tuple, Dict, List, Optional
from prompts import (
    INTERVIEWER_SYSTEM_PROMPT,
    PERSONA_FOCUS_GROUP_PROMPT,
    CONFLICT_ROUTER_PROMPT,
    DEBATE_ENGINE_PROMPT,
    HALLUCINATION_GUARD_PROMPT,
    META_ANALYST_PROMPT,
    OCEAN_PROFILES,
    DIFFICULTY_MODIFIERS,
    PERSONA_ANCHORS,
    JUDGE_CONVERSATION_PROMPT
)
from services.llm import llm_provider
from graph import FocusGroupState, build_focus_group_graph

sessions: dict[str, dict] = {}

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
PANEL_AGENTS_DESIGN = ["design_critic", "dr_iyer_design", "meera_design", "expert", "vc"]
PANEL_AGENTS_NON_TECH = ["suresh", "hostile", "beginner", "vc", "enthusiastic"]

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
        elif t == "interviewer_question":
            lines.append(f"{name} asked: {content}")
        elif t == "persona_response":
            lines.append(f"{name}: {content}")
        elif t == "debate_interjection":
            lines.append(f"{name} interjected: {content}")
        elif t == "interviewer_invitation":
            lines.append(f"{name} invited: {content}")
        elif t == "pitcher_response":
            lines.append(f"Pitcher: {content}")
        elif t == "debate_question":
            directed = turn.get("directed_at_name", "Panel")
            lines.append(f"Debate Engine → {directed}: {content}")
        elif t == "pitcher_input":
            lines.append(f"Pitcher: {content}")
        elif t == "pitcher_message":
            lines.append(f"Pitcher (jumped in): {content}")
    
    return "\n".join(lines)

# --- V3 LANGGRAPH NODES ---

async def interviewer_node(state: FocusGroupState):
    """Lead Interviewer directs the focus group."""
    prompt = INTERVIEWER_SYSTEM_PROMPT
    
    # Identify which personas haven't spoken much or have specific biases
    transcript = build_conversation_context({"conversation": state["conversation"]})
    
    # Format difficulty instruction
    difficulty_instruction = DIFFICULTY_MODIFIERS.get(
        state["difficulty"], DIFFICULTY_MODIFIERS["standard"]
    )["question"]
    
    # NEW: Pass active panelists to the interviewer so it doesn't hallucinate names
    panelists_info = "\n".join([
        f"- {AGENTS_CONFIG[pid]['name']} ({AGENTS_CONFIG[pid]['role']})"
        for pid in state["domain"].get("active_panel", ["vc"])
    ])
    
    user_input = f"PITCH SUMMARY:\n{state['pitch_summary']}\n\nACTIVE PANELISTS:\n{panelists_info}\n\nCONVERSATION SO FAR:\n{transcript}\n\nDifficulty: {difficulty_instruction}"
    
    response = await llm_provider.generate_response(
        prompt, user_input, state["provider"], stream=False
    )
    
    # Parse directed_at and question
    directed_at = "vc" # Default
    question = response
    research_note = ""
    
    if "Directed at:" in response:
        try:
            directed_at_raw = response.split("Directed at:")[1].split("\n")[0].strip().lower()
            # Match with persona IDs
            for pid in state["domain"].get("active_panel", ["vc"]):
                if pid in directed_at_raw or AGENTS_CONFIG[pid]["name"].lower() in directed_at_raw:
                    directed_at = pid
                    break
            question = response.split("Question:")[1].split("Researcher note:")[0].strip()
            research_note = response.split("Researcher note:")[1].strip()
        except:
            pass

    new_turn = {
        "type": "interviewer_question",
        "agent_id": "interviewer",
        "agent_name": AGENTS_CONFIG.get("interviewer", {"name": "The Interviewer"})["name"],
        "content": question,
        "research_note": research_note,
        "directed_at": directed_at
    }
    
    active_panel = state.get("domain", {}).get("active_panel", ["vc", "hostile", "enthusiastic"])
    remaining_personas = [pid for pid in active_panel if pid != directed_at][:2]
    remaining_personas.insert(0, directed_at)

    return {
        "conversation": [new_turn],
        "current_question": question,
        "directed_at": directed_at,
        "turn_count": state.get("turn_count", 0) + 1,
        "should_invite_pitcher": (state.get("turn_count", 0) + 1) % 4 == 0,
        "remaining_personas": remaining_personas
    }

def map_ocean_to_behavior(profile: dict) -> str:
    behaviors = []
    openness = profile.get("openness", 0.5)
    agreeableness = profile.get("agreeableness", 0.5)
    neuroticism = profile.get("neuroticism", 0.5)
    
    if openness > 0.7:
        behaviors.append("explores ideas and speculates")
    elif openness < 0.3:
        behaviors.append("prefers proven ideas")
        
    if agreeableness < 0.3:
        behaviors.append("direct and confrontational")
    elif agreeableness > 0.7:
        behaviors.append("supportive and cooperative")
        
    if neuroticism > 0.7:
        behaviors.append("risk-sensitive and cautious")
    elif neuroticism < 0.3:
        behaviors.append("calm and confident")
        
    return ", ".join(behaviors) if behaviors else "neutral and analytical"

async def persona_response_node(state: FocusGroupState):
    """A persona responds to the interviewer or another persona."""
    session = sessions.get(state["session_id"], {})
    
    if session.get("force_end") or state.get("force_end"):
        return {"session_complete": True}
        
    if session.get("pitcher_interrupt") or state.get("pitcher_interrupt"):
        msg = session.get("pitcher_message", state.get("pitcher_message", ""))
        
        if "pitcher_interrupt" in session:
            session["pitcher_interrupt"] = False
            session["pitcher_message"] = ""
            
        new_turn = {
            "type": "pitcher_interrupt",
            "agent_name": "Pitcher",
            "content": msg
        }
        
        return {
            "conversation": [new_turn],
            "pitcher_interrupt": False,
            "pitcher_message": ""
        }
        
    remaining = state.get("remaining_personas", [])
    if remaining:
        agent_id = remaining[0]
        new_remaining = remaining[1:]
    else:
        agent_id = state.get("directed_at", "vc")
        new_remaining = []
        
    agent_config = AGENTS_CONFIG.get(agent_id, AGENTS_CONFIG.get("vc", {}))
    persona_anchor = PERSONA_ANCHORS.get(agent_id, "")
    ocean = OCEAN_PROFILES.get(agent_id, OCEAN_PROFILES.get("vc", {}))
    
    behavior_text = map_ocean_to_behavior(ocean)
    
    recent_discussion = "Recent panel discussion:\n"
    recent_turns = [t for t in state.get("conversation", []) if t.get("type") == "persona_response"][-3:]
    if recent_turns:
        for t in recent_turns:
            recent_discussion += f" {t.get('agent_name', 'Unknown')}: {t.get('content', '')}\n"
    else:
        recent_discussion += " No prior responses yet.\n"
    
    prompt = PERSONA_FOCUS_GROUP_PROMPT.format(
        persona_anchor=persona_anchor,
        behavior=behavior_text,
        core_bias=ocean.get("core_bias", ""),
        hidden_objection=ocean.get("hidden_objection", ""),
        episodic_memory=ocean.get("episodic_memory", ""),
        pitch_summary=state.get("pitch_summary", ""),
        question=state.get("current_question", ""),
        recent_discussion=recent_discussion,
        conversation_so_far=build_conversation_context({"conversation": state.get("conversation", [])}),
        difficulty_instruction=DIFFICULTY_MODIFIERS.get(state.get("difficulty", "standard"), DIFFICULTY_MODIFIERS["standard"])["reaction"]
    )
    
    response = await llm_provider.generate_response(
        "Respond as the persona.", prompt, state.get("provider", "gemini"), stream=False
    )
    
    new_turn = {
        "type": "persona_response",
        "agent_id": agent_id,
        "agent_name": agent_config.get("name", agent_id),
        "content": response
    }
    
    debate_rounds = state.get("debate_rounds", 0)
    if state.get("debate_rounds", 0) > 0 or state.get("conflict_detected"):
        debate_rounds += 1
        
    return {
        "conversation": [new_turn],
        "last_two_responses": (state.get("last_two_responses", []) + [new_turn])[-2:],
        "remaining_personas": new_remaining,
        "debate_rounds": debate_rounds
    }

async def conflict_router_node(state: FocusGroupState):
    """Analyzes recent responses for conflict."""
    if len(state["last_two_responses"]) < 2:
        return {"conflict_detected": False}
        
    prompt = CONFLICT_ROUTER_PROMPT.format(
        response_a_agent=state["last_two_responses"][0]["agent_name"],
        response_a=state["last_two_responses"][0]["content"],
        response_b_agent=state["last_two_responses"][1]["agent_name"],
        response_b=state["last_two_responses"][1]["content"]
    )
    
    try:
        raw = await llm_provider.generate_response(
            "Analyze conflict. JSON only.", prompt, state["provider"], stream=False
        )
        start = raw.find("{")
        end = raw.rfind("}") + 1
        result = json.loads(raw[start:end])
        
        return {
            "conflict_detected": result.get("conflict_detected", False),
            "conflict_topic": result.get("conflict_topic"),
            "debater_a": result.get("recommended_debaters", [None, None])[0],
            "debater_b": result.get("recommended_debaters", [None, None])[1]
        }
    except:
        return {"conflict_detected": False}

async def debate_engine_node(state: FocusGroupState):
    """Pits two personas against each other."""
    debater_a_id = state.get("debater_a") or "vc"
    debater_b_id = state.get("debater_b") or "hostile"
    
    last_two = state.get("last_two_responses", [])
    persona_a_name = last_two[0].get("agent_name")
    persona_a_response = last_two[0].get("content")
    persona_b_name = last_two[1].get("agent_name")
    persona_b_response = last_two[1].get("content")
    
    prompt = DEBATE_ENGINE_PROMPT.format(
        persona_a_name=persona_a_name,
        persona_a_response=persona_a_response,
        persona_b_name=persona_b_name,
        persona_b_response=persona_b_response,
        conflict_topic=state.get("conflict_topic", ""),
        pitch_summary=state.get("pitch_summary", ""),
        difficulty_instruction=DIFFICULTY_MODIFIERS.get(state.get("difficulty", "standard"), DIFFICULTY_MODIFIERS["standard"])["question"]
    )
    
    question = await llm_provider.generate_response(
        "Moderator: ask the debate question.", prompt, state.get("provider", "gemini"), stream=False
    )
    
    new_turn = {
        "type": "debate_interjection",
        "agent_id": "interviewer",
        "agent_name": AGENTS_CONFIG.get("interviewer", {"name": "The Interviewer"})["name"],
        "content": question
    }
    
    return {
        "conversation": [new_turn],
        "current_question": question,
        "directed_at": debater_a_id,
        "conflict_detected": False,
        "debate_rounds": 0
    }

async def hallucination_guard_node(state: FocusGroupState):
    """Fact-checks the last persona response."""
    last_turn = state["conversation"][-1]
    if last_turn["type"] != "persona_response":
        return {}
        
    prompt = HALLUCINATION_GUARD_PROMPT.format(
        agent_name=last_turn["agent_name"],
        claim=last_turn["content"],
        pitch_summary=state["pitch_summary"]
    )
    
    try:
        raw = await llm_provider.generate_response(
            "Fact-check. JSON only.", prompt, state["provider"], stream=False
        )
        start = raw.find("{")
        end = raw.rfind("}") + 1
        result = json.loads(raw[start:end])
        
        if result.get("flag", False):
            flag_entry = {
                "agent_name": last_turn["agent_name"],
                "content": last_turn["content"],
                "flag_reason": result.get("flag_reason"),
                "confidence": result.get("confidence")
            }
            return {"flagged_claims": [flag_entry]}
    except:
        pass
    return {}

async def invite_pitcher_node(state: FocusGroupState):
    """Invites the pitcher to respond."""
    new_turn = {
        "type": "interviewer_invitation",
        "agent_id": "interviewer",
        "agent_name": AGENTS_CONFIG["interviewer"]["name"],
        "content": "I'll pause here. What do you have to say to that?"
    }
    
    session_id = state["session_id"]
    if session_id in sessions:
        session = sessions[session_id]
        
        session["events"]["answer_event"].clear()
        await session["events"]["answer_event"].wait()
        
        answer = session["pending_answer"]
        session["pending_answer"] = ""
        
        pitcher_turn = {
            "type": "pitcher_response",
            "agent_name": "Pitcher",
            "content": answer
        }
        
        return {
            "conversation": [new_turn, pitcher_turn],
            "should_invite_pitcher": True
        }
        
    return {
        "conversation": [new_turn],
        "should_invite_pitcher": True 
    }

async def check_completion_node(state: FocusGroupState):
    """Checks if the session should end."""
    session = sessions.get(state["session_id"], {})
    if session.get("force_end") or state.get("force_end"):
        return {"session_complete": True}
        
    return {
        "session_complete": state["turn_count"] >= 12
    }

# --- ORCHESTRATOR ---

async def stream_echochamber(
    session_id: str,
    session: dict,
    provider: str,
    difficulty: str = "standard"
) -> AsyncGenerator[dict, None]:
    """
    EchoChamber-style LangGraph orchestrator.
    """
    # ── SETUP ────────────────────────────────────────
    # Initialize State
    initial_state: FocusGroupState = {
        "session_id": session_id,
        "pitch_summary": session["pitch_summary"],
        "domain": session["domain"],
        "difficulty": difficulty,
        "provider": provider,
        "conversation": [],
        "current_question": "",
        "directed_at": "",
        "turn_count": 0,
        "last_two_responses": [],
        "conflict_detected": False,
        "conflict_topic": "",
        "debater_a": "",
        "debater_b": "",
        "pitcher_message_pending": False,
        "pitcher_message": "",
        "should_invite_pitcher": False,
        "session_complete": False,
        "flagged_claims": []
    }
    
    # Update session object
    session["exchange_count"] = 0
    session.setdefault("flagged_claims", [])
    
    yield sse_event("echochamber_start", {
        "personas": [
            {"id": pid, "name": AGENTS_CONFIG.get(pid, {}).get("name", pid)} 
            for pid in session.get("active_panel", [])
        ],
        "session_id": session_id
    })

    # Compile Graph
    graph = build_focus_group_graph(
        interviewer_node,
        persona_response_node,
        conflict_router_node,
        debate_engine_node,
        invite_pitcher_node,
        hallucination_guard_node,
        check_completion_node
    )
    
    # ── GRAPH EXECUTION ──────────────────────────────
    async for event in graph.astream(initial_state):
        # LangGraph 'astream' yields dicts like {'node_name': state_update}
        node_name = list(event.keys())[0]
        update = event[node_name]
        
        if not update:
            continue
            
        # Merge update into our local session for persistence/reference
        if "conversation" in update:
            for turn in update["conversation"]:
                # Stream the new turn
                yield sse_event("agent_turn", turn)
                session["conversation"].append(turn)
                
        if "flagged_claims" in update:
            for fc in update["flagged_claims"]:
                yield sse_event("claim_flagged", fc)
                session["flagged_claims"].append(fc)
        
        # Handle intervention invitation
        if update.get("should_invite_pitcher"):
            # Wait block moved to invite_pitcher_node
            # We still yield waiting state before the node blocks. Wait, the node already yielded?
            # LangGraph astream yields update AFTER the node returns.
            # So the wait happened inside the node. We just send a sync here if needed, but 
            # the next node will emit the conversation update with the pitcher response.
            pass
            
        await asyncio.sleep(0.5) # Pacing
        
    # ── COMPLETION ───────────────────────────────────
    yield sse_event("echochamber_complete", {
        "session_id": session_id
    })
    
    async for event in stream_meta_analysis(session_id, session, provider):
        yield event

async def stream_meta_analysis(session_id: str, session: dict, provider: str):
    """Produces the Black Swan Report."""
    yield sse_event("status", {"message": "Meta-Analyst is uncovering non-obvious insights...", "phase": "meta_analysis"})
    
    transcript = build_conversation_context(session)
    prompt = META_ANALYST_PROMPT.format(
        pitch_summary=session["pitch_summary"],
        conversation_transcript=transcript,
        domain=session["domain"].get("sub_domain", "general")
    )
    
    full_report_json = ""
    try:
        raw = await llm_provider.generate_response(
            "You are a Meta-Analyst. JSON only.", prompt, provider, stream=False
        )
        start = raw.find("{")
        end = raw.rfind("}") + 1
        full_report_json = raw[start:end]
        report = json.loads(full_report_json)
        
        session["black_swan"] = report
        yield sse_event("black_swan_report", report)
    except Exception as e:
        yield sse_event("error", {"message": f"Meta-analysis failed: {str(e)}"})
    
    # Generate Key Insights
    sys_prompt = "You are an expert analyst. Extract exactly 3 key insights from the panel discussion. Focus on: repeated concerns, strongest validation, major objections. Return exactly 3 short bullet points starting with a bullet character (•)."
    try:
        insights_raw = await llm_provider.generate_response(
            sys_prompt, transcript, provider, stream=False
        )
        session["key_insights"] = [i.strip() for i in insights_raw.split('\\n') if i.strip()]
    except Exception:
        session["key_insights"] = ["No insights available."]
    
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
    "vc": {
        "name": "Arjun Mehta", 
        "role": "Skeptical VC",
        "system_prompt": """You are Arjun Mehta, 41, a Partner at 
an early-stage venture fund in Bengaluru.
You have 12 years in venture capital and 
have evaluated over 400 startup pitches.
You have invested in 22 companies.
You are intellectually rigorous, direct, 
and slightly impatient.
You are not mean but you are never soft.

EVALUATION PRIORITIES (in this order):
1. Market size — vitamin or painkiller? 
   TAM above $500M with a credible source?
2. Defensibility — what is the moat? 
   Why can't a competitor copy in 6 months?
3. Traction — has anyone paid for this?
   One paying stranger beats 10,000 signups.

VOICE RULES:
- Medium-length responses. No bullet points.
- Use em-dashes for asides — like this.
- Never say great idea or interesting concept.
- Always end with one sharp question.
- Reference real companies as comparisons.

RED LINES — always challenge these:
- No competition claim: name a competitor.
- Huge market claim: demand a number.
- AI-powered X pitch: ask what job it does.
- Everyone as target: demand first 10 
  paying customers by name.

FOCUS GROUP BEHAVIOR:
You are in a structured panel interview.\nThe Lead Strategist will direct questions \nat you by name. When asked, respond in \n2-3 sentences from your perspective only.\nIf another persona said something in the \nlast few turns that you agree or disagree \nwith, reference them by name.\nDo not give a speech. Make your point \nand let the conversation move.\nYour OCEAN profile: high conscientiousness,\nlow agreeableness. This means you are \nprecise and direct, not warm or agreeable.\nYour hidden objection surfaces when you \nhear vague claims about market size, \nviral growth, or lack of competition.\nWhen you hear these, challenge immediately."""
    },
    "enthusiastic": {
        "name": "Priya Sharma", 
        "role": "Product Manager",
        "system_prompt": """You are Priya Sharma, 24, Product Manager 
at a mid-size tech company in Mumbai.
You are an early adopter who loves finding 
tools that solve real problems.
You have 40+ apps on your phone.
You pay for 6 SaaS subscriptions.
You are enthusiastic but not naive.
Your enthusiasm is earned, not given.

EVALUATION PRIORITIES (in this order):
1. Do I personally have this problem?
2. Can I set this up in under 5 minutes?
3. Does it respect my time?

VOICE RULES:
- First person always. I would use this...
- Reference your own life specifically.
- Warm when something genuinely excites you.
- 3-4 sentences. You are busy.
- No jargon. No TAM, moat, ICP.

RED LINES — always challenge these:
- Simple and easy with complex flow: 
  call out the contradiction.
- If you don't feel the pain: say so.
- Significant behavior change required: 
  flag as adoption risk.

FOCUS GROUP BEHAVIOR:
You are in a structured panel interview. \nRespond in 2-3 sentences from your \npersonal lived experience.\nReference your own daily life specifically.\nWhen Ravi is being too pessimistic about \nsomething you genuinely believe in, \npush back by name and say why.\nYour OCEAN profile: high openness, \nhigh extraversion. You speak warmly \nand specifically about your own life.\nYour hidden objection surfaces when you \nhear the solution requires significant \nbehavior change or complex onboarding."""
    },
    "hostile": {
        "name": "Ravi Kumar", 
        "role": "Ops Manager",
        "system_prompt": """You are Ravi Kumar, 38, Operations Manager 
at a manufacturing company in Pune.
You have 15 years managing teams.
You use WhatsApp and Excel.
You have been burned by 3 software 
implementations that overpromised.
You are not stupid. You need proof.

EVALUATION PRIORITIES (in this order):
1. Does the current way work fine?
2. What happens when it fails?
3. Who is responsible when it goes wrong?

VOICE RULES:
- Short sentences. Maximum 3. Never more.
- Start objections with Look,
- Reference your own bad experiences.
- No startup language. Ever.
- You are honest. Not mean.

RED LINES — always challenge these:
- App replacing human contact: 
  my parents want a call not an app.
- Assuming reliable internet: raise this.
- Expensive subscription for simple problem:
  compare to free alternative.
- Health or personal data: be suspicious.

FOCUS GROUP BEHAVIOR:
You are in a structured panel interview.\nMaximum 3 sentences. Start with Look,\nYou are the person who asks what everyone\nis thinking but won't say.\nWhen Priya gets enthusiastic, you are \noften the counterweight — not to be \nnegative, but because someone has to \nask what happens when it breaks.\nYour OCEAN profile: low agreeableness,\nhigh neuroticism. You are terse and \nskeptical. You need proof.\nYour hidden objection surfaces when you \nhear easy, seamless, or just works."""
    },
    "expert": {
        "name": "Dr. Ananya Iyer", 
        "role": "Industry Consultant",
        "system_prompt": """You are Dr. Ananya Iyer, 36, Associate 
Professor and industry consultant.
Your domain shifts to match the pitch:
- Health → public health researcher
- Finance → behavioral economist
- Education → learning sciences researcher
- Tech → HCI researcher
- Other → most relevant field expert
You have 10 years research experience.
You have read the papers they haven't.

EVALUATION PRIORITIES (in this order):
1. Technical accuracy — is the claim true?
2. Prior art — has this been tried? Name it.
3. Regulatory landscape — what rules apply?

VOICE RULES:
- Academic precision, plain English.
- Always cite one real specific reference.
- If you cannot cite real, say so — never 
  invent a prior attempt.
- 3-4 sentences.
- Never say interesting as filler.

RED LINES — always challenge these:
- First ever claim: name a prior attempt.
- Regulatory underestimation: flag it.
- Statistics without source: challenge them.
- Oversimplification: flag and offer path.

FOCUS GROUP BEHAVIOR:
You are in a structured panel interview.\nRespond in 3-4 sentences with precision.\nAlways cite at least one real specific \nreference — a study, a company, a paper.\nIf you cannot cite a real one, say \nI am not aware of a specific prior attempt \nrather than inventing one.\nWhen someone makes a statistic claim, \nyou are the person who checks it.\nYour OCEAN profile: very high \nconscientiousness, accuracy-biased.\nYour hidden objection surfaces when you \nhear studies show or research proves \nwithout a source."""
    },
    "competitor": {
        "name": "Meera Pillai", 
        "role": "Marketing Manager",
        "system_prompt": """You are Meera Pillai, 31, Marketing Manager
at an e-commerce company in Chennai.
You use 8-10 tools every day.
You already use a competitor product for 
whatever the pitcher is describing.
You will name it and speak as its user.

EVALUATION PRIORITIES (in this order):
1. Does this do something my tool cannot?
   Not marginally — meaningfully different.
2. What is the switching cost?
3. Will this company exist in 2 years?

VOICE RULES:
- Always name your current tool first.
- Use my current tool already does this.
- Speak in value and switching cost terms.
- 3-4 sentences. Direct. No hedging.

RED LINES — always challenge these:
- Novelty claims: name existing feature.
- Better UX as main differentiator: 
  ask for specific better interaction.
- No pricing mentioned: always ask cost.

FOCUS GROUP BEHAVIOR:
You are in a structured panel interview.\nAlways name a specific tool you use.\n3-4 sentences. Direct. \nYour most important contribution in \nany session is naming the competitor \nthe pitcher forgot to mention.\nWhen someone claims something is unique, \nyou are the one who says actually \n[competitor] already does this.\nYour OCEAN profile: high \nconscientiousness, moderate agreeableness.\nYour hidden objection surfaces when you \nhear replaces, all-in-one, or migrate."""
    },
    "beginner": {
        "name": "Kiran", 
        "role": "Student",
        "system_prompt": """You are Kiran, 19, second-year engineering
student at a tier-3 college in a small city.
You use Instagram, YouTube, and WhatsApp.
You have never paid for an app.
You do not know what SaaS, TAM, MVP mean.
You are not stupid. Different world.

EVALUATION PRIORITIES (in this order):
1. Can I explain this in one sentence?
2. Is it free?
3. Does it work on basic Android?

VOICE RULES:
- Informal. Maximum 3 sentences.
- Use bhai or yaar naturally, not forced.
- If you don't understand a word: ask.
- Not embarrassed to be confused.

RED LINES — always flag these:
- Jargon: what does that mean?
- Payment requirement: is this free?
- Complex setup: how many steps?
- Not for me: is this even for someone 
  like me?

FOCUS GROUP BEHAVIOR:
You are in a structured panel interview.\nMaximum 3 sentences. Informal.\nUse bhai or yaarc occasionally, naturally.\nYou are the clarity test for the panel.\nWhen you do not understand something,\nsay so immediately and simply.\nWhen something sounds expensive, say so.\nYour OCEAN profile: high openness,\nhigh agreeableness, simplicity-biased. \nYour hidden objection surfaces when you \nhear subscription, premium, or upgrade."""
    },
    "suresh": {
        "name": "Suresh Nair", 
        "role": "Shop Owner",
        "system_prompt": """You are Suresh Nair, 52, owner of 4 
medical stores in Kerala for 22 years.
You have seen businesses succeed and fail.
You do not care about vision or ambition.
You care about: does this work on the ground?

EVALUATION PRIORITIES (in this order):
1. Unit economics — profit per unit 
   after every cost?
2. Operations — who does the work at 7am?
3. Working capital — cash before revenue?

VOICE RULES:
- Short sentences. Maximum 4.
- Say in my experience when referencing 
  your own business.
- Use specific rupee amounts.
- Never use startup language.

RED LINES — always raise these:
- No unit economics: ask for breakdown.
- Staff will handle it: ask who specifically.
- Ignores working capital: ask months 
  they can survive with zero revenue.

FOCUS GROUP BEHAVIOR:
You are in a structured panel interview.\nMaximum 4 sentences. \nSay in my experience when you draw on \nyour 22 years of running a business.\nUse specific rupee amounts when comparing.\nYou ask the operational questions nobody \nelse thinks to ask.\nYour OCEAN profile: very high \nconscientiousness, low openness.\nYou are pragmatic and number-focused.\nYour hidden objection surfaces when you \nhear scale, automate, or runs itself."""
    },
    "design_critic": {
        "name": "Aisha Thomas", 
        "role": "Design Strategist",
        "system_prompt": "You are Aisha Thomas, an high-end aesthetic critic.\nFOCUS GROUP BEHAVIOR:\nYou bring the aesthetic \nand usability lens nobody else has. \nIf an image has been uploaded you comment \non specific visual elements you can see. \nIf no image exists, ask what the design \nlanguage is before giving any opinion."
    },
    "dr_iyer_design": {
        "name": "Dr. Ananya Iyer (Design)", 
        "role": "Technical Design Critic",
        "system_prompt": "You are Dr. Ananya Iyer in design mode.\nYou evaluate the actual visual work — not \nthe pitch, the work. You look for whether \ndesign choices are intentional or accidental, \nculturally appropriate for the Indian market, \nand technically sound for production. \nCRITICAL: Only reference real design movements, \nreal brands, real designers. Never invent \na reference. \nIn this focus group your question references \nsomething specific you can see or infer \nabout the design itself."
    },
    "meera_design": {
        "name": "Meera Pillai (Design)", 
        "role": "Design Client",
        "system_prompt": "You are Meera Pillai evaluating a designer \nas a potential hire for a brand project.\nYou have a budget of 80,000 to 1,50,000 \nrupees. One previous freelancer was excellent. \nOne vanished after the advance payment. \nYou are professionally cautious. \nIn this focus group you ask client questions \nnot critic questions — can I trust this \nperson with my CEO's first impression, \nwhat does this cost, how many revisions, \nwhat file formats do I get."
    },
    "interviewer": {
        "name": "Claude (Interviewer)", 
        "role": "Lead Strategist",
        "system_prompt": "You are the Lead Strategist running a focus group."
    }
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
    async for event in stream_echochamber(session_id, session, provider, difficulty):
        yield event
        
    if pitcher_id:
        report = session.get("black_swan", {})
        summary_verdict = report.get("one_line_summary", "")
        save_pitcher_memory(pitcher_id, session, summary_verdict)

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
