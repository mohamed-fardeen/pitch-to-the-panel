import json
import asyncio
import os
from typing import AsyncGenerator, Tuple, Dict, List, Optional
from prompts import (
    CONTROLLER_PROMPT,
    REFLECTION_PROMPT,
    PERSONA_PROMPT,
    PITCH_REFINER_PROMPT,
    FINAL_ANALYST_PROMPT,
    BLACK_SWAN_PROMPT,
    OCEAN_PROFILES,
    PERSONA_ANCHORS,
    BASE_SYSTEM_PROMPT,
    MODE_PROMPTS,
    MODE_INSTRUCTIONS,
    MEMORY_UPDATE_PROMPT,
    extract_json,
    JUDGE_CONVERSATION_PROMPT,
    SEARCH_TOOL_PROMPT,
    FACT_CHECK_PROMPT
)

AGENTS_CONFIG = {
    "vc": {
        "name": "Arjun Mehta",
        "role": "Venture Capitalist",
        "system_prompt": "Senior analyst at Elevation Capital. Focus on TAM, moats, and Series A readiness."
    },
    "enthusiastic": {
        "name": "Priya Sharma",
        "role": "Product Manager",
        "system_prompt": "Ex-meta PM. Focus on user adoption, emotional resonance, and viral loops."
    },
    "hostile": {
        "name": "Ravi Kumar",
        "role": "Operations Manager",
        "system_prompt": "Jaded logistics expert. Focus on burn rate, operational inefficiencies, and 'real world' failure points."
    },
    "expert": {
        "name": "Dr. Ananya Iyer",
        "role": "Industry Consultant",
        "system_prompt": "Academic rigor. Focus on technical feasibility, research backing, and long-term defensibility."
    },
    "competitor": {
        "name": "Meera Pillai",
        "role": "Marketing Manager",
        "system_prompt": "Aggressive growth hacker. Focus on switching costs, acquisition cost, and competitive landscape."
    },
    "beginner": {
        "name": "Kiran",
        "role": "Student",
        "system_prompt": "Target consumer. Focus on simplicity, clarity, and 'why would I use this?'"
    },
    "suresh": {
        "name": "Suresh Nair",
        "role": "Medical Store Owner",
        "system_prompt": "Ground-level entrepreneur. Focus on unit economics and practical everyday utility."
    },
    "design_critic": {
        "name": "Aisha Thomas",
        "role": "Design Strategist",
        "system_prompt": "UX purist. Focus on trust, interface psychology, and brand storytelling."
    },
    "dr_iyer_design": {
        "name": "Dr. Ananya Iyer (Design)",
        "role": "Technical Design Critic",
        "system_prompt": "Academic precision in UI/UX and product psychology."
    },
    "meera_design": {
        "name": "Meera Pillai (Design)",
        "role": "Design Client",
        "system_prompt": "Customer-first design requirements and budget management."
    },
    "interviewer": {
        "name": "Lead Strategist",
        "role": "Lead Strategist",
        "system_prompt": "You are the Lead Strategist running a focus group."
    }
}

# FIXED: Removed duplicate AGENTS_CONFIG and redundant prompts import
from services.llm import llm_provider
from graph import FocusGroupState, build_agentic_graph
from pydantic import BaseModel, validator
from typing import Literal, Optional, AsyncGenerator, Tuple, Dict, List, Annotated
import operator

AGENT_GOALS = {
    "vc":           "Identify scalable business potential and market size. Demand traction, moats and unit economics.",
    "enthusiastic": "Explore user excitement and viral potential. Champion the emotional hook.",
    "hostile":      "Expose risks, inefficiencies, and realistic failure points. Assume it will break.",
    "expert":       "Validate technical feasibility and long-term defensibility with academic rigor.",
    "competitor":   "Analyze competitive threats, switching costs, and strategic positioning.",
    "beginner":     "Check clarity and usability for normal everyday users. Speak for the confused.",
    "suresh":       "Evaluate practical real-world viability and unit economics at ground level.",
    "design_critic":"Assess trust signals, UX psychology, and emotional brand connection.",
    "dr_iyer_design": "Critique product-design precision, cognitive load, and technical UX rigor.",
    "meera_design": "Represent client expectations, budget constraints, and design ROI.",
    "interviewer":  "Guide the session with strategic questions. Surface hidden assumptions."
}

class ControllerDecision(BaseModel):
    action: Literal["ask_persona", "ask_pitcher", "use_tool", "reflect", "end_session"]
    target: Optional[str] = "vc"
    input: dict = {}
    reason: Optional[str] = ""

    @validator("input", always=True)
    def ensure_input_dict(cls, v):
        return v if isinstance(v, dict) else {}


sessions: dict[str, dict] = {}
    
def handle_interrupt_if_present(state: FocusGroupState, session: dict) -> dict | None:
    """
    Checks both state and session for a live pitcher interrupt.
    If found, clears the flag everywhere and returns the interrupt turn dict.
    If not found, returns None — caller should continue normally.
    """
    pitcher_interrupt = state.get("pitcher_interrupt") or session.get("pitcher_interrupt", False)
    if not pitcher_interrupt:
        return None
    
    msg = state.get("pitcher_message", "") or session.get("pitcher_message", "")
    
    # Clear from session
    if "pitcher_interrupt" in session:
        session["pitcher_interrupt"] = False
        session["pitcher_message"] = ""
    
    new_turn = {
        "type": "pitcher_response", # Standardized (Issue 5)
        "agent_name": "Pitcher",
        "content": msg
    }
    
    print(f"[INTERRUPT] pitcher jumped in: '{msg[:80]}'")
    return {
        "conversation": [new_turn],
        "pitcher_interrupt": False,
        "pitcher_message": "",
        "awaiting_user_input": False,
        "input_type": "pitcher_response" # FIXED: Standardized type
    }

