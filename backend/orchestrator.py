import json
import asyncio
import os
from typing import AsyncGenerator, Tuple, Dict, List, Optional
from prompts import (
    DIFFICULTY_MODIFIERS,
    CONTROLLER_PROMPT,
    REFLECTION_PROMPT,
    PERSONA_FOCUS_GROUP_PROMPT,
    PITCH_REFINER_PROMPT,
    FINAL_ANALYST_PROMPT,
    BLACK_SWAN_PROMPT,
    OCEAN_PROFILES,
    PERSONA_ANCHORS
)
import prompts # For direct access to tool prompts if needed
from services.llm import llm_provider
from graph import FocusGroupState, build_agentic_graph
from pydantic import BaseModel, validator
from typing import Literal, Optional, AsyncGenerator, Tuple, Dict, List

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
        "type": "pitcher_interrupt",
        "agent_name": "Pitcher",
        "content": msg
    }
    
    print(f"[INTERRUPT] pitcher jumped in: '{msg[:80]}'")
    return {
        "conversation": [new_turn],
        "pitcher_interrupt": False,
        "pitcher_message": "",
        "awaiting_user_input": False,
        "input_type": "interrupt"
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

async def safe_wait(event):
    if not event.is_set():
        await event.wait()
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
            lines.append(f"{name} asked: {content}")
        elif t == "tool_output":
            lines.append(f"{name}: {content}")
    
    return "\n".join(lines)

# --- V3 LANGGRAPH NODES (REMOVED) ---

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

# --- REMOVED V3 NODES ---

# --- ORCHESTRATOR ---

# --- AGENTIC V4 NODES ---

async def pitch_refiner_node(state: FocusGroupState):
    """Refines the initial pitch for better analysis."""
    # Check for interrupt
    if state.get("pitcher_interrupt"):
        return {"pitcher_interrupt": False}

    if state.get("awaiting_pitch_confirmation"):
        session = sessions.get(state["session_id"])

        if session:
            await safe_wait(session["events"]["summary_approved"])
            
            # Use the corrected summary from HITL if available
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

    # FIRST ENTRY: Generate refined pitch
    prompt = PITCH_REFINER_PROMPT.format(pitch=state['pitch_summary'])
    
    refined = await llm_provider.generate_response(
        "You are a professional startup pitch editor.", prompt, state["provider"], stream=False
    )
    
    # Store in session so the hitl/approve endpoint can find it
    session = sessions.get(state["session_id"])
    if session:
        if "hitl_data" not in session: session["hitl_data"] = {}
        session["hitl_data"]["summary"] = refined # frontend expects .summary
        session["refined_pitch"] = refined
        
        # We also need to clear the wait event for the next pass
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

    # Handle wait for user input (Answers and Pitcher Responses)
    if state.get("awaiting_user_input"):
        session = sessions.get(state["session_id"])

        if session:
            # Poll with short timeouts instead of blocking indefinitely.
            # This prevents the SSE connection from going silent and timing out.
            event = session["events"]["answer_event"]
            while not event.is_set():
                # Check for session end signal
                if session.get("action") == "end_session":
                    return {"action": "end_session", "awaiting_user_input": False}
                try:
                    await asyncio.wait_for(asyncio.shield(event.wait()), timeout=5.0)
                except asyncio.TimeoutError:
                    pass  # Heartbeats are sent by the stream loop; just keep polling.
            event.clear()

            ans = session.get("pending_answer", "")
            session["pending_answer"] = ""

            conv_update = {
                "type": "pitcher_response",
                "agent_name": "Pitcher",
                "content": ans
            }
            
            # We don't return immediately! We append it to state locally so the LLM prompt sees it.
            if "conversation" not in state:
                state["conversation"] = []
            state["conversation"].append(conv_update)
            
            # We record the updates needed for the graph
            state_updates = {
                "conversation": [conv_update],
                "awaiting_user_input": False,
                "input_type": "answer"
            }
        else:
            state_updates = {}
    else:
        state_updates = {}

    # --- STEP 0 HARD GUARD ---
    if state.get("step_count", 0) == 0:
        print("[CONTROLLER] Initializing step 0 → forcing ask_persona")
        return {
            "action": "ask_persona",
            "action_input": {"target": "vc"},
            "step_count": 1
        }

    # Use reflection to detect natural completion
    reflection = state.get("reflection", {})
    if (
        not reflection.get("should_continue", True)
        and reflection.get("confidence", 0.0) >= 0.8
    ):
        return {
            "action": "end_session",
            "action_input": {},
            "action_history": ["end_session"],
            "step_count": state.get("step_count", 0) + 1
        }

    context = build_conversation_context({"conversation": state.get("conversation", [])}, last_n=10)
    history_str = ", ".join(state.get("action_history", [])[-5:])

    formatted_prompt = CONTROLLER_PROMPT.format(
        last_persona_used=state.get("last_persona_used", "none"),
        action_history=history_str,
        context=context,
        memory=json.dumps(state.get("memory", {})),
        reflection=json.dumps(state.get("reflection", {})),
        input_type=state.get("input_type", ""),
        step_count=state.get("step_count", 0)
    )

    try:
        response = await llm_provider.generate_response(
            formatted_prompt, "Decide the next action.", state["provider"], stream=False
        )
        # Strip markdown code fences if present
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]

        start = clean.find("{")
        end = clean.rfind("}") + 1
        raw_dict = json.loads(clean[start:end])

        # Validate via Pydantic
        decision = ControllerDecision(**raw_dict)

        action = decision.action
        action_input = decision.input or {}

        # Validate target
        valid_personas = list(AGENTS_CONFIG.keys())
        action_input["target"] = decision.target if decision.target in valid_personas else "vc"

        # If tool specified inside input, enforce use_tool action
        if action_input.get("tool") and action_input["tool"] in ["search", "fact_check"]:
            action = "use_tool"

        print(f"[CONTROLLER] step={state.get('step_count', 0)} action={action} target={action_input.get('target', 'n/a')} reason={decision.reason[:60]}")

        final_update = {
            "action": action,
            "action_input": action_input,
            "action_history": [action],
            "step_count": state.get("step_count", 0) + 1
        }
        final_update.update(state_updates)
        return final_update

    except Exception as e:
        print(f"[CONTROLLER ERROR] Fallback engaged: {e}")
        # Graceful fallback — iterate through all valid personas if JSON crashes
        fallback_personas = list(AGENTS_CONFIG.keys())
        last_used = state.get("last_persona_used", "")
        # Find index of last_used, or default to -1 so we start at 0
        try:
            last_idx = fallback_personas.index(last_used)
        except ValueError:
            last_idx = -1
            
        next_persona = fallback_personas[(last_idx + 1) % len(fallback_personas)]
        fallback_update = {
            "action": "ask_persona",
            "action_input": {"target": next_persona},
            "action_history": ["ask_persona"],
            "step_count": state.get("step_count", 0) + 1
        }
        fallback_update.update(state_updates)
        return fallback_update

