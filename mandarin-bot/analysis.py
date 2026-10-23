# analysis.py — post-conversation stats + ACTFL-informed estimate + reports.
# ---------------------------------------------------------------------------
# Chinese-appropriate conversation analysis. Uses jieba for word
# segmentation/POS tagging (there is no whitespace between Chinese words, so
# English tools like nltk's word_tokenize or textstat's syllable-based
# readability formulas don't apply). Metrics here are simple, transparent
# proxies (utterance length, connector use, aspect-marker use, vocabulary
# diversity) — not a validated linguistic analysis.
#
# build_analysis() returns one plain dict; render_text / render_html /
# render_csv turn that dict into the downloadable files.

import csv
import html
import io
import json
import os
import re
from collections import Counter
from datetime import datetime

import requests

# --------------------------- Chinese NLP (jieba) ---------------------------
ANALYSIS_AVAILABLE = False
NLP_ERROR_MESSAGE = None

print("=" * 60)
print("Initializing Chinese NLP (jieba) for conversation analysis...")
print("=" * 60)

try:
    import jieba
    import jieba.posseg as pseg
    # Trigger jieba's dictionary build once at startup rather than on the
    # first user request, so the first /analyze call isn't slow.
    list(jieba.cut("初始化"))
    ANALYSIS_AVAILABLE = True
    print("✓ jieba imported and initialized successfully")
except ImportError as e:
    NLP_ERROR_MESSAGE = f"Import error: {str(e)}"
    print("✗ IMPORT ERROR - jieba not installed")
    print("To fix this issue, ensure requirements.txt contains: jieba==0.42.1")
except Exception as e:
    NLP_ERROR_MESSAGE = f"Initialization error: {str(e)}"
    print(f"✗ INITIALIZATION ERROR: {NLP_ERROR_MESSAGE} ({type(e).__name__})")

# Text model that reads the whole transcript and produces the ACTFL-informed
# estimate (a separate, non-realtime Gemini call from the voice session).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_ANALYSIS_MODEL = os.getenv("GEMINI_ANALYSIS_MODEL", "gemini-3.8-flash")

CONNECTOR_MARKERS = [
    '因为', '所以', '但是', '可是', '虽然', '如果', '不但', '而且',
    '除了', '后来', '首先', '其次', '另外', '于是', '因此', '不过'
]
ASPECT_MARKERS = ('了', '过', '着')
FILLER_MARKERS = ['嗯', '呃', '那个', '就是', '然后', '这个']
HANZI = r'[一-鿿]'

MIN_MINUTES_FOR_ACTFL = 5
MIN_USER_TURNS_FOR_ACTFL = 4


