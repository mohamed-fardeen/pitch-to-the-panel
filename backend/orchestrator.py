import json
import asyncio
import os
from prompts import AGENT_PROMPTS
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

async def run_round1(session_id: str, session: dict, pitch: str, provider: str, pitcher_id: str = None):
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
      "domain": "tech|food_beverage|retail|services|agriculture|education|healthcare|manufacturing|creative|social_impact|physical_product|other",
      "sub_domain": "specific one-line description e.g. 'chai franchise' or 'handloom textiles'",
      "is_tech_primary": true,
      "is_physical_product": false,
      "business_model": "b2c|b2b|b2b2c|marketplace|franchise|subscription|other",
      "target_customer": "one sentence describing the actual end customer",
      "key_metrics": ["3 most important success metrics for THIS business type"],
      "likely_competitors": ["2-3 real competitor names specific to this domain"],
      "panel_mode": "standard|design|physical_product|non_tech"
    }

    panel_mode rules:
    - standard: tech/software/app/SaaS pitches
    - design: brand identity, UI/UX, graphic design, typography pitches  
    - physical_product: any pitch for a physical manufactured item
    - non_tech: food, retail, services, agriculture, hospitality, events
    """
    
    try:
        domain_json_str = await llm_provider.generate_response(domain_prompt, summary, provider, stream=False)
        start_idx = domain_json_str.find("{")
        end_idx = domain_json_str.rfind("}") + 1
        domain_data = json.loads(domain_json_str[start_idx:end_idx])
    except Exception:
        domain_data = {
            "sub_domain": "Tech Startup", "is_tech_primary": True, 
            "business_model": "b2b", "target_customer": "general", 
            "key_metrics": ["revenue"], "likely_competitors": [], 
            "panel_mode": "standard"
        }
    
    yield {
        "event": "hitl_summary_approval",
        "data": json.dumps({
            "summary": summary,
            "domain": domain_data,
            "session_id": session_id,
            "message": "Is this what you meant? Correct anything before the panel sees it."
        })
    }

    # WAIT FOR HUMAN IN THE LOOP APPROVAL
    await session["events"]["summary_approved"].wait()

    # The user may have updated the pitch/summary in the HITL state
    final_pitch = session["hitl_data"].get("corrected_summary")
    if not final_pitch:
        final_pitch = summary
        
    yield {
        "event": "domain_classified",
        "data": json.dumps(domain_data)
    }

    domain_context = f"""
    DOMAIN CONTEXT — calibrate your response to this specific business type:
    Business type: {domain_data.get('sub_domain')}
    Is primarily tech: {domain_data.get('is_tech_primary')}  
    Business model: {domain_data.get('business_model')}
    Target customer: {domain_data.get('target_customer')}
    Key success metrics: {', '.join(domain_data.get('key_metrics', []))}
    
    Evaluate as an expert in THIS type of business. Do NOT apply generic tech startup logic to a non-tech business.
    """

    session["summary"] = final_pitch
    session["domain"] = domain_data

    # Feature 5: Inject Memory
    if pitcher_id:
        memory = load_pitcher_memory(pitcher_id)
        if memory:
            yield { "event": "returning_pitcher", "data": json.dumps(memory) }
            memory_context = f"PITCHER HISTORY:\nThis pitcher has used this platform before ({memory.get('pitch_count')} previous pitch(es)).\nPrevious pitch summary: {memory.get('last_pitch_summary')}\nWeakness identified last time: {memory.get('weaknesses')}\nIf relevant, acknowledge their progress.\n"
            domain_context = f"{memory_context}\n\n{domain_context}"

    # Feature 9: Operator Agent Panel Selection
    panel_mode = domain_data.get("panel_mode", "standard")
    
    if panel_mode == "design":
        active_panel = PANEL_AGENTS_DESIGN
    elif panel_mode in ["non_tech", "physical_product"]:
        active_panel = PANEL_AGENTS_NON_TECH
    else:
        active_panel = PANEL_AGENTS_STANDARD
        
    session["active_panel"] = active_panel

    session_round1 = {}
    
    for agent_index, agent_key in enumerate(active_panel):
        system_prompt = AGENT_PROMPTS.get(agent_key, "")
        
        # Design Mode Overrides for standard agent slots
        if panel_mode == "design":
            if agent_key == "expert":
                system_prompt = AGENT_PROMPTS.get("dr_iyer_design", system_prompt)
            elif agent_key == "competitor":
                system_prompt = AGENT_PROMPTS.get("meera_design", system_prompt)
        
        previous_responses = ""
        for prev_key in active_panel[:agent_index]:
            if prev_key in session_round1:
                previous_responses += f"[{prev_key.upper()}]: {session_round1[prev_key]}\n\n"
        
        cross_ref_instruction = ""
        if agent_index > 0:
            cross_ref_instruction = f"""
            PREVIOUS PANEL RESPONSES (read these before responding):
            {previous_responses}
            
            IMPORTANT: You MUST directly address at least one point made above.
            Use their name: "The VC said X but..." or "Building on Priya's point..."
            This is a live debate, not independent reports.
            """
            
        user_prompt = f"{domain_context}\n\nHere is the startup pitch:\n\n{final_pitch}\n\n{cross_ref_instruction}"

        if agent_key == "competitor":
            yield {"event": "competitor_research_complete", "data": json.dumps({"status": "Meera is searching the web..."})}
            competitor_data = await search_competitors(domain_data)
            if competitor_data:
                user_prompt = f"{competitor_data}\n\n{user_prompt}"

        agent_full_text = ""
        try:
            stream = await llm_provider.generate_response(system_prompt, user_prompt, provider, stream=True)
            async for chunk in stream:
                agent_full_text += chunk
                yield {
                    "event": "message",
                    "data": json.dumps({"agent": agent_key, "chunk": chunk, "state": "streaming"})
                }
            
            session_round1[agent_key] = agent_full_text
            yield {
                "event": "message",
                "data": json.dumps({"agent": agent_key, "chunk": "", "state": "done"})
            }
        except Exception as e:
            session_round1[agent_key] = f"Error: {str(e)}"
            yield {
                "event": "error",
                "data": json.dumps({"agent": agent_key, "error": str(e)})
            }

async def generate_question_selection(pitch: str, round1_responses: dict, provider: str) -> dict:
    available_agents = list(round1_responses.keys())
    agent_keys_str = ", ".join(available_agents)
    
    system_prompt = f"""You are an orchestrator agent. Your job is to read the startup pitch and all panel responses.
