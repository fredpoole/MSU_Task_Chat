// app.js — setup screen, Gemini Live voice client, and report downloads.
// -----------------------------------------------------------------------
// Flow: the learner builds a partner on the setup screen → POST
// /api/session returns a single-use ephemeral token plus the `setup`
// message → we open the Gemini Live WebSocket directly from the browser,
// stream 16 kHz PCM from the mic, and play back the 24 kHz PCM the model
// returns. Transcripts of both sides come from Gemini's own input/output
// transcription and are kept in `conversation` for /analyze.

const LIVE_WS_URL =
  'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained';

// Sent as a hidden "user" turn so the partner speaks first. Not shown or logged.
const KICKOFF_TEXT = '（对话开始。请你先开口，用中文自然地打个招呼，然后开始这个任务。）';
const NUDGE_TEXT = '（学生好像卡住了。请你用更简单的中文继续对话，或者换个说法再问一次。）';
const MAX_RECONNECTS = 3;
const STORAGE_KEY = 'mandarinPartnerSetup';

const $ = (id) => document.getElementById(id);

let OPTIONS = null;
let form = null;            // what the learner picked on the setup screen
let activeProfile = null;   // normalized profile returned by the server (name/voice filled in)
let activeSummary = null;
let conversation = [];
let lastAnalysis = null;

// ============================== helpers ==============================

function setStatus(state, label) {
  $('statusBox').hidden = false;
  $('statusDot').className = 'status-dot ' + state;
  $('statusText').textContent = label || { idle: 'Idle', connecting: 'Connecting…', ready: 'Listening', error: 'Error' }[state] || state;
}

// Traditional → Simplified normalizer (OpenCC loads from a CDN; if it's
// blocked we just leave text as-is rather than breaking the transcript).
let t2s = null;
function toSimplified(txt) {
  if (t2s === null) {
    try { t2s = typeof OpenCC !== 'undefined' ? OpenCC.Converter({ from: 't', to: 'cn' }) : false; }
    catch (e) { t2s = false; }
  }
  if (!t2s) return txt;
  try { return t2s(txt); } catch (e) { return txt; }
}

function find(list, id) { return list.find((x) => x.id === id); }

function slug(s) { return String(s || '').replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '') || 'partner'; }

function download(filename, content, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function base64FromBuffer(buf) {
  const bytes = new Uint8Array(buf);
  let bin = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

function bufferFromBase64(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

// ============================== setup screen ==============================

function defaultForm() {
  return { ...OPTIONS.defaults, personalities: [...OPTIONS.defaults.personalities] };
}

function loadInitialForm() {
  // 1) a shared link (#setup=...) wins, 2) the last setup on this device, 3) defaults
  const m = location.hash.match(/setup=([^&]+)/);
  if (m) {
    try {
      const json = new TextDecoder().decode(Uint8Array.from(atob(decodeURIComponent(m[1])), (c) => c.charCodeAt(0)));
      return { ...defaultForm(), ...JSON.parse(json) };
    } catch (e) { console.warn('Bad setup link', e); }
  }
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return { ...defaultForm(), ...JSON.parse(saved) };
  } catch (e) { /* storage unavailable */ }
  return defaultForm();
}

function saveForm() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(form)); } catch (e) { /* ignore */ }
}

function fillSelect(el, items, labelFn = (x) => x.label) {
  el.innerHTML = '';
  for (const it of items) {
    const o = document.createElement('option');
    o.value = it.id;
    o.textContent = labelFn(it);
    el.appendChild(o);
  }
}

