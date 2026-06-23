import json
import asyncio
import os
import copy
from typing import AsyncGenerator, Tuple, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
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

# ─── Agent personas (Tier 0d) ──────────────────────────────────────
# The persona catalog is now loaded from YAML files at apps/api/agents/
# personas/. The dicts below are computed from the YAMLs at import time.
# Edit the YAMLs to change a persona — no code changes needed.
# See docs/personas.md.

from services.llm import llm_provider
from graph import FocusGroupState, build_agentic_graph
from typing import Literal, Annotated
import operator

# Load the catalog eagerly so AGENTS_CONFIG / AGENT_GOALS / OCEAN_PROFILES
# are plain dicts at module level (as the legacy code expects).
from agents.loader import AGENTS_CONFIG, AGENT_GOALS, OCEAN_PROFILES  # noqa: E402,F401

class VerdictSchema(BaseModel):
    strongest_point: str = Field(description="The strongest strategic advantage")
    biggest_weakness: str = Field(description="The primary risk factor")
    fix_before_next_pitch: str = Field(description="Immediate recommendation before the next pitch")
    investment_score: float = Field(description="Score out of 10 based on confidence")
    recommendation: str = Field(description="Pass, Conditional, or Invest")

class ControllerDecision(BaseModel):
    action: Literal["ask_persona", "ask_pitcher", "use_tool", "reflect", "end_session"]
    target: Optional[str] = "vc"
    input: dict = {}
    reason: Optional[str] = ""

    @field_validator("input", mode="before")
    @classmethod
    def ensure_input_dict(cls, v):
        return v if isinstance(v, dict) else {}


sessions: dict[str, dict] = {}


def force_end_signal(session: dict) -> bool:
    return bool(session.get("force_end"))


def check_force_end() -> dict:
    return {
        "action": "end",
        "awaiting_user_input": False,
        "pitcher_interrupt": False,
    }


async def safe_queue_put(session: dict, event: dict) -> None:
    queue = session.get("sse_queue")
    if queue is not None:
        try:
            await queue.put(event)
        except Exception as e:
            print(f"[SSE QUEUE ERROR] {e}")


def check_manual_interrupt(state: FocusGroupState, session: dict) -> dict | None:
    """
    Checks for a manual 'Jump In' interruption via interrupt_event.
    Injects an acknowledgement from the current/last speaker + the founder message.
    """
    events = session.get("events", {})
    if "interrupt_event" in events and events["interrupt_event"].is_set():
        events["interrupt_event"].clear()
        
        if session.get("force_end"):
            return {"action": "end_session"}

        msg = session.get("interrupt_message", "Manual interruption")
        
        last_agent_id = state.get("last_persona_used", "interviewer")
        agent = AGENTS_CONFIG.get(last_agent_id, {"name": "Panelist", "role": "Expert"})
        
        import random
        acks = [
            f"Hold on — let's hear from the founder. Go ahead.",
            f"Looks like you want to add something — please, go ahead.",
            f"Wait, I see the founder jumping in. Let's pause and listen.",
            f"Ah, an interjection. Please continue, we're listening.",
            f"Interesting point, please explain that further."
        ]
        ack_text = random.choice(acks)
        
        print(f"[INTERRUPT] {last_agent_id} acknowledging: {ack_text}")
        
        ack_turn = {
            "type": "persona_response",
            "agent_id": last_agent_id,
            "agent_name": agent["name"],
            "content": ack_text
        }
        
        founder_turn = {
            "type": "pitcher_response",
            "agent_name": "Founder (Jump In)",
            "content": msg
        }
        
        return {
            "conversation": [ack_turn, founder_turn],
            "action": "ask_persona",
            "action_input": {"target": None}, # Force controller to pick next based on this new context
            "pitcher_interrupt": False,
            "awaiting_user_input": False,
            "last_user_interrupt": msg
        }
    return None

try:
    from tavily import TavilyClient
    tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY")) if os.getenv("TAVILY_API_KEY") else None
except ImportError:
    tavily_client = None
except Exception:
    tavily_client = None

async def perform_initial_domain_search(domain_info: dict) -> str:
    """Pre-search context for the controller."""
    query = f"{domain_info.get('sub_domain', '')} competitors India 2026 pricing"
    competitor_context = "LIVE COMPETITOR RESEARCH (searched just now):\n"
    
    if tavily_client:
        try:
            results = await asyncio.to_thread(tavily_client.search, query=query, max_results=3)
            for r in results.get("results", []):
                competitor_context += f"- {r.get('title')}: {r.get('content')}\n"
            return competitor_context
        except Exception:
            pass # fall through to DDG

    # DuckDuckGo Fallback
    try:
        from services.search import search_competitors
        ddg_results = await search_competitors(query, max_results=3)
        if not ddg_results: return ""
        for r in ddg_results:
            competitor_context += f"- {r.get('title')}: {r.get('body')}\n"
        return competitor_context
    except Exception:
        return ""

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
            "weaknesses": "Check Verdict for Weaknesses",
            "verdict": verdict,
            "pitch_count": memory.get(pitcher_id, {}).get("pitch_count", 0) + 1
        }
        with open(MEMORY_FILE, "w") as f: json.dump(memory, f, indent=2)
    except Exception: pass


