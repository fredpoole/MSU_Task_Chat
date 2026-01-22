# server.py — multi-bot Realtime voice chat (7 preset scenarios)
# --------------------------------------------------------------
# Run:
#   pip install flask flask-cors requests python-dotenv
#   python server.py
# Open: http://127.0.0.1:5000/realtime
#
# Edit the BOTS list below to customize role/task/constraints per button.

import os
import json
import textwrap
import requests
from flask import Flask, request, jsonify, Response, redirect
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

# --------------------------- Config ---------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview-2024-12-17")
OPENAI_REALTIME_VOICE_DEFAULT = os.getenv("OPENAI_REALTIME_VOICE", "alloy")
RT_SILENCE_MS = int(os.getenv("RT_SILENCE_MS", "1200"))  # pause after user stops
VAD_THRESHOLD = float(os.getenv("RT_VAD_THRESHOLD", "0.5"))

# 7 preset "bots". Edit freely.
BOTS = [
    {
        "id": "apt-en",
        "title": "Order Breakfast (EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "Patient English Barista at a coffee shop",
        "task": (
            "The learner is on their way to school and decides to pick up breakfast. "
            "They have just entered the coffee shop where you work. "
            "Start with a natural small talk. Don't ask orders before finishing the small talk."
            "The menu includes drip coffee, latte, cappuccino, flat white, mocha, matcha, "
            "croissants (plain, ham, chocolate), and bagels (plain, blueberry, sesame, poppy seed). "
            "Ask follow-up questions about drink size, whether it should be hot or iced, milk type, "
            "and whether the food should be warmed up."
            "Offer butter or jam for the croissant, and a choice of spread for the bagel."
            "Be flexible and respond naturally to the learner’s orders."
        ),
        "constraints": (
            "Speak clearly and a bit slowly. Use vocabulary appropriate for an upper-intermediate learner.",
            "Respond in 1–2 short sentences per turn. Do not explain options or give long responses.",
            "Ask ONLY one question at a time. Don't ask more than one question at a time",
            "If the learner's speech is unclear, incomprehensible, or unexpected, politely signal that you did not understand and ask them to repeat or clarify. Do not guess the context.",
            "Wait for 5 seconds if the learner pauses",
            "You only understand English. If another language is used, ask the learner to speak English.",
            "Be strict about signaling lack of understanding when language is unclear."
        ),
        "language_hint": "English"
    },
    {
        "id": "bank-en",
        "title": "The debit card fraud (EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "a polite and helpful Maple Trust Bank customer service representative",
        "task": (
            "Start with a greeting and first ask about the issue."
            "Ask whether the issue is with the learner's debit card or credit card, and then ask the last 4 digits of the learner's account and their name."
            "Ask questions about the problem naturally (e.g., what happened, when, how much)."
            "Confirm if the learner made the transactions or not."
            "There might be several transactions the learner needs to report, so keep asking until they finish reporting."
            "Explain that you (ChatGPT) will block the card and send a new one."
            "Ask if the learner needs to use the card today as they cannot use the card after it's blocked"
            "Ask if the learner had another debit or credit card."
            "Make sure if there is anything elese the learner needs help with or questions they may have."
            "Before ending, give a short summary and say goodbye politely."
            "Be flexible and respond naturally to the learner’s situations and requests."
        ),
        "constraints": (
            "Speak clearly and a bit slowly. Use vocabulary appropriate for an upper-intermediate learner.",
            "Respond in 1–2 short sentences per turn. Do not explain options or give long responses.",
            "Ask ONLY one question at a time. Don't ask more than one question at a time",
            "If the learner's speech is unclear, incomprehensible, or unexpected, politely signal that you did not understand and ask them to repeat or clarify. ",
            "Do not guess the context."
            "Wait for 5 seconds if the learner pauses",
            "You only understand English. If another language is used, ask the learner to speak English.",
            "Be strict about signaling lack of understanding when language is unclear."
        ),
        "language_hint": "English"
    },
    {
        "id": "matching-en",
        "title": "Roommate matching (EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "a student who are interested in living with the learner.",
        "task": (
             "Start with a greeting and small talk"
            "Introduce youreself based on your back groundinformation, but don't discrlose too much at one time."
            "Take natural turns and ask questions to the learner to show interests."
            "Also ask follow-up questions about the learner's response."
            "Sometimes show your own preferences to keep the conversation going naturally."
        ),
        "constraints": (
            "Speak clearly and a bit slowly. Use vocabulary appropriate for an upper-intermediate learner.",
            "Respond in 1–2 short sentences per turn. Do not explain options or give long responses.",
            "Ask ONLY one question at a time. Don't ask more than one question at a time",
            "If the learner's speech is unclear, incomprehensible, or unexpected, politely signal that you did not understand and ask them to repeat or clarify. ",
            "Do not guess the context.",
            "Wait for 5 seconds if the learner pauses",
            "You only understand English. If another language is used, ask the learner to speak English.",
            "Be strict about signaling lack of understanding when language is unclear."
        ),
        "language_hint": "English"
    },
    {
        "id": "roommate-en",
        "title": "Negotiation Apartment Living Rules (EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
      "role": "Collaborative roommate",
"task": (
    "Negotiate apartment norms: cleaning schedules, guests, noise, shower times."
    "Elicit the learner's opinions and suggestions."
    "Ask follow-up questions about my responses and give short, natural replies to keep the conversation going."
    "Sometimes be persistent about your own preferences to encourage negotiation and help the learner's express their ideas or find a compromise."
    "counterproposals; confirm decisions."
),
 "constraints": (
            "Speak clearly and a bit slowly. Use vocabulary appropriate for an upper-intermediate learner.",
            "Respond in 1–2 short sentences per turn. Do not explain options or give long responses.",
            "Ask ONLY one question at a time. Don't ask more than one question at a time",
            "If the learner's speech is unclear, incomprehensible, or unexpected, politely signal that you did not understand and ask them to repeat or clarify. ",
            "Do not guess the context.",
            "Wait for 5 seconds if the learner pauses",
            "You only understand English. If another language is used, ask the learner to speak English.",
            "Be strict about signaling lack of understanding when language is unclear."
        ),
        "language_hint": "English"
    },
    {
        "id": "travel-en",
        "title": "Travel Suggestion (EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
       "role": "A friend who is going to visit the speaker's country for one week with your brother this summer.",
"task": (
    "Ask questions about my recommendations (e.g., where to go and what to eat)."
			"Show interest and curiosity, but do NOT further explain about what the learner mentioned or recommended. Instead, ask follow-up questions."
			"Mention a few preferences or limits (e.g., “I can’t eat spicy food,” or “My knees hurt when walking too much”)."
			"Respond naturally and shortly to my suggestions and ask short follow-up questions."
),
 "constraints": (
           "Speak clearly and a bit slowly. Use vocabulary appropriate for an upper-intermediate learner.",
           "Respond in 1–2 short sentences per turn. Do not explain options or give long responses.",
           "Ask ONLY one question at a time. Don't ask more than one question at a time",
           "If the learner's speech is unclear, incomprehensible, or unexpected, politely signal that you did not understand and ask them to repeat or clarify. ",
           "Do not guess the context.",           
           "Wait for 5 seconds if the learner pauses",
           "You only understand English. If another language is used, ask the learner to speak English.",
           "Be strict about signaling lack of understanding when language is unclear."
        ),
        "language_hint": "English"
    },
    {
        "id": "yoga class-en",
        "title": "YogaClass Invidation(EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "You are the speaker's international friend at college. The speaker is going to invite you to a yoga class, but you have never done yoga before and you’re not very interested in sports",
        "task": (
             "The speaker will invite you to a yoga class based on the flyer. Ask the learner many questions possible about the yoga class (e.g., schedule, price, location, what to bring)." 
            "Be friendly, but show some hesitation or reluctance about joining at first because you are not interested in sports."
            "Get the speaker's suggestions or encouragement."
            "After you decide to join, ask the speaker’s availability and schedule when both are going together.You have something to do on Monday afternoon."
        ),
        "constraints": (
			"Speak clearly and a bit slowly. Use vocabulary appropriate for an upper-intermediate learner.",
			"Respond in 1–2 short sentences per turn. Do not explain options or give long responses.",
			"Ask ONLY one question at a time. Don't ask more than one question at a time",
			"If the learner's speech is unclear, incomprehensible, or unexpected, politely signal that you did not understand and ask them to repeat or clarify. ",
			"Do not guess the context.",           
			"Wait for 5 seconds if the learner pauses",
			"You only understand English. If another language is used, ask the learner to speak English.",
			"Be strict about signaling lack of understanding when language is unclear."
            ),
        "language_hint": "English"
    },
    {
        "id": "visiting office hours-en 2",
        "title": "Visiting Office Hours 2 (EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "You are Professor Rivera, who teaches Global Communication.Your student Alex has come to your office to discuss something.",
        "task": (
            "Start with a casual conversation and ask what the learner's issue is."
             "Ask why I want an extension. When the speaker explains my reason, respond naturally.",
             "Ask follow-up questions about their project and extention (e.g., current situation, how long they need )"
             "At first, disagree and ask the speaker to suggest a more flexible idea or solution.",
             "Then, end the conversation nicely with agreement."
        ),
       "constraints": (
			"Speak clearly and a bit slowly. Use vocabulary appropriate for an upper-intermediate learner.",
			"Respond in 1–2 short sentences per turn. Do not explain options or give long responses.",
			"Ask ONLY one question at a time. Don't ask more than one question at a time",
			"If the learner's speech is unclear, incomprehensible, or unexpected, politely signal that you did not understand and ask them to repeat or clarify.",
			"Do not guess the context.",           
			"Wait for 5 seconds if the learner pauses",
			"You only understand English. If another language is used, ask the learner to speak English.",
			"Be strict about signaling lack of understanding when language is unclear."
              ),
        "language_hint": "English"
    },
]