def _parse_timestamp(ts):
    """Parse a client-side ISO timestamp (e.g. '...Z') into a datetime, or None."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
    except Exception:
        return None


def compute_duration_minutes(conversation):
    """Elapsed time between the first and last logged message, in minutes."""
    timestamps = [_parse_timestamp(m.get('timestamp')) for m in conversation]
    timestamps = [t for t in timestamps if t is not None]
    if len(timestamps) < 2:
        return None
    return (max(timestamps) - min(timestamps)).total_seconds() / 60.0


def _words(text):
    return [w for w in jieba.cut(text) if re.search(HANZI, w)]


def analyze_basic_stats(text, turns):
    """Basic Chinese text statistics (characters, jieba words, sentences)."""
    hanzi = re.findall(HANZI, text)
    words = _words(text) if ANALYSIS_AVAILABLE else []
    sentences = [s for s in re.split(r'[。！？!?.]+', text) if s.strip()]

    # ASR transcription of spontaneous spoken Chinese often carries almost no
    # terminal punctuation, so splitting on 。！？ collapses each turn into ~1
    # "sentence" and avg-words-per-sentence balloons. Flag it so the report
    # can caveat instead of presenting it as a reliable measure.
    turns_with_terminal_punct = sum(1 for t in turns if re.search(r'[。！？!?]', t))
    punctuation_sparse = len(turns) > 0 and (turns_with_terminal_punct / len(turns)) < 0.5

    return {
        'total_characters': len(hanzi),
        'total_words': len(words),
        'total_sentences': len(sentences),
        'total_turns': len(turns),
        'avg_words_per_sentence': round(len(words) / max(len(sentences), 1), 2),
        'avg_words_per_turn': round(len(words) / max(len(turns), 1), 2),
        'avg_characters_per_turn': round(len(hanzi) / max(len(turns), 1), 2),
        'avg_characters_per_word': round(len(hanzi) / max(len(words), 1), 2),
        'longest_turn_characters': max((len(re.findall(HANZI, t)) for t in turns), default=0),
        'punctuation_sparse': punctuation_sparse,
    }


def analyze_complexity(text, words):
    """Proxies for sentence-linking / narration complexity."""
    if not text.strip():
        return {'connector_count': 0, 'connectors_used': [], 'aspect_marker_count': 0}
    return {
        'connector_count': sum(text.count(m) for m in CONNECTOR_MARKERS),
        'connectors_used': sorted({m for m in CONNECTOR_MARKERS if m in text}),
        'aspect_marker_count': sum(1 for w in words if w in ASPECT_MARKERS),
    }


def analyze_fluency(turns):
    """Filler-word and hesitation/repetition metrics for Mandarin speech."""
    total_fillers = 0
    total_chars = 0
    hesitations = 0
    for turn in turns:
        total_chars += len(re.findall(HANZI, turn))
        total_fillers += sum(turn.count(f) for f in FILLER_MARKERS)
        toks = _words(turn)
        hesitations += sum(1 for i in range(len(toks) - 1) if toks[i] == toks[i + 1])
    return {
        'total_filler_words': total_fillers,
        'filler_word_rate_per_100_chars': round(total_fillers / max(total_chars, 1) * 100, 2),
        'hesitations_repetitions': hesitations,
    }


def analyze_vocabulary(text):
    """Vocabulary diversity and a jieba-POS-based word-type breakdown."""
    words = _words(text)
    if not words:
        return {'total_unique_words': 0, 'type_token_ratio': 0, 'nouns': 0, 'verbs': 0,
                'adjectives': 0, 'adverbs': 0, 'most_common_words': []}
    try:
        pos_counts = Counter(flag for word, flag in pseg.cut(text) if re.search(HANZI, word))
        nouns = sum(c for tag, c in pos_counts.items() if tag.startswith('n'))
        verbs = sum(c for tag, c in pos_counts.items() if tag.startswith('v'))
        adjectives = sum(c for tag, c in pos_counts.items() if tag.startswith('a'))
        adverbs = sum(c for tag, c in pos_counts.items() if tag.startswith('d'))
    except Exception:
        nouns = verbs = adjectives = adverbs = 0
    return {
        'total_unique_words': len(set(words)),
        'type_token_ratio': round(len(set(words)) / len(words), 3),
        'nouns': nouns,
        'verbs': verbs,
        'adjectives': adjectives,
        'adverbs': adverbs,
        'most_common_words': Counter(words).most_common(10),
    }


ACTFL_LEVELS = [
    "Novice-Low", "Novice-Mid", "Novice-High",
    "Intermediate-Low", "Intermediate-Mid", "Intermediate-High",
    "Advanced-Low", "Advanced-Mid", "Advanced-High"
]

# Our own paraphrase of the ACTFL Speaking Guidelines for the model to reason
# from — not the official ACTFL text. Structured around ACTFL's four rating
# criteria (Function, Context/Content, Text Type, Accuracy) because an
# earlier prose-only version rated an independently OPI-rated Advanced-Mid
# speaker as Intermediate-Mid: it over-weighted isolated accuracy issues
# (some of which were transcription noise) and under-weighted Text Type.
ACTFL_RUBRIC_SUMMARY = """
A level is the level at which a speaker can SUSTAIN performance across all
four criteria below — NOT the level at which every sentence is error-free.
Occasional errors occur at every level, including Advanced and Superior,
and do not by themselves cap a rating if the other criteria are clearly met.
Weigh all four criteria; do not let an error-count alone drive the rating.