function buildSetup() {
  // Levels
  const levelBox = $('levelOptions');
  levelBox.innerHTML = '';
  for (const lv of OPTIONS.levels) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'option-card';
    b.dataset.id = lv.id;
    b.innerHTML = `<b></b><small></small>`;
    b.querySelector('b').textContent = lv.label;
    b.querySelector('small').textContent = lv.hint;
    b.onclick = () => { form.level = lv.id; render(); };
    levelBox.appendChild(b);
  }

  // Tasks (grouped) + custom
  const taskSel = $('taskSelect');
  taskSel.innerHTML = '';
  const groups = [...new Set(OPTIONS.tasks.map((t) => t.group))];
  for (const g of groups) {
    const og = document.createElement('optgroup');
    og.label = g;
    for (const t of OPTIONS.tasks.filter((t) => t.group === g)) {
      const o = document.createElement('option');
      o.value = t.id;
      o.textContent = t.label;
      og.appendChild(o);
    }
    taskSel.appendChild(og);
  }
  const custom = document.createElement('option');
  custom.value = 'custom';
  custom.textContent = '✏️ Write my own task…';
  taskSel.appendChild(custom);
  taskSel.onchange = () => { form.task = taskSel.value; render(); };
  $('customTask').oninput = (e) => { form.custom_task = e.target.value; render(false); };

  // Gender
  const gBox = $('genderOptions');
  gBox.innerHTML = '';
  for (const g of OPTIONS.genders) {
    const b = document.createElement('button');
    b.type = 'button';
    b.dataset.id = g.id;
    b.textContent = g.label;
    b.onclick = () => { form.gender = g.id; form.voice = ''; render(); };
    gBox.appendChild(b);
  }

  // Personality chips (max 3)
  const pBox = $('personalityOptions');
  pBox.innerHTML = '';
  for (const p of OPTIONS.personalities) {
    const b = document.createElement('button');
    b.type = 'button';
    b.dataset.id = p.id;
    b.textContent = p.label;
    b.onclick = () => {
      const i = form.personalities.indexOf(p.id);
      if (i >= 0) form.personalities.splice(i, 1);
      else {
        form.personalities.push(p.id);
        if (form.personalities.length > 3) form.personalities.shift();
      }
      render();
    };
    pBox.appendChild(b);
  }

  fillSelect($('ageSelect'), OPTIONS.ages);
  fillSelect($('accentSelect'), OPTIONS.accents);
  fillSelect($('speedSelect'), OPTIONS.speeds);
  fillSelect($('feedbackSelect'), OPTIONS.feedback);

  const bind = (id, key) => { $(id).onchange = $(id).oninput = (e) => { form[key] = e.target.value; render(false); }; };
  bind('ageSelect', 'age');
  bind('accentSelect', 'accent');
  bind('speedSelect', 'speed');
  bind('feedbackSelect', 'feedback');
  bind('voiceSelect', 'voice');
  bind('nameInput', 'name');
  bind('occupationInput', 'occupation');
  bind('hometownInput', 'hometown');
  bind('extraInput', 'extra');
}

function suggestedVoice() {
  if (['middle', 'senior'].includes(form.age) && !form.personalities.length) return OPTIONS.older_voice[form.gender];
  const first = form.personalities[0] || 'warm';
  return OPTIONS.voice_suggestions[form.gender][first];
}