async def persona_node(state: FocusGroupState):
    """Executes a single persona response."""
    session = sessions.get(state["session_id"], {})
    
    interrupt_result = handle_interrupt_if_present(state, session)
    if interrupt_result:
        return interrupt_result

    target = state["action_input"].get("target", "vc")
    agent_config = AGENTS_CONFIG.get(target, AGENTS_CONFIG["vc"])
    print(f"[PERSONA] agent={target} step={state.get('step_count', 0)}")
    
    context = build_conversation_context({"conversation": state["conversation"]}, last_n=8)
    recent_turns = [t for t in state.get("conversation", []) if t.get("type") == "persona_response"][-3:]
    recent_discussion = "\n".join([f"{t['agent_name']}: {t['content']}" for t in recent_turns])
    
    ocean = OCEAN_PROFILES.get(target, OCEAN_PROFILES.get("vc", {}))
    behavior_text = map_ocean_to_behavior(ocean)
    persona_anchor = PERSONA_ANCHORS.get(target, agent_config.get("system_prompt", ""))

    difficulty_instruction = DIFFICULTY_MODIFIERS.get(state.get("difficulty", "standard"), DIFFICULTY_MODIFIERS["standard"])["reaction"]

    prompt = PERSONA_FOCUS_GROUP_PROMPT.format(
        persona_anchor=persona_anchor,
        behavior=behavior_text,
        core_bias=ocean.get("core_bias", ""),
        hidden_objection=ocean.get("hidden_objection", ""),
        episodic_memory=ocean.get("episodic_memory", ""),
        pitch_summary=state["pitch_summary"],
        question=state["action_input"].get("question", "What is your perspective on this pitch component?"),
        recent_discussion=recent_discussion,
        conversation_so_far=context,
        difficulty_instruction=difficulty_instruction
    )
    try:
        response = await llm_provider.generate_response(
            f"Respond as {agent_config.get('name')}.", prompt, state["provider"], stream=False
        )
    except Exception as e:
        print(f"[PERSONA ERROR] Agent {target} crashed: {e}")
        response = "That is an interesting point. Let me think about its implications."
    
    new_turn = {
        "type": "persona_response",
        "agent_id": target,
        "agent_name": agent_config["name"],
        "content": response
    }
    
    return {
        "conversation": [new_turn],
        "last_persona_used": target
    }