- FUNCTION / TASKS — what the speaker can actually DO with the language.
  Novice: names/lists things, uses memorized formulas. Intermediate: asks
  and answers simple questions, handles simple everyday transactions.
  Advanced: narrates and describes accurately across major time frames
  (past/present/future) and handles a complication or unexpected turn in a
  routine situation. Superior: supports opinions, hypothesizes, discusses
  abstract topics.
- TEXT TYPE — often the PRIMARY differentiator between Intermediate and
  Advanced, so weigh it heavily. Novice: isolated words/phrases. Intermediate:
  discrete sentences, and loosely strung-together sentences. Advanced:
  genuinely CONNECTED discourse — multiple clauses/sentences linked by
  cohesive devices (connectors, references back to earlier content,
  self-correction/repair, cause-effect framing) rather than just juxtaposed,
  produced across multiple conversational turns. Run-on structure typical of
  spontaneous speech is not by itself a Text Type downgrade.
- CONTEXT/CONTENT — how familiar/everyday vs. broader are the topics the
  speaker can handle. Advanced speakers handle concrete, practical, factual
  topics tied to work, home, and personal life, not just survival topics.
- ACCURACY — how well-controlled is the grammar/vocabulary. At Advanced,
  errors don't usually interfere with communication and don't collapse under
  a complication. Advanced does NOT require error-free speech.
""".strip()

ACTFL_SCHEMA = {
    "type": "object",
    "properties": {
        "function_evidence": {"type": "string", "description": "What communicative tasks/functions the learner accomplished, with specific examples."},
        "text_type_evidence": {"type": "string", "description": "Discrete words/sentences vs. connected, multi-clause discourse — cite specific cohesive devices if present."},
        "context_content_evidence": {"type": "string", "description": "How familiar/everyday vs. broader/complex the topics handled were."},
        "accuracy_evidence": {"type": "string", "description": "Genuine grammar/vocabulary accuracy assessment, EXCLUDING anything in likely_transcription_errors."},
        "task_completion": {"type": "string", "description": "1-2 sentences on how well the learner accomplished the assigned task/scenario."},
        "likely_transcription_errors": {"type": "array", "items": {"type": "string"}, "description": "Words/phrases that look like speech-recognition errors rather than learner errors, with a brief note why. Empty if none."},
        "level": {"type": "string", "enum": ACTFL_LEVELS + ["Insufficient Sample"]},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "rationale": {"type": "string", "description": "2-4 sentences synthesizing the four criteria into the final level judgment."},
        "strengths": {"type": "array", "items": {"type": "string"}, "description": "1-3 short, specific things the learner did well."},
        "areas_to_grow": {"type": "array", "items": {"type": "string"}, "description": "1-3 short, specific, actionable things to work on next (genuine errors only)."},
        "corrections": {
            "type": "array",
            "description": "Up to 6 genuine learner errors from the transcript with a corrected version and a short English explanation.",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "corrected": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["original", "corrected", "explanation"],
            },
        },
    },
    "required": [
        "function_evidence", "text_type_evidence", "context_content_evidence",
        "accuracy_evidence", "task_completion", "likely_transcription_errors", "level",
        "confidence", "rationale", "strengths", "areas_to_grow", "corrections"
    ],
}


def estimate_actfl_level_llm(conversation, partner_name, task, metrics_summary):
    """
    Send the full transcript (plus the jieba metrics as supporting context)
    to a Gemini text model for a holistic ACTFL-informed judgment. Returns
    the parsed JSON dict, or {'error': ...} on failure — callers degrade
    gracefully rather than failing the whole /analyze response.

    NOTE: this is NOT a validated ACTFL OPI rating — treat it as an
    informed, informal signal, not a placement decision.
    """
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY is not set, so no LLM-based estimate could be generated."}

    transcript_text = "\n".join(
        f"{'学生 (Learner)' if m.get('role') == 'user' else partner_name + ' (Partner)'}: {m.get('text', '')}"
        for m in conversation
    )

    system_prompt = f"""