Identify the single most pressing, difficult, or highest-stakes unresolved objection among the agents.
Then, select the agent who is best suited to ask that question directly to the pitcher.

Output JSON only, in this format:
{{
  "selected_agent": "agent_key",
  "question": "The exact wording of the question to ask the pitcher"
}}

The available agent_keys are: {agent_keys_str}.
Do not include any other text except the JSON."""

    responses_text = "\n\n".join([f"[{k.upper()}]\n{v}" for k, v in round1_responses.items()])
    user_prompt = f"PITCH:\n{pitch}\n\nAGENT RESPONSES:\n{responses_text}"
    
    try:
        response = await llm_provider.generate_response(system_prompt, user_prompt, provider, stream=False)
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0].strip()
        else:
            json_str = response.strip()
        data = json.loads(json_str)
        return data
    except Exception as e:
        return {
            "selected_agent": "vc",
            "question": "Can you explain how you plan to monetize this, specifically naming your first paying customer?"
        }

async def run_round2(pitch: str, answer: str, round1_responses: dict, provider: str):
    active_panel = list(round1_responses.keys())
    
    async def generate_for_agent(agent_key: str):
        system_prompt = AGENT_PROMPTS[agent_key]
        round1 = round1_responses.get(agent_key, "")
        user_prompt = f"Original Pitch: {pitch}\n\nYour previous response: {round1}\n\nPitcher's live answer to the panel's pressing question: {answer}\n\nRespond to their answer in 2-3 sentences max."
        
        try:
            stream = await llm_provider.generate_response(system_prompt, user_prompt, provider, stream=True)
            async for chunk in stream:
                yield {
                    "event": "message",
                    "data": json.dumps({"agent": agent_key, "chunk": chunk, "state": "streaming"})
                }
            yield {
                "event": "message",
                "data": json.dumps({"agent": agent_key, "chunk": "", "state": "done"})
            }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"agent": agent_key, "error": str(e)})
            }

    queue = asyncio.Queue()
    async def consume_stream(agent_key):
        async for item in generate_for_agent(agent_key):
            await queue.put(item)
    
    tasks = [asyncio.create_task(consume_stream(agent)) for agent in active_panel]
    
    async def monitor_tasks():
        await asyncio.gather(*tasks)
        await queue.put(None)
        
    asyncio.create_task(monitor_tasks())
    
    while True:
        item = await queue.get()
        if item is None:
            break
        yield item

async def generate_verdict(pitch: str, answer: str, round1: dict, round2: dict, provider: str) -> str:
    system_prompt = AGENT_PROMPTS.get("judge", "You are the judge.")
    
    r1_text = "\n\n".join([f"[{k.upper()}]\n{v}" for k, v in round1.items()])
    r2_text = "\n\n".join([f"[{k.upper()}]\n{v}" for k, v in round2.items()])
    
    user_prompt = f"PITCH:\n{pitch}\n\nROUND 1 RESPONSES:\n{r1_text}\n\nPITCHER'S LIVE ANSWER:\n{answer}\n\nROUND 2 RESPONSES:\n{r2_text}\n\nGenerate the final 3-part verdict."
    
    response = await llm_provider.generate_response(system_prompt, user_prompt, provider, stream=False)
    return response

async def generate_fact_check(agent_claim: str, challenge: str, provider: str) -> str:
    FACT_CHECK_PROMPT = "You are a neutral fact-checker. Respond in 2 sentences about this claim."
    user_prompt = f"Agent claim: {agent_claim}\nPitcher challenge: {challenge}"
    return await llm_provider.generate_response(FACT_CHECK_PROMPT, user_prompt, provider, stream=False)

async def generate_pushback_verdict(pitch: str, answer: str, round1: dict, round2: dict, pushback: str, provider: str) -> str:
    system_prompt = AGENT_PROMPTS.get("judge", "You are the judge.")
    
    r1_text = "\n\n".join([f"[{k.upper()}]\n{v}" for k, v in round1.items()])
    r2_text = "\n\n".join([f"[{k.upper()}]\n{v}" for k, v in round2.items()])
    
    user_prompt = f"PITCH:\n{pitch}\n\nROUND 1 RESPONSES:\n{r1_text}\n\nPITCHER'S LIVE ANSWER:\n{answer}\n\nROUND 2 RESPONSES:\n{r2_text}\n\nTHE PITCHER PUSHED BACK WITH:\n{pushback}\n\nGenerate an adjusted 3-part verdict."
    return await llm_provider.generate_response(system_prompt, user_prompt, provider, stream=False)