// Re-sync every control from `form`. `full` also rewrites text inputs
// (skipped while typing so the cursor doesn't jump).
function render(full = true) {
  document.querySelectorAll('#levelOptions .option-card').forEach((b) => b.classList.toggle('active', b.dataset.id === form.level));
  document.querySelectorAll('#genderOptions button').forEach((b) => b.classList.toggle('active', b.dataset.id === form.gender));
  document.querySelectorAll('#personalityOptions button').forEach((b) => b.classList.toggle('active', form.personalities.includes(b.dataset.id)));

  const suggested = suggestedVoice();
  const voices = OPTIONS.voices.filter((v) => v.gender === form.gender);
  const voiceSel = $('voiceSelect');
  fillSelect(voiceSel, [{ id: '', label: `Auto (${suggested})` }, ...voices], (v) => v.label || `${v.id} — ${v.character}`);
  if (!voices.some((v) => v.id === form.voice)) form.voice = '';

  $('customTaskField').hidden = form.task !== 'custom';
  if (full) {
    $('taskSelect').value = form.task;
    $('customTask').value = form.custom_task || '';
    $('ageSelect').value = form.age;
    $('accentSelect').value = form.accent;
    $('speedSelect').value = form.speed;
    $('feedbackSelect').value = form.feedback;
    $('nameInput').value = form.name || '';
    $('occupationInput').value = form.occupation || '';
    $('hometownInput').value = form.hometown || '';
    $('extraInput').value = form.extra || '';
  }
  voiceSel.value = form.voice;

  // Preview sentence
  const gender = find(OPTIONS.genders, form.gender);
  const age = find(OPTIONS.ages, form.age);
  const pers = form.personalities.map((id) => find(OPTIONS.personalities, id).label.split(' ')[0].toLowerCase());
  const task = form.task === 'custom'
    ? (form.custom_task ? `“${form.custom_task.slice(0, 120)}”` : '(describe your task above)')
    : find(OPTIONS.tasks, form.task).label;
  const desc = [pers.join(', '), gender.label.split(' ')[0].toLowerCase(), 'speaker'].filter(Boolean).join(' ');
  const who = form.name ? `${form.name}, a ${desc}` : `A ${desc}`;
  const where = form.hometown ? ` from ${form.hometown}` : '';
  const job = form.occupation ? ` who works as ${form.occupation}` : '';
  $('previewText').innerHTML = '';
  $('previewText').append(
    `${who} (${age.label.toLowerCase().replace(/ \((.*)\)/, ', $1')})${where}${job}, speaking `,
    Object.assign(document.createElement('b'), { textContent: find(OPTIONS.accents, form.accent).label }),
    ` Mandarin at a `,
    Object.assign(document.createElement('b'), { textContent: find(OPTIONS.levels, form.level).label }),
    ` level. Task: `,
    Object.assign(document.createElement('b'), { textContent: task }),
    '.'
  );
  $('startBtn').disabled = form.task === 'custom' && !form.custom_task.trim();
  saveForm();
}

function randomize() {
  const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
  const shuffled = [...OPTIONS.personalities].sort(() => Math.random() - 0.5);
  form = {
    ...form,
    task: pick(OPTIONS.tasks).id,
    gender: pick(OPTIONS.genders).id,
    age: pick(OPTIONS.ages).id,
    personalities: shuffled.slice(0, 1 + Math.floor(Math.random() * 2)).map((p) => p.id),
    accent: pick(OPTIONS.accents).id,
    name: '', occupation: '', hometown: '', extra: '', voice: '',
  };
  render();
}

async function copySetupLink() {
  const json = JSON.stringify(form);
  const b64 = btoa(String.fromCharCode(...new TextEncoder().encode(json)));
  const url = `${location.origin}${location.pathname}#setup=${encodeURIComponent(b64)}`;
  try {
    await navigator.clipboard.writeText(url);
    $('copyLinkBtn').textContent = '✓ Link copied';
  } catch (e) {
    prompt('Copy this link:', url);
  }
  setTimeout(() => { $('copyLinkBtn').textContent = '🔗 Copy link to this setup'; }, 2000);
}

// ============================== audio ==============================

class MicStreamer {
  constructor(onChunk) { this.onChunk = onChunk; this.muted = false; }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.ctx = new AudioContext();
    await this.ctx.audioWorklet.addModule('/static/pcm-recorder.js');
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, 'pcm-recorder');
    this.node.port.onmessage = (e) => {
      $('micMeter').style.width = this.muted ? '0%' : Math.min(100, e.data.rms * 400) + '%';
      if (!this.muted) this.onChunk(e.data.pcm);
    };
    src.connect(this.node);
    // Keep the worklet in the rendered graph (some browsers skip nodes that
    // don't reach the destination) without playing the mic back.
    const mute = this.ctx.createGain();
    mute.gain.value = 0;
    this.node.connect(mute).connect(this.ctx.destination);
  }

  stop() {
    try { this.node && this.node.disconnect(); } catch (e) { /* ignore */ }
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    if (this.ctx) this.ctx.close();
    $('micMeter').style.width = '0%';
  }
}