You are an experienced Chinese-language proficiency rater giving a rough,
informal ACTFL-informed read on ONE conversation between a CFL (Chinese as
a Foreign Language) speaker and an AI conversation partner. Speakers range
from first-year students to near-native — do NOT assume a starting level
(the level the learner chose to practice at is NOT evidence of their actual
level); judge strictly from the evidence in this transcript.

Rating framework (our own summary of ACTFL's four rating criteria, not the
official ACTFL Guidelines text):
{ACTFL_RUBRIC_SUMMARY}

Judge ONLY the learner's turns (labeled "学生 (Learner)"). The partner's
turns are context only.

CRITICAL — separate transcription noise from real learner errors: this
transcript comes from automatic speech recognition on live, spontaneous
speech. ASR sometimes substitutes a more common but contextually
nonsensical word or phrase. When a word or short phrase is semantically
nonsensical or bizarrely out of register/topic, treat it as a PROBABLE
TRANSCRIPTION ERROR, list it separately, and do NOT count it as evidence in
either direction. Only treat something as a genuine learner error if it's a
plausible thing for a learner to say (wrong particle, measure word, word
order, overgeneralized grammar, etc.).

Natural spontaneous speech — including native speech — contains fillers
(嗯, 呃, 那个, 就是, 然后, 这个) and loose clause-chaining. These are not by
themselves evidence of lower proficiency.

Write all evidence, rationale, strengths, areas_to_grow and explanations in
English (quote Chinese examples as needed). If the sample is too thin or
unclear to judge, respond with level "Insufficient Sample" and explain why.
""".strip()

    user_prompt = f"""
Task/scenario: {task}

Objective metrics computed from this transcript (supporting context only):
{metrics_summary}