# Feature 4: Firecrawl MCP Setup
try:
    from tavily import TavilyClient
    tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY")) if os.getenv("TAVILY_API_KEY") else None
except ImportError:
    tavily_client = None
except Exception:
    tavily_client = None

async def search_competitors(domain_info: dict) -> str:
    if not tavily_client: return ""
    query = f"{domain_info.get('sub_domain', '')} competitors India 2026 pricing"
    try:
        # Run synchronous operation in an executor thread
        results = await asyncio.to_thread(tavily_client.search, query=query, max_results=3)
        competitor_context = "LIVE COMPETITOR RESEARCH (searched just now):\n"
        for r in results.get("results", []):
            competitor_context += f"- {r.get('title', '')}: {r.get('content', '')}\n"
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

async def safe_wait(event, timeout=10.0):
    """Wait for an event with a timeout fallback."""
    try:
        if not event.is_set():
            await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        print(f"[TIMEOUT] safe_wait exceeded {timeout}s. Continuing automatically.")
    finally:
        event.clear()

def build_conversation_context(session: dict, last_n: int = None) -> str:
    """
    Build a readable transcript of the conversation so far.
    If last_n is set, only includes the last N turns.
    """
    conversation = session.get("conversation", [])
    if not conversation:
        return "No exchanges yet."
    
    # Trim to last N turns if specified
    if last_n is not None:
        conversation = conversation[-last_n:]
    
    lines = []
    for turn in conversation:
        t = turn["type"]
        name = turn.get("agent_name", "Unknown")
        content = turn.get("content", "")

        if t == "question":
            lines.append(f"{name} asked: {content}")
        elif t == "pitcher_response": # FIXED: Standardized type (removed 'answer')
            lines.append(f"Pitcher: {content}")
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
        elif t == "debate_question":
            lines.append(f"{name} asked: {content}")
        elif t == "tool_output":
            lines.append(f"{name}: {content}")
    
    return "\n".join(lines)

def map_ocean_to_behavior(profile: dict) -> str:
    behaviors = []
    openness = profile.get("openness", 0.5)
    conscientiousness = profile.get("conscientiousness", 0.5)
    extraversion = profile.get("extraversion", 0.5)
    agreeableness = profile.get("agreeableness", 0.5)
    neuroticism = profile.get("neuroticism", 0.5)
    
    if openness > 0.7: behaviors.append("explores ideas and speculates")
    elif openness < 0.3: behaviors.append("prefers proven ideas")
        
    if conscientiousness > 0.7: behaviors.append("methodical and detail-oriented")
    elif conscientiousness < 0.3: behaviors.append("spontaneous and flexible")

    if extraversion > 0.7: behaviors.append("vocal and energetic")
    elif extraversion < 0.3: behaviors.append("quiet and observant")

    if agreeableness < 0.3: behaviors.append("direct and confrontational")
    elif agreeableness > 0.7: behaviors.append("supportive and cooperative")
        
    if neuroticism > 0.7: behaviors.append("risk-sensitive and cautious")
    elif neuroticism < 0.3: behaviors.append("calm and confident")
        
    return ", ".join(behaviors) if behaviors else "neutral and analytical"

# --- AGENTIC V4 NODES ---

