# Pitch to the Panel — Setup Guide

## Project Structure

```
pitch-to-the-panel/
├── backend/
│   ├── main.py          ← FastAPI server, all agent logic
│   └── requirements.txt
└── frontend/
    ├── src/app/
│   │   ├── page.js      ← Main UI
│   │   └── layout.js
    ├── next.config.js
    └── package.json
```

---

## Step 1 — Get your Anthropic API key

1. Go to https://console.anthropic.com
2. Create an API key
3. Copy it — you'll need it in Step 3

---

## Step 2 — Backend setup

```bash
# Navigate to backend
cd pitch-to-the-panel/backend

# Create virtual environment
python -m venv venv

# Activate it
# On Mac/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Step 3 — Set your API key

```bash
# Create .env file in the backend folder
echo "ANTHROPIC_API_KEY=your_key_here" > .env
```

Or set it as an environment variable directly:
```bash
# Mac/Linux
export ANTHROPIC_API_KEY=your_key_here

# Windows
set ANTHROPIC_API_KEY=your_key_here
```

Then add this to the top of main.py (after the imports):
```python
from dotenv import load_dotenv
import os
load_dotenv()
# The anthropic client picks up ANTHROPIC_API_KEY automatically
```

---

## Step 4 — Run the backend

```bash
# From the backend/ folder, with venv activated:
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

Test it: open http://localhost:8000/health in your browser.
You should see: {"status": "ok"}

---

## Step 5 — Frontend setup

```bash
# Open a new terminal tab
cd pitch-to-the-panel/frontend

# Install dependencies
npm install
```

---

## Step 6 — Run the frontend

```bash
npm run dev
```

You should see:
```
- ready started server on 0.0.0.0:3000, url: http://localhost:3000
```

Open http://localhost:3000 in your browser.

---

## Step 7 — Test it

1. Type or voice a pitch in the text box
2. Click "Pitch it →"
3. Watch 6 agents react in real time
4. Answer the question from the most skeptical agent
5. Read your verdict

---

## Troubleshooting

**"CORS error" in browser console**
→ Make sure the backend is running on port 8000
→ Check that CORS origins in main.py includes "http://localhost:3000"

**"API key not found" error**
→ Make sure ANTHROPIC_API_KEY is set in your environment
→ Restart the backend after setting the key

**Agents respond slowly**
→ Normal — each agent takes 3-8 seconds to stream
→ Agents run sequentially to avoid rate limits
→ For faster demo, reduce max_tokens in main.py (line: max_tokens=200)

**Voice input not working**
→ Chrome and Edge support Web Speech API
→ Firefox does not — use Chrome for the expo demo
→ Allow microphone access when prompted

**Frontend shows blank page**
→ Check browser console for errors
→ Make sure you're using Node 18+: node --version

---

## Deploying for the expo (optional)

### Backend — deploy to Render (free)
1. Push your code to a GitHub repo
2. Go to https://render.com
3. New Web Service → connect your repo
4. Build command: pip install -r requirements.txt
5. Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
6. Add environment variable: ANTHROPIC_API_KEY = your_key

### Frontend — deploy to Vercel (free)
1. Push your code to GitHub
2. Go to https://vercel.com
3. Import your repo → select the frontend/ folder as root
4. Add environment variable: NEXT_PUBLIC_API_URL = https://your-render-url.onrender.com
5. Deploy

---

## Cost estimate

Each full demo session (pitch → round1 → question → answer → round2 → verdict):
- ~2,000 input tokens + ~1,200 output tokens
- At Claude Sonnet pricing: approximately ₹2-3 per session
- For a 4-hour expo with 60 demos: approximately ₹150-180 total

---

## Customizing agent prompts

All 6 agent system prompts are in main.py under the AGENTS dictionary.
Each agent has a "system_prompt" field — edit these to tune the voices.

Key things to tune:
- Make Kiran (first_timer) use more Hindi phrases if your audience is from India
- Add a specific local competitor to Meera's prompt for your domain
- Adjust Arjun's red lines based on what pitches you expect at your expo

---

## File you'll edit most

**main.py** — everything is in here:
- AGENTS dict: system prompts for all 6 agents
- JUDGE_SYSTEM_PROMPT: verdict format
- QUESTION_SELECTOR_PROMPT: how the question is chosen
- extract_pitch_summary(): how the pitch is parsed
- compute_sentiment(): sentiment detection (simple keyword-based)

**frontend/src/app/page.js** — the entire UI:
- Demo scenarios (bottom of the idle screen) — swap these for your expo audience
- AGENT_META: names, colors, initials — change if you rename agents
- RoomTemp component: the live sentiment meter

---

## The self-referential demo (do this with every judge)

Paste this exact pitch:
"An AI platform where anyone can pitch their startup idea out loud and get real-time reactions
from a panel of 6 AI personas — a skeptical VC, two potential users, a domain expert,
a competitor's customer, and a confused first-timer. The panel debates, asks you a hard question,
and delivers a 3-line verdict you can act on immediately. The whole thing takes 90 seconds."

Watch the panel react to itself. Kiran will ask if it's free.
Arjun will ask who your first paying customer is.
Priya will say she'd use it right now.
It works every time.