async def generate_radar_chart_image(scores: dict) -> str:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        import io
        import base64

        labels = list(scores.keys())
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

def sse_event(event_type: str, data: dict) -> dict:
    return {"event": event_type, "data": json.dumps(data)}

async def safe_wait(event, timeout=10.0):
    try:
        if not event.is_set():
            await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        print(f"[TIMEOUT] safe_wait exceeded {timeout}s. Continuing automatically.")
    finally:
        event.clear()

def build_conversation_context(session: dict, last_n: int = None) -> str:
    conversation = session.get("conversation", [])
    if not conversation:
        return "No exchanges yet."
    
    if last_n is not None:
        conversation = conversation[-last_n:]
    
    lines = []
    for turn in conversation:
        t = turn["type"]
        name = turn.get("agent_name", "Unknown")
        content = turn.get("content", "")

        if t == "question":
            lines.append(f"{name} asked: {content}")
        elif t == "pitcher_response":
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

async def pitch_refiner_node(state: FocusGroupState):
    if state.get("pitcher_interrupt"):
        return {"pitcher_interrupt": False}
    if state.get("awaiting_pitch_confirmation"):
        session = sessions.get(state["session_id"])
        if session:
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

        # Phase 3: Retrieve past pitches for historical context injection
        try:
            from services.db import retrieve_past_pitches, format_past_pitches_for_context
            past = await retrieve_past_pitches(refined, top_k=2)
            if past:
                history_context = format_past_pitches_for_context(past)
                session["past_pitch_context"] = history_context
                print(f"[DB] Injecting {len(past)} past pitch(es) into session context.")
                # Emit to frontend for visibility
                await safe_queue_put(session, sse_event("past_pitches_found", {
                    "count": len(past),
                    "message": f"Found {len(past)} previous pitch(es) — agents will reference your history."
                }))
        except Exception as e:
            print(f"[DB] Past pitch retrieval skipped: {e}")
    
    return {
        "refined_pitch": refined,
        "awaiting_pitch_confirmation": True
    }