async def pitcher_node(state: FocusGroupState):
    """Asks the pitcher a question."""
    if state.get("awaiting_user_input"):
        return {"status": "waiting"}
    
    session = sessions.get(state["session_id"], {})
    
    interrupt_result = handle_interrupt_if_present(state, session)
    if interrupt_result:
        return interrupt_result
    
    if state.get("awaiting_user_input"):
        return {} # Wait

    target_persona = state["action_input"].get("target", "interviewer")
    agent_name = AGENTS_CONFIG.get(target_persona, {"name": "The Interviewer"})["name"]
    
    # Lead-in question or direct question from action_input
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
        "input_type": "answer"
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
                # Summarize the search results using the search tool prompt
                result_content = await llm_provider.generate_response(
                    prompts.SEARCH_TOOL_PROMPT,
                    f"Query: {query}\n\nSearch Results:\n{raw_results}",
                    state["provider"],
                    stream=False
                )
            except Exception as e:
                result_content = f"Search failed: {str(e)}"
        else:
            result_content = "Search tool not configured. Tavily API key missing."
    else:  # fact_check
        formatted_prompt = prompts.FACT_CHECK_PROMPT.format(claim=query)
        result_content = await llm_provider.generate_response(
            "You are a neutral fact-checker. Output only in the specified format.",
            formatted_prompt,
            state["provider"],
            stream=False
        )
        source = "Internal Analysis"

    tool_result = {
        "type": tool_type,
        "content": result_content,
        "source": source
    }
    
    new_turn = {
        "type": "tool_output",
        "agent_name": "Research Tool",
        "content": f"[{tool_type.upper()}] {result_content} (Source: {source})"
    }
    
    return {
        "conversation": [new_turn]
    }

async def memory_update_node(state: FocusGroupState):
    """
    Dedicated memory update node. Runs after persona or tool turns.
    Reads the last conversation turn and extracts signals into memory.
    Keeps memory extraction centralized and consistent.
    """
    conversation = state.get("conversation", [])

    if not conversation:
        return {"memory": state.get("memory", {})}

    last_turn = conversation[-1]

    # Only update memory for substantive content turns
    if last_turn.get("type") not in ["persona_response", "tool_output", "pitcher_response"]:
        return {"memory": state.get("memory", {})}

    try:
        updated_memory = await update_memory(state, last_turn)

        if not isinstance(updated_memory, dict):
            updated_memory = state.get("memory", {})

        return {"memory": updated_memory}

    except Exception as e:
        print(f"[MEMORY ERROR]: {e}")
        return {"memory": state.get("memory", {})}