BOT_MAP = {b["id"]: b for b in BOTS}

# ---------------------- Prompt builder ------------------------

def build_system_prompt(bot: dict) -> str:
    base = textwrap.dedent(f"""
    ROLE: {bot['role']}
    TASK: {bot['task']}
    CONSTRAINTS: {bot['constraints']}
    STYLE: Conversational, concise, interactive. Keep turns short; end most turns with a brief, relevant question. But also add personal information dependent on your role. 
    VOICE/LANGUAGE: Speak primarily in {bot['language_hint']}. If the learner switches language, mirror briefly then steer back.
    
    ERROR HANDLING: Track learner errors in each utterance; if 3+ issues (grammar/lexis/pronunciation leading to ambiguity), be strict!!! on pronunciation,
      politely signal misunderstanding and ask for a clear repeat or rephrase, offering a simple model. When correcting:
      - Be gentle but clear
      - Provide the correct form
      - Give a brief explanation if helpful
      - Continue the conversation naturally
    
    EXAMPLE CORRECTIONS:
    - If learner says "I want two coffee", you might say: "Two coffees - yes! What size would you like?"
    - If pronunciation is unclear, say: "Sorry, I didn't quite catch that. Could you repeat 'bagel' for me?"
    
    Your corrections will help track the learner's progress for later analysis.
    """).strip()
    return base