async def controller_node(state: FocusGroupState):
    session = sessions.get(state["session_id"], {})

    if force_end_signal(session):
        return check_force_end()
    
    if state.get("interrupt") == True:
        return {
            "action": "ask_pitcher",
            "awaiting_user_input": True,
            "action_input": {"target": "interviewer", "question": "The founder has something to add."}
        }

    interrupt_result = check_manual_interrupt(state, session)
    if interrupt_result:
        if isinstance(interrupt_result, dict):
            interrupt_result["action"] = interrupt_result.get("action", "ask_persona")
        return interrupt_result

    if session.get("action") == "end_session":
        session["action"] = None 
        return {
            "action": "end_session",
            "awaiting_user_input": False,
            "pitcher_interrupt": False
        }

    mode = state.get("mode", "venture")
    state_updates = {}

    active_panel = state.get("domain", {}).get("active_panel")
    if not active_panel:
        active_panel = ["vc", "expert", "enthusiastic"]
        state["domain"] = state.get("domain", {})
        state["domain"]["active_panel"] = active_panel

    reflection     = state.get("reflection", {})
    global_mem     = state.get("memory", {})
    last_used      = state.get("last_persona_used", "")
    action_history = state.get("action_history", [])
    max_steps      = state.get("max_steps", 20)
    current_step   = state.get("step_count", 0)

    def _ctrl_return(action, action_input=None, **extra):
        result = {
            "action": action,
            "action_input": action_input or {},
            "action_history": [action],
        }
        result.update(extra)
        return result

    if current_step < 2:
        next_agent = active_panel[current_step % len(active_panel)]
        return _ctrl_return("ask_persona", {"target": next_agent})

    if current_step >= max_steps:
        return _ctrl_return("end_session")

    # Don't let reflection end the session before enough agents have spoken.
    # Without this floor, the LLM sometimes declares "high confidence" after
    # just 2 turns and we surface a meaningless verdict/report.
    MIN_TURNS_BEFORE_END = 6
    if current_step >= MIN_TURNS_BEFORE_END and not reflection.get("should_continue", True) and reflection.get("confidence", 0.0) >= 0.8:
        return _ctrl_return("end_session")

    missing = reflection.get("missing", [])
    if missing and mode != "spark":
        q = f"Clarify: {missing[0]}"
        return _ctrl_return("ask_pitcher", {"question": q, "target": "interviewer"})

    recent_actions = action_history[-5:]
    if sum(1 for a in recent_actions if a == "ask_persona") >= 4:
        return _ctrl_return("reflect")

    next_priority = reflection.get("next_priority", "")
    if next_priority:
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

    opinions = global_mem.get("opinions", [])
    if len(opinions) > 5:
        return _ctrl_return("reflect")

    context = build_conversation_context({"conversation": state.get("conversation", [])}, last_n=10)
    history_str = ", ".join(state.get("action_history", [])[-5:])

    recent_speakers = [turn.get("agent_id") for turn in state.get("conversation", []) if turn.get("type") == "persona_response"][-3:]
    recent_speakers_str = ", ".join(recent_speakers) if recent_speakers else "None"

    print(f"\n--- [STEP {current_step}] CONTROLLER INPUT ---")
    print(f"Recent Speakers: {recent_speakers_str}")
    print(f"Action History: {history_str}")

    formatted_prompt = CONTROLLER_PROMPT.format(
        mode=mode,
        mode_goal=MODE_INSTRUCTIONS.get(mode, "Standard evaluation."),
        recent_speakers=recent_speakers_str,
        action_history=history_str,
        context=context,
        memory=json.dumps(state.get("memory", {})),
        reflection=json.dumps(state.get("reflection", {})),
        input_type=state.get("input_type", ""),
        step_count=current_step
    )

    # Phase 3: Prepend pitch history context if it exists
    past_pitch_context = session.get("past_pitch_context", "")
    if past_pitch_context:
        formatted_prompt = past_pitch_context + "\n\n" + formatted_prompt


    try:
        response = await llm_provider.generate_response(
            formatted_prompt, "Decide the next action.", state["provider"], stream=False
        )
        decision_data = extract_json(response)
        print(f"[CONTROLLER OUTPUT] Raw JSON: {decision_data}")

        if decision_data.get("action") == "ask_persona":
            t = decision_data.get("target")
            if t not in active_panel or t in recent_speakers[-1:]:
                # Fallback to next round-robin agent if target invalid or repeats the immediate last speaker
                idx = active_panel.index(last_used) if last_used in active_panel else -1
                decision_data["target"] = active_panel[(idx + 1) % len(active_panel)]

        if decision_data.get("action") == "ask_pitcher":
            freq = 6 if mode == "spark" else (3 if mode == "reality" else 4)
            if not missing and current_step % freq != 0:
                idx = active_panel.index(last_used) if last_used in active_panel else -1
                decision_data = {"action": "ask_persona", "target": active_panel[(idx + 1) % len(active_panel)]}

        if decision_data.get("action") == "use_tool":
            tool = (decision_data.get("input") or {}).get("tool", "search")
            if mode == "spark":
                idx = active_panel.index(last_used) if last_used in active_panel else -1
                decision_data = {"action": "ask_persona", "target": active_panel[(idx + 1) % len(active_panel)], "reason": "spark suppresses tools"}
            elif mode == "reality" and tool != "fact_check":
                if not decision_data.get("input"): decision_data["input"] = {}
                decision_data["input"]["tool"] = "fact_check"

        if next_priority and decision_data.get("action") in ["ask_persona", "ask_pitcher"]:
            decision_data.setdefault("input", {})
            decision_data["input"]["priority_context"] = next_priority

        decision = ControllerDecision(**decision_data)
        action   = decision.action
        persona_id = decision.target

        action_input = decision.input or {}
        if persona_id:
            action_input["target"] = persona_id

        if action == "ask_pitcher":
            action_input["question"] = action_input.get("question", action_input.get("query", "Can you clarify your previous point?"))

        if not action or action not in ["ask_persona", "ask_pitcher", "use_tool", "reflect", "end_session"]:
            print(f"[CONTROLLER VALIDATION] Invalid action {action}, falling back to ask_persona")
            action = "ask_persona"
            idx = active_panel.index(last_used) if last_used in active_panel else -1
            action_input["target"] = active_panel[(idx + 1) % len(active_panel)]

        print(f"[CONTROLLER OUTPUT] Final Action: {action} | Target: {action_input.get('target', 'None')}")

        # NOTE: step_count is incremented by memory_update_node (post-step),
        # not here (pre-step). Incrementing in both caused premature termination.
        state_updates.update({
            "action": action,
            "action_input": action_input,
            "action_history": [action],
        })
        return state_updates

    except Exception as e:
        fallback_personas = state.get("domain", {}).get("active_panel", [])
        if not fallback_personas:
            fallback_personas = ["vc", "expert", "enthusiastic"]

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
        }
        fallback_update.update(state_updates)
        return fallback_update