async def update_memory(state: FocusGroupState, new_turn: dict) -> dict:
    """Extracts risks, strengths, claims, and contradictions from a turn into memory."""
    base_memory = state.get("memory")

    if not isinstance(base_memory, dict):
        base_memory = {
            "claims": [],
            "risks": [],
            "strengths": [],
            "contradictions": []
        }

    new_memory = base_memory.copy()
    
    content = str(new_turn.get("content", "")).lower()
    original = str(new_turn.get("content", ""))
    agent = new_turn.get("agent_name", "Unknown")

    # Ensure all list keys exist
    for key in ["claims", "risks", "strengths", "contradictions"]:
        if key not in new_memory:
            new_memory[key] = []

    # RISKS — expanded signal set
    risk_signals = [
        "risk", "concern", "problem", "weakness", "threat", "danger",
        "won't work", "will not work", "not scalable", "can't scale",
        "regulatory", "compliance", "liability", "churn", "burn",
        "competition will", "already exists", "no moat", "commoditized"
    ]
    if any(k in content for k in risk_signals):
        new_memory["risks"].append({
            "agent": agent,
            "content": original,
            "turn_type": new_turn.get("type", "")
        })

    # STRENGTHS — expanded signal set
    strength_signals = [
        "strength", "advantage", "benefit", "strong", "moat",
        "genuinely", "impressed", "works well", "real pain", "traction",
        "paying", "customers already", "retention", "growth",
        "defensible", "unique", "differentiated"
    ]
    if any(k in content for k in strength_signals):
        new_memory["strengths"].append({
            "agent": agent,
            "content": original,
            "turn_type": new_turn.get("type", "")
        })

    # CLAIMS — factual statements that may need verification
    claim_signals = [
        "market is", "market size", "worth", "billion", "million users",
        "studies show", "research shows", "proven", "according to",
        "%", "percent", "cagr", "tam", "industry"
    ]
    if any(k in content for k in claim_signals):
        new_memory["claims"].append({
            "agent": agent,
            "content": original,
            "needs_verification": True
        })

    # CONTRADICTIONS — direct disagreements between panelists
    contradiction_signals = [
        "disagree", "actually", "that's not", "that is not",
        "wrong about", "incorrect", "on the contrary",
        "i would push back", "push back on", "but ravi", "but priya",
        "but arjun", "but meera", "but dr. iyer", "but kiran"
    ]
    if any(k in content for k in contradiction_signals):
        new_memory["contradictions"].append({
            "agent": agent,
            "content": original,
            "turn_type": new_turn.get("type", "")
        })

    # Add Memory Limits (Demo Safe)
    MAX_ITEMS = 20
    for key in ["risks", "strengths", "claims", "contradictions"]:
        new_memory[key] = new_memory[key][-MAX_ITEMS:]

    return new_memory

async def reflection_node(state: FocusGroupState):
    """Analyzes conversation and updates reflection state."""
    session = sessions.get(state["session_id"], {})
    
    interrupt_result = handle_interrupt_if_present(state, session)
    if interrupt_result:
        return interrupt_result

    print(f"[REFLECTION] step={state.get('step_count', 0)} confidence={state.get('reflection', {}).get('confidence', 0)}")

    context = build_conversation_context({"conversation": state.get("conversation", [])})
    
    user_input = json.dumps({
        "conversation": context,
        "memory": state.get("memory", {})
    })
    
    try:
        # Fix for B6/B7: Don't use .format() on REFLECTION_PROMPT/FINAL_ANALYST_PROMPT
        response = await llm_provider.generate_response(
            REFLECTION_PROMPT, user_input, state["provider"], stream=False
        )
        
        start = response.find("{")
        end = response.rfind("}") + 1
        reflection_data = json.loads(response[start:end])
        
        return {
            "reflection": reflection_data,
            "last_reflection_step": state.get("step_count", 0)
        }
    except Exception as e:
        return {
            "last_reflection_step": state.get("step_count", 0)
        }