async def pitch_refiner_node(state: FocusGroupState):
    """Refines the initial pitch for better analysis."""
    # Check for interrupt
    if state.get("pitcher_interrupt"):
        return {"pitcher_interrupt": False}
    if state.get("awaiting_pitch_confirmation"):
        session = sessions.get(state["session_id"])
        if session:
            # FIXED: Add timeout fallback for demo safety (Fix 2)
            event = session["events"]["summary_approved"]
            try:
                await asyncio.wait_for(event.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                print("[TIMEOUT] Auto-approving summary")
            
            event.clear()
            
            approved_summary = session.get("hitl_data", {}).get("corrected_summary")
            if approved_summary:
                state["pitch_summary"] = approved_summary
                session["pitch_summary"] = approved_summary
            else:
                state["pitch_summary"] = session["pitch_summary"]

        return {
            "pitch_summary": state["pitch_summary"],
            "awaiting_pitch_confirmation": False,
            "input_type": ""
        }

    mode = state.get("mode", "venture")
    foci = {
        "spark": "novelty, emotional resonance, vision",
        "venture": "tam, moat, unit economics",
        "reality": "operational risks, logistics, scale"
    }
    prompt = PITCH_REFINER_PROMPT.format(
        mode=mode,
        pitch=state['pitch_summary'],
        focus=foci.get(mode, "clarity, value prop")
    )
    
    refined = await llm_provider.generate_response(
        "You are a professional startup pitch editor.", prompt, state["provider"], stream=False
    )
    
    session = sessions.get(state["session_id"])
    if session:
        if "hitl_data" not in session: session["hitl_data"] = {}
        session["hitl_data"]["summary"] = refined
        session["refined_pitch"] = refined
        session["events"]["summary_approved"].clear()
    
    return {
        "refined_pitch": refined,
        "awaiting_pitch_confirmation": True
    }

async def controller_node(state: FocusGroupState):
    """The central brain that decides the next action."""
    session = sessions.get(state["session_id"], {})
    
    interrupt_result = handle_interrupt_if_present(state, session)
    if interrupt_result:
        return interrupt_result
    mode = state.get("mode", "venture")
    state_updates = {}

    # FIX 1: DEFINE missing variables in controller_node
    active_panel   = session.get("active_panel", [])
    if not active_panel:
        raise ValueError("Critical Error: active_panel is empty.") # FIX 6: Safety check

    reflection     = state.get("reflection", {})
    global_mem     = state.get("memory", {})
    last_used      = state.get("last_persona_used", "")
    action_history = state.get("action_history", [])
    max_steps      = state.get("max_steps", 20)
    current_step   = state.get("step_count", 0) # FIX 3: Centralized step increment
    next_step      = current_step + 1

    def _ctrl_return(action, action_input=None, **extra):
        """Helper: build a deterministic controller return dict."""
        result = {
            "action": action,
            "action_input": action_input or {},
            "action_history": [action],
            "step_count": next_step,
        }
        result.update(extra)
        print(f"[CONTROLLER RULE] {action} → {(action_input or {}).get('target', '-')}")
        return result

    # ══════════════════════════════════════════════
    # HARD RULE LAYER  (evaluated top-to-bottom)
    # ══════════════════════════════════════════════

    # RULE 0: Force first 2 steps (Deterministic start - Fix 4)
    if current_step < 2:
        next_agent = active_panel[current_step % len(active_panel)]
        return _ctrl_return("ask_persona", {"target": next_agent})

    # RULE 1: max_steps exceeded
    if current_step >= max_steps:
        return _ctrl_return("end_session")

    # RULE 2: Reflection says stop with high confidence
    if not reflection.get("should_continue", True) and reflection.get("confidence", 0.0) >= 0.8:
        return _ctrl_return("end_session")

    # RULE 3: Missing info in reflection → ask_pitcher (except spark mode)
    missing = reflection.get("missing", [])
    if missing and mode != "spark":
        q = f"Clarify: {missing[0]}"
        return _ctrl_return("ask_pitcher", {"question": q, "target": "interviewer"})

    # RULE 4: Too many consecutive persona turns without a reflection
    recent_actions = action_history[-5:]
    if sum(1 for a in recent_actions if a == "ask_persona") >= 4:
        return _ctrl_return("reflect")

    # RULE 5: reality mode + zero risks identified → force hostile/suresh first
    if mode == "reality" and not global_mem.get("risks"):
        force_p = "hostile" if "hostile" in active_panel else ("suresh" if "suresh" in active_panel else active_panel[0])
        if force_p != last_used:
            return _ctrl_return("ask_persona", {"target": force_p})

    # FIX 6: REMOVE DEAD remaining_personas logic (redundant Rule 6/7)

    # RULE 7: Same persona about to repeat → rotate
    next_candidate = active_panel[0]
    if last_used in active_panel:
        idx = active_panel.index(last_used)
        next_candidate = active_panel[(idx + 1) % len(active_panel)]

    if next_candidate == last_used and len(active_panel) > 1:
        idx = active_panel.index(last_used)
        next_candidate = active_panel[(idx + 1) % len(active_panel)]
        return _ctrl_return("ask_persona", {"target": next_candidate})

    # PART 4 — Reflection next_priority → inject as query context
    next_priority = reflection.get("next_priority", "")

    # FIX 7: PRIORITIZE reflection.next_priority (Move before memory rules)
    if next_priority:
        # Determine next candidate for the priority route
        if last_used in active_panel:
            idx = active_panel.index(last_used)
            nc = active_panel[(idx + 1) % len(active_panel)]
        else:
            nc = active_panel[0]
            
        return _ctrl_return(
            "ask_persona",
            {
                "target": nc,
                "priority_context": next_priority
            }
        )

    # FIX 6: USE opinions IN CONTROLLER (Reflection triggered by discussion density)
    opinions = global_mem.get("opinions", [])
    if len(opinions) > 5:
        return _ctrl_return("reflect")

    # FIX 10: AGENT INTERRUPTION (Agents feel alive - Fix 8: Memory-driven)
    if current_step > 0 and len(global_mem.get("risks", [])) >= 2:
        if last_used in active_panel:
            idx = active_panel.index(last_used)
            nc = active_panel[(idx + 1) % len(active_panel)]
        else:
            nc = active_panel[0]
            
        return _ctrl_return(
            "ask_persona",
            {"target": nc, "interrupt": True}
        )

    # ═══════════════════════════════════════════════════════════
    # PRE-LLM DETERMINISTIC ROUTING (Fixes 3-7)
    # ═══════════════════════════════════════════════════════════

    # FIX 6: Round-robin — always derive next from active_panel index
    covered = global_mem.get("covered_topics", [])
    if last_used in active_panel:
        idx = active_panel.index(last_used)
        step_offset = 2 if len(covered) > 5 else 1  # FIX 7: skip ahead when topics exhausted
        next_candidate = active_panel[(idx + step_offset) % len(active_panel)]
    else:
        next_candidate = active_panel[0]

    # FIX 4a: Many risks accumulated → force hostile analysis
    if len(global_mem.get("risks", [])) >= 3 and mode != "spark":
        force_agent = "hostile" if "hostile" in active_panel else active_panel[0]
        if force_agent != last_used:
            return _ctrl_return("ask_persona", {"target": force_agent})

    # FIX 4b: Strong strengths → let VC weigh in
    if len(global_mem.get("strengths", [])) >= 3 and "vc" in active_panel and last_used != "vc":
        return _ctrl_return("ask_persona", {"target": "vc"})

    # FIX 3: Skip LLM for routine rotation (let LLM in every 3rd step for variety)
    import random
    current_step = state.get("step_count", 0)
    context = build_conversation_context({"conversation": state.get("conversation", [])}, last_n=10)
    history_str = ", ".join(state.get("action_history", [])[-5:])

    # FIX 3: Dynamic routing probability
    if next_candidate and next_candidate != last_used and random.random() > 0.3:
        return _ctrl_return("ask_persona", {"target": next_candidate})

    formatted_prompt = CONTROLLER_PROMPT.format(
        mode=mode,
        mode_goal=MODE_INSTRUCTIONS.get(mode, "Standard evaluation."),
        last_persona_used=state.get("last_persona_used", "none"),
        action_history=history_str,
        context=context,
        memory=json.dumps(state.get("memory", {})),
        reflection=json.dumps(state.get("reflection", {})),
        input_type=state.get("input_type", ""),
        step_count=current_step
    )

    try:
        response = await llm_provider.generate_response(
            formatted_prompt, "Decide the next action.", state["provider"], stream=False
        )
        decision_data = extract_json(response)

        # ── Post-LLM guardrails (lighter — hard rules already fired above) ──

        # Validate/fix target persona
        if decision_data.get("action") == "ask_persona":
            t = decision_data.get("target")
            if t not in active_panel or t == last_used:
                idx = active_panel.index(last_used) if last_used in active_panel else -1
                decision_data["target"] = active_panel[(idx + 1) % len(active_panel)]

        # Restrict ask_pitcher by mode frequency
        if decision_data.get("action") == "ask_pitcher":
            freq = 6 if mode == "spark" else (3 if mode == "reality" else 4)
            if not missing and current_step % freq != 0:
                idx = active_panel.index(last_used) if last_used in active_panel else -1
                decision_data = {"action": "ask_persona", "target": active_panel[(idx + 1) % len(active_panel)]}

        # Mode-based tool restrictions
        if decision_data.get("action") == "use_tool":
            tool = (decision_data.get("input") or {}).get("tool", "search")
            if mode == "spark":
                idx = active_panel.index(last_used) if last_used in active_panel else -1
                decision_data = {"action": "ask_persona", "target": active_panel[(idx + 1) % len(active_panel)], "reason": "spark suppresses tools"}
            elif mode == "reality" and tool != "fact_check":
                if not decision_data.get("input"): decision_data["input"] = {}
                decision_data["input"]["tool"] = "fact_check"

        # Inject next_priority as query context if available
        if next_priority and decision_data.get("action") in ["ask_persona", "ask_pitcher"]:
            decision_data.setdefault("input", {})
            decision_data["input"]["priority_context"] = next_priority

        # Pydantic validation
        decision = ControllerDecision(**decision_data)
        action   = decision.action
        persona_id = decision.target

        action_input = decision.input or {}
        action_input["target"] = persona_id

        if decision.reason:
            print(f"[CONTROLLER LOG] {action} → {persona_id} | {decision.reason}")
        
        print(f"[CONTROLLER ACTION] {action}")
        print(f"[STEP] {current_step}")

        if action == "ask_pitcher":
            action_input["question"] = action_input.get("question", action_input.get("query", "Can you clarify your previous point?"))

        state_updates.update({
            "action": action,
            "action_input": action_input,
            "action_history": [action],
            "step_count": next_step
        })
        return state_updates

    except Exception as e:
        print(f"[CONTROLLER ERROR] Fallback engaged: {e}")
        fallback_personas = session.get("active_panel", []) # FIXED
        last_used = state.get("last_persona_used", "")
        try:
            last_idx = fallback_personas.index(last_used)
        except ValueError:
            last_idx = -1
            
        next_persona = fallback_personas[(last_idx + 1) % len(fallback_personas)]
        fallback_update = {
            "action": "ask_persona",
            "action_input": {"target": next_persona},
            "action_history": ["ask_persona"],
            "step_count": next_step
        }
        fallback_update.update(state_updates)
        return fallback_update

async def persona_node(state: FocusGroupState):
    """Executes a single persona response."""
    session = sessions.get(state["session_id"], {})
    
    interrupt_result = handle_interrupt_if_present(state, session)
    if interrupt_result:
        return interrupt_result

    mode = state.get("mode", "venture")
    mode_prompt = MODE_PROMPTS.get(mode, MODE_PROMPTS["venture"])

    # FIX 4: NO mutation — local update only
    action_input = state["action_input"]
    persona_id   = action_input["target"]
    if persona_id not in AGENTS_CONFIG:
        raise ValueError(f"Invalid persona selected: {persona_id}")

    agent_memory = state.get("agent_memory", {}).copy()
    if persona_id not in agent_memory:
        agent_memory[persona_id] = {
            "claims": [], "risks": [], "strengths": [], "contradictions": [], "opinions": []
        }
    
    agent_mem = agent_memory.get(persona_id, {})
    priority_context = action_input.get("priority_context", "") # FIX 7: Extract priority context

    agent_config = AGENTS_CONFIG.get(persona_id, AGENTS_CONFIG["vc"])
    persona_anchor = PERSONA_ANCHORS.get(persona_id, "")
    
    ocean = OCEAN_PROFILES.get(persona_id, OCEAN_PROFILES["vc"])
    behavior_text = map_ocean_to_behavior(ocean)

    base = BASE_SYSTEM_PROMPT.format(
        mode_prompt=mode_prompt,
        persona_anchor=persona_anchor,
        behavior=behavior_text
    )

    global_mem  = state.get("memory", {})

    # PART 3 — Memory-driven tone
    own_risks     = agent_mem.get("risks", [])
    own_strengths = agent_mem.get("strengths", [])
    agent_confidence = len(own_strengths) - len(own_risks)
    if agent_confidence < 0:
        tone_instruction = "Your OWN memory has flagged serious risks. Be sharper, more skeptical, and press harder."
    elif agent_confidence > 0:
        tone_instruction = "Your OWN memory shows genuine strengths. Reinforce them confidently and build on the momentum."
    else:
        tone_instruction = "Stay balanced. Lead with a specific probe rather than a generic comment."

    # PART 5 — Covered topics (anti-repetition)
    covered_topics = json.dumps(global_mem.get("covered_topics", []))

    # PART 6 — Anti-repetition: detect if last 2 responses are from this same agent
    recent_conv = state.get("conversation", [])[-4:]
    same_agent_recent = [t for t in recent_conv if t.get("agent_id") == persona_id]
    anti_rep_instruction = ""
    if len(same_agent_recent) >= 2:
        anti_rep_instruction = (
            "WARNING: You have spoken recently. DO NOT repeat your previous angle. "
            "You MUST either: (a) ask a completely new question, "
            "(b) challenge an assumption made by another panelist, or "
            "(c) introduce a brand new risk or opportunity not yet raised."
        )

    # PART 2 — Agent goal
    agent_goal = AGENT_GOALS.get(persona_id, "Evaluate the pitch from your unique perspective.")

    # PERSONA MEMORY DEBUG
    print(f"[PERSONA EXEC] {persona_id} | Global Risks: {len(global_mem.get('risks', []))} | Private Risks: {len(agent_mem.get('risks', []))}")

    prompt = PERSONA_PROMPT.format(
        base_prompt=base,
        pitch=state.get("pitch_summary", ""),
        recent_discussion=build_conversation_context({"conversation": state["conversation"]}, last_n=8),
        risks=json.dumps(global_mem.get("risks", [])),
        strengths=json.dumps(global_mem.get("strengths", [])),
        claims=json.dumps(global_mem.get("claims", [])),
        contradictions=json.dumps(global_mem.get("contradictions", [])),
        agent_memory=json.dumps(agent_mem),
        agent_goal=agent_goal,
        tone_instruction=tone_instruction,
        covered_topics=covered_topics,
        anti_rep_instruction=anti_rep_instruction,
        priority_context=priority_context # FIX 7: Inject into format
    )

    try:
        response = await llm_provider.generate_response(
            f"Respond as {agent_config['name']}. You MUST push toward your goal. Do not be reactive — steer.",
            prompt, state["provider"], stream=False
        )
    except Exception as e:
        print(f"[PERSONA ERROR] {persona_id}: {e}")
        response = "That is a complex point. Let me think about its implications."

    new_turn = {
        "type": "persona_response",
        "agent_id": persona_id,
        "agent_name": agent_config["name"],
        "content": response
    }
    
    return {
        "conversation": [new_turn],
        "last_persona_used": persona_id,
        "agent_memory": agent_memory # Return locally updated memory
    }

async def pitcher_node(state: FocusGroupState):
    """Asks the pitcher a question."""
    session = sessions.get(state["session_id"], {})
    
    interrupt_result = handle_interrupt_if_present(state, session)
    if interrupt_result:
        return interrupt_result
    
    # FIXED: Logic moved here from controller for cleaner graph routing (Fix 2 & 4)
    if state.get("awaiting_user_input"):
        event = session["events"]["answer_event"]
        
        # FIXED: Safe wait pattern (no race condition) (Fix 4)
        if not event.is_set():
            # FIXED: Safety timeout fallback (Fix 7)
            try:
                await asyncio.wait_for(asyncio.shield(event.wait()), timeout=60.0)
            except asyncio.TimeoutError:
                print("[TIMEOUT] No user response, continuing...")
                return {"awaiting_user_input": False}
        
        # Clear once more
        event.clear()

        ans = session.get("pending_answer", "")
        session["pending_answer"] = ""

        new_turn = {
            "type": "pitcher_response",
            "agent_name": "Pitcher",
            "content": ans
        }
        
        return {
            "conversation": [new_turn],
            "awaiting_user_input": False,
            "input_type": "pitcher_response"
        }

    target_persona = state["action_input"].get("target", "interviewer")
    agent_name = AGENTS_CONFIG.get(target_persona, {"name": "The Interviewer"})["name"]
    question = state["action_input"].get("question", "What do you think about the points raised?")
    
    new_turn = {
        "type": "interviewer_question",
        "agent_id": target_persona,
        "agent_name": agent_name,
        "content": question
    }
    
    return {
        "conversation": [new_turn],
        "awaiting_user_input": True,
        "input_type": "pitcher_response"
    }

async def tool_node(state: FocusGroupState):
    """Executes search or fact-check tools."""
    session = sessions.get(state["session_id"], {})
    
    interrupt_result = handle_interrupt_if_present(state, session)
    if interrupt_result:
        return interrupt_result

    action_input = state["action_input"]
    tool_type = action_input.get("tool", "search")
    query = action_input.get("query", state["pitch_summary"])
    print(f"[TOOL] type={tool_type} query={query[:60]}")
    
    result_content = ""
    source = ""
    
    if tool_type == "search":
        if tavily_client:
            try:
                results = await asyncio.to_thread(tavily_client.search, query=query, max_results=2)
                raw_results = ""
                for r in results.get("results", []):
                    raw_results += f"- {r.get('title', '')}: {r.get('content', '')}\n"
                    source = r.get("url", "web")
                result_content = await llm_provider.generate_response(
                    SEARCH_TOOL_PROMPT,
                    f"Query: {query}\n\nSearch Results:\n{raw_results}",
                    state["provider"],
                    stream=False
                )
            except Exception as e:
                result_content = f"Search failed: {str(e)}"
        else:
            result_content = "Search tool not configured. Tavily API key missing."
    else:  # fact_check
        formatted_prompt = FACT_CHECK_PROMPT.format(claim=query)
        result_content = await llm_provider.generate_response(
            "You are a neutral fact-checker.",
            formatted_prompt,
            state["provider"],
            stream=False
        )
        source = "Internal Analysis"

    new_turn = {
        "type": "tool_output",
        "agent_name": "Research Tool",
        "content": f"[{tool_type.upper()}] {result_content} (Source: {source})"
    }
    return {"conversation": [new_turn]}

async def memory_update_node(state: FocusGroupState):
    print("[GRAPH] node=memory_update")
    conversation = state.get("conversation", [])
    if not conversation:
        return {
            "memory": state.get("memory", {}),
            "agent_memory": state.get("agent_memory", {})
        }

    last_turn = conversation[-1]
    print("[MEMORY CHECK TYPE]", last_turn.get("type"))
    if last_turn.get("type") not in ["persona_response", "tool_output", "pitcher_response"]:
        print(f"[MEMORY SKIP] Unsupported type: {last_turn.get('type')}")
        return {
            "memory": state.get("memory", {}),
            "agent_memory": state.get("agent_memory", {})
        }

    try:
        updated_memory, updated_agent_mem = await update_memory(state, last_turn)
        
        # DEBUG LOGGING
        print(f"[GLOBAL MEMORY] {state.get('memory')}")
        print(f"[AGENT MEMORY] {state.get('agent_memory')}")
        print(f"[STEP] {state.get('step_count')}")
            
        # FIX: Preserve all agents - do not overwrite entire dict
        existing = state.get("agent_memory", {}).copy()
        existing.update(updated_agent_mem)

        return {"memory": updated_memory, "agent_memory": existing}
    except Exception as e:
        print(f"[MEMORY ERROR]: {e}")
        return {
            "memory": state.get("memory", {}), 
            "agent_memory": state.get("agent_memory", {})
        }

async def update_memory(state: FocusGroupState, new_turn: dict) -> Tuple[dict, dict]:
    base_memory = state.get("memory", {
        "claims": [], "risks": [], "strengths": [], "contradictions": [], "opinions": [], "covered_topics": []
    })
    agent_memory = state.get("agent_memory", {})
    agent_id = new_turn.get("agent_id")
    
    if not agent_id:
        # Fallback to pitcher or tool identification
        agent_id = "pitcher" if new_turn.get("type") == "pitcher_response" else "research_tool"
    
    formatted_prompt = MEMORY_UPDATE_PROMPT.format(
        content=new_turn.get("content", ""),
        agent_name=new_turn.get("agent_name", "Unknown"),
        memory=json.dumps(base_memory)
    )
    try:
        response = await llm_provider.generate_response(
            "Extract memory signals.", formatted_prompt, state["provider"], stream=False
        )
        print(f"[MEMORY RAW] {response}")
        updated = extract_json(response)
        
        # KEY RECONCILIATION: Fix common LLM naming slips
        mapping = {"risk": "risks", "strength": "strengths", "claim": "claims", "contradiction": "contradictions", "opinion": "opinions", "topic": "covered_topics", "topics": "covered_topics"}
        for k, v in mapping.items():
            if k in updated and v not in updated:
                updated[v] = updated[k]

        print(f"[MEMORY PARSED] {updated}")
        
        if not updated:
            print("[MEMORY WARNING] Empty extraction from LLM")
            return base_memory, agent_memory

        # GUARANTEE: Never let the memory update be fully empty if context exists
        if not any(updated.get(k) for k in ["claims", "risks", "strengths", "opinions"]):
            # Use agent_id (from outer scope) to attribute the default insight
            updated["opinions"] = [f"{agent_id or 'Participant'} shared their perspective on this segment"]

        def apply_update(mem, include_topics=False):
            # Target all core keys
            for key in ["claims", "risks", "strengths", "contradictions", "opinions"]:
                new_items = updated.get(key, [])
                if isinstance(new_items, list):
                    if key not in mem: mem[key] = []
                    for item in new_items:
                        if item and str(item).strip() and item not in mem[key]:
                            mem[key].append(str(item).strip())
            
            if include_topics:
                new_topics = updated.get("covered_topics", [])
                if isinstance(new_topics, list):
                    if "covered_topics" not in mem: mem["covered_topics"] = []
                    for t in new_topics:
                        if t and str(t).strip() and t not in mem["covered_topics"]:
                            mem["covered_topics"].append(str(t).strip())
                mem["covered_topics"] = mem["covered_topics"][-50:]

            # Enforce 20-item limit per category and ensure keys exist
            for key in ["claims", "risks", "strengths", "contradictions", "opinions"]:
                if key not in mem: mem[key] = []
                if isinstance(mem[key], list):
                    mem[key] = mem[key][-20:]
            
            if include_topics and "covered_topics" not in mem:
                mem["covered_topics"] = []
                
            return mem
            
        updated_base = apply_update(base_memory, include_topics=True)
        
        if agent_id:
            if agent_id not in agent_memory:
                agent_memory[agent_id] = {k: [] for k in ["claims", "risks", "strengths", "contradictions", "opinions"]}
            agent_memory[agent_id] = apply_update(agent_memory[agent_id], include_topics=False)
            
        return updated_base, agent_memory
    except Exception as e:
        print(f"[MEMORY UPDATE ERROR] {e}")
        return base_memory, agent_memory

async def reflection_node(state: FocusGroupState):
    session = sessions.get(state["session_id"], {})
    interrupt_result = handle_interrupt_if_present(state, session)
    if interrupt_result:
        return interrupt_result

    mode = state.get("mode", "venture")
    context = build_conversation_context({"conversation": state.get("conversation", [])})
    user_input = json.dumps({"conversation": context, "memory": state.get("memory", {})})
    
    try:
        formatted_sys = REFLECTION_PROMPT.format(mode=mode)
        response = await llm_provider.generate_response(formatted_sys, user_input, state["provider"], stream=False)
        reflection_data = extract_json(response)
        return {
            "reflection": reflection_data,
            "last_reflection_step": state.get("step_count", 0)
        }
    except Exception as e:
        print(f"[REFLECTION ERROR] {e}")
        return {"last_reflection_step": state.get("step_count", 0)}

async def final_node(state: FocusGroupState):
    mode = state.get("mode", "venture")
    context = build_conversation_context({"conversation": state.get("conversation", [])})
    user_input = json.dumps({
        "conversation": context,
        "memory": state.get("memory", {}),
        "reflection": state.get("reflection", {})
    })
    try:
        formatted_sys = FINAL_ANALYST_PROMPT.format(mode=mode)
        response = await llm_provider.generate_response(formatted_sys, user_input, state["provider"], stream=False)
    except Exception as e:
        response = f"Evaluation error: {str(e)}"
    session = sessions.get(state["session_id"])
    if session:
        session["verdict"] = response
    return {"action": "end_session"}

async def stream_echochamber(session_id: str, session: dict, provider: str, mode: str = "venture") -> AsyncGenerator[dict, None]:
    if not session.get("domain") or not session["domain"].get("panel_mode"):
        summary_prompt = "Summarize this startup pitch in 2-3 clear sentences."
        try:
            summary = await llm_provider.generate_response(summary_prompt, session["pitch_summary"], provider, stream=False)
        except Exception:
            summary = session["pitch_summary"][:200]

        domain_prompt = """Read this pitch summary and classify it. Output ONLY valid JSON:
{
  "domain": "tech|food_beverage|retail|services|agriculture|education|healthcare|manufacturing|creative|physical_product|other",
  "sub_domain": "specific one-line description",
  "panel_mode": "standard|design|physical_product|non_tech"
}"""
        try:
            domain_json_str = await llm_provider.generate_response(domain_prompt, summary, provider, stream=False)
            # FIXED: Issue 5 Robust JSON Parsing
            domain_data = extract_json(domain_json_str)
        except Exception:
            domain_data = {"sub_domain": "General Tech", "panel_mode": "standard"}

        if mode == "spark":
            active_panel = ["enthusiastic", "beginner", "design_critic", "vc", "expert"]
        elif mode == "reality":
            active_panel = ["hostile", "suresh", "expert", "competitor", "vc"]
        else: # venture or default
            active_panel = ["vc", "competitor", "expert", "enthusiastic", "hostile"]

        domain_data["active_panel"] = active_panel
        session["domain"] = domain_data
        session["active_panel"] = active_panel
        yield sse_event("domain_classified", {**domain_data, "active_panel": active_panel, "mode": mode})

    # Resolve active_panel from session (set during domain classification or a prior call)
    _panel_from_session = session.get("active_panel", [])
    if not _panel_from_session:
        if mode == "spark":
            _panel_from_session = ["enthusiastic", "beginner", "design_critic", "vc", "expert"]
        elif mode == "reality":
            _panel_from_session = ["hostile", "suresh", "expert", "competitor", "vc"]
        else:
            _panel_from_session = ["vc", "competitor", "expert", "enthusiastic", "hostile"]
        session["active_panel"] = _panel_from_session

    initial_state: FocusGroupState = {
        "session_id": session_id,
        "pitch_summary": session["pitch_summary"],
        "domain": session["domain"],
        "mode": mode,
        "provider": provider,
        "action": "",
        "action_input": {},
        "action_history": [],
        "step_count": 0,
        "max_steps": (25 if mode == "spark" else 20 if mode == "venture" else 15),
        "last_reflection_step": 0,
        "last_persona_used": "",
        "input_type": "confirmation",
        "awaiting_user_input": False,
        "pitcher_interrupt": False,
        "pitcher_message": "",
        "pending_answer": "",
        "refined_pitch": "",
        "awaiting_pitch_confirmation": False,
        "memory": { "claims": [], "risks": [], "strengths": [], "contradictions": [], "opinions": [], "covered_topics": [] },
        "agent_memory": {
            agent_id: { "claims": [], "risks": [], "strengths": [], "contradictions": [], "opinions": [] }
            for agent_id in _panel_from_session
        },
        "reflection": { "missing": [], "confidence": 0.0, "should_continue": True },
        "conversation": []
    }
    
    graph = build_agentic_graph(
        pitch_refiner_node, controller_node, persona_node, pitcher_node,
        tool_node, reflection_node, final_node, memory_update_node
    )

    _SENTINEL = object()
    queue: asyncio.Queue = asyncio.Queue()
    yielded_start = False

    async def run_graph():
        nonlocal yielded_start
        try:
            state_step_counter = 0
            async for event in graph.astream(initial_state):
                state_step_counter += 1
                node_name = list(event.keys())[0]
                update = event[node_name]
                if not update: continue

                m = session.get("memory", {})
                agent_id = update.get("last_persona_used") or session.get("last_persona_used")
                agent_name = ""
                if agent_id and agent_id in AGENTS_CONFIG:
                    agent_name = AGENTS_CONFIG[agent_id].get("name", "")

                await queue.put(sse_event("debug_node", {
                    "node": node_name.replace("_node", ""),
                    "step": update.get("step_count") or state_step_counter,
                    "action": update.get("action") or None,
                    "agent_name": agent_name,
                    "memory_snapshot": {
                        "risks": len(m.get("risks", [])),
                        "strengths": len(m.get("strengths", [])),
                        "claims": len(m.get("claims", [])),
                        "contradictions": len(m.get("contradictions", [])),
                    }
                }))

                # FIXED: Complete state sync (Fix 3)
                for key in [
                    "awaiting_user_input",
                    "awaiting_pitch_confirmation",
                    "input_type",
                    "action",
                    "memory",
                    "step_count",
                    "last_persona_used",
                    "pitcher_interrupt",
                    "pitcher_message",
                    "pending_answer",
                    "agent_memory" # FIX 5: Sync agent_memory
                ]:
                    if key in update:
                        session[key] = update[key]
                        if key in ["memory", "agent_memory"]:
                            # FIX 5: Prevent SSE memory spam - only emit if data actually changed
                            if session.get(key) != update[key]:
                                session[key] = update[key]
                                m_obj = session.get("memory", {})
                                print(f"[SSE MEMORY EMIT] Risks: {len(m_obj.get('risks', []))}")
                                
                                await queue.put(sse_event("memory_update", {
                                    "memory": session.get("memory", {}),
                                    "agent_memory": session.get("agent_memory", {})
                                }))

                if "conversation" in update:
                    for turn in update["conversation"]:
                        await queue.put(sse_event("agent_turn", turn))
                        session["conversation"].append(turn)

                if not yielded_start and (node_name == "controller" or "conversation" in update):
                    await queue.put(sse_event("echochamber_start", {
                        "session_id": session_id,
                        "message": "The panel is now analyzing your pitch...",
                        "personas": [
                            {"id": k, "name": v["name"], "role": v["role"]}
                            for k, v in AGENTS_CONFIG.items() if k in session.get("active_panel", [])
                        ]
                    }))
                    yielded_start = True

                if update.get("refined_pitch"):
                    await queue.put(sse_event("hitl_summary_approval", {
                        "session_id": session_id,
                        "summary": update["refined_pitch"]
                    }))

                if update.get("action") == "end_session": break
        except Exception as e:
            print(f"[GRAPH ERROR] {e}")
        finally:
            await queue.put(_SENTINEL)

    graph_task = asyncio.create_task(run_graph())
    try:
        while True:
            item = await queue.get()
            if item is _SENTINEL: break
            yield item
    finally:
        graph_task.cancel()

    async for event in stream_meta_analysis(session_id, session, provider):
        yield event

async def stream_meta_analysis(session_id: str, session: dict, provider: str):
    yield sse_event("status", {"message": "Meta-Analyst is uncovering non-obvious insights...", "phase": "meta_analysis"})
    context = build_conversation_context(session)
    formatted_prompt = BLACK_SWAN_PROMPT.format(
        mode=session.get("mode", "venture"),
        conversation=context,
        memory=json.dumps(session.get("memory", { "claims": [], "risks": [], "strengths": [], "contradictions": [] }))
    )
    try:
        raw = await llm_provider.generate_response(formatted_prompt, "Insights", provider, stream=False)
        session["black_swan_insight"] = raw
        yield sse_event("black_swan_report", {"insight": raw})
    except Exception: pass
    
    session["phase"] = "verdict"
    yield sse_event("conversation_complete", {"session_id": session_id})
    async for event in stream_verdict_from_conversation(session_id, session, provider):
        yield event

async def stream_verdict_from_conversation(session_id: str, session: dict, provider: str):
    yield sse_event("status", {"message": "Judge is reading...", "phase": "verdict_start"})
    transcript = build_conversation_context(session)
    user_input = f"PITCH SUMMARY:\n{session['pitch_summary']}\n\nTRANSCRIPT:\n{transcript}"
    system = JUDGE_CONVERSATION_PROMPT
    yield sse_event("agent_start", {"agent_id": "judge", "name": "The Judge", "role": "Verdict"})
    full_verdict = ""
    try:
        stream = await llm_provider.generate_response(system, user_input, provider, stream=True)
        async for text in stream:
            full_verdict += text
            yield sse_event("agent_token", {"agent_id": "judge", "token": text})
    except Exception: pass
    session["verdict"] = full_verdict
    parts = parse_verdict_parts(full_verdict)
    yield sse_event("verdict_complete", {"verdict": full_verdict, "parts": parts, "session_id": session_id})

def parse_verdict_parts(full_verdict: str) -> dict:
    parts = {"strongest": "", "weakness": "", "fix": ""}
    # Simplified parsing for the fix
    return parts

async def handle_verdict_pushback(session_id: str, pushback: str, provider: str, sessions: dict):
    session = sessions.get(session_id)
    if not session: return
    prompt = f"Verdict:\n{session['verdict']}\n\nPushback:\n{pushback}"
    yield sse_event("pushback_response_start", {"session_id": session_id})
    full_resp = ""
    try:
        stream = await llm_provider.generate_response("Judge", prompt, provider, stream=True)
        async for text in stream:
            full_resp += text
            yield sse_event("agent_token", {"agent_id": "judge", "token": text, "type": "pushback_response"})
    except Exception: pass
    session["verdict_final"] = session["verdict"] + "\n\nJudge Response: " + full_resp
    yield sse_event("session_complete", {"session_id": session_id, "verdict": session["verdict_final"]})

async def generate_rebuttal_response(session: dict, agent_id: str, agent_claim: str, user_text: str, provider: str) -> str:
    agent = AGENTS_CONFIG.get(agent_id, {"name": "Agent", "role": "Panelist"})
    PROMPT = f"You are {agent['name']}. Claim: {agent_claim}. User: {user_text}. Respond brief."
    return await llm_provider.generate_response(PROMPT, user_text, provider, stream=False)

async def generate_fact_check(agent_id: str, agent_claim: str, challenge: str, provider: str) -> str:
    agent = AGENTS_CONFIG.get(agent_id, {"name": "Agent", "role": "Panelist"})
    PROMPT = f"You are {agent['name']}. Claim: {agent_claim}. Challenge: {challenge}. Respond brief."
    return await llm_provider.generate_response(PROMPT, challenge, provider, stream=False)

# FIXED: Standardized run_round1 to use the unified conversation types
async def run_round1(session_id: str, session: dict, pitch: str, provider: str, pitcher_id: Optional[str] = None, difficulty: str = "standard"):
    summary_prompt = "Summarize."
    summary = await llm_provider.generate_response(summary_prompt, pitch, provider, stream=False)
    domain_prompt = "Classify."
    domain_json_str = await llm_provider.generate_response(domain_prompt, summary, provider, stream=False)
    domain_data = extract_json(domain_json_str)
    session["pitch_summary"] = summary
    session["domain"] = domain_data
    session["active_panel"] = PANEL_AGENTS_STANDARD
    async for event in stream_echochamber(session_id, session, provider, "venture"):
        yield event
