# 中文口语练习 — Mandarin speaking practice (Gemini Live)

Learners design their own conversation partner, talk to them by voice in Mandarin,
and download stats and an ACTFL-informed analysis afterwards.

## What the learner can customize

| Setting | Options |
|---|---|
| Level | Novice Low → Advanced (controls the partner's vocabulary, sentence length, pace) |
| Task | 10 conversation topics, 8 role-plays, or a task the learner writes |
| Partner | gender, age, up to 3 personality traits, name, occupation, hometown, free-text details |
| Speech | accent (best effort), speed, correction style, voice |

All options live in [`partner.py`](partner.py). Edit the lists there to add tasks,
personalities or accents; the setup screen picks them up automatically.
**Copy link to this setup** produces a URL that opens the app with the same partner
already chosen. That's useful for assigning a specific scenario to a class.

### About accents
Gemini Live has no accent or language-code setting. The accent is requested in the
partner's instructions, so you'll hear it mostly in word choice and intonation, and how
strong it is varies. The UI labels it "best effort".

## Downloads after a conversation
- **Report (.html)**: partner settings, ACTFL-informed estimate, strengths and areas to
  grow, corrections, all stats, and the transcript. It's printable, so you can save it as a PDF.
- **Stats (.csv)**: one row per conversation with fixed columns, so files from many
  students can be stacked into one spreadsheet.
- **All data (.json)**: everything, including the full transcript and raw metrics.
- **Plain text (.txt)**: the classic text report.

The level estimate needs about 5+ minutes and 4+ learner turns.

## Running

```bash
pip install -r requirements.txt
cp .env.example .env   # then put your key in it
python server.py       # http://127.0.0.1:5000/
```

### Environment variables
| Variable | Default | |
|---|---|---|
| `GEMINI_API_KEY` | — | **Required.** From Google AI Studio. Only the server sees it. |
| `GEMINI_LIVE_MODEL` | `gemini-3.8-live` | Voice model |
| `GEMINI_ANALYSIS_MODEL` | `gemini-3.8-flash` | Model for the ACTFL estimate |
| `RT_SILENCE_MS` | `1200` | Pause length (ms) that ends the learner's turn |

`OPENAI_API_KEY` is no longer used.

### Render
Root directory `mandarin-bot`, build `pip install -r requirements.txt`, start
`gunicorn server:app`. Set `GEMINI_API_KEY` on the service's Environment tab.
`/debug/nlp` shows whether jieba loaded and whether the key is set.

## How it works
- `POST /api/session` builds the system instruction from the learner's choices and mints a
  single-use **ephemeral token**. The browser then opens the Gemini Live WebSocket directly,
  so the API key never reaches the browser.
- The browser streams 16 kHz PCM from the mic (`static/pcm-recorder.js`) and plays the
  24 kHz PCM the model returns. Both sides are transcribed by Gemini.
- Google rotates Live connections about every 10 minutes. The client reconnects
  transparently using session resumption, keeping the same partner and context.
- `POST /analyze` runs the jieba-based stats, asks Gemini for the ACTFL-informed estimate,
  and returns all four download formats.

Files: `server.py` (Flask routes), `partner.py` (options + prompt builder),
`analysis.py` (stats, ACTFL estimate, report renderers), `static/` (browser app).