async def final_node(state: FocusGroupState):
    """Synthesizes final verdict and ends the session."""
    print(f"[FINAL] generating verdict for session={state.get('session_id')} turns={len(state.get('conversation', []))}")
    context = build_conversation_context({"conversation": state.get("conversation", [])})

    user_input = json.dumps({
        "conversation": context,
        "memory": state.get("memory", {}),
        "reflection": state.get("reflection", {})
    })

    try:
        # Fix for B7: Don't use .format() on FINAL_ANALYST_PROMPT
        response = await llm_provider.generate_response(
            FINAL_ANALYST_PROMPT, user_input, state["provider"], stream=False
        )
    except Exception as e:
        response = f"Evaluation error: {str(e)}"

    session = sessions.get(state["session_id"])
    if session:
        session["verdict"] = response

    return {"action": "end_session"}


# --- UPDATED ORCHESTRATOR ---

async def stream_echochamber(
    session_id: str,
    session: dict,
    provider: str,
    difficulty: str = "standard"
) -> AsyncGenerator[dict, None]:
    # --- Domain classification (moved from run_round1 into V4 flow) ---
    if not session.get("domain") or not session["domain"].get("panel_mode"):
        summary_prompt = "Summarize this startup pitch in 2-3 clear sentences focusing on the core problem, solution, and business model. Never use pleasantries."
        try:
            summary = await llm_provider.generate_response(summary_prompt, session["pitch_summary"], provider, stream=False)
        except Exception:
            summary = session["pitch_summary"][:200]

        domain_prompt = """Read this pitch summary and classify it. Output ONLY valid JSON, no other text:
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
}"""
        try:
            domain_json_str = await llm_provider.generate_response(domain_prompt, summary, provider, stream=False)
            start_idx = domain_json_str.find("{")
            end_idx = domain_json_str.rfind("}") + 1
            domain_data = json.loads(domain_json_str[start_idx:end_idx])
        except Exception:
            domain_data = {"sub_domain": "General Tech", "is_tech_primary": True, "panel_mode": "standard"}

        panel_mode = domain_data.get("panel_mode", "standard")
        if panel_mode == "design":
            active_panel = PANEL_AGENTS_DESIGN
        elif panel_mode in ["non_tech", "physical_product"]:
            active_panel = PANEL_AGENTS_NON_TECH
        else:
            active_panel = PANEL_AGENTS_STANDARD

        domain_data["active_panel"] = active_panel
        session["domain"] = domain_data
        session["active_panel"] = active_panel

        yield sse_event("domain_classified", {**domain_data, "active_panel": active_panel})

    initial_state: FocusGroupState = {
        "session_id": session_id,
        "pitch_summary": session["pitch_summary"],
        "domain": session["domain"], # now contains active_panel
        "difficulty": difficulty,
        "provider": provider,
        
        "action": "",
        "action_input": {},
        "action_history": [],
        "step_count": 0,
        "max_steps": 20,
        "last_reflection_step": 0,
        "last_persona_used": "",
        
        "input_type": "confirmation",
        "awaiting_user_input": False,
        "pitcher_interrupt": False,
        "pitcher_message": "",
        
        "refined_pitch": "",
        "awaiting_pitch_confirmation": False,
        
        "memory": { "claims": [], "risks": [], "strengths": [], "contradictions": [] },
        "reflection": { "missing": [], "confidence": 0.0, "should_continue": True },
        
        "conversation": []
    }
    
    print(f"[SESSION START] session_id={session_id} difficulty={difficulty} provider={provider}")
    print(f"[SESSION PITCH] {session['pitch_summary'][:100]}...")
    
    # Flags to prevent double-yielding
    yielded_start = False

    # Compile Graph
    graph = build_agentic_graph(
        pitch_refiner_node,
        controller_node,
        persona_node,
        pitcher_node,
        tool_node,
        reflection_node,
        final_node,
        memory_update_node
    )

    _SENTINEL = object()  # signals queue is done

    queue: asyncio.Queue = asyncio.Queue()

    async def run_graph():
        """Runs the LangGraph and pushes SSE events into the queue."""
        nonlocal yielded_start
        try:
            state_step_counter = 0
            async for event in graph.astream(initial_state):
                state_step_counter += 1
                node_name = list(event.keys())[0]
                update = event[node_name]
                print(f"[GRAPH] node={node_name} keys={list(update.keys()) if update else '[]'}")
                if not update:
                    continue

                import time
                await queue.put(sse_event("debug_node", {
                    "node": node_name,
                    "step": update.get("step_count") or state_step_counter,
                    "action": update.get("action") or None,
                    "target": (update.get("action_input") or {}).get("target") or None,
                    "memory_snapshot": {
                        "risks": len((update.get("memory") or session.get("memory", {}) or {}).get("risks", [])),
                        "strengths": len((update.get("memory") or session.get("memory", {}) or {}).get("strengths", [])),
                        "claims": len((update.get("memory") or session.get("memory", {}) or {}).get("claims", [])),
                        "contradictions": len((update.get("memory") or session.get("memory", {}) or {}).get("contradictions", [])),
                    },
                    "timestamp": time.time()
                }))

                # Sync critical flags from state → session
                for key in [
                    "awaiting_user_input",
                    "awaiting_pitch_confirmation",
                    "input_type",
                    "pitcher_interrupt",
                    "pitcher_message",
                    "action",
                    "action_input",
                    "memory"
                ]:
                    if key in update:
                        session[key] = update[key]

                if "conversation" in update:
                    for turn in update["conversation"]:
                        await queue.put(sse_event("agent_turn", turn))
                        session["conversation"].append(turn)

                if update.get("awaiting_user_input"):
                    conv_turns = update.get("conversation") or session.get("conversation", [])
                    last_turn = conv_turns[-1] if conv_turns else {}
                    await queue.put(sse_event("waiting_for_pitcher", {
                        "question": last_turn.get("content", "What is your response to the panel?"),
                        "agent_id": last_turn.get("agent_id", "interviewer")
                    }))

                if not yielded_start and (node_name == "controller" or "conversation" in update):
                    await queue.put(sse_event("echochamber_start", {
                        "session_id": session_id,
                        "message": "The panel is now analyzing your pitch...",
                        "personas": [
                            {"id": k, "name": v["name"], "role": v["role"], "avatar": v.get("avatarUrl", "")}
                            for k, v in AGENTS_CONFIG.items() if k in session.get("active_panel", [])
                        ]
                    }))
                    yielded_start = True

                if update.get("refined_pitch"):
                    await queue.put(sse_event("hitl_summary_approval", {
                        "session_id": session_id,
                        "summary": update["refined_pitch"],
                        "message": "I've refined your pitch for the panel. Does this look accurate?"
                    }))

                if update.get("action") == "end_session":
                    break

                turn_count = len(session.get("conversation", []))
                if turn_count > 40:
                    print(f"[SAFETY] Session {session_id} exceeded 40 turns. Forcing verdict.")
                    await queue.put(sse_event("status", {"message": "Wrapping up the panel discussion..."}))
                    break

        except Exception as e:
            print(f"[GRAPH ERROR] Session {session_id} crashed: {type(e).__name__}: {str(e)}")
            await queue.put(sse_event("error", {
                "message": "The panel encountered a technical issue. Generating your verdict from what was discussed.",
                "session_id": session_id
            }))
            if session.get("conversation"):
                async for ev in stream_verdict_from_conversation(session_id, session, provider):
                    await queue.put(ev)
        finally:
            await queue.put(_SENTINEL)

    async def send_heartbeats():
        """Sends periodic keepalive pings while waiting for pitcher input."""
        while True:
            await asyncio.sleep(8)
            if session.get("awaiting_user_input"):
                await queue.put(sse_event("heartbeat", {"status": "waiting_for_pitcher"}))

    graph_task = asyncio.create_task(run_graph())
    heartbeat_task = asyncio.create_task(send_heartbeats())

    try:
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            yield item
    finally:
        graph_task.cancel()
        heartbeat_task.cancel()
        try:
            await graph_task
        except asyncio.CancelledError:
            pass
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    # Final meta-analysis (verdict, black swan)
    async for event in stream_meta_analysis(session_id, session, provider):
        yield event