async def persona_node(state: FocusGroupState):
    session = sessions.get(state["session_id"], {})

    if force_end_signal(session):
        return check_force_end()

    interrupt_result = check_manual_interrupt(state, session)
    if interrupt_result:
        return interrupt_result

    mode = state.get("mode", "venture")
    mode_prompt = MODE_PROMPTS.get(mode, MODE_PROMPTS["venture"])

    action_input = state["action_input"]
    persona_id   = action_input["target"]
    if persona_id not in AGENTS_CONFIG:
        raise ValueError(f"Invalid persona selected: {persona_id}")

    agent_memory = copy.deepcopy(state.get("agent_memory", {}))
    if persona_id not in agent_memory:
        agent_memory[persona_id] = {
            "claims": [], "risks": [], "strengths": [], "contradictions": [], "opinions": [],
            "concerns": [], "agent_opinions": [], "disagreements": []
        }
    
    agent_mem = agent_memory.get(persona_id, {})
    priority_context = action_input.get("priority_context", "")

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
    
    if priority_context:
        agent_angle_map = {
            "vc": f"From your ROI perspective, the key blocker is: {priority_context}",
            "enthusiastic": f"The user experience angle here is: {priority_context}",
            "hostile": f"The operational risk you spotted is: {priority_context}",
            "expert": f"The technical validity question is: {priority_context}",
            "competitor": f"The competitive/growth risk is: {priority_context}",
            "beginner": f"The clarity issue you found is: {priority_context}",
            "suresh": f"The real-world execution problem is: {priority_context}",
            "design_critic": f"The trust/UX issue is: {priority_context}"
        }
        agent_concerns = agent_mem.get("concerns", [])
        if agent_concerns:
            priority_context = agent_angle_map.get(persona_id, priority_context) + f" Your private concern: {agent_concerns[0]}"
        else:
            priority_context = agent_angle_map.get(persona_id, priority_context)

    aggressiveness = session.get("aggressiveness", 5)
    if aggressiveness >= 8:
        aggression_str = "[SYSTEM: EXTREMELY AGGRESSIVE & HOSTILE. Interrogate mercilessly. Give no quarter. Be harsh and direct.] "
    elif aggressiveness <= 3:
        aggression_str = "[SYSTEM: VERY SUPPORTIVE & GENTLE. Frame your critiques as friendly, collaborative advice. Be polite and encouraging.] "
    else:
        aggression_str = "[SYSTEM: BALANCED. Critique strictly but constructively.] "

    own_risks     = agent_mem.get("risks", [])
    own_strengths = agent_mem.get("strengths", [])
    agent_confidence = len(own_strengths) - len(own_risks)
    
    if agent_confidence < 0:
        tone_instruction = aggression_str + "Your OWN memory has flagged serious risks. Be sharper, more skeptical, and press harder."
    elif agent_confidence > 0:
        tone_instruction = aggression_str + "Your OWN memory shows genuine strengths. Reinforce them confidently and build on the momentum."
    else:
        tone_instruction = aggression_str + "Stay balanced. Lead with a specific probe rather than a generic comment."

    covered_topics = json.dumps(global_mem.get("covered_topics", []))

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

    agent_goal = AGENT_GOALS.get(persona_id, "Evaluate the pitch from your unique perspective.")

    agent_memory_formatted = json.dumps(agent_mem)
    if agent_mem.get("concerns") or agent_mem.get("agent_opinions") or agent_mem.get("disagreements"):
        formatted_concerns = agent_mem.get("concerns", [])
        formatted_opinions = agent_mem.get("agent_opinions", [])
        formatted_disagreements = agent_mem.get("disagreements", [])
        
        agent_concerns_str = "\n".join([f"⚠ {c}" for c in formatted_concerns[:3]]) if formatted_concerns else ""
        agent_opinions_str = "\n".join([f"💭 {o}" for o in formatted_opinions[:3]]) if formatted_opinions else ""
        agent_disagreements_str = "\n".join([f"⚖ {d}" for d in formatted_disagreements[:2]]) if formatted_disagreements else ""
        
        agent_memory_formatted = f"""DETAILED PRIVATE STATE:
Concerns: {agent_concerns_str or "(none)"}
Opinions: {agent_opinions_str or "(none)"}
Disagreements: {agent_disagreements_str or "(none)"}
Full State: {json.dumps(agent_mem)}"""

    prompt = PERSONA_PROMPT.format(
        base_prompt=base,
        pitch=state.get("pitch_summary", ""),
        recent_discussion=build_conversation_context({"conversation": state["conversation"]}, last_n=8),
        risks=json.dumps(global_mem.get("risks", [])),
        strengths=json.dumps(global_mem.get("strengths", [])),
        claims=json.dumps(global_mem.get("claims", [])),
        contradictions=json.dumps(global_mem.get("contradictions", [])),
        agent_memory=agent_memory_formatted,
        agent_goal=agent_goal,
        tone_instruction=tone_instruction,
        priority_context=priority_context,
        covered_topics=covered_topics,
        anti_rep_instruction=anti_rep_instruction
    )

    if session.get("sse_queue") is not None:
        # Extract signals to show what the agent is "thinking" about
        signals = []
        if agent_mem:
            for k, v in list(agent_mem.items())[-2:]:
                signals.append(f"Recalling: {str(v)[:60]}...")
        elif global_mem.get("risks"):
            signals.append(f"Evaluating Risk: {global_mem['risks'][-1][:60]}...")
        elif global_mem.get("strengths"):
            signals.append(f"Noting Strength: {global_mem['strengths'][-1][:60]}...")

        if not signals:
            signals.append("Analyzing recent conversation context...")

        await safe_queue_put(session, sse_event("agent_thinking", {
            "agent_id": persona_id,
            "name": agent_config["name"],
            "signals": signals
        }))

        await safe_queue_put(session, sse_event("agent_start", {
            "agent_id": persona_id,
            "name": agent_config["name"]
        }))

    
    try:
        full_response = await llm_provider.generate_response(
            f"Respond as {agent_config['name']}. You MUST push toward your goal. Do not be reactive — steer.",
            prompt, state["provider"], stream=False
        )
    except Exception as e:
        full_response = "That is a complex point. Let me think about its implications."

    new_turn = {
        "type": "persona_response",
        "agent_id": persona_id,
        "agent_name": agent_config["name"],
        "role": persona_id,
        "content": full_response
    }
    
    return {
        "conversation": [new_turn],
        "messages": [full_response],
        "current_speaker": agent_config["name"],
        "last_persona_used": persona_id,
        "is_speaking": False,
        "agent_memory": { persona_id: agent_memory[persona_id] }
    }