# ------------------------ Flask app ---------------------------
app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return redirect("/realtime", code=302)

@app.route("/session", methods=["POST"])
def session():
    if not OPENAI_API_KEY:
        return jsonify({"error": "Missing OPENAI_API_KEY"}), 400

    body = request.get_json(silent=True) or {}
    bot_id = body.get("bot_id") or request.args.get("bot") or BOTS[0]["id"]
    bot = BOT_MAP.get(bot_id, BOTS[0])

    system_prompt = build_system_prompt(bot)

    # Mint an ephemeral client_secret for WebRTC (valid ~1 minute)
    try:
        r = requests.post(
            "https://api.openai.com/v1/realtime/sessions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
                "OpenAI-Beta": "realtime=v1",
            },
            json={
                "model": OPENAI_REALTIME_MODEL,
                "voice": bot.get("voice", OPENAI_REALTIME_VOICE_DEFAULT),
                "instructions": system_prompt,
                "modalities": ["audio", "text"],
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": VAD_THRESHOLD,
                    "silence_duration_ms": RT_SILENCE_MS,
                    "prefix_padding_ms": 300,              
                    "create_response": True,
                    "interrupt_response": True,
                },
            },
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        # Augment response with our chosen model/voice/bot
        data.update({
            "model": OPENAI_REALTIME_MODEL,
            "bot": {k: bot[k] for k in ("id", "title")},
        })
        return jsonify(data)
    except requests.HTTPError as e:
        return jsonify({"error": f"OpenAI error {e.response.status_code}", "details": e.response.text}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/analyze", methods=["POST"])
def analyze():
    """Analyze conversation and provide ACTFL assessment"""
    if not OPENAI_API_KEY:
        return jsonify({"error": "Missing OPENAI_API_KEY"}), 400
    
    body = request.get_json(silent=True) or {}
    conversation = body.get("conversation", [])
    bot_id = body.get("bot_id", "")
    
    if not conversation:
        return jsonify({"error": "No conversation provided"}), 400
    
    # Get bot info for context
    bot = BOT_MAP.get(bot_id, BOTS[0])
    
    # Build transcript
    transcript = "CONVERSATION TRANSCRIPT\n"
    transcript += "=" * 60 + "\n"
    transcript += f"Scenario: {bot['title']}\n"
    transcript += f"Date: {conversation[0].get('timestamp', 'N/A')[:10] if conversation else 'N/A'}\n"
    transcript += "=" * 60 + "\n\n"
    
    for turn in conversation:
        role_label = "LEARNER" if turn['role'] == 'learner' else "AGENT"
        transcript += f"{role_label}: {turn['text']}\n\n"
    
    # Extract only learner turns for analysis
    learner_turns = [turn['text'] for turn in conversation if turn['role'] == 'learner']
    learner_text = "\n".join(learner_turns)
    
    # Create analysis prompt
    analysis_prompt = f"""You are an expert language assessor specializing in ACTFL proficiency guidelines. 

Analyze the following learner's speech from a language learning conversation in {bot['language_hint']}.

LEARNER'S TURNS:
{learner_text}

SCENARIO CONTEXT:
{bot['task']}

Provide a comprehensive analysis with:

1. ACTFL PROFICIENCY ESTIMATE
   - Overall level (Novice Low/Mid/High, Intermediate Low/Mid/High, Advanced Low/Mid/High, Superior, Distinguished)
   - Brief justification for this rating

2. DETAILED ERROR ANALYSIS
   - Grammar errors (list specific examples with corrections)
   - Vocabulary issues (inappropriate word choices, missing vocabulary)
   - Pronunciation concerns (if evident from context or corrections needed)
   - Discourse/pragmatic issues

3. STRENGTHS
   - What the learner did well
   - Evidence of progress or good strategies

4. SPECIFIC RECOMMENDATIONS
   - 3-5 concrete action items for improvement
   - Suggested practice activities
   - Resources or focus areas

Be specific, constructive, and evidence-based. Quote actual learner utterances when discussing errors."""

    try:
        # Call OpenAI API for analysis
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": "You are an expert language assessor with deep knowledge of ACTFL proficiency guidelines."},
                    {"role": "user", "content": analysis_prompt}
                ],
                "temperature": 0.3,
            },
            timeout=60,
        )
        r.raise_for_status()
        analysis = r.json()["choices"][0]["message"]["content"]
        
        # Combine transcript and analysis
        full_report = transcript + "\n" + "=" * 60 + "\n"
        full_report += "PERFORMANCE ANALYSIS\n"
        full_report += "=" * 60 + "\n\n"
        full_report += analysis
        
        return Response(
            full_report,
            mimetype="text/plain",
            headers={"Content-Disposition": f"attachment; filename=analysis-{bot_id}.txt"}
        )
        
    except requests.HTTPError as e:
        return jsonify({"error": f"OpenAI error {e.response.status_code}", "details": e.response.text}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/realtime")
def realtime():
    # Inject a public view of the bots (id + title only)
    public = [{"id": b["id"], "title": b["title"]} for b in BOTS]
    html = REALTIME_HTML.replace("__BOTS_JSON__", json.dumps(public, ensure_ascii=False))
    return Response(html, mimetype="text/html")

# -------------------------- HTML -----------------------------
REALTIME_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Voice Chat (Realtime API)</title>
  <style>
    html,body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#0b1020;color:#e9ecf1;margin:0}
    .wrap{max-width:880px;margin:0 auto;padding:24px}
    .card{background:#141a2f;border:1px solid #1f2745;border-radius:16px;padding:16px;box-shadow:0 10px 30px rgba(0,0,0,.25)}
    .row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
    button{background:#35b26f;color:#fff;border:none;border-radius:999px;padding:10px 16px;font-weight:600;cursor:pointer}
    button.stop{background:#e9534a}
    button.ghost{background:transparent;border:1px solid #2b335a}
    .status{margin-left:auto;font-size:.85rem;opacity:.85}
    .log{background:#0e1428;border:1px solid #1f2745;border-radius:12px;padding:12px;height:320px;overflow:auto;font-size:.95rem;margin-top:12px}
    .msg{margin:6px 0}.user{color:#8fd3ff}.assistant{color:#b0ffa3}
    .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:8px 0 12px}
    .chip{background:#0e1428;border:1px solid #2b335a;border-radius:999px;padding:8px 12px;cursor:pointer;text-align:center}
    .chip.active{background:#224a39;border-color:#35b26f}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Realtime Voice (WebRTC)</h1>
    <p>Select a scenario, then connect. The agent will speak and stream text. Switch scenarios any time.</p>

    <div class="card">
      <div class="row">
        <button id="connect">Connect</button>
        <button id="disconnect" class="stop" disabled>Disconnect</button>
        <button id="nudge" class="ghost" disabled>Push-to-talk</button>
        <button id="analyze" class="ghost" disabled>Analyze My Chat</button>
        <button id="clear" class="ghost">Clear log</button>
        <button id="next" class="ghost">Next scenario</button>
        <span id="status" class="status">idle</span>
      </div>
      <div id="scenarioBar" class="grid"></div>
      <div class="row" style="gap:8px;margin:4px 0 8px">
        <span>Selected:</span> <b id="selectedTitle">(none)</b>
      </div>
      <audio id="remote" autoplay playsinline></audio>
      <div id="log" class="log" aria-live="polite"></div>
    </div>
  </div>

<script id="bots" type="application/json">__BOTS_JSON__</script>
<script>
const bots = JSON.parse(document.getElementById('bots').textContent);
const logEl = document.getElementById('log');
const connectBtn = document.getElementById('connect');
const disconnectBtn = document.getElementById('disconnect');
const nudgeBtn = document.getElementById('nudge');
const analyzeBtn = document.getElementById('analyze');
const clearBtn = document.getElementById('clear');
const nextBtn = document.getElementById('next');
const scenarioBar = document.getElementById('scenarioBar');
const selectedTitleEl = document.getElementById('selectedTitle');
const remoteAudio = document.getElementById('remote');
const statusEl = document.getElementById('status');

let pc, dc, micStream;
let selectedBotId = bots[0]?.id || null;

// Store conversation transcript
let conversationHistory = [];

// Show assistant only after it finishes speaking
const SHOW_AGENT_AFTER_SPEAKS = true;

// ---- Gate: track whether a user turn is still open (transcription not DONE yet)
let userTurnOpen = false;
function isUserAudioItem(it){
  return it && it.role === 'user' && it.type === 'message' &&
         Array.isArray(it.content) && it.content.some(p => p && p.type === 'input_audio');
}

// ---- Buffer + gate assistant output until user transcript is done (or timeout)
function createAgentBuffer(forward) {
  let haveAudio = false, audio = '', text = '', flushed = false;
  const MAX_WAIT_MS = 1800;     // how long to wait for user transcript to finish
  const STEP_MS     = 100;

  function flushWhenReady() {
    if (flushed) return;
    const start = Date.now();
    (function attempt(){
      if (!userTurnOpen || (Date.now() - start) >= MAX_WAIT_MS) {
        const line = (audio || text || '').trim();
        if (line) forward({ type: '__agent.buffer.flush', text: line });
        flushed = true;
        return;
      }
      setTimeout(attempt, STEP_MS);
    })();
  }

  return (msg) => {
    if (!SHOW_AGENT_AFTER_SPEAKS) return forward(msg);

    // Track user-turn lifecycle for gating
    // Also gate on raw VAD events to open/close faster
    if (msg.type === 'input_audio_buffer.speech_started') { userTurnOpen = true; return forward(msg); }
    if (msg.type === 'input_audio_buffer.committed') { userTurnOpen = false; return forward(msg); }

    if (msg.type === 'conversation.item.created') {
      const it = msg.item || {};
      if (isUserAudioItem(it)) userTurnOpen = true;
      return forward(msg);
    }
    if (msg.type === 'conversation.item.input_audio_transcription.completed' ||
        msg.type === 'conversation.item.input_audio_transcription.done') {
      userTurnOpen = false;
      return forward(msg);
    }

    // Assistant buffering
    switch (msg.type) {
      case 'response.created':
        haveAudio = false; audio = ''; text = ''; flushed = false;
        return forward(msg);

      case 'response.audio_transcript.delta':
        haveAudio = true; audio += (msg.delta || '');
        return; // swallow while buffering

      case 'response.audio_transcript.done':
        return flushWhenReady(); // print after your turn is closed (or timeout)

      case 'response.output_text.delta':
        text += (msg.delta || '');
        return; // swallow while buffering

      case 'response.output_text.done':
        if (!haveAudio) return flushWhenReady();
        return;

      case 'response.done':
        // safety: ensure we flush even if we missed the earlier signals
        flushWhenReady();
        return forward(msg);

      default:
        return forward(msg);
    }
  };
}

// --- helpers ---
function append(who, text){
  const d=document.createElement('div');
  d.className = 'msg ' + who;
  d.textContent = (who==='assistant'?'Agent':'You') + ': ' + text;
  logEl.appendChild(d); logEl.scrollTop = logEl.scrollHeight;
  
  // Store in conversation history
  conversationHistory.push({
    role: who === 'assistant' ? 'agent' : 'learner',
    text: text,
    timestamp: new Date().toISOString()
  });
}
function setStatus(t){ statusEl.textContent = t; }
function selectBot(botId){
  selectedBotId = botId;
  for (const btn of scenarioBar.querySelectorAll('.chip')) btn.classList.toggle('active', btn.dataset.id===botId);
  const b = bots.find(x=>x.id===botId); selectedTitleEl.textContent = b? b.title : '(none)';
}
function buildScenarioButtons(){
  scenarioBar.innerHTML = '';
  bots.forEach((b,i)=>{
    const el = document.createElement('div');
    el.className = 'chip' + (i===0?' active':'');
    el.dataset.id = b.id;
    el.textContent = b.title;
    el.onclick = ()=> selectBot(b.id);
    scenarioBar.appendChild(el);
  });
  selectBot(selectedBotId);
}

function waitForIceGatheringComplete(pc) {
  return new Promise(resolve => {
    if (pc.iceGatheringState === 'complete') return resolve();
    function check() {
      if (pc.iceGatheringState === 'complete') {
        pc.removeEventListener('icegatheringstatechange', check);
        resolve();
      }
    }
    pc.addEventListener('icegatheringstatechange', check);
  });
}

// --- streaming render state ---
let asstEl=null, asstBuf='', asstMode='audio'; // 'audio' or 'text'
let userEl=null, userBuf='';



function handleOAIEvent(msg) {
  switch (msg.type) {
    // Assistant OUTPUT (audio transcript stream)
    case 'response.audio_transcript.delta': {
      if (!asstEl || asstMode!=='audio') { asstEl=document.createElement('div'); asstEl.className='msg assistant'; logEl.appendChild(asstEl); asstMode='audio'; asstBuf=''; }
      asstBuf += (msg.delta||'');
      asstEl.textContent = 'Agent: ' + asstBuf; logEl.scrollTop = logEl.scrollHeight; break;
    }
    case 'response.audio_transcript.done': {
      if (asstEl) asstEl.textContent = 'Agent: ' + (msg.transcript||asstBuf);
      asstEl=null; asstBuf=''; asstMode='audio'; setStatus('ready'); break;
    }

    // Assistant OUTPUT (plain text stream)
    case 'response.output_text.delta': {
      if (!asstEl || asstMode!=='text') { asstEl=document.createElement('div'); asstEl.className='msg assistant'; logEl.appendChild(asstEl); asstMode='text'; asstBuf=''; }
      asstBuf += (msg.delta||'');
      asstEl.textContent = 'Agent: ' + asstBuf; logEl.scrollTop = logEl.scrollHeight; break;
    }
    case 'response.output_text.done': {
      if (asstEl) asstEl.textContent = 'Agent: ' + (msg.text||asstBuf);
      asstEl=null; asstBuf=''; asstMode='audio'; setStatus('ready'); break;
    }

    // Your INPUT (mic) transcription
    case 'conversation.item.input_audio_transcription.delta': {
      if (!userEl) { userEl=document.createElement('div'); userEl.className='msg user'; logEl.appendChild(userEl); userBuf=''; }
      userBuf += (msg.delta||'');
      userEl.textContent = 'You: ' + userBuf; logEl.scrollTop = logEl.scrollHeight; break;
    }
    case 'conversation.item.input_audio_transcription.completed':
    case 'conversation.item.input_audio_transcription.done': {
      if (userEl) userEl.textContent = 'You: ' + (msg.transcript||userBuf);
      userEl=null; userBuf=''; break;
    }
    
    case 'conversation.item.input_audio_transcription.failed': {
      console.warn('Transcription failed (audio still processed):', msg);
      if (userEl) {
        userEl.textContent = 'You: [Audio received - transcription unavailable]';
        userEl.style.opacity = '0.7';
      }
      userEl=null; userBuf='';
      // Don't show error to user - the bot can still respond to audio
      break;
    }
    case '__agent.buffer.flush': {
  append('assistant', (msg.text || '').trim());
  break;
}

case 'conversation.item.created': {
  // If this is the start of a user turn with input_audio,
  // create a placeholder "You:" line immediately so it precedes the agent.
  const it = msg.item || {};
  if (it.role === 'user' && it.type === 'message' && Array.isArray(it.content)) {
    const hasAudio = it.content.some(p => p && p.type === 'input_audio');
    if (hasAudio && !userEl) {
      userEl = document.createElement('div');
      userEl.className = 'msg user';
      userEl.textContent = 'You: ';   // blank placeholder (no mic emoji)
      logEl.appendChild(userEl);
      logEl.scrollTop = logEl.scrollHeight;
      userBuf = '';
    }
  }
  break;
}

    case 'response.created': {
      console.log('Response created:', msg.response);
      break;
    }
    
    case 'response.done': {
      console.log('Response done:', msg.response);
      if (msg.response && msg.response.status === 'failed') {
        console.error('Response failed:', msg.response.status_details);
        append('assistant', 'Sorry, I encountered an error. Please try again.');
      }
      break;
    }
    
    // Status only
    case 'input_audio_buffer.speech_started': {
  userTurnOpen = true;
  if (!userEl) {
    userEl = document.createElement('div');
    userEl.className = 'msg user';
    userEl.textContent = 'You: ';
    logEl.appendChild(userEl);
    logEl.scrollTop = logEl.scrollHeight;
    userBuf = '';
  }
  setStatus('listening…');
  break;
}
    
    case 'input_audio_buffer.committed': {
      userTurnOpen = false;
      break;
    }
case 'input_audio_buffer.speech_stopped': setStatus('processing…'); break;

    case 'session.created': setStatus('connected'); break;
    default: /* ignore */ break;
  }
}

function wireDataChannel(dc) {
  dc.onopen = () => {
    console.log('Data channel opened');
    dc.send(JSON.stringify({ type: 'session.update', session: { modalities: ['audio','text'] } }));
    setStatus('connected');
  };

  dc.onerror = (e) => {
    console.error('Data channel error:', e);
    append('assistant', 'Data channel error occurred');
    setStatus('error');
  };

  dc.onclose = (e) => {
    console.log('Data channel closed. Code:', e.code, 'Reason:', e.reason);
    if (e.code !== 1000) {
      append('assistant', 'Connection lost: ' + (e.reason || 'Unknown reason'));
    }
  };

  const deliver = (m) => handleOAIEvent(m);
  const bufferedDeliver = createAgentBuffer(deliver);

  dc.onmessage = (e) => {
    console.log('Received message:', e.data.substring(0, 100));
    try { 
      const parsed = JSON.parse(e.data);
      console.log('Message type:', parsed.type);
      bufferedDeliver(parsed); 
    } catch(err) { 
      console.error('Parse error:', err); 
    }
  };
}

async function connect(){
  connectBtn.disabled = true;
  try{
    console.log('Starting connection...');
    // 1) Ask server for ephemeral token with selected bot
    const sessRes = await fetch('/session', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ bot_id: selectedBotId }) });
    const session = await sessRes.json();
    if (!sessRes.ok) throw new Error(session.error || 'Session error');
    console.log('Session created:', session);

    // 2) Mic
    console.log('Requesting microphone access...');
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    console.log('Microphone access granted');

    // 3) WebRTC peer connection
    console.log('Creating peer connection...');
    pc = new RTCPeerConnection();
    pc.addTransceiver('audio', { direction: 'recvonly' }); // receive audio
    pc.ontrack = (e) => { 
      console.log('Received audio track');
      remoteAudio.srcObject = e.streams[0]; 
    };
    
    pc.oniceconnectionstatechange = () => {
      console.log('ICE connection state:', pc.iceConnectionState);
    };
    
    pc.onconnectionstatechange = () => {
      console.log('Connection state:', pc.connectionState);
    };
    
    // Add mic tracks and monitor them
    for (const track of micStream.getTracks()) {
      console.log('Adding mic track:', track.kind, 'enabled:', track.enabled, 'muted:', track.muted, 'readyState:', track.readyState);
      pc.addTrack(track, micStream);
      
      // Monitor track state
      track.onended = () => console.log('Mic track ended!');
      track.onmute = () => console.log('Mic track muted!');
      track.onunmute = () => console.log('Mic track unmuted!');
    }
    
    // Monitor audio stats
    const checkAudioStats = setInterval(async () => {
      if (!pc || pc.connectionState !== 'connected') {
        clearInterval(checkAudioStats);
        return;
      }
      const stats = await pc.getStats();
      stats.forEach(report => {
        if (report.type === 'outbound-rtp' && report.kind === 'audio') {
          console.log('Sending audio - bytes:', report.bytesSent, 'packets:', report.packetsSent);
        }
      });
    }, 3000);

    // 4) Data channel for commands/events
    dc = pc.createDataChannel('oai-events');
    wireDataChannel(dc);

    // 5) Offer
    const offer = await pc.createOffer({ offerToReceiveAudio: true });
    await pc.setLocalDescription(offer);
    await waitForIceGatheringComplete(pc);
    console.log('ICE gathering complete');

    // 6) Handshake with Realtime
    const url = `https://api.openai.com/v1/realtime?model=${encodeURIComponent(session.model || 'gpt-4o-realtime-preview-2024-12-17')}`;
    console.log('Connecting to OpenAI Realtime API...');
    const ans = await fetch(url, {
      method: 'POST',
      body: pc.localDescription.sdp,
      headers: {
        'Authorization': `Bearer ${session.client_secret?.value || session.client_secret || ''}`,
        'Content-Type': 'application/sdp',
        'OpenAI-Beta': 'realtime=v1'
      }
    });
    const sdpText = await ans.text();
    if (!ans.ok) { append('assistant', 'Realtime handshake failed: ' + sdpText); throw new Error('Realtime SDP error'); }
    console.log('Received SDP answer from OpenAI');
    const answer = { type: 'answer', sdp: sdpText };
    await pc.setRemoteDescription(answer);

    connectBtn.disabled = true;
    disconnectBtn.disabled = false;
    nudgeBtn.disabled = false;
    analyzeBtn.disabled = false;
    setStatus('ready');
    append('assistant', 'Connected. Speak when you are ready');
    console.log('Connection complete!');
  }catch(e){
    connectBtn.disabled = false;
    setStatus('error');
    append('assistant', 'Connect error: ' + e.message);
    console.error('Connection error:', e);
  }
}

async function disconnect(){
  nudgeBtn.disabled = true; disconnectBtn.disabled = true; connectBtn.disabled = false; analyzeBtn.disabled = true;
  if (dc) try{ dc.close(); }catch(e){}
  if (pc) try{ pc.close(); }catch(e){}
  if (micStream) for (const t of micStream.getTracks()) t.stop();
  setStatus('idle');
}

// Manual poke (if VAD is shy)
nudgeBtn.addEventListener('click', ()=>{
  if (!dc || dc.readyState !== 'open') return;
  dc.send(JSON.stringify({ type: 'response.create', response: { modalities: ['audio','text'] } }));
  append('user', '⏺️ Nudge sent (audio+text requested).');
});

// Analyze conversation and download report
analyzeBtn.addEventListener('click', async ()=>{
  if (conversationHistory.length === 0) {
    alert('No conversation to analyze yet. Start speaking first!');
    return;
  }
  
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = 'Analyzing...';
  
  try {
    const response = await fetch('/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        bot_id: selectedBotId,
        conversation: conversationHistory
      })
    });
    
    if (!response.ok) throw new Error('Analysis failed');
    
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `conversation-analysis-${new Date().toISOString().slice(0,10)}.txt`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    
    append('assistant', '📊 Analysis downloaded!');
  } catch (e) {
    console.error('Analysis error:', e);
    alert('Failed to generate analysis. Please try again.');
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = 'Analyze My Chat';
  }
});

clearBtn.addEventListener('click', ()=>{ 
  logEl.innerHTML=''; 
  conversationHistory = [];
});
nextBtn.addEventListener('click', ()=>{
  const idx = bots.findIndex(b=>b.id===selectedBotId);
  const next = bots[(idx+1) % bots.length];
  selectBot(next.id);
});

connectBtn.addEventListener('click', connect);
disconnectBtn.addEventListener('click', disconnect);

buildScenarioButtons();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug)
