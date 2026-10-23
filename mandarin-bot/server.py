# server.py — customizable Mandarin conversation partner (Gemini Live voice)
# ---------------------------------------------------------------------------
# CFL (Chinese as a Foreign Language) speaking practice. The learner builds
# their own conversation partner on the setup screen (level, task, gender,
# age, personality, accent, ...), talks to it by voice through the Gemini
# Live API, and downloads stats + an ACTFL-informed analysis afterwards.
#
#   partner.py   — setup-screen options + system-instruction builder
#   analysis.py  — jieba stats, Gemini ACTFL estimate, report renderers
#   static/      — the browser app (setup screen, voice client, downloads)
#
# Run:
#   pip install -r requirements.txt
#   GEMINI_API_KEY=... python server.py
# Open: http://127.0.0.1:5000/

import os
import traceback
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_from_directory
from flask_cors import CORS

load_dotenv()

import analysis  # noqa: E402  (reads GEMINI_* env vars at import, after load_dotenv)
import partner  # noqa: E402

# --------------------------- Config ---------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live")
# Voice-activity detection: how long a pause (ms) ends the learner's turn.
# Learners pause mid-sentence a lot, so this is longer than a native default.
RT_SILENCE_MS = int(os.getenv("RT_SILENCE_MS", "1200"))

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
CORS(app)


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/realtime")
def realtime_page():
    # Old URL from the OpenAI version — keep existing links working.
    return redirect("/")


@app.route("/api/options")
def options():
    return jsonify({**partner.OPTIONS, "defaults": partner.DEFAULT_PROFILE})


@app.route("/api/session", methods=["POST"])
def create_session():
    """
    Build the partner from the learner's choices and mint a single-use
    ephemeral Gemini token so the browser can open the Live WebSocket
    without ever seeing GEMINI_API_KEY.

    Returns the token, the normalized profile (with the name/hometown/voice
    actually used), and the exact `setup` message the browser must send.
    """
    if not GEMINI_API_KEY:
        msg = "GEMINI_API_KEY is not set on this server (Render: Environment tab)."
        print(f"create_session error: {msg}")
        return jsonify({"error": msg}), 500

    data = request.json or {}
    # On reconnect (session resumption) the browser sends back the profile
    # it already has, so the same partner/voice is kept.
    profile = partner.normalize_profile(data.get("profile"))
    instructions = partner.build_instructions(profile)

    setup = {
        "model": f"models/{GEMINI_LIVE_MODEL}",
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": profile["voice"]}}
            },
        },
        "systemInstruction": {"parts": [{"text": instructions}]},
        "inputAudioTranscription": {},
        "outputAudioTranscription": {},
        "realtimeInputConfig": {
            "automaticActivityDetection": {
                "silenceDurationMs": RT_SILENCE_MS,
                "prefixPaddingMs": 300,
                # Learners speak hesitantly and quietly; don't cut them off.
                "endOfSpeechSensitivity": "END_SENSITIVITY_LOW",
            }
        },
        # Lets the browser reconnect transparently when Google rotates the
        # connection (~10 min), and sliding-window compression lifts the
        # ~15 min cap on audio sessions.
        "sessionResumption": {"handle": data["resume_handle"]} if data.get("resume_handle") else {},
        "contextWindowCompression": {"slidingWindow": {}},
    }

    now = datetime.now(timezone.utc)
    token_body = {
        "uses": 1,
        "expireTime": (now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "newSessionExpireTime": (now + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # A constrained token's setup REPLACES whatever the browser sends, so
        # the whole partner setup (instructions, voice, transcription...)
        # has to live here — locking only the model silently dropped the
        # learner's persona/voice/level. Also means the browser can't
        # swap in its own system prompt.
        "bidiGenerateContentSetup": setup,
    }

    def mint(body):
        return requests.post(
            "https://generativelanguage.googleapis.com/v1beta/auth_tokens",
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json=body,
            timeout=15,
        )

    try:
        resp = mint(token_body)
        if resp.status_code == 400 and "Unknown name" in resp.text:
            # The constraint field name differs between API versions; the
            # token is still single-use and expires in minutes without it.
            print(f"Token constraint rejected, retrying without it: {resp.text[:300]}")
            token_body.pop("bidiGenerateContentSetup")
            resp = mint(token_body)
        if not resp.ok:
            print(f"Gemini token error {resp.status_code}: {resp.text}")
            return jsonify({
                "error": f"Gemini token error {resp.status_code}",
                "detail": resp.text[:2000],
            }), resp.status_code
        token = resp.json().get("name")
        if not token:
            return jsonify({"error": "Gemini token response had no token", "detail": resp.text[:2000]}), 502
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "token": token,
        "profile": profile,
        "profile_summary": partner.describe_profile(profile),
        "setup": setup,
    })


@app.route("/analyze", methods=["POST"])
def analyze_conversation():
    """
    Analyze the conversation and return every download format at once:
    the analysis as JSON, plus ready-to-save text, HTML and CSV reports.
    """
    try:
        data = request.json or {}
        conversation = [
            {"role": m.get("role"), "text": str(m.get("text", "")), "timestamp": m.get("timestamp")}
            for m in data.get("conversation", [])
            if m.get("role") in ("user", "assistant") and str(m.get("text", "")).strip()
        ]
        if not conversation:
            return jsonify({"error": "No conversation data provided"}), 400

        profile = partner.normalize_profile(data.get("profile"))
        result = analysis.build_analysis(
            conversation, profile, partner.describe_profile(profile), partner.task_label(profile))
        return jsonify({
            "analysis": result,
            "text": analysis.render_text(result),
            "html": analysis.render_html(result),
            "csv": analysis.render_csv(result),
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/debug/nlp")
def debug_nlp():
    """Check Chinese NLP (jieba) and API configuration status."""
    return jsonify({
        "analysis_available": analysis.ANALYSIS_AVAILABLE,
        "error_message": analysis.NLP_ERROR_MESSAGE,
        "gemini_key_set": bool(GEMINI_API_KEY),
        "live_model": GEMINI_LIVE_MODEL,
        "analysis_model": analysis.GEMINI_ANALYSIS_MODEL,
    })


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug)