async def pitcher_node(state: FocusGroupState):
    session = sessions.get(state["session_id"], {})

    if force_end_signal(session):
        return check_force_end()

    interrupt_result = check_manual_interrupt(state, session)
    if interrupt_result:
        return interrupt_result

    if state.get("awaiting_user_input"):
        event = session["events"]["answer_event"]
        
        if not event.is_set():
            try:
                await asyncio.wait_for(asyncio.shield(event.wait()), timeout=30.0)
            except asyncio.TimeoutError:
                return {"awaiting_user_input": False}
        
        event.clear()

        if session.get("action") == "end_session":
            session["action"] = None
            return {
                "action": "end_session",
                "awaiting_user_input": False,
                "pitcher_interrupt": False
            }

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
    session = sessions.get(state["session_id"], {})

    if force_end_signal(session):
        return check_force_end()

    interrupt_result = check_manual_interrupt(state, session)
    if interrupt_result:
        return interrupt_result

    action_input = state["action_input"]
    tool_type = action_input.get("tool", "search")
    query = action_input.get("query", state["pitch_summary"])
    
    result_content = ""
    source = ""
    
    if tool_type == "search":
        search_success = False
        if tavily_client:
            try:
                results = await asyncio.to_thread(tavily_client.search, query=query, max_results=2)
                raw_results = ""
                for r in results.get("results", []):
                    raw_results += f"- {r.get('title', '')}: {r.get('content', '')}\n"
                    source = r.get("url", "web")
                
                if raw_results.strip():
                    result_content = await llm_provider.generate_response(
                        SEARCH_TOOL_PROMPT,
                        f"Query: {query}\n\nSearch Results:\n{raw_results}",
                        state["provider"],
                        stream=False
                    )
                    search_success = True
            except Exception as e:
                print(f"[TAVILY ERROR] {e}")
        
        if not search_success:
            try:
                from services.search import search_competitors
                ddg_results = await search_competitors(query, max_results=2)
                raw_results = ""
                for r in ddg_results:
                    raw_results += f"- {r.get('title', '')}: {r.get('body', '')}\n"
                    source = r.get("href", "web")
                
                if not raw_results.strip():
                    result_content = "Search returned no results."
                else:
                    result_content = await llm_provider.generate_response(
                        SEARCH_TOOL_PROMPT,
                        f"Query: {query}\n\nSearch Results:\n{raw_results}",
                        state["provider"],
                        stream=False
                    )
            except Exception as e:
                result_content = f"Search failed: {str(e)}"
    else:
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
        "agent_id": f"tool_{tool_type}",
        "agent_name": "Research Tool",
        "content": f"[{tool_type.upper()}] {result_content} (Source: {source})"
    }
    return {"conversation": [new_turn]}

async def memory_update_node(state: FocusGroupState):
    session = sessions.get(state["session_id"], {})

    if force_end_signal(session):
        return {
            "memory": state.get("memory", {}),
            "agent_memory": state.get("agent_memory", {}),
            **check_force_end(),
        }

    interrupt_result = check_manual_interrupt(state, session)
    if interrupt_result:
        return interrupt_result

    conversation = state.get("conversation", [])
    if not conversation:
        return {
            "memory": state.get("memory", {}),
            "agent_memory": state.get("agent_memory", {})
        }

    last_turn = conversation[-1]
    if last_turn.get("type") not in ["persona_response", "tool_output", "pitcher_response"]:
        return {
            "memory": state.get("memory", {}),
            "agent_memory": state.get("agent_memory", {})
        }

    new_step_count = state.get("step_count", 0) + 1

    try:
        updated_memory, updated_agent_mem = await update_memory(state, last_turn)
        
        existing = state.get("agent_memory", {}).copy()
        for agent_id, data in updated_agent_mem.items():
            if agent_id not in existing:
                existing[agent_id] = data
            else:
                for key, values in data.items():
                    if key not in existing[agent_id]:
                        existing[agent_id][key] = []
                    existing[agent_id][key].extend(
                        v for v in values if v not in existing[agent_id][key]
                    )

        history_item = {
            "step": new_step_count,
            "risks_count": len(updated_memory.get("risks", [])),
            "strengths_count": len(updated_memory.get("strengths", [])),
            "contradiction_count": len(updated_memory.get("contradictions", [])),
            "last_agent": last_turn.get("agent_id")
        }

        print(f"[MEMORY UPDATE] Success, Step Count -> {new_step_count}")
        return {
            "memory": updated_memory,
            "agent_memory": existing,
            "memory_history": [history_item],
            "step_count": new_step_count
        }
    except Exception as e:
        print(f"[MEMORY UPDATE] FAILED: {str(e)} -> Using fallback memory, Step Count -> {new_step_count}")
        return {
            "memory": state.get("memory", {}), 
            "agent_memory": state.get("agent_memory", {}),
            "step_count": new_step_count
        }