class PcmPlayer {
  constructor() {
    this.ctx = new AudioContext({ sampleRate: 24000 });
    this.nextTime = 0;
    this.sources = new Set();
  }

  play(b64, mimeType) {
    const rate = Number((/rate=(\d+)/.exec(mimeType || '') || [])[1]) || 24000;
    const int16 = new Int16Array(bufferFromBase64(b64));
    if (!int16.length) return;
    const audio = this.ctx.createBuffer(1, int16.length, rate);
    const ch = audio.getChannelData(0);
    for (let i = 0; i < int16.length; i++) ch[i] = int16[i] / 0x8000;
    const src = this.ctx.createBufferSource();
    src.buffer = audio;
    src.connect(this.ctx.destination);
    const start = Math.max(this.nextTime, this.ctx.currentTime + 0.04);
    src.start(start);
    this.nextTime = start + audio.duration;
    this.sources.add(src);
    $('partnerAvatar').classList.add('speaking');
    src.onended = () => {
      this.sources.delete(src);
      if (!this.sources.size) $('partnerAvatar').classList.remove('speaking');
    };
  }

  // Learner barged in: drop everything still queued.
  interrupt() {
    for (const s of this.sources) { try { s.stop(); } catch (e) { /* ignore */ } }
    this.sources.clear();
    this.nextTime = 0;
    $('partnerAvatar').classList.remove('speaking');
  }

  close() { this.interrupt(); this.ctx.close(); }
}

// ============================== transcript ==============================

const drafts = { user: null, assistant: null };

function appendSystem(text) {
  const div = document.createElement('div');
  div.className = 'log-entry system';
  div.textContent = text;
  $('chatLog').appendChild(div);
  $('chatLog').scrollTop = $('chatLog').scrollHeight;
}

// Transcription arrives in small chunks; grow a draft bubble until the turn ends.
function addChunk(role, text) {
  const other = role === 'user' ? 'assistant' : 'user';
  if (drafts[other]) commit(other);
  if (!drafts[role]) {
    const el = document.createElement('div');
    el.className = `log-entry ${role} draft`;
    $('chatLog').appendChild(el);
    drafts[role] = { el, text: '', timestamp: new Date().toISOString() };
  }
  drafts[role].text += text;
  drafts[role].el.textContent = toSimplified(drafts[role].text.trim());
  $('chatLog').scrollTop = $('chatLog').scrollHeight;
}

function commit(role) {
  const d = drafts[role];
  if (!d) return;
  drafts[role] = null;
  const text = toSimplified(d.text.trim());
  if (!text) { d.el.remove(); return; }
  d.el.textContent = text;
  d.el.classList.remove('draft');
  conversation.push({ role, text, timestamp: d.timestamp });
}

// ============================== live session ==============================

const live = {
  ws: null, mic: null, player: null,
  resumeHandle: null, ending: false, reconnects: 0,
  started: null, timer: null,
};

function send(obj) {
  if (live.ws && live.ws.readyState === WebSocket.OPEN) live.ws.send(JSON.stringify(obj));
}

async function requestSession(resumeHandle) {
  const resp = await fetch('/api/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile: activeProfile || form, resume_handle: resumeHandle || null }),
  });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error((body.error || 'Session request failed') + (body.detail ? ': ' + body.detail : ''));
  return body;
}