async def stream_meta_analysis(session_id: str, session: dict, provider: str):
    """Produces the Black Swan Report."""
    yield sse_event("status", {"message": "Meta-Analyst is uncovering non-obvious insights...", "phase": "meta_analysis"})
    
    context = build_conversation_context(session)
    formatted_prompt = BLACK_SWAN_PROMPT.format(
        conversation=context,
        memory=json.dumps(session.get("memory", { "claims": [], "risks": [], "strengths": [], "contradictions": [] }))
    )
    
    try:
        raw = await llm_provider.generate_response(
            formatted_prompt, "Uncover non-obvious insights.", provider, stream=False
        )
        # We assume the output format for Black Swan Insight is plain text/markdown 
        # as per the new persona prompt, but we'll try to keep it compatible with existing expectations.
        session["black_swan_insight"] = raw
        yield sse_event("black_swan_report", {"insight": raw})
    except Exception as e:
        yield sse_event("error", {"message": f"Black Swan analysis failed: {str(e)}"})
    
    # Generate Key Insights
    sys_prompt = "You are an expert analyst. Extract exactly 3 key insights from the panel discussion. Focus on: repeated concerns, strongest validation, major objections. Return exactly 3 short bullet points starting with a bullet character (•)."
    try:
        insights_raw = await llm_provider.generate_response(
            sys_prompt, context, provider, stream=False
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
    
    parts = parse_verdict_parts(full_verdict)
    session["verdict_parts"] = parts
    yield sse_event("verdict_complete", {"verdict": full_verdict, "parts": parts, "session_id": session_id})
    
    yield sse_event("verdict_pushback_available", {"session_id": session_id, "message": "You can push back on one part."})

def parse_verdict_parts(full_verdict: str) -> dict:
    """
    Parses the three verdict sections with tolerance for LLM header variations.
    Tries multiple known phrasings before giving up.
    """
    parts = {"strongest": "", "weakness": "", "fix": ""}

    # --- Strongest point ---
    strongest_markers = [
        "Your strongest point:",
        "Strongest point:",
        "Your strongest point is",
        "Strongest:",
        "Strong point:",
    ]
    weakness_markers = [
        "Your biggest weakness:",
        "Biggest weakness:",
        "Your biggest weakness is",
        "Weakness:",
        "Main weakness:",
    ]
    fix_markers = [
        "Before your next pitch:",
        "Before next pitch:",
        "Next step:",
        "Action item:",
        "Fix:",
        "One fix:",
    ]

    def extract_between(text, start_markers, end_markers):
        for start in start_markers:
            if start.lower() in text.lower():
                idx = text.lower().find(start.lower())
                after = text[idx + len(start):]
                for end in end_markers:
                    if end.lower() in after.lower():
                        end_idx = after.lower().find(end.lower())
                        return after[:end_idx].strip()
                # No end marker found — take until next double newline or end
                return after.split("\n\n")[0].strip()
        return ""

    def extract_after(text, start_markers):
        for start in start_markers:
            if start.lower() in text.lower():
                idx = text.lower().find(start.lower())
                after = text[idx + len(start):]
                return after.split("\n\n")[0].strip()
        return ""

    parts["strongest"] = extract_between(full_verdict, strongest_markers, weakness_markers)
    parts["weakness"] = extract_between(full_verdict, weakness_markers, fix_markers)
    parts["fix"] = extract_after(full_verdict, fix_markers)

    return parts

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
        "name": "Lead Strategist", 
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
