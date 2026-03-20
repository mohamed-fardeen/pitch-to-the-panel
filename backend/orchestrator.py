import json
import asyncio
import os
from prompts import (
    AGENT_PROMPTS, 
    QUESTION_GENERATOR_PROMPT, 
    REACTION_GENERATOR_PROMPT, 
    INTERRUPT_CHECK_PROMPT, 
    JUDGE_CONVERSATION_PROMPT,
    DIFFICULTY_MODIFIERS
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

async def generate_agent_question(session: dict, agent_id: str, provider: str, difficulty: str = "standard"):
    """Stream one sharp question from the current agent."""
    agent = AGENTS_CONFIG[agent_id]
    conversation_context = build_conversation_context(session)
    difficulty_instruction = DIFFICULTY_MODIFIERS.get(difficulty, DIFFICULTY_MODIFIERS["standard"])
    
    competitor_ctx = ""
    if agent_id == "competitor":
        yield sse_event("competitor_research_start", {"message": f"{agent['name']} is searching the web..."})
        try:
            competitor_ctx = await search_competitors(session["domain"]) + "\n\n"
        except Exception:
            pass
        yield sse_event("competitor_research_done", {})
        
    memory_ctx = ""
    if "pitcher_memory" in session:
        mem = session["pitcher_memory"]
        memory_ctx = f"PITCHER HISTORY:\nThis pitcher has pitched before ({mem.get('pitch_count')} times).\nPrevious pitch: {mem.get('last_pitch_summary')}\nWeakness last time: {mem.get('weaknesses')}\nIf relevant, acknowledge their progress.\n\n"
    
    system = QUESTION_GENERATOR_PROMPT.format(
        agent_name=agent["name"],
        difficulty_instruction=difficulty_instruction
    )
    
    user_message = f"""{memory_ctx}{competitor_ctx}PITCH SUMMARY:
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
    
    try:
        stream = await llm_provider.generate_response(system, user_message, provider, stream=True)
        async for text in stream:
            full_question += text
            yield sse_event("agent_token", {
                "agent_id": agent_id,
                "token": text,
                "type": "question"
            })
    except Exception as e:
        full_question = f"Error generating question: {str(e)}"
    
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

async def generate_agent_reaction(session: dict, agent_id: str, question: str, answer: str, provider: str, difficulty: str = "standard"):
    """Stream agent's reaction after pitcher answers."""
    agent = AGENTS_CONFIG[agent_id]
    difficulty_instruction = DIFFICULTY_MODIFIERS.get(difficulty, DIFFICULTY_MODIFIERS["standard"])
    system = REACTION_GENERATOR_PROMPT.format(
        agent_name=agent["name"],
        question=question,
        answer=answer,
        difficulty_instruction=difficulty_instruction
    )
    
    user_message = f"""Stay completely in character as {agent['name']}.
React honestly to what the pitcher just said.
1-2 sentences only. No new question. Pure reaction."""

    full_reaction = ""
    yield sse_event("agent_reaction_start", {
        "agent_id": agent_id,
        "name": agent["name"]
    })
    
    try:
        stream = await llm_provider.generate_response(system, user_message, provider, stream=True)
        async for text in stream:
            full_reaction += text
            yield sse_event("agent_token", {
                "agent_id": agent_id,
                "token": text,
                "type": "reaction"
            })
    except Exception as e:
        full_reaction = f"Error generating reaction: {str(e)}"
    
    # Store reaction in conversation log
    session["conversation"].append({
        "turn": len(session["conversation"]),
        "type": "reaction",
        "agent_id": agent_id,
        "agent_name": agent["name"],
        "content": full_reaction,
        "timestamp": str(asyncio.get_event_loop().time())
    })
    
    yield sse_event("agent_reaction_done", {
        "agent_id": agent_id,
        "reaction": full_reaction
    })

async def check_interrupt(session: dict, current_agent_id: str, question: str, answer: str, reaction: str, provider: str) -> dict | None:
    """Check if another agent should interrupt."""
    current_index = session["active_panel"].index(current_agent_id)
    if current_index >= len(session["active_panel"]) - 1:
        return None
    
    interrupt_count = sum(1 for t in session["conversation"] if t["type"] == "interrupt_q")
    if interrupt_count >= 2:
        return None
    
    conversation_so_far = build_conversation_context(session)
    prompt = INTERRUPT_CHECK_PROMPT.format(
        agent_name=AGENTS_CONFIG[current_agent_id]["name"],
        question=question,
        answer=answer,
        reaction=reaction,
        conversation_so_far=conversation_so_far
    )
    
    try:
        raw = await llm_provider.generate_response("You are a debate moderator. Output only valid JSON.", prompt, provider, stream=False)
        start = raw.find("{")
        end = raw.rfind("}") + 1
        result = json.loads(raw[start:end])
        
        if result.get("should_interrupt") and result.get("agent_id"):
            agent_id = result["agent_id"]
            if agent_id in session["active_panel"]:
                interrupting_agent_index = session["active_panel"].index(agent_id)
                if interrupting_agent_index > current_index:
                    return result
        return None
    except Exception:
        return None

async def stream_interrupt(session: dict, interrupt_data: dict):
    """Stream an interrupt question."""
    agent_id = interrupt_data["agent_id"]
    agent = AGENTS_CONFIG[agent_id]
    followup = interrupt_data["followup_question"]
    
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

async def stream_full_conversation(session_id: str, session: dict, provider: str, difficulty: str = "standard"):
    """Main hybrid conversation orchestrator."""
    yield sse_event("status", {
        "message": "Panel is ready. First question coming...",
        "phase": "conversation_start"
    })
    
    active_panel = session["active_panel"]
    
    for agent_index, agent_id in enumerate(active_panel):
        session["current_agent_index"] = agent_index
        session["current_agent_id"] = agent_id
        
        # STEP A: Agent asks question
        async for event in generate_agent_question(session, agent_id, provider, difficulty):
            yield event
        
        question = session["conversation"][-1]["content"]
        
        # STEP B: Wait for pitcher's answer
        session["events"]["answer_event"].clear()
        session["waiting_for"] = "answer"
        
        yield sse_event("waiting_for_answer", {
            "agent_id": agent_id,
            "agent_name": AGENTS_CONFIG[agent_id]["name"],
            "question": question,
            "agent_index": agent_index,
            "total_agents": len(active_panel),
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
            "timestamp": str(asyncio.get_event_loop().time())
        })
        
        yield sse_event("pitcher_answer_received", {"answer": answer, "agent_id": agent_id})
        
        # STEP C: Agent reacts
        async for event in generate_agent_reaction(session, agent_id, question, answer, provider, difficulty):
            yield event
        
        reaction = session["conversation"][-1]["content"]
        
        # STEP D: Interrupt check
        interrupt = await check_interrupt(session, agent_id, question, answer, reaction, provider)
        if interrupt:
            async for event in stream_interrupt(session, interrupt):
                yield event
            
            int_q = interrupt["followup_question"]
            int_id = interrupt["agent_id"]
            
            session["events"]["answer_event"].clear()
            session["waiting_for"] = "interrupt_answer"
            
            yield sse_event("waiting_for_answer", {
                "agent_id": int_id,
                "agent_name": AGENTS_CONFIG[int_id]["name"],
                "question": int_q,
                "is_interrupt": True,
                "session_id": session_id
            })
            
            await session["events"]["answer_event"].wait()
            int_a = session["pending_answer"]
            session["pending_answer"] = ""
            session["waiting_for"] = None
            
            session["conversation"].append({
                "turn": len(session["conversation"]),
                "type": "interrupt_a",
                "agent_id": "pitcher",
                "agent_name": "Pitcher",
                "content": int_a,
                "timestamp": str(asyncio.get_event_loop().time())
            })
            
            yield sse_event("interrupt_answer_received", {"answer": int_a, "agent_id": int_id})
        
        await asyncio.sleep(0.4)
    
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
    
    yield sse_event("agent_start", {"agent_id": "judge", "name": "The Judge", "role": "Verdict"})
    
    full_verdict = ""
    try:
        stream = await llm_provider.generate_response(JUDGE_CONVERSATION_PROMPT, user_input, provider, stream=True)
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

async def handle_verdict_pushback(session_id: str, pushback: str, provider: str):
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
async def run_round1(session_id: str, session: dict, pitch: str, provider: str, pitcher_id: str = None, difficulty: str = "standard"):
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
    async for event in stream_full_conversation(session_id, session, provider, difficulty):
        yield event
        
    if pitcher_id:
        save_pitcher_memory(pitcher_id, session, session.get("verdict_final") or session.get("verdict", ""))

async def generate_fact_check(agent_claim: str, challenge: str, provider: str) -> str:
    FACT_CHECK_PROMPT = "You are a neutral fact-checker. Respond in 2 sentences about this claim."
    user_prompt = f"Agent claim: {agent_claim}\nPitcher challenge: {challenge}"
    return await llm_provider.generate_response(FACT_CHECK_PROMPT, user_prompt, provider, stream=False)
