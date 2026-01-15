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
        "role": "Patient Polish conversation partner",
        "task": (
            "Task Situation: It’s Monday morning at 8 a.m. in October. You are on your way to school and decide to pick up breakfast for yourself and your friend. You have just entered a coffee shop. Your Goal: Order any food and a drink you want. Order food and a drink for your friend. Your friend loves bagels and lattes but cannot have dairy products (e.g., cow’s milk)."
        ),
        "constraints": (
            "Speak slowly; use novice-high vocabulary. Track learner errors; if an utterance has 3+ mistakes, "
            "signal partial misunderstanding and ask them to repeat or rephrase, then scaffold."
        ),
        "language_hint": "English"
    },
    {
        "id": "rest-es",
        "title": "Restaurant Booking (ES)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "Compañero de conversación en español",
        "task": (
            "Practicar reservas y pedidos en un restaurante: saludar, número de personas, hora, alergias, "
            "preferencias y cuenta."
        ),
        "constraints": (
            "Habla claro y despacio; vocabulario de nivel intermedio-bajo. Negocia significado si hay 3+ errores; "
            "pide repetir con una pista."
        ),
        "language_hint": "Spanish"
    },
    {
        "id": "doctor-en",
        "title": "Doctor Visit (ZH)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "Supportive clinic intake partner",
        "task": (
            "Simulate a primary-care intake: symptoms, duration, severity, medications, allergies, history. "
            "Encourage precise descriptions and safety-seeking behavior."
        ),
        "constraints": "Speak calmly; define medical terms briefly; check comprehension; novice-high register.",
        "language_hint": "Chinese"
    },
    {
        "id": "travel-es",
        "title": "Travel Booking (IT)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
      "role": "Agente di viaggi",
"task": (
    "Aiuta a prenotare un viaggio: date, destinazioni, budget, alloggio, trasporto. Rafforza numeri, "
    "date e conferme."
),
"constraints": "Ritmo lento; riformula quando c'è confusione; conferma i dati chiave.",
        "language_hint": "Italian"
    },
    {
        "id": "job-en",
        "title": "Job Interview (FR)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
       "role": "Coach d'entretien",
"task": (
    "Mène un entretien simulé : expérience, compétences, exemples STAR, relances. Offre un bref retour après chaque "
    "réponse et un résumé en trois points à la fin."
),
"constraints": "Utilise un vocabulaire accessible ; garde des tours de parole courts ; une question à la fois.",
        "language_hint": "French"
    },
    {
        "id": "roommate-en",
        "title": "Roommate Negotiation (ES)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "Collaborative roommate",
        "task": (
            "Negotiate apartment norms: cleaning, guests, noise, shared costs. Seek agreement with proposals and "
            "counterproposals; confirm decisions."
        ),
        "constraints": "Slow pace, novice-high; negotiate meaning after 3+ mistakes.",
        "language_hint": "Spanish"
    },
    {
        "id": "returns-es",
        "title": "Customer Service Return (ES)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "Agente de atención al cliente",
        "task": (
            "Practica devoluciones/cambios: saludar, describir problema, ticket, política, opciones. Modela cortesía y "
            "frases útiles."
        ),
        "constraints": "Habla despacio, frases cortas; comprueba comprensión; pide repetir tras 3+ errores.",
        "language_hint": "Spanish"
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
      politely signal misunderstanding and ask for a clear repeat or rephrase, offering a simple model. 
    RECAP: When the scenario goals are completed, give a 2–3 bullet summary and suggest one actionable next step.
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
const clearBtn = document.getElementById('clear');
const nextBtn = document.getElementById('next');
const scenarioBar = document.getElementById('scenarioBar');
const selectedTitleEl = document.getElementById('selectedTitle');
const remoteAudio = document.getElementById('remote');
const statusEl = document.getElementById('status');

let pc, dc, micStream;
let selectedBotId = bots[0]?.id || null;

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
    
    for (const track of micStream.getTracks()) {
      console.log('Adding mic track:', track.kind);
      pc.addTrack(track, micStream);
    }

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
  nudgeBtn.disabled = true; disconnectBtn.disabled = true; connectBtn.disabled = false;
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

clearBtn.addEventListener('click', ()=>{ logEl.innerHTML=''; });
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