function openSocket(session, isResume) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`${LIVE_WS_URL}?access_token=${encodeURIComponent(session.token)}`);
    ws.binaryType = 'arraybuffer';
    live.ws = ws;
    let ready = false;

    ws.onopen = () => send({ setup: session.setup });
    ws.onerror = () => { if (!ready) reject(new Error('Could not connect to Gemini Live.')); };
    ws.onclose = (ev) => {
      if (!ready) { reject(new Error(`Gemini closed the connection (${ev.code}) ${ev.reason || ''}`)); return; }
      if (ws === live.ws) onSocketClosed(ev);
    };
    ws.onmessage = (ev) => {
      let msg;
      try {
        msg = JSON.parse(typeof ev.data === 'string' ? ev.data : new TextDecoder().decode(ev.data));
      } catch (e) { console.warn('Unparseable message', e); return; }

      if (msg.setupComplete) {
        ready = true;
        resolve();
        if (!isResume) send({ clientContent: { turns: [{ role: 'user', parts: [{ text: KICKOFF_TEXT }] }], turnComplete: true } });
        return;
      }
      handleServerMessage(msg);
    };
  });
}

function handleServerMessage(msg) {
  const sc = msg.serverContent;
  if (sc) {
    if (sc.inputTranscription && sc.inputTranscription.text) addChunk('user', sc.inputTranscription.text);
    if (sc.outputTranscription && sc.outputTranscription.text) addChunk('assistant', sc.outputTranscription.text);
    for (const part of (sc.modelTurn && sc.modelTurn.parts) || []) {
      if (part.inlineData && part.inlineData.data) {
        if (drafts.user) commit('user');
        live.player.play(part.inlineData.data, part.inlineData.mimeType);
      }
    }
    if (sc.interrupted) { live.player.interrupt(); commit('assistant'); }
    if (sc.turnComplete) { commit('user'); commit('assistant'); }
  }
  if (msg.sessionResumptionUpdate && msg.sessionResumptionUpdate.resumable && msg.sessionResumptionUpdate.newHandle) {
    live.resumeHandle = msg.sessionResumptionUpdate.newHandle;
  }
  if (msg.goAway) {
    // Google is about to rotate this connection; move to a new one now.
    reconnect();
  }
}

function onSocketClosed(ev) {
  if (live.ending) return;
  console.warn('Live socket closed', ev.code, ev.reason);
  reconnect(ev);
}

async function reconnect(ev) {
  if (live.ending || live.reconnecting) return;
  if (!live.resumeHandle || live.reconnects >= MAX_RECONNECTS) {
    setStatus('error', 'Disconnected');
    appendSystem(`Connection lost${ev && ev.reason ? ' (' + ev.reason + ')' : ''}. Your transcript is saved — you can still analyze it.`);
    endConversation(true);
    return;
  }
  live.reconnecting = true;
  live.reconnects++;
  setStatus('connecting', 'Reconnecting…');
  const old = live.ws;
  try {
    const session = await requestSession(live.resumeHandle);
    await openSocket(session, true);
    try { old && old.close(); } catch (e) { /* ignore */ }
    live.reconnects = 0;
    setStatus('ready');
  } catch (e) {
    console.error('Reconnect failed', e);
    live.reconnecting = false;
    return reconnect(ev);
  }
  live.reconnecting = false;
}

