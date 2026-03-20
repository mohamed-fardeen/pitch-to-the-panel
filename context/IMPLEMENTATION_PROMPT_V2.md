# Pitch to the Panel — Implementation Prompt v2.0
# Everything BEYOND the existing PRD (v1.0)
# Use this prompt with Claude Code or any AI code editor
# Paste the entire thing as your first message

---

## CONTEXT — What already exists

You are building on top of an existing system documented in PRD v1.0.
The base system already has:

- FastAPI backend (main.py) with 6 agent system prompts + Judge agent
- SSE streaming of agent responses token by token
- In-memory session store
- Next.js frontend with agent card grid, sentiment meters, room temperature meter
- Pitch extraction → Round 1 → Question selection → Pitcher answer → Round 2 → Verdict flow
- Web Speech API voice input
- 3 demo scenarios pre-built

DO NOT rebuild what already exists.
Only add the new features described below.
Preserve all existing functionality.

---

## NEW FEATURES TO IMPLEMENT

Implement all of the following in order of priority.
Each feature is self-contained — build and test one before moving to the next.

---

### FEATURE 1 — Domain Classifier Agent (Priority: Critical)

**What it does:**
Before activating the panel, a lightweight classifier reads the pitch and
outputs a structured domain classification. This classification is injected
into every agent's context so they evaluate the pitch appropriately for
its domain — not as a generic tech startup.

**Implementation:**

Add to main.py:

```python
DOMAIN_CLASSIFIER_PROMPT = """
Read this pitch summary and classify it. Output ONLY valid JSON, no other text:

{
  "domain": "tech|food_beverage|retail|services|agriculture|education|
             healthcare|manufacturing|creative|social_impact|physical_product|other",
  "sub_domain": "specific one-line description e.g. 'chai franchise' or 'handloom textiles'",
  "is_tech_primary": true|false,
  "is_physical_product": true|false,
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
```

Add `async def classify_domain(pitch_summary: str) -> dict` function.
Call it after `extract_pitch_summary`, before Round 1.
Store result in session as `session["domain"]`.

Inject into every agent's user_message:
```
DOMAIN CONTEXT — calibrate your response to this specific business type:
Business type: {domain['sub_domain']}
Is primarily tech: {domain['is_tech_primary']}  
Business model: {domain['business_model']}
Target customer: {domain['target_customer']}
Key success metrics: {', '.join(domain['key_metrics'])}

Evaluate as an expert in THIS type of business.
Ask questions and raise objections relevant to THIS domain.
Do NOT apply generic tech startup logic to a non-tech business.
```

Emit new SSE event: `domain_classified` with the full domain object.
Frontend displays domain badge next to pitch summary.

---

### FEATURE 2 — Agent Cross-Referencing (Priority: Critical)

**What it does:**
Agents in Round 1 run sequentially. From Agent 2 onwards, each agent
reads all previous agents' responses and MUST directly reference at least
one. Creates real debate instead of isolated opinions.

**Implementation:**

In `stream_round1`, modify the user_message for agents after the first:

```python
# Build context of previous responses
previous_responses = ""
for prev_id in AGENT_ORDER[:agent_index]:
    if prev_id in session["round1"] and session["round1"][prev_id]:
        prev_name = AGENTS[prev_id]["name"]
        prev_resp = session["round1"][prev_id]
        previous_responses += f"{prev_name}: {prev_resp}\n\n"

# Add to user_message only for agent_index > 0
if agent_index > 0:
    cross_ref_instruction = f"""
PREVIOUS PANEL RESPONSES (read these before responding):
{previous_responses}

IMPORTANT: You MUST directly address at least one point made above.
Use their name: "Arjun said X but..." or "Building on Priya's point..."
or "I disagree with Ravi because..."
This is a live debate, not independent reports.
"""
```

Pass `agent_index` through the loop (enumerate AGENT_ORDER).
Do NOT add cross-referencing instruction to Agent 0 (first agent).

---

### FEATURE 3 — Human in the Loop (Priority: Critical)

**What it does:**
Four intervention points where the pitcher can shape the debate.
System pauses and waits for human decision before continuing.

**Implementation:**

**HITL Point 1 — Pitch Summary Approval**