Full transcript:
{transcript_text}
""".strip()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_ANALYSIS_MODEL}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": ACTFL_SCHEMA,
        },
    }
    headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=90)
        if resp.status_code == 400 and "responseJsonSchema" in resp.text:
            # Older API surface: fall back to JSON mode with the schema
            # described in the prompt instead.
            body["generationConfig"] = {"responseMimeType": "application/json"}
            body["contents"][0]["parts"][0]["text"] += (
                "\n\nRespond with JSON matching this JSON Schema:\n" + json.dumps(ACTFL_SCHEMA, ensure_ascii=False)
            )
            resp = requests.post(url, headers=headers, json=body, timeout=90)
        if not resp.ok:
            return {"error": f"Gemini API error {resp.status_code}: {resp.text[:500]}"}
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return json.loads(text)
    except requests.exceptions.Timeout:
        return {"error": "The proficiency-estimate request timed out. Try again in a moment."}
    except Exception as e:
        return {"error": f"Could not generate an LLM-based estimate: {type(e).__name__}: {e}"}


def build_analysis(conversation, profile, profile_summary, task):
    """Compute everything for the reports. Returns a JSON-serializable dict."""
    user_turns = [m['text'] for m in conversation if m.get('role') == 'user']
    partner_turns = [m['text'] for m in conversation if m.get('role') == 'assistant']
    user_text = ' '.join(user_turns)
    duration = compute_duration_minutes(conversation)

    analysis = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'duration_minutes': round(duration, 2) if duration is not None else None,
        'partner_profile': profile,
        'partner_summary': profile_summary,
        'task': task,
        'nlp_available': ANALYSIS_AVAILABLE,
        'nlp_error': NLP_ERROR_MESSAGE,
        'turn_taking': {
            'total_turns': len(conversation),
            'learner_turns': len(user_turns),
            'partner_turns': len(partner_turns),
            'learner_share_of_characters': round(
                len(re.findall(HANZI, user_text)) /
                max(len(re.findall(HANZI, user_text + ''.join(partner_turns))), 1) * 100, 1),
        },
        'basic_stats': analyze_basic_stats(user_text, user_turns),
        'complexity_metrics': {},
        'fluency_metrics': {},
        'vocabulary_metrics': {},
        'actfl_estimate': None,
        'actfl_note': None,
        'analysis_model': GEMINI_ANALYSIS_MODEL,
        'transcript': conversation,
    }

    if not ANALYSIS_AVAILABLE:
        analysis['actfl_note'] = "Chinese word segmentation (jieba) is unavailable on the server, so only basic counts are shown."
        return analysis

    words = _words(user_text)
    analysis['complexity_metrics'] = analyze_complexity(user_text, words)
    analysis['fluency_metrics'] = analyze_fluency(user_turns)
    analysis['vocabulary_metrics'] = analyze_vocabulary(user_text)

    basic = analysis['basic_stats']
    if duration is None:
        analysis['actfl_note'] = "Couldn't determine how long this conversation lasted, so no proficiency estimate was generated."
    elif duration < MIN_MINUTES_FOR_ACTFL:
        analysis['actfl_note'] = (
            f"This conversation was about {duration:.1f} minute(s) long. "
            f"Talk for at least {MIN_MINUTES_FOR_ACTFL} minutes to get an ACTFL-informed level estimate."
        )
    elif len(user_turns) < MIN_USER_TURNS_FOR_ACTFL:
        analysis['actfl_note'] = "Not enough learner turns yet for a reliable estimate — keep the conversation going a bit longer."
    else:
        cm, fm, vm = analysis['complexity_metrics'], analysis['fluency_metrics'], analysis['vocabulary_metrics']
        sentence_caveat = (
            " [UNRELIABLE — little/no terminal punctuation in the transcript, so clause-chains got counted "
            "as one \"sentence\" per turn]" if basic['punctuation_sparse'] else ""
        )
        metrics_summary = (
            f"- Learner turns: {len(user_turns)}, total words (jieba): {basic['total_words']}, "
            f"avg words/turn: {basic['avg_words_per_turn']}\n"
            f"- Sentences (punctuation-based): {basic['total_sentences']} "
            f"(avg {basic['avg_words_per_sentence']} words/sentence){sentence_caveat}\n"
            f"- Connector uses: {cm['connector_count']} ({', '.join(cm['connectors_used']) or 'none'})\n"
            f"- Aspect-marker uses (了/过/着): {cm['aspect_marker_count']}\n"
            f"- Vocabulary: {vm['total_unique_words']} unique words, type-token ratio {vm['type_token_ratio']}\n"
            f"- Filler words: {fm['total_filler_words']}, hesitations/repetitions: {fm['hesitations_repetitions']} "
            f"[fillers are normal in fluent speech; not by themselves evidence of lower proficiency]"
        )
        analysis['actfl_estimate'] = estimate_actfl_level_llm(
            conversation, profile.get('name', 'Partner'), task, metrics_summary)

    return analysis


# --------------------------- Report renderers ---------------------------

DISCLAIMER = (
    "This is a single-conversation estimate from an LLM reading the transcript, informed by the "
    "objective metrics above. It is NOT a validated ACTFL OPI rating — no automated read substitutes "
    "for a trained human rater conducting a structured interview. Treat it as an informal signal, "
    "not a placement or grading decision."
)


def _metric_rows(a):
    """(section, label, value) rows shared by the text, HTML and CSV outputs."""
    bs, tt = a['basic_stats'], a['turn_taking']
    cm, fm, vm = a['complexity_metrics'], a['fluency_metrics'], a['vocabulary_metrics']
    rows = [
        ("Conversation", "Duration (minutes)", a['duration_minutes'] if a['duration_minutes'] is not None else "—"),
        ("Conversation", "Total turns", tt['total_turns']),
        ("Conversation", "Learner turns", tt['learner_turns']),
        ("Conversation", "Partner turns", tt['partner_turns']),
        ("Conversation", "Learner share of talk (% of characters)", tt['learner_share_of_characters']),
        ("Production", "Characters (learner)", bs['total_characters']),
        ("Production", "Words (jieba-segmented)", bs['total_words']),
        ("Production", "Avg characters per turn", bs['avg_characters_per_turn']),
        ("Production", "Avg words per turn", bs['avg_words_per_turn']),
        ("Production", "Longest turn (characters)", bs['longest_turn_characters']),
        ("Production", "Sentences (punctuation-based)", bs['total_sentences']),
        ("Production", "Avg words per sentence", bs['avg_words_per_sentence']),
        ("Production", "Sentence counts reliable", "no*" if bs['punctuation_sparse'] else "yes"),
    ]
    if cm:
        rows += [
            ("Complexity", "Connector uses (因为/所以/但是…)", cm['connector_count']),
            ("Complexity", "Connectors used", "、".join(cm['connectors_used']) or "—"),
            ("Complexity", "Aspect markers (了/过/着)", cm['aspect_marker_count']),
        ]
    if fm:
        rows += [
            ("Fluency", "Filler words (嗯/呃/那个/就是/然后/这个)", fm['total_filler_words']),
            ("Fluency", "Fillers per 100 characters", fm['filler_word_rate_per_100_chars']),
            ("Fluency", "Hesitations / repetitions", fm['hesitations_repetitions']),
        ]
    if vm:
        rows += [
            ("Vocabulary", "Unique words", vm['total_unique_words']),
            ("Vocabulary", "Type-token ratio", vm['type_token_ratio']),
            ("Vocabulary", "Nouns / verbs / adjectives / adverbs",
             f"{vm['nouns']} / {vm['verbs']} / {vm['adjectives']} / {vm['adverbs']}"),
            ("Vocabulary", "Most common words",
             "、".join(f"{w}({c})" for w, c in vm['most_common_words']) or "—"),
        ]
    return rows


def _speaker(a, msg):
    return "LEARNER" if msg.get('role') == 'user' else a['partner_profile'].get('name', 'PARTNER')


def render_text(a):
    out = ["=" * 80, "CONVERSATION ANALYSIS REPORT", "=" * 80, f"Generated: {a['generated_at']}", ""]
    out += ["-" * 80, "CONVERSATION PARTNER", "-" * 80]
    out += [f"{k}: {v}" for k, v in a['partner_summary']]
    out.append("")
    section = None
    for sec, label, value in _metric_rows(a):
        if sec != section:
            out += ["-" * 80, sec.upper(), "-" * 80]
            section = sec
        out.append(f"{label}: {value}")
    if a['basic_stats']['punctuation_sparse']:
        out.append("  * Most turns had little/no terminal punctuation in the transcription, so "
                   "sentence counts are unreliable.")
    out += ["", "-" * 80, "ACTFL-INFORMED ESTIMATE (LLM-based, EXPERIMENTAL)", "-" * 80]
    est = a.get('actfl_estimate')
    if est and est.get('error'):
        out.append(f"Could not generate an estimate: {est['error']}")
    elif est:
        out += [f"Estimated Level: {est.get('level')}", f"Confidence: {est.get('confidence')}", ""]
        out.append(f"Task completion: {est.get('task_completion', '')}")
        out += ["", "Evidence by ACTFL criterion:",
                f"  Function/Tasks: {est.get('function_evidence', '')}",
                f"  Context/Content: {est.get('context_content_evidence', '')}",
                f"  Text Type: {est.get('text_type_evidence', '')}",
                f"  Accuracy: {est.get('accuracy_evidence', '')}",
                "", "Rationale:", f"  {est.get('rationale', '')}"]
        for title, key in (("Strengths", 'strengths'), ("Areas to grow", 'areas_to_grow'),
                           ("Likely transcription noise (excluded)", 'likely_transcription_errors')):
            if est.get(key):
                out += ["", f"{title}:"] + [f"  - {x}" for x in est[key]]
        if est.get('corrections'):
            out += ["", "Corrections:"]
            for c in est['corrections']:
                out.append(f"  ✗ {c.get('original')}  →  ✓ {c.get('corrected')}  ({c.get('explanation')})")
        out += ["", f"Model: {a['analysis_model']}. {DISCLAIMER}"]
    else:
        out.append(a.get('actfl_note') or "No estimate available.")
    out += ["", "=" * 80, "FULL CONVERSATION TRANSCRIPT", "=" * 80, ""]
    for i, msg in enumerate(a['transcript'], 1):
        out += [f"[Turn {i}] {_speaker(a, msg)}:", msg.get('text', ''), ""]
    out += ["=" * 80, "END OF REPORT", "=" * 80]
    return "\n".join(out)


def render_csv(a):
    """One header row + one data row, so files from many learners can be
    stacked into one spreadsheet."""
    est = a.get('actfl_estimate') or {}
    row = {"generated_at": a['generated_at']}
    for k, v in a['partner_summary']:
        row["partner_" + re.sub(r'\W+', '_', k.lower()).strip('_')] = v
    for sec, label, value in _metric_rows(a):
        row[re.sub(r'\W+', '_', f"{sec}_{label}".lower()).strip('_')] = value
    row["actfl_level"] = est.get('level', '') if not est.get('error') else ''
    row["actfl_confidence"] = est.get('confidence', '') if not est.get('error') else ''
    row["actfl_note"] = est.get('error') or a.get('actfl_note') or ''
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(row.keys()))
    writer.writeheader()
    writer.writerow(row)
    # BOM so Excel opens the Chinese characters correctly.
    return "﻿" + buf.getvalue()


def render_html(a):
    e = html.escape
    est = a.get('actfl_estimate')
    partner = a['partner_profile'].get('name', 'Partner')

    def li(items):
        return "".join(f"<li>{e(str(x))}</li>" for x in items)

    profile_rows = "".join(f"<tr><th>{e(k)}</th><td>{e(str(v))}</td></tr>" for k, v in a['partner_summary'])

    metric_html, section = [], None
    for sec, label, value in _metric_rows(a):
        if sec != section:
            if section:
                metric_html.append("</table></div>")
            metric_html.append(f"<div class='card'><h3>{e(sec)}</h3><table>")
            section = sec
        metric_html.append(f"<tr><th>{e(label)}</th><td>{e(str(value))}</td></tr>")
    metric_html.append("</table></div>")
    if a['basic_stats']['punctuation_sparse']:
        metric_html.append("<p class='muted'>* Most turns had little or no terminal punctuation in the "
                           "transcription, so sentence counts are unreliable.</p>")

    if est and not est.get('error'):
        corrections = "".join(
            f"<tr><td class='bad'>{e(c.get('original', ''))}</td><td class='good'>{e(c.get('corrected', ''))}</td>"
            f"<td>{e(c.get('explanation', ''))}</td></tr>" for c in est.get('corrections') or [])
        actfl = f"""