async function startConversation(samePartner) {
  $('setupScreen').hidden = true;
  $('chatScreen').hidden = false;
  $('resultsPanel').hidden = true;
  $('resultsSummary').hidden = true;
  $('downloads').hidden = true;
  $('chatLog').innerHTML = '';
  conversation = [];
  lastAnalysis = null;
  drafts.user = drafts.assistant = null;
  if (!samePartner) activeProfile = null;
  Object.assign(live, { resumeHandle: null, ending: false, reconnects: 0, reconnecting: false });
  window.scrollTo(0, 0);

  setStatus('connecting');
  $('partnerName').textContent = form.name || 'Connecting…';
  $('partnerMeta').textContent = '';
  $('partnerAvatar').textContent = (form.name || '?').slice(0, 1);

  try {
    // Create audio contexts inside the click handler so autoplay rules allow sound.
    live.player = new PcmPlayer();
    live.mic = new MicStreamer((pcm) => {
      send({ realtimeInput: { audio: { data: base64FromBuffer(pcm), mimeType: 'audio/pcm;rate=16000' } } });
    });
    await live.mic.start();

    const session = await requestSession(null);
    activeProfile = session.profile;
    activeSummary = session.profile_summary;
    showPartner();
    await openSocket(session, false);
  } catch (e) {
    console.error(e);
    setStatus('error');
    $('partnerName').textContent = 'Not connected';
    appendSystem('Could not start: ' + e.message);
    if (e.name === 'NotAllowedError') appendSystem('Please allow microphone access and try again.');
    endConversation(true);
    return;
  }

  setStatus('ready');
  appendSystem('Connected — your partner will say hello. Speak whenever you are ready.');
  $('muteBtn').disabled = $('nudgeBtn').disabled = $('endBtn').disabled = false;
  live.started = Date.now();
  live.timer = setInterval(() => {
    const s = Math.floor((Date.now() - live.started) / 1000);
    $('timer').textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }, 1000);
}

function showPartner() {
  const p = activeProfile;
  $('partnerName').textContent = p.name;
  $('partnerAvatar').textContent = p.name.slice(0, 1);
  const get = (label) => (activeSummary.find(([k]) => k === label) || [])[1];
  $('partnerMeta').textContent = [get('Task'), `${get('Accent (requested)')} · ${get('Practice level')}`, `from ${p.hometown}`]
    .filter(Boolean).join(' · ');
}

function endConversation(silent) {
  live.ending = true;
  commit('user');
  commit('assistant');
  clearInterval(live.timer);
  try { live.ws && live.ws.close(); } catch (e) { /* ignore */ }
  live.ws = null;
  if (live.mic) live.mic.stop();
  if (live.player) live.player.close();
  live.mic = live.player = null;
  $('muteBtn').disabled = $('nudgeBtn').disabled = $('endBtn').disabled = true;
  if (!silent) { setStatus('idle', 'Ended'); appendSystem('Conversation ended.'); }
  $('resultsPanel').hidden = false;
  $('analyzeBtn').disabled = !conversation.some((m) => m.role === 'user');
  $('againBtn').hidden = !activeProfile;
}

// ============================== analysis ==============================