After pitch extraction and domain classification, PAUSE and emit:
```python
yield sse_event("hitl_summary_approval", {
    "summary": session["pitch_summary"],
    "domain": session["domain"],
    "session_id": session_id,
    "message": "Is this what you meant? Correct anything before the panel sees it."
})
# Stop streaming. Wait for /pitch/approve-summary endpoint.
```

Add endpoint `POST /pitch/approve-summary`:
```python
class SummaryApproval(BaseModel):
    session_id: str
    approved: bool
    corrected_summary: str | None = None
```
If corrected, update `session["pitch_summary"]`. Then continue to Round 1.
Use `asyncio.Event()` per session to signal the waiting stream to continue.

**HITL Point 2 — Debate Steering**

After Round 1 completes, before question selection, emit:
```python
yield sse_event("hitl_steer_debate", {
    "session_id": session_id,
    "options": [
        {"id": "proceed", "label": "Accept — let the panel ask their question"},
        {"id": "clarify", "label": "Clarify something the panel misunderstood"},
        {"id": "address", "label": "Address a specific agent's concern first"}
    ]
})
```
Add endpoint `POST /pitch/steer`:
```python
class SteerRequest(BaseModel):
    session_id: str
    choice: str  # "proceed" | "clarify" | "address"
    clarification: str | None = None
    target_agent_id: str | None = None
```
If clarify/address: inject clarification into session context, 
emit `clarification_added` event, then proceed to question selection.

**HITL Point 3 — Challenge Agent Claim**

This is always available during Round 1 display (not a pause point).
Add endpoint `POST /pitch/challenge`:
```python
class ChallengeRequest(BaseModel):
    session_id: str
    agent_id: str
    challenge_text: str
```

On challenge, run a Fact-Check Agent:
```python
FACT_CHECK_PROMPT = """
You are a neutral fact-checker. The pitcher has challenged an agent's claim.
Agent claim: {agent_claim}
Pitcher challenge: {challenge}

Respond in exactly 2 sentences:
1. Whether the agent's claim was accurate, partially accurate, or inaccurate.
2. What the correct information is, with a specific example or evidence.

Be completely neutral. Do not favor the pitcher or the agent."""
```

Stream fact-check result as SSE event `fact_check_result`.
If agent was wrong, append correction to that agent's response display.

**HITL Point 4 — Verdict Negotiation**

After verdict, emit:
```python
yield sse_event("hitl_verdict_negotiation", {
    "verdict": session["verdict"],
    "parts": session["verdict_parts"],
    "session_id": session_id
})
```
Add endpoint `POST /pitch/pushback`:
```python
class PushbackRequest(BaseModel):
    session_id: str
    pushback: str  # Which part and why they disagree
```
Judge re-evaluates with pushback context. Emits `verdict_final` with
original verdict + pushback + judge's response. Shows both on card.

---

### FEATURE 4 — Firecrawl MCP for Live Competitor Research (Priority: High)