async def update_memory(state: FocusGroupState, new_turn: dict) -> Tuple[dict, dict]:
    base_memory = copy.deepcopy(state.get("memory", {
        "claims": [], "risks": [], "strengths": [], "contradictions": [], "opinions": [], "covered_topics": []
    }))
    agent_memory = copy.deepcopy(state.get("agent_memory", {}))
    
    tool_type = new_turn.get("type", "tool")
    agent_id = new_turn.get("agent_id") or f"tool_{tool_type}"
    
    formatted_prompt = MEMORY_UPDATE_PROMPT.format(
        content=new_turn.get("content", ""),
        agent_name=new_turn.get("agent_name", "Unknown"),
        agent_id=agent_id,
        memory=json.dumps(base_memory)
    )
    try:
        response = await llm_provider.generate_response(
            "Extract memory signals.", formatted_prompt, state["provider"], stream=False
        )
        updated = extract_json(response)
        
        mapping = {
            "risk": "risks", "strength": "strengths", "claim": "claims", 
            "contradiction": "contradictions", "opinion": "opinions", 
            "topic": "covered_topics", "topics": "covered_topics",
            "concern": "concerns",
            "agent_concern": "concerns",
            "agent_opinion": "agent_opinions",
            "disagreement": "disagreements"
        }
        for k, v in mapping.items():
            if k in updated and v not in updated:
                updated[v] = updated[k]
        
        if not updated:
            updated = {
                "opinions": [new_turn.get("content", "")[:80]]
            }

        def apply_update(mem, include_topics=False):
            mem = copy.deepcopy(mem)
            for key in ["claims", "risks", "strengths", "contradictions", "opinions"]:
                new_items = updated.get(key, [])
                if isinstance(new_items, list):
                    if key not in mem: mem[key] = []
                    for item in new_items:
                        if item and str(item).strip():
                            item_clean = str(item).strip()
                            if item_clean not in mem[key]:
                                mem[key].append(item_clean)
                    mem[key] = mem[key][-15:]
            
            if include_topics:
                new_topics = updated.get("covered_topics", [])
                if isinstance(new_topics, list):
                    if "covered_topics" not in mem: mem["covered_topics"] = []
                    for t in new_topics:
                        if t and str(t).strip() and t not in mem["covered_topics"]:
                            mem["covered_topics"].append(str(t).strip())
                mem["covered_topics"] = mem["covered_topics"][-50:]

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
                agent_memory[agent_id] = {
                    "stance": "Neutral",
                    "concerns": [],
                    "positives": [],
                    "confidence": 50,
                    "notes": [],
                    "claims": [], "risks": [], "strengths": [], "contradictions": [], "opinions": [], "disagreements": []
                }
            
            agent_memory[agent_id] = apply_update(agent_memory[agent_id], include_topics=False)
            
            if "stance" in updated: 
                agent_memory[agent_id]["stance"] = updated["stance"]
            if "confidence" in updated:
                try:
                    agent_memory[agent_id]["confidence"] = int(updated["confidence"])
                except:
                    pass
            
            for key in ["concerns", "positives", "disagreements"]:
                src_key = "agent_disagreements" if key == "disagreements" else key
                new_items = updated.get(src_key, [])
                if isinstance(new_items, list):
                    if key not in agent_memory[agent_id]: agent_memory[agent_id][key] = []
                    for item in new_items:
                        item_clean = str(item).strip()
                        if item_clean and item_clean not in agent_memory[agent_id][key]:
                            agent_memory[agent_id][key].append(item_clean)
                    agent_memory[agent_id][key] = agent_memory[agent_id][key][-10:]
            
        return updated_base, agent_memory
    except Exception as e:
        return base_memory, agent_memory

async def reflection_node(state: FocusGroupState):
    session = sessions.get(state["session_id"], {})

    if force_end_signal(session):
        return check_force_end()

    interrupt_result = check_manual_interrupt(state, session)
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
        return {"last_reflection_step": state.get("step_count", 0)}