async function analyze() {
  const btn = $('analyzeBtn');
  btn.disabled = true;
  btn.textContent = 'Analyzing… (this can take ~30 s)';
  try {
    const resp = await fetch('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation, profile: activeProfile || form }),
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(body.error || 'Analysis failed');
    lastAnalysis = body;
    showSummary(body.analysis);
    $('downloads').hidden = false;
  } catch (e) {
    alert('Failed to generate analysis: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '📊 Analyze again';
  }
}

function showSummary(a) {
  const box = $('resultsSummary');
  box.innerHTML = '';
  box.hidden = false;
  const est = a.actfl_estimate;

  const levelRow = document.createElement('div');
  levelRow.className = 'summary-level';
  if (est && !est.error) {
    levelRow.append(
      Object.assign(document.createElement('span'), { className: 'badge', textContent: est.level }),
      Object.assign(document.createElement('span'), { className: 'muted', textContent: `ACTFL-informed estimate · ${est.confidence} confidence · not an official rating` }),
    );
  } else {
    levelRow.append(Object.assign(document.createElement('span'), { className: 'muted', textContent: (est && est.error) || a.actfl_note || '' }));
  }
  box.appendChild(levelRow);

  const tiles = document.createElement('div');
  tiles.className = 'stat-tiles';
  const tile = (value, label) => {
    const t = document.createElement('div');
    t.className = 'stat-tile';
    t.append(Object.assign(document.createElement('b'), { textContent: value }), Object.assign(document.createElement('small'), { textContent: label }));
    tiles.appendChild(t);
  };
  tile(a.duration_minutes != null ? a.duration_minutes.toFixed(1) : '—', 'minutes');
  tile(a.turn_taking.learner_turns, 'your turns');
  tile(a.basic_stats.total_characters, 'characters spoken');
  tile(a.basic_stats.avg_characters_per_turn, 'characters / turn');
  tile(a.turn_taking.learner_share_of_characters + '%', 'of the talking');
  if (a.vocabulary_metrics && a.vocabulary_metrics.total_unique_words != null) tile(a.vocabulary_metrics.total_unique_words, 'unique words');
  if (a.complexity_metrics && a.complexity_metrics.connector_count != null) tile(a.complexity_metrics.connector_count, 'connectors used');
  box.appendChild(tiles);

  if (est && !est.error) {
    const cols = document.createElement('div');
    cols.className = 'summary-cols';
    const list = (title, items) => {
      const d = document.createElement('div');
      d.appendChild(Object.assign(document.createElement('b'), { textContent: title }));
      const ul = document.createElement('ul');
      for (const it of items || []) ul.appendChild(Object.assign(document.createElement('li'), { textContent: it }));
      d.appendChild(ul);
      cols.appendChild(d);
    };
    list('Strengths', est.strengths);
    list('Areas to grow', est.areas_to_grow);
    box.appendChild(cols);
  }
}

function downloadReport(format) {
  if (!lastAnalysis) return;
  const name = slug(activeProfile ? activeProfile.name : 'partner');
  const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-');
  const base = `mandarin-chat-${name}-${stamp}`;
  if (format === 'html') download(`${base}.html`, lastAnalysis.html, 'text/html;charset=utf-8');
  if (format === 'csv') download(`${base}.csv`, lastAnalysis.csv, 'text/csv;charset=utf-8');
  if (format === 'txt') download(`${base}.txt`, lastAnalysis.text, 'text/plain;charset=utf-8');
  if (format === 'json') download(`${base}.json`, JSON.stringify(lastAnalysis.analysis, null, 2), 'application/json');
}

// ============================== wiring ==============================

async function init() {
  try {
    const resp = await fetch('/api/options');
    OPTIONS = await resp.json();
  } catch (e) {
    $('previewText').textContent = 'Could not load options from the server: ' + e.message;
    return;
  }
  form = loadInitialForm();
  buildSetup();
  render();

  $('startBtn').onclick = () => startConversation(false);
  $('randomBtn').onclick = randomize;
  $('copyLinkBtn').onclick = copySetupLink;
  $('endBtn').onclick = () => endConversation(false);
  $('nudgeBtn').onclick = () => {
    send({ clientContent: { turns: [{ role: 'user', parts: [{ text: NUDGE_TEXT }] }], turnComplete: true } });
    appendSystem('Nudged your partner to keep going.');
  };
  $('muteBtn').onclick = () => {
    const mic = live.mic;
    if (!mic) return;
    mic.muted = !mic.muted;
    if (mic.muted) send({ realtimeInput: { audioStreamEnd: true } });
    $('muteBtn').firstChild.textContent = mic.muted ? '🔇 Unmute mic ' : '🎙️ Mute mic ';
  };
  $('toggleTranscriptBtn').onclick = () => {
    const hidden = $('chatLog').classList.toggle('hidden-transcript');
    $('toggleTranscriptBtn').textContent = hidden ? 'Show transcript' : 'Hide transcript';
  };
  $('analyzeBtn').onclick = analyze;
  $('newPartnerBtn').onclick = () => {
    $('chatScreen').hidden = true;
    $('setupScreen').hidden = false;
    $('statusBox').hidden = true;
    window.scrollTo(0, 0);
  };
  $('againBtn').onclick = () => startConversation(true);
  document.querySelectorAll('#downloads [data-format]').forEach((b) => {
    b.onclick = () => downloadReport(b.dataset.format);
  });
  window.addEventListener('beforeunload', (e) => {
    if (conversation.length && !lastAnalysis) { e.preventDefault(); e.returnValue = ''; }
  });
}

init();