**What it does:**
Meera (Competitor's Customer) uses Firecrawl to search for real current
competitors before responding instead of relying on training data.
Makes competitor objections grounded in live market reality.

**Setup:**
```bash
pip install firecrawl-py
# Get free API key at firecrawl.dev (500 credits/month free)
```

Add to .env: `FIRECRAWL_API_KEY=your_key_here`

Add to main.py:
```python
from firecrawl import FirecrawlApp
firecrawl = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))

async def search_competitors(domain_info: dict) -> str:
    """Search for current competitors for this specific domain."""
    query = f"{domain_info['sub_domain']} competitors India 2026 pricing"
    try:
        results = firecrawl.search(query, params={"limit": 3})
        competitor_context = "LIVE COMPETITOR RESEARCH (searched just now):\n"
        for r in results.get("data", [])[:3]:
            competitor_context += f"- {r.get('title', '')}: {r.get('snippet', '')}\n"
        return competitor_context
    except Exception:
        return ""  # Fail silently — agent uses training data as fallback
```

In `stream_round1`, for the competitor agent ONLY:
```python
if agent_id == "competitor":
    competitor_data = await search_competitors(session["domain"])
    user_message = competitor_data + "\n\n" + user_message
```

Emit SSE event `competitor_research_complete` before competitor agent starts,
showing a "Meera is searching the web..." status indicator.

---

### FEATURE 5 — Memory MCP for Returning Pitchers (Priority: High)

**What it does:**
System remembers pitchers across sessions. If someone pitched before,
agents reference their previous pitch and whether they've addressed
the weaknesses identified last time.

**Setup:**
```bash
npm install -g @modelcontextprotocol/server-memory
```

Add to main.py:
```python
import subprocess, json

MEMORY_FILE = "pitcher_memory.json"

def load_pitcher_memory(pitcher_id: str) -> dict | None:
    """Load previous session data for this pitcher."""
    try:
        with open(MEMORY_FILE, "r") as f:
            memory = json.load(f)
        return memory.get(pitcher_id)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def save_pitcher_memory(pitcher_id: str, session_data: dict):
    """Save session data for future reference."""
    try:
        try:
            with open(MEMORY_FILE, "r") as f:
                memory = json.load(f)
        except:
            memory = {}
        memory[pitcher_id] = {
            "last_pitch_summary": session_data["pitch_summary"],
            "domain": session_data.get("domain", {}),
            "weaknesses": session_data.get("verdict_parts", {}).get("weakness", ""),
            "verdict": session_data.get("verdict", ""),
            "timestamp": session_data.get("timestamp", ""),
            "pitch_count": memory.get(pitcher_id, {}).get("pitch_count", 0) + 1
        }
        with open(MEMORY_FILE, "w") as f:
            json.dump(memory, f, indent=2)
    except Exception:
        pass  # Fail silently
```

Add `pitcher_id` field to `PitchRequest` (optional, user-provided name or email hash).

If pitcher has previous session, inject memory context into all agents:
```
PITCHER HISTORY:
This pitcher has used this platform before ({pitch_count} previous pitch(es)).
Previous pitch: {last_pitch_summary}
Weakness identified last time: {weaknesses}

If relevant, acknowledge their progress. If they've addressed the previous 
weakness, credit them for it. If they haven't, note that it's still unresolved.
```

Emit `returning_pitcher` SSE event with previous session summary.
Frontend shows "Welcome back" banner with previous weakness reminder.

Save memory at session completion (after verdict).

---

### FEATURE 6 — Radar Chart Scoring Tool (Priority: High)

**What it does:**
After Round 1, a Scoring Agent evaluates the pitch on 5 dimensions
and generates a radar chart that renders live on the frontend.

**Setup:**
```bash
pip install matplotlib numpy
```

Add Scoring Agent to main.py:
```python
SCORING_AGENT_PROMPT = """
You are a startup pitch evaluator. Based on the pitch and panel reactions,
score this pitch on exactly these 5 dimensions. Output ONLY valid JSON:

{
  "problem_clarity": <1-10>,
  "market_size": <1-10>,
  "differentiation": <1-10>,
  "feasibility": <1-10>,
  "founder_credibility": <1-10>,
  "reasoning": {
    "problem_clarity": "one sentence why",
    "market_size": "one sentence why",
    "differentiation": "one sentence why",
    "feasibility": "one sentence why",
    "founder_credibility": "one sentence why"
  }
}

Be honest. An average pitch should score 5-6. Reserve 9-10 for exceptional.
Base scores on the pitch content AND the panel's reactions.
"""

async def generate_radar_chart(scores: dict) -> str:
    """Generate radar chart and return as base64 PNG."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    import base64
    import io

    categories = ["Problem\nClarity", "Market\nSize", 
                  "Differentiation", "Feasibility", "Founder\nCredibility"]
    values = [
        scores["problem_clarity"], scores["market_size"],
        scores["differentiation"], scores["feasibility"],
        scores["founder_credibility"]
    ]
    
    N = len(categories)
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    values_plot = values + [values[0]]
    angles += angles[:1]

    fig, ax = plt.subplots(1, 1, figsize=(5, 5), 
                            subplot_kw=dict(projection='polar'))
    fig.patch.set_facecolor('#0F172A')
    ax.set_facecolor('#0F172A')
    
    ax.plot(angles, values_plot, 'o-', linewidth=2, color='#1A56DB')
    ax.fill(angles, values_plot, alpha=0.25, color='#1A56DB')
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, size=9, color='#94A3B8')
    ax.set_ylim(0, 10)
    ax.set_yticks([2, 4, 6, 8, 10])
    ax.set_yticklabels(['2', '4', '6', '8', '10'], size=7, color='#475569')
    ax.grid(color='#1E293B', linewidth=0.5)
    ax.spines['polar'].set_color('#1E293B')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', 
                facecolor='#0F172A', dpi=120)
    buf.seek(0)
    chart_b64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()
    return chart_b64
```

Run scoring agent after Round 1 completes.
Store scores in `session["scores"]`.
Emit SSE event `radar_chart_ready` with base64 PNG and scores dict.
Frontend renders chart image in right sidebar below Room Temperature.

---

### FEATURE 7 — Canvas + Sketch-to-3D for Physical Products (Priority: Medium)

**What it does:**
For physical product pitches, show a drawing canvas.
User sketches their product. System sends sketch to Meshy.ai API,
gets a 3D render back, agents evaluate the actual visual.

**Setup:**
```bash
pip install requests
# Get free API key at meshy.ai (limited free generations)
```

Add to .env: `MESHY_API_KEY=your_key_here`

Add to main.py:
```python
import requests, base64, time

async def sketch_to_3d(sketch_base64: str, description: str) -> str | None:
    """Send sketch to Meshy.ai and return render as base64 PNG."""
    headers = {"Authorization": f"Bearer {os.getenv('MESHY_API_KEY')}"}
    
    # Create image-to-3D task
    payload = {
        "image_url": f"data:image/png;base64,{sketch_base64}",
        "ai_model": "meshy-4",
        "topology": "quad",
        "target_polycount": 30000
    }
    
    try:
        response = requests.post(
            "https://api.meshy.ai/v1/image-to-3d",
            json=payload, headers=headers
        )
        task_id = response.json().get("result")
        if not task_id:
            return None
        
        # Poll for completion (max 60 seconds)
        for _ in range(12):
            await asyncio.sleep(5)
            status_response = requests.get(
                f"https://api.meshy.ai/v1/image-to-3d/{task_id}",
                headers=headers
            )
            data = status_response.json()
            if data.get("status") == "SUCCEEDED":
                thumbnail_url = data.get("thumbnail_url")
                if thumbnail_url:
                    img_data = requests.get(thumbnail_url).content
                    return base64.b64encode(img_data).decode('utf-8')
            elif data.get("status") == "FAILED":
                return None
        return None
    except Exception:
        return None
```

Add new endpoint `POST /sketch/submit`:
```python
class SketchRequest(BaseModel):
    session_id: str
    sketch_base64: str  # PNG canvas export
    description: str    # Brief text description of what they drew
```

Returns SSE stream:
- `sketch_processing`: "Generating 3D model from your sketch..."
- `sketch_complete`: { "render_b64": base64_png } on success
- `sketch_failed`: fallback message on failure

When 3D render is available, store in `session["product_render"]`.
Pass render as image to all agents alongside pitch text (vision API call).

**Frontend canvas component** (add to page.js):
- Show canvas only when `domain.is_physical_product === true`
- HTML5 canvas with pen/eraser/clear tools
- "Generate 3D Model" button exports canvas as PNG base64
- Loading state shows "Generating your product..." with spinner
- On complete: shows 3D render thumbnail, "Looks good, activate panel" button

---

### FEATURE 8 — One-Page PDF Report (Priority: Medium)

**What it does:**
After verdict, generate a downloadable PDF containing:
pitch summary, radar chart, all agent responses, verdict, 
and 3D render if available.

**Setup:**
```bash
pip install reportlab pillow
```

Add to main.py:
```python
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import mm
import io, base64

async def generate_pdf_report(session: dict) -> bytes:
    """Generate complete pitch report as PDF bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                             topMargin=15*mm, bottomMargin=15*mm,
                             leftMargin=15*mm, rightMargin=15*mm)
    
    styles = getSampleStyleSheet()
    brand = HexColor('#1A56DB')
    dark = HexColor('#111827')
    gray = HexColor('#6B7280')
    light = HexColor('#F3F4F6')
    
    content = []
    
    # Header
    header_style = ParagraphStyle('header', fontSize=20, textColor=white,
                                   backColor=HexColor('#1E3A5F'), 
                                   spaceAfter=6, spaceBefore=0,
                                   leftIndent=10, rightIndent=10)
    content.append(Paragraph("PITCH TO THE PANEL — Evaluation Report", header_style))
    content.append(Spacer(1, 10))
    
    # Pitch summary
    content.append(Paragraph("What you pitched:", 
                              ParagraphStyle('label', fontSize=10, textColor=gray)))
    content.append(Paragraph(session.get("pitch_summary", ""), 
                              ParagraphStyle('body', fontSize=11, textColor=dark, 
                                            spaceAfter=10)))
    content.append(Spacer(1, 6))
    
    # Radar chart if available
    if session.get("scores"):
        chart_b64 = await generate_radar_chart(session["scores"])
        chart_data = base64.b64decode(chart_b64)
        chart_img = io.BytesIO(chart_data)
        content.append(Image(chart_img, width=80*mm, height=80*mm))
        content.append(Spacer(1, 6))
    
    # 3D render if available
    if session.get("product_render"):
        render_data = base64.b64decode(session["product_render"])
        render_img = io.BytesIO(render_data)
        content.append(Paragraph("Your Product Concept:", 
                                  ParagraphStyle('label', fontSize=10, textColor=gray)))
        content.append(Image(render_img, width=80*mm, height=60*mm))
        content.append(Spacer(1, 6))
    
    # Agent responses summary
    content.append(Paragraph("What the panel said:", 
                              ParagraphStyle('section', fontSize=12, textColor=brand,
                                            spaceBefore=8, spaceAfter=4)))
    
    agent_data = []
    for agent_id in AGENTS:
        if agent_id in session.get("round1", {}):
            agent_name = AGENTS[agent_id]["name"]
            response = session["round1"][agent_id][:300] + "..." \
                       if len(session["round1"].get(agent_id, "")) > 300 \
                       else session["round1"].get(agent_id, "")
            agent_data.append([
                Paragraph(agent_name, ParagraphStyle('agent', fontSize=9, 
                                                      textColor=brand)),
                Paragraph(response, ParagraphStyle('resp', fontSize=9, 
                                                   textColor=dark))
            ])
    
    if agent_data:
        t = Table(agent_data, colWidths=[35*mm, 130*mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), light),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#E5E7EB')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        content.append(t)
        content.append(Spacer(1, 10))
    
    # Verdict
    parts = session.get("verdict_parts", {})
    if parts:
        content.append(Paragraph("The Verdict:", 
                                  ParagraphStyle('section', fontSize=12, textColor=brand)))
        
        verdict_items = [
            ("✓ Strongest Point", parts.get("strongest", ""), '#065F46', '#ECFDF5'),
            ("⚠ Biggest Weakness", parts.get("weakness", ""), '#92400E', '#FFFBEB'),
            ("→ Before Next Pitch", parts.get("fix", ""), '#1E3A5F', '#EFF6FF'),
        ]
        
        for label_text, body_text, text_color, bg_color in verdict_items:
            if body_text:
                vt = Table([[
                    Paragraph(label_text, ParagraphStyle('vlabel', fontSize=9,
                                                          textColor=HexColor(text_color))),
                    Paragraph(body_text, ParagraphStyle('vbody', fontSize=10,
                                                         textColor=HexColor(text_color)))
                ]], colWidths=[40*mm, 125*mm])
                vt.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor(bg_color)),
                    ('PADDING', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0, white),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                content.append(vt)
                content.append(Spacer(1, 4))
    
    doc.build(content)
    buffer.seek(0)
    return buffer.read()
```

Add endpoint `GET /session/{session_id}/report`:
```python
@app.get("/session/{session_id}/report")
async def download_report(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404)
    pdf_bytes = await generate_pdf_report(sessions[session_id])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=pitch-report.pdf"}
    )
```

Frontend: show "Download Pitch Report" button after verdict renders.
Button calls `GET /session/{session_id}/report`.

---

### FEATURE 9 — Operator Agent for Non-Tech Pitches (Priority: Medium)

**What it does:**
For non-tech pitches (food, retail, services, manufacturing),
replace the Technical Feasibility perspective with Suresh Nair —
someone who has actually run a physical business.

**Add to AGENTS dict in main.py:**
```python
"operator": {
    "id": "operator",
    "name": "Suresh Nair",
    "role": "Experienced Operator",
    "color": "#0284C7",
    "avatar_initials": "SN",
    "avatar_bg": "#0C4A6E",
    "activates_for": ["food_beverage", "retail", "services", 
                      "manufacturing", "agriculture", "non_tech"],
    "system_prompt": """You are Suresh Nair, 52, who has run a chain of 
4 successful medical stores in Kerala for 22 years. You understand 
the realities of running a physical business in India deeply.

You evaluate pitches on:
1. Unit economics — does each sale/transaction make money after costs?
2. Operations — how will this actually work day to day?
3. People — who runs this on the ground, and can you trust them?

VOICE: Practical, experience-based. You reference specific numbers from 
your own business. Short sentences. You say 'in my experience' often.
You are not impressed by ideas — only by numbers and execution plans.

RED LINES:
- No discussion of unit economics: 'Tell me what you make per unit after all costs.'
- Assuming operations run themselves: 'Who opens the shop at 7am?'
- Unrealistic margins: compare to industry standard margins you know.
- Underestimating working capital: 'Have you calculated how much cash
  you need before your first rupee of revenue comes in?'"""
}
```

In `stream_round1`, check `session["domain"]["panel_mode"]`:
- If `non_tech`: replace `first_timer` with `operator` in AGENT_ORDER
  (Kiran's questions don't apply to B2B or non-consumer pitches)
- If `physical_product`: add `operator` as 7th agent
- Otherwise: use standard AGENT_ORDER

---

### FEATURE 10 — Design Mode with Vision (Priority: Medium)

**What it does:**
For design pitches, accept an image upload.
All agents receive the image alongside the pitch text.
Dr. Iyer becomes a design critic.
Meera becomes a potential client.

**Add image upload to PitchRequest:**
```python
class PitchRequest(BaseModel):
    pitch_transcript: str
    session_id: str | None = None
    image_data: str | None = None   # base64 encoded
    image_type: str | None = None   # "image/png" | "image/jpeg"
    pitcher_id: str | None = None   # for memory
```

Store in session: `session["design_image"] = { "data": ..., "type": ... }`

In agent message builder, when image is present:
```python
if session.get("design_image") and domain.get("panel_mode") == "design":
    messages = [{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": session["design_image"]["type"],
                    "data": session["design_image"]["data"]
                }
            },
            {"type": "text", "text": user_message}
        ]
    }]
else:
    messages = [{"role": "user", "content": user_message}]
```

Override Dr. Iyer's system prompt for design mode:
```python
if agent_id == "expert" and domain.get("panel_mode") == "design":
    system_prompt = """You are Dr. Ananya Iyer, design researcher and critic.
You evaluate visual work through:
- Visual hierarchy: does the eye go where it should?
- Typography: are font choices appropriate for the context and audience?
- Color theory: does the palette communicate the right emotion?
- Gestalt principles: does the whole feel coherent and intentional?
- Cultural context: does this work for the specific Indian market it targets?

You reference real designers, real brands, real design movements.
If you can see the design: comment on specific visual elements you observe.
If the design has clear strengths, credit them. If it has lazy defaults, say so.
Keep response under 100 words."""
```

Override Meera's system prompt for design mode:
```python
if agent_id == "competitor" and domain.get("panel_mode") == "design":
    system_prompt = """You are Meera Pillai, 31, Marketing Manager.
You are evaluating this designer as a potential hire for a branding project.
You are NOT comparing software tools — you are deciding whether to hire this person.

You evaluate:
1. Does this work fit our brand's target audience?
2. Is this designer's style flexible or one-note?
3. What would this cost and is it worth it versus a freelancer on Fiverr?
4. Can I show this to my CEO without embarrassment?

Be honest about whether you would actually commission work from this designer."""
```

**Frontend design upload** (add to page.js):
When domain is detected as design pitch, show:
```
[ Upload your design work ]
Accepted: PNG, JPG, PDF screenshot
```
Convert to base64, include in PitchRequest.

---

## UPDATED SESSION OBJECT

After all features, session stores:
```python
{
  "id": str,
  "pitch_summary": str,
  "pitch_summary_approved": bool,
  "domain": dict,           # from Domain Classifier
  "design_image": dict,     # base64 image if design mode
  "product_render": str,    # base64 3D render if physical product
  "round1": dict,           # agent_id -> response
  "round2": dict,           # agent_id -> response  
  "question": dict,         # selected question
  "pitcher_answer": str,
  "verdict": str,
  "verdict_parts": dict,    # strongest, weakness, fix
  "scores": dict,           # radar chart scores
  "steered": bool,          # HITL steering happened
  "challenges": list,       # fact-check challenges
  "pushback": str,          # verdict pushback if any
  "pitcher_id": str,        # for memory
  "timestamp": str,
  "phase": str
}
```

---

## UPDATED SSE EVENT LIST

New events to handle in frontend:

```
domain_classified          → show domain badge, set panel_mode
hitl_summary_approval      → show approval UI, pause
hitl_steer_debate          → show steering options, pause  
clarification_added        → show confirmation banner
competitor_research_start  → show "Meera is searching..." indicator
competitor_research_done   → clear indicator
fact_check_result          → show fact-check bubble under challenged agent
hitl_verdict_negotiation   → show pushback input after verdict
verdict_final              → replace verdict with final negotiated version
radar_chart_ready          → render chart image in sidebar
returning_pitcher          → show welcome back banner with prev weakness
sketch_processing          → show 3D generation spinner
sketch_complete            → show 3D render, enable panel activation
```

---

## UPDATED FRONTEND REQUIREMENTS

Add to page.js:

1. **Domain badge** — small colored tag showing domain type next to pitch summary
2. **HITL approval screen** — editable summary before panel activates
3. **Steering options** — 3-button choice after Round 1
4. **Challenge button** — small "⚑ Challenge" link under each agent response
5. **Fact-check bubble** — inline below challenged agent response
6. **Radar chart** — image rendered in right sidebar after Round 1
7. **Canvas component** — drawing surface for physical product pitches
8. **3D render display** — thumbnail shown after Meshy generation
9. **Image upload** — drag-and-drop for design pitches
10. **Returning pitcher banner** — "Welcome back" with previous weakness
11. **Verdict pushback input** — text input + submit after verdict
12. **Download PDF button** — appears after verdict renders
13. **Operator agent card** — same structure as other agents, different color

---

## ENVIRONMENT VARIABLES NEEDED

```env
ANTHROPIC_API_KEY=           # required — all agents
FIRECRAWL_API_KEY=           # Feature 4 — competitor research (free tier ok)
MESHY_API_KEY=               # Feature 7 — 3D generation (free tier ok)
```

---

## BUILD ORDER

Build in exactly this sequence. Test each before moving to the next.

1. Domain Classifier (Feature 1) — all other features depend on domain
2. Agent Cross-Referencing (Feature 2) — improves base demo immediately  
3. HITL Summary Approval only (Feature 3, Point 1) — lowest risk HITL
4. Radar Chart (Feature 6) — high visual impact, standalone
5. HITL Steering + Challenge (Feature 3, Points 2-3)
6. Firecrawl Competitor Research (Feature 4)
7. Memory MCP (Feature 5)
8. PDF Report (Feature 8)
9. Operator Agent (Feature 9)
10. Design Mode + Vision (Feature 10)
11. Canvas + 3D (Feature 7) — build last, most complex
12. HITL Verdict Negotiation (Feature 3, Point 4) — polish step

---

## WHAT NOT TO CHANGE

- Existing 6 agent system prompts (in AGENTS dict)
- Judge system prompt
- SSE streaming infrastructure
- Session creation flow
- Basic Next.js layout and agent card design
- Room Temperature meter logic
- Web Speech API integration
- CORS configuration
- All existing routes (/pitch/start, /pitch/answer, /session/{id}, /agents, /health)

---

## RESEARCH CITATIONS TO ADD TO YOUR README

When documenting the new features, cite:
- Domain classification: Agentic AI Survey (arXiv 2510.25445)
- HITL co-discretion: Salah & Alnoor, Jan 2026 (doi 10.1080/01900692.2025.2605225)
- Agent cross-referencing: Intrinsic Memory Agents, Chen et al., Aug 2025
- Competitor research: REDEREF routing, Hosseini et al., Feb 2026
- 3D generation: Meshy.ai image-to-3D API
- Memory: AgentSociety persistent memory patterns