async def final_node(state: FocusGroupState):
    session = sessions.get(state["session_id"], {})
    if session.get("cancelled"):
        report = {
            "pitch_summary": state.get("pitch_summary", ""),
            "strengths": state.get("memory", {}).get("strengths", []),
            "risks": state.get("memory", {}).get("risks", []),
            "claims": state.get("memory", {}).get("claims", []),
            "contradictions": state.get("memory", {}).get("contradictions", []),
            "verdict": "Debate Aborted. The session was interrupted or cancelled.",
            "confidence_score": 0,
            "investment_signal": "ABORTED",
            "cancelled": True
        }
        session["final_report"] = report
        return {"action": "end_session", "final_report": report}

    mode = state.get("mode", "venture")
    context = build_conversation_context({"conversation": state.get("conversation", [])})
    memory = state.get("memory", {})

    strengths = memory.get("strengths", [])
    risks = memory.get("risks", [])
    claims = memory.get("claims", [])
    contradictions = memory.get("contradictions", [])
    missing_points = memory.get("missing", [])

    strength_pts = min(10, len(strengths))
    risk_pts = min(10, len(risks))
    clarity_pts = min(10, len(claims))
    consistency_pts = min(10, len(contradictions))

    confidence_score = int(
        (strength_pts * 0.4 + clarity_pts * 0.3 + (10 - risk_pts) * 0.2 + (10 - consistency_pts) * 0.1) * 10
    )
    confidence_score = max(0, min(100, confidence_score))

    if confidence_score >= 75:
        investment_signal = "STRONG"
    elif confidence_score >= 50:
        investment_signal = "MEDIUM"
    else:
        investment_signal = "WEAK"

    verdict_text, verdict_parts = await generate_verdict_text(
        strengths, risks, claims, contradictions, confidence_score, mode, state["provider"]
    )

    charts = await generate_report_charts(strength_pts, risk_pts, clarity_pts, confidence_score)

    report = {
        "pitch_summary": state.get("pitch_summary", ""),
        "strengths": strengths,
        "risks": risks,
        "claims": claims,
        "contradictions": contradictions,
        "missing_points": missing_points,
        "verdict": verdict_text,
        "confidence_score": confidence_score,
        "investment_signal": investment_signal,
        "charts": charts,
        "scores": {
            "strength": strength_pts,
            "risk": risk_pts,
            "clarity": clarity_pts,
            "consistency": consistency_pts
        }
    }

    session = sessions.get(state["session_id"])
    if session:
        black_swan = session.get("black_swan_insight", "")
        if black_swan:
            report["black_swan_insight"] = black_swan
        
        session["final_report"] = report
        session["verdict"] = verdict_text
        session["verdict_parts"] = verdict_parts

        # Phase 3: Persist pitch to vector DB (fire-and-forget)
        try:
            from services.db import save_pitch_history
            asyncio.create_task(save_pitch_history(
                session_id=state["session_id"],
                pitch_summary=state.get("pitch_summary", ""),
                verdict_parts=verdict_parts,
                confidence_score=confidence_score
            ))
        except Exception as e:
            print(f"[DB] Pitch save skipped: {e}")
        
    return {"action": "end_session", "final_report": report}

async def handle_interrupt_node(state: FocusGroupState):
    session = sessions.get(state["session_id"], {})
    msg = session.get("interrupt_message", "Manual interruption")
    last_agent_id = state.get("last_persona_used", "interviewer")

    await safe_queue_put(session, sse_event("speech_stop", {
        "reason": "user_interrupt",
        "agent_id": last_agent_id
    }))
        
    import random
    acks = [
        "Looks like the pitcher wants to jump in. Go ahead.",
        "Wait, we have an interjection. Let's hear it.",
        "Ah, the founder has something to add. Please continue.",
        "Hold on, I see the founder jumping in."
    ]
    ack_text = random.choice(acks)
    
    agent = AGENTS_CONFIG.get(last_agent_id, AGENTS_CONFIG["vc"])
    
    ack_turn = {
        "type": "persona_response",
        "agent_id": last_agent_id,
        "agent_name": agent["name"],
        "content": ack_text
    }
    
    session["is_speaking"] = False
    
    return {
        "conversation": [ack_turn],
        "pitcher_interrupt": False,
        "awaiting_user_input": True, 
        "pitcher_message": msg,
        "is_speaking": False,
        "action": "ask_pitcher"
    }

async def generate_verdict_text(strengths, risks, claims, contradictions, confidence_score, mode, provider):
    prompt = f"""Generate a professional, decisive verdict for this startup pitch evaluation.

ANALYSIS DATA:
- Strengths: {len(strengths)}
- Risks: {len(risks)}
- Claims: {len(claims)}
- Contradictions: {len(contradictions)}
- Confidence Score: {confidence_score}/100

MODE: {mode}

You MUST output ONLY a valid JSON object matching this exact schema, with NO markdown formatting:
{{
    "strongest_point": "string",
    "biggest_weakness": "string",
    "fix_before_next_pitch": "string",
    "investment_score": float,
    "recommendation": "string"
}}"""

    try:
        verdict_json = await llm_provider.generate_response(
            "You are a professional startup judge. Output pure JSON.", prompt, provider, stream=False
        )
        json_data = extract_json(verdict_json)
        verdict_obj = VerdictSchema(**json_data)
        
        verdict_str = f"Recommendation: {verdict_obj.recommendation} (Score: {verdict_obj.investment_score}/10)\n\n" \
                      f"This idea shows strong potential but we noted some areas of improvement. See the detailed breakdown."
        
        parts = {
            "strongest": verdict_obj.strongest_point,
            "weakness": verdict_obj.biggest_weakness,
            "fix": verdict_obj.fix_before_next_pitch
        }
        return verdict_str, parts
    except Exception as e:
        return "Evaluation completed.", {
            "strongest": "", "weakness": "", "fix": ""
        }