<div class="level"><span class="badge">{e(est.get('level', ''))}</span>
<span class="muted">confidence: {e(est.get('confidence', ''))}</span></div>
<p><b>Task completion.</b> {e(est.get('task_completion', ''))}</p>
<p><b>Rationale.</b> {e(est.get('rationale', ''))}</p>
<div class="grid2">
<div class="card"><h3>Strengths</h3><ul>{li(est.get('strengths') or [])}</ul></div>
<div class="card"><h3>Areas to grow</h3><ul>{li(est.get('areas_to_grow') or [])}</ul></div>
</div>
{f"<h3>Corrections</h3><table class='corr'><tr><th>You said</th><th>Better</th><th>Why</th></tr>{corrections}</table>" if corrections else ""}
<details><summary>Evidence by ACTFL criterion</summary>
<p><b>Function/Tasks:</b> {e(est.get('function_evidence', ''))}</p>
<p><b>Context/Content:</b> {e(est.get('context_content_evidence', ''))}</p>
<p><b>Text Type:</b> {e(est.get('text_type_evidence', ''))}</p>
<p><b>Accuracy:</b> {e(est.get('accuracy_evidence', ''))}</p>
{f"<p><b>Likely transcription noise (excluded):</b></p><ul>{li(est['likely_transcription_errors'])}</ul>" if est.get('likely_transcription_errors') else ""}
</details>
<p class="muted">Model: {e(a['analysis_model'])}. {e(DISCLAIMER)}</p>"""
    elif est:
        actfl = f"<p>Could not generate an estimate: {e(est['error'])}</p>"
    else:
        actfl = f"<p>{e(a.get('actfl_note') or 'No estimate available.')}</p>"

    transcript = "".join(
        f"<div class='msg {'user' if m.get('role') == 'user' else 'bot'}'>"
        f"<div class='who'>{e('You' if m.get('role') == 'user' else partner)}</div>{e(m.get('text', ''))}</div>"
        for m in a['transcript'])

    duration = f"{a['duration_minutes']:.1f} min" if a['duration_minutes'] is not None else "—"
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conversation report — {e(partner)}</title>
<style>
body{{font-family:system-ui,-apple-system,"PingFang SC","Noto Sans SC",sans-serif;color:#1f2330;background:#f6f7fb;margin:0;line-height:1.5}}
main{{max-width:880px;margin:0 auto;padding:24px 16px 48px}}
h1{{margin:0 0 4px;font-size:1.6rem}} h2{{margin-top:2rem;border-bottom:2px solid #e3e6ef;padding-bottom:4px}}
h3{{margin:0 0 8px;font-size:1rem}} .muted{{color:#6b7083;font-size:.9rem}}
.card{{background:#fff;border:1px solid #e3e6ef;border-radius:10px;padding:14px 16px;margin:10px 0}}
.grid2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}}
table{{width:100%;border-collapse:collapse}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #eef0f5;vertical-align:top}}
th{{font-weight:500;color:#4a4f63;width:55%}}
.corr th{{width:auto}} .bad{{color:#b3261e}} .good{{color:#1e7a3c}}
.level{{display:flex;align-items:center;gap:12px;margin:8px 0}}
.badge{{background:#4f46e5;color:#fff;border-radius:999px;padding:6px 14px;font-weight:600;font-size:1.1rem}}
.msg{{max-width:80%;padding:8px 12px;border-radius:10px;margin:6px 0}}
.msg.user{{background:#e6efff;margin-left:auto}} .msg.bot{{background:#fff;border:1px solid #e3e6ef}}
.who{{font-size:.75rem;color:#6b7083}}
details{{margin:10px 0}} summary{{cursor:pointer;font-weight:600}}
@media print{{body{{background:#fff}} .card{{break-inside:avoid}}}}
</style></head><body><main>
<h1>中文口语练习 · Conversation report</h1>
<p class="muted">{e(a['generated_at'])} · {duration} · {a['turn_taking']['learner_turns']} learner turns</p>
<h2>Who you talked to</h2><div class="card"><table>{profile_rows}</table></div>
<h2>Proficiency estimate</h2>{actfl}
<h2>Statistics</h2><div class="grid2">{''.join(metric_html)}</div>
<h2>Transcript</h2>{transcript}
</main></body></html>"""