async def generate_report_charts(strength_score, risk_score, clarity_score, confidence_score):
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        import io
        import base64

        charts = {}

        fig, ax = plt.subplots(figsize=(8, 5))
        categories = ['Strength', 'Risk', 'Clarity', 'Confidence']
        values = [strength_score, risk_score, clarity_score, confidence_score]
        colors = ['green', 'red', 'blue', 'orange']

        bars = ax.bar(categories, values, color=colors, alpha=0.7)
        ax.set_ylim(0, 10)
        ax.set_ylabel('Score (1-10)')
        ax.set_title('Pitch Evaluation Scores')
        ax.grid(axis='y', alpha=0.3)

        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                   f'{value}', ha='center', va='bottom', fontweight='bold')

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        charts['bar_chart'] = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(6, 6))
        sizes = [strength_score, risk_score]
        labels = ['Strength', 'Risk']
        colors = ['#4CAF50', '#F44336']

        if sum(sizes) > 0:
            ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
            ax.set_title('Strength vs Risk Balance')
            ax.axis('equal')

            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
            buf.seek(0)
            charts['pie_chart'] = base64.b64encode(buf.read()).decode('utf-8')
            plt.close(fig)
        else:
            charts['pie_chart'] = None

        return charts
    except Exception:
        return {"bar_chart": None, "pie_chart": None}

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
            domain_data = extract_json(domain_json_str)
        except Exception:
            domain_data = {"sub_domain": "General Tech", "panel_mode": "standard"}

        if mode == "spark":
            active_panel = ["enthusiastic", "beginner", "vc", "expert"]
        elif mode == "reality":
            active_panel = ["hostile", "expert", "vc", "beginner"]
        else:
            active_panel = ["vc", "expert", "enthusiastic", "hostile"]

        domain_data["active_panel"] = active_panel
        session["domain"] = domain_data
        session["active_panel"] = active_panel
        yield sse_event("domain_classified", {**domain_data, "active_panel": active_panel, "mode": mode})

    _panel_from_session = session.get("active_panel", [])
    
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
        "is_speaking": False,
        "pending_answer": "",
        "refined_pitch": "",
        "awaiting_pitch_confirmation": False,
        "memory": { "claims": [], "risks": [], "strengths": [], "contradictions": [], "opinions": [], "covered_topics": [] },
        "agent_memory": {
            agent_id: {
                "claims": [], "risks": [], "strengths": [], "contradictions": [], "opinions": [],
                "concerns": [], "agent_opinions": [], "disagreements": []
            }
            for agent_id in _panel_from_session
        },
        "reflection": { "missing": [], "confidence": 0.0, "should_continue": True },
        "conversation": []
    }
    
    graph = build_agentic_graph(
        pitch_refiner_node, controller_node, persona_node, pitcher_node,
        tool_node, reflection_node, final_node, memory_update_node,
        handle_interrupt_node
    )

    _SENTINEL = object()
    queue: asyncio.Queue = asyncio.Queue()
    yielded_start = False

    session["sse_queue"] = queue

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
                    "agent_memory",
                    "memory_history"
                ]:
                    if key in update:
                        if key == "memory_history":
                            if key not in session: session[key] = []
                            session[key].extend(update[key])
                        elif key in ["memory", "agent_memory"]:
                            curr_val = json.dumps(session.get(key, {}), sort_keys=True)
                            new_val  = json.dumps(update[key], sort_keys=True)
                            
                            if curr_val != new_val:
                                if key == "agent_memory":
                                    existing = session.get("agent_memory", {})
                                    for aid, data in update["agent_memory"].items():
                                        if aid not in existing:
                                            existing[aid] = data
                                        else:
                                            if isinstance(data, dict):
                                                for k, v in data.items():
                                                    if isinstance(v, list):
                                                        if k not in existing[aid]: existing[aid][k] = []
                                                        for item in v:
                                                            if item not in existing[aid][k]:
                                                                existing[aid][k].append(item)
                                                    else:
                                                        existing[aid][k] = v
                                    session["agent_memory"] = existing
                                else:
                                    session[key] = update[key]
                                    
                                await queue.put(sse_event("memory_update", {
                                    "memory": session.get("memory", {}),
                                    "agent_memory": session.get("agent_memory", {}),
                                    "memory_history": session.get("memory_history", [])
                                }))
                        else:
                            session[key] = update[key]

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
    session["graph_task"] = graph_task
    try:
        while True:
            item = await queue.get()
            if item is _SENTINEL: break
            yield item
    finally:
        session["sse_queue"] = None
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

    # In normal flow, final_node has already populated session["verdict"] and
    # session["verdict_parts"]. This function is now a safety-net fallback
    # for legacy / interrupted sessions that arrive here without them.
    full_verdict = session.get("verdict")
    parts = session.get("verdict_parts", {"strongest": "", "weakness": "", "fix": ""})

    if full_verdict and any(parts.values()):
        yield sse_event("verdict_complete", {"verdict": full_verdict, "parts": parts, "session_id": session_id})
        return

    # Fallback path: regenerate structured verdict using VerdictSchema
    if not full_verdict:
        transcript = build_conversation_context(session)
        user_input = f"PITCH SUMMARY:\n{session['pitch_summary']}\n\nTRANSCRIPT:\n{transcript}"
        full_verdict, parts = await generate_verdict_text(
            session.get("memory", {}).get("strengths", []),
            session.get("memory", {}).get("risks", []),
            session.get("memory", {}).get("claims", []),
            session.get("memory", {}).get("contradictions", []),
            session.get("final_report", {}).get("confidence_score", 50),
            session.get("mode", "venture"),
            provider,
        )
        session["verdict"] = full_verdict
        session["verdict_parts"] = parts

    yield sse_event("verdict_complete", {"verdict": full_verdict, "parts": parts, "session_id": session_id})

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
