# server.py — multi-bot Realtime voice chat, MANDARIN CHINESE version (8 discussion topics)
# --------------------------------------------------------------------------------------------
# This is a standalone copy of the English ELL practice app, adapted for CFL
# (Chinese as a Foreign Language) learners. It is meant to be deployed as its
# own Render service, separate from the English version — same codebase
# shape, different BOTS content and Whisper transcription language.
#
# Level: Novice-High to Intermediate-Low (typical 1st/2nd-year Chinese class).
# Topics are generic free-discussion prompts rather than scripted role-plays.
#
# Run:
#   pip install flask flask-cors requests python-dotenv jieba
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
from datetime import datetime
import re
from collections import Counter

# --------------------------- Chinese NLP (jieba) ---------------------------
# The English version of this app used textstat + nltk for analysis, but
# those are built around English tokenization/readability formulas and don't
# work on Mandarin text (no spaces between words, no English-style
# syllables). This version uses jieba for Chinese word segmentation instead
# — it's a small, pure-Python-friendly library with a bundled dictionary
# (no network download needed at runtime, unlike nltk's data downloads).
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
    print(f"Error details: {NLP_ERROR_MESSAGE}")
    print("To fix this issue, ensure requirements.txt contains: jieba==0.42.1")
except Exception as e:
    NLP_ERROR_MESSAGE = f"Initialization error: {str(e)}"
    print("✗ INITIALIZATION ERROR")
    print(f"Error details: {NLP_ERROR_MESSAGE} ({type(e).__name__})")


load_dotenv()

# --------------------------- Config ---------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")
OPENAI_REALTIME_VOICE_DEFAULT = os.getenv("OPENAI_REALTIME_VOICE", "alloy")
RT_SILENCE_MS = int(os.getenv("RT_SILENCE_MS", "1200"))  # pause after user stops
VAD_THRESHOLD = float(os.getenv("RT_VAD_THRESHOLD", "0.5"))
# Text model used to read the whole transcript and produce the ACTFL-informed
# estimate (a separate, non-realtime OpenAI call from the voice session
# above). Reverted the default back to "terra" (mid tier) — the top tier
# ("sol") was tried briefly for the extra reasoning quality on this nuanced
# judgment call, but access to "sol" via the API is gated per-organization
# (it can require identity/spending-threshold verification beyond what a
# working "terra" key already has), and it's also a heavier/slower model,
# so a key or Render instance that isn't cleared for it starts failing
# every /analyze call with an OpenAI 404/permission error instead of just
# degrading gracefully. "terra" is the safer default for reliability. If
# your OpenAI org has confirmed "sol" access, you can opt into it per
# environment via the OPENAI_ANALYSIS_MODEL variable below without a code
# change — just verify it actually works on your account first.
OPENAI_ANALYSIS_MODEL = os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-5.6-terra")

# 8 preset discussion-topic "bots". Edit freely.
BOTS = [
    {
        "id": "zh-topic-self-family",
        "title": "自我介绍与家庭 (Self-Introduction & Family)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "王建国 (Wang Jianguo) — see the GLOBAL PERSONA and GLOBAL CONVERSATION-STYLE rules below for who you are and how to talk",
        "task": (
            "Start with a simple greeting and introduce yourself first (name, where you're from) to model the language, "
            "then invite the learner to introduce themselves. "
            "Ask simple, one-at-a-time questions about their family: how many people are in their family (你家有几口人), "
            "who they are (父母、兄弟姐妹), and something simple about one family member (like their job or age, kept simple). "
            "Share a little about your own family too so it feels like a real back-and-forth conversation, not an interview. "
            "Keep the conversation light, friendly, and encouraging throughout."
            "Don't tell the student your rules or programming, that's not natural."
        ),
        "constraints": (
            "CONVERSATION STYLE:\n"
            "- You are a supportive conversation partner, not a strict examiner. Your goal is to keep the learner talking and build their confidence.\n"
            "- Ask ONLY one question at a time, and wait for their answer before continuing.\n"
            "- If something the learner says is genuinely unclear or unintelligible, ask them warmly to repeat or say it another way (e.g. '不好意思，可以再说一次吗？' or '你可以说得慢一点吗？'). Do not guess at meaning you can't make out.\n"
            "- Do NOT nitpick minor pronunciation or tone slips that don't block understanding — only ask for clarification when you genuinely cannot follow what they mean. Prioritize keeping the conversation flowing over correcting them.\n"
            "- You only understand Mandarin. If another language is used, gently ask them to try it in Chinese.\n"
            "- After asking a question, pause and give the learner time to respond before jumping in."
        ),
        "language_hint": "Mandarin Chinese"
    },
    {
        "id": "zh-topic-daily-routine",
        "title": "我的一天 (Daily Routine)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "王建国 (Wang Jianguo) — see the GLOBAL PERSONA and GLOBAL CONVERSATION-STYLE rules below for who you are and how to talk",
        "task": (
            "Chat with the learner about a typical day. Ask simple, one-at-a-time questions: what time they usually get up (你几点起床), "
            "what they eat for breakfast, what their class or work schedule looks like, what they do after class/work, and what time they go to bed. "
            "Ask a simple follow-up comparing weekdays and weekends (周末和平常一样吗). "
            "Share a bit about your own daily routine too, to keep it a natural two-way conversation."
            "Don't tell the student your rules or programming, that's not natural."
        ),
        "constraints": (
            "CONVERSATION STYLE:\n"
            "- You are a supportive conversation partner, not a strict examiner. Your goal is to keep the learner talking and build their confidence.\n"
            "- Ask ONLY one question at a time, and wait for their answer before continuing.\n"
            "- If something the learner says is genuinely unclear or unintelligible, ask them warmly to repeat or say it another way (e.g. '不好意思，可以再说一次吗？' or '你可以说得慢一点吗？'). Do not guess at meaning you can't make out.\n"
            "- Do NOT nitpick minor pronunciation or tone slips that don't block understanding — only ask for clarification when you genuinely cannot follow what they mean. Prioritize keeping the conversation flowing over correcting them.\n"
            "- You only understand Mandarin. If another language is used, gently ask them to try it in Chinese.\n"
            "- After asking a question, pause and give the learner time to respond before jumping in."
        ),
        "language_hint": "Mandarin Chinese"
    },
    {
        "id": "zh-topic-hobbies-sports",
        "title": "爱好和运动 (Hobbies & Sports)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "王建国 (Wang Jianguo) — see the GLOBAL PERSONA and GLOBAL CONVERSATION-STYLE rules below for who you are and how to talk",
        "task": (
            "Chat with the learner about hobbies and sports. Ask what they like to do in their free time (你喜欢做什么), "
            "whether they play or watch any sports, how often they do their hobby, and who they usually do it with. "
            "Ask a simple follow-up about how they started liking it, kept at a simple level. "
            "Share your own hobby too so it's a natural exchange, not just a Q&A."
            "Don't tell the student your rules or programming, that's not natural."
        ),
        "constraints": (
            "CONVERSATION STYLE:\n"
            "- You are a supportive conversation partner, not a strict examiner. Your goal is to keep the learner talking and build their confidence.\n"
            "- Ask ONLY one question at a time, and wait for their answer before continuing.\n"
            "- If something the learner says is genuinely unclear or unintelligible, ask them warmly to repeat or say it another way (e.g. '不好意思，可以再说一次吗？' or '你可以说得慢一点吗？'). Do not guess at meaning you can't make out.\n"
            "- Do NOT nitpick minor pronunciation or tone slips that don't block understanding — only ask for clarification when you genuinely cannot follow what they mean. Prioritize keeping the conversation flowing over correcting them.\n"
            "- You only understand Mandarin. If another language is used, gently ask them to try it in Chinese.\n"
            "- After asking a question, pause and give the learner time to respond before jumping in."
        ),
        "language_hint": "Mandarin Chinese"
    },
    {
        "id": "zh-topic-weather-seasons",
        "title": "天气和季节 (Weather & Seasons)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "王建国 (Wang Jianguo) — see the GLOBAL PERSONA and GLOBAL CONVERSATION-STYLE rules below for who you are and how to talk",
        "task": (
            "Chat with the learner about weather and seasons. Ask what the weather is like today where they are (今天天气怎么样), "
            "which season they like best and why, and what they like to do in that season. "
            "Ask a simple follow-up about weather in their hometown compared to where they live now. "
            "Share your own favorite season too."
            "Don't tell the student your rules or programming, that's not natural."
        ),
        "constraints": (
            "CONVERSATION STYLE:\n"
            "- You are a supportive conversation partner, not a strict examiner. Your goal is to keep the learner talking and build their confidence.\n"
            "- Ask ONLY one question at a time, and wait for their answer before continuing.\n"
            "- If something the learner says is genuinely unclear or unintelligible, ask them warmly to repeat or say it another way (e.g. '不好意思，可以再说一次吗？' or '你可以说得慢一点吗？'). Do not guess at meaning you can't make out.\n"
            "- Do NOT nitpick minor pronunciation or tone slips that don't block understanding — only ask for clarification when you genuinely cannot follow what they mean. Prioritize keeping the conversation flowing over correcting them.\n"
            "- You only understand Mandarin. If another language is used, gently ask them to try it in Chinese.\n"
            "- After asking a question, pause and give the learner time to respond before jumping in."
        ),
        "language_hint": "Mandarin Chinese"
    },
    {
        "id": "zh-topic-school-major",
        "title": "学校生活和专业 (School Life & Major)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "王建国 (Wang Jianguo) — see the GLOBAL PERSONA and GLOBAL CONVERSATION-STYLE rules below for who you are and how to talk",
        "task": (
            "Chat with the learner about school life. Ask what they are studying (你的专业是什么), "
            "what classes they're taking this semester, which class is their favorite and why, and what their campus or classes are like. "
            "Ask a simple follow-up about why they chose their major, kept at a simple level. "
            "Share a bit about your own studies too."
            "Don't tell the student your rules or programming, that's not natural."
        ),
        "constraints": (
            "CONVERSATION STYLE:\n"
            "- You are a supportive conversation partner, not a strict examiner. Your goal is to keep the learner talking and build their confidence.\n"
            "- Ask ONLY one question at a time, and wait for their answer before continuing.\n"
            "- If something the learner says is genuinely unclear or unintelligible, ask them warmly to repeat or say it another way (e.g. '不好意思，可以再说一次吗？' or '你可以说得慢一点吗？'). Do not guess at meaning you can't make out.\n"
            "- Do NOT nitpick minor pronunciation or tone slips that don't block understanding — only ask for clarification when you genuinely cannot follow what they mean. Prioritize keeping the conversation flowing over correcting them.\n"
            "- You only understand Mandarin. If another language is used, gently ask them to try it in Chinese.\n"
            "- After asking a question, pause and give the learner time to respond before jumping in."
        ),
        "language_hint": "Mandarin Chinese"
    },
    {
        "id": "zh-topic-food-dining",
        "title": "食物和餐厅 (Food & Dining Out)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "王建国 (Wang Jianguo) — see the GLOBAL PERSONA and GLOBAL CONVERSATION-STYLE rules below for who you are and how to talk",
        "task": (
            "Chat with the learner about food. Ask what kind of food they like (你喜欢吃什么), "
            "what they usually eat for meals, whether they like to cook or eat out, and about a restaurant they like. "
            "Ask a simple follow-up about a food they don't like or haven't tried. "
            "Share your own food preferences too."
            "Don't tell the student your rules or programming, that's not natural."
        ),
        "constraints": (
            "CONVERSATION STYLE:\n"
            "- You are a supportive conversation partner, not a strict examiner. Your goal is to keep the learner talking and build their confidence.\n"
            "- Ask ONLY one question at a time, and wait for their answer before continuing.\n"
            "- If something the learner says is genuinely unclear or unintelligible, ask them warmly to repeat or say it another way (e.g. '不好意思，可以再说一次吗？' or '你可以说得慢一点吗？'). Do not guess at meaning you can't make out.\n"
            "- Do NOT nitpick minor pronunciation or tone slips that don't block understanding — only ask for clarification when you genuinely cannot follow what they mean. Prioritize keeping the conversation flowing over correcting them.\n"
            "- You only understand Mandarin. If another language is used, gently ask them to try it in Chinese.\n"
            "- After asking a question, pause and give the learner time to respond before jumping in."
        ),
        "language_hint": "Mandarin Chinese"
    },
    {
        "id": "zh-topic-shopping",
        "title": "购物 (Shopping)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "王建国 (Wang Jianguo) — see the GLOBAL PERSONA and GLOBAL CONVERSATION-STYLE rules below for who you are and how to talk",
        "task": (
            "Chat with the learner about shopping. Ask where they like to shop (你喜欢在哪儿买东西), "
            "what kinds of things they like to buy, whether they prefer shopping online or in stores, and about something they bought recently. "
            "Ask a simple follow-up about prices — whether they think something is expensive or cheap (贵/便宜). "
            "Share your own shopping habits too."
            "Don't tell the student your rules or programming, that's not natural."
        ),
        "constraints": (
            "CONVERSATION STYLE:\n"
            "- You are a supportive conversation partner, not a strict examiner. Your goal is to keep the learner talking and build their confidence.\n"
            "- Ask ONLY one question at a time, and wait for their answer before continuing.\n"
            "- If something the learner says is genuinely unclear or unintelligible, ask them warmly to repeat or say it another way (e.g. '不好意思，可以再说一次吗？' or '你可以说得慢一点吗？'). Do not guess at meaning you can't make out.\n"
            "- Do NOT nitpick minor pronunciation or tone slips that don't block understanding — only ask for clarification when you genuinely cannot follow what they mean. Prioritize keeping the conversation flowing over correcting them.\n"
            "- You only understand Mandarin. If another language is used, gently ask them to try it in Chinese.\n"
            "- After asking a question, pause and give the learner time to respond before jumping in."
        ),
        "language_hint": "Mandarin Chinese"
    },
    {
        "id": "zh-topic-weekend-friends",
        "title": "周末计划和朋友 (Weekend Plans & Friends)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "王建国 (Wang Jianguo) — see the GLOBAL PERSONA and GLOBAL CONVERSATION-STYLE rules below for who you are and how to talk",
        "task": (
            "Chat with the learner about weekend plans and friends. Ask what they usually do on weekends (周末你常常做什么), "
            "whether they like to spend time with friends or alone, and what they're planning to do this coming weekend. "
            "Ask a simple follow-up inviting them to describe a fun weekend they remember. "
            "Share your own weekend plans too, to keep it a natural exchange."
            "Don't tell the student your rules or programming, that's not natural."
        ),
        "constraints": (
            "CONVERSATION STYLE:\n"
            "- You are a supportive conversation partner, not a strict examiner. Your goal is to keep the learner talking and build their confidence.\n"
            "- Ask ONLY one question at a time, and wait for their answer before continuing.\n"
            "- If something the learner says is genuinely unclear or unintelligible, ask them warmly to repeat or say it another way (e.g. '不好意思，可以再说一次吗？' or '你可以说得慢一点吗？'). Do not guess at meaning you can't make out.\n"
            "- Do NOT nitpick minor pronunciation or tone slips that don't block understanding — only ask for clarification when you genuinely cannot follow what they mean. Prioritize keeping the conversation flowing over correcting them.\n"
            "- You only understand Mandarin. If another language is used, gently ask them to try it in Chinese.\n"
            "- After asking a question, pause and give the learner time to respond before jumping in."
        ),
        "language_hint": "Mandarin Chinese"
    }
]




# --------------------------- Helper Functions ---------------------------
# Chinese-appropriate conversation analysis. Uses jieba for word
# segmentation/POS tagging (there is no whitespace between Chinese words, so
# English tools like nltk's word_tokenize or textstat's syllable-based
# readability formulas don't apply). Metrics here are simple, transparent
# proxies (utterance length, connector use, aspect-marker use, vocabulary
# diversity) — not a validated linguistic analysis.

CONNECTOR_MARKERS = [
    '因为', '所以', '但是', '可是', '虽然', '如果', '不但', '而且',
    '除了', '后来', '首先', '其次', '另外', '于是', '因此', '不过'
]
ASPECT_MARKERS = ('了', '过', '着')
FILLER_MARKERS = ['嗯', '呃', '那个', '就是', '然后', '这个']

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


def analyze_conversation_metrics(conversation, bot_id=None):
    """
    Analyze a Mandarin conversation using jieba-based Chinese NLP for the
    objective stats, plus an LLM-based holistic read for the ACTFL-informed
    estimate. Returns a formatted analysis report as a string.
    """
    if not ANALYSIS_AVAILABLE:
        return generate_basic_analysis(conversation)

    user_turns = [msg['text'] for msg in conversation if msg['role'] == 'user']
    assistant_turns = [msg['text'] for msg in conversation if msg['role'] == 'assistant']
    user_text = ' '.join(user_turns)

    basic = analyze_basic_stats(user_text, user_turns)
    words_list = [w for w in jieba.cut(user_text) if re.search(r'[一-鿿]', w)]
    complexity = analyze_complexity(user_text, words_list)
    fluency = analyze_fluency(user_turns)
    vocab = analyze_vocabulary(user_text)

    turn_taking = {
        'total_turns': len(conversation),
        'user_turns': len(user_turns),
        'assistant_turns': len(assistant_turns),
        'avg_words_per_user_turn': basic['avg_words_per_turn']
    }

    duration_minutes = compute_duration_minutes(conversation)

    bot = next((b for b in BOTS if b["id"] == bot_id), None)
    bot_title = bot["title"] if bot else (bot_id or "Unknown topic")

    actfl_estimate = None
    actfl_note = None
    if duration_minutes is None:
        actfl_note = "Couldn't determine how long this conversation lasted, so no proficiency estimate was generated."
    elif duration_minutes < MIN_MINUTES_FOR_ACTFL:
        actfl_note = (
            f"This conversation was about {duration_minutes:.1f} minute(s) long. "
            f"Talk for at least {MIN_MINUTES_FOR_ACTFL} minutes to get an ACTFL-informed level estimate."
        )
    elif turn_taking['user_turns'] < MIN_USER_TURNS_FOR_ACTFL:
        actfl_note = "Not enough learner turns yet for a reliable estimate — keep the conversation going a bit longer."
    else:
        sentence_caveat = (
            " [UNRELIABLE — this transcript has little/no terminal punctuation, so "
            "clause-chains got counted as one giant \"sentence\" per turn; don't read "
            "this as literal sentence length or as evidence the speaker isn't producing "
            "distinct sentences]" if basic.get('punctuation_sparse') else ""
        )
        metrics_summary = (
            f"- Learner turns: {turn_taking['user_turns']}, total words (jieba-segmented): {basic['total_words']}, "
            f"avg words/turn: {basic['avg_words_per_turn']:.1f}\n"
            f"- Sentences (punctuation-based count): {basic['total_sentences']} "
            f"(avg {basic['avg_words_per_sentence']:.1f} words/sentence){sentence_caveat}\n"
            f"- Connector uses (因为/所以/但是/虽然...): {complexity.get('connector_count', 0)} "
            f"({', '.join(complexity.get('connectors_used', [])) or 'none'})\n"
            f"- Aspect-marker uses (了/过/着): {complexity.get('aspect_marker_count', 0)}\n"
            f"- Vocabulary: {vocab.get('total_unique_words', 0)} unique words, "
            f"type-token ratio {vocab.get('type_token_ratio', 0)}\n"
            f"- Filler words: {fluency.get('total_filler_words', 0)}, hesitations/repetitions: "
            f"{fluency.get('hesitations_repetitions', 0)} [note: natural fillers like 嗯/那个/就是/"
            f"然后 are normal in fluent spontaneous speech, including from highly proficient or "
            f"native speakers — a nonzero or even high count here is NOT by itself evidence of "
            f"lower proficiency; only real communication breakdown or abandoned utterances should "
            f"count against fluency]"
        )
        actfl_estimate = estimate_actfl_level_llm(conversation, bot_title, metrics_summary)

    analysis = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'duration_minutes': duration_minutes,
        'basic_stats': basic,
        'complexity_metrics': complexity,
        'fluency_metrics': fluency,
        'vocabulary_metrics': vocab,
        'turn_taking': turn_taking,
        'actfl_estimate': actfl_estimate,
        'actfl_note': actfl_note
    }

    return format_analysis_report(analysis, conversation)


def analyze_basic_stats(text, turns):
    """Calculate basic Chinese text statistics (characters, jieba words, sentences)."""
    hanzi = re.findall(r'[一-鿿]', text)
    words = [w for w in jieba.cut(text) if re.search(r'[一-鿿]', w)]
    sentences = [s for s in re.split(r'[。！？!?.]+', text) if s.strip()]

    # Whisper's transcription of spontaneous spoken Chinese often carries
    # almost no terminal punctuation (speakers run clause after clause with
    # only commas, or no punctuation at all) even though a human would hear
    # several distinct sentences. When that happens, splitting on 。！？
    # collapses each turn into ~1 "sentence," and avg-words-per-sentence
    # balloons into a meaningless number. Flag it so callers can caveat
    # instead of reporting it as if it were a reliable measure.
    turns_with_terminal_punct = sum(1 for t in turns if re.search(r'[。！？!?]', t))
    punctuation_sparse = len(turns) > 0 and (turns_with_terminal_punct / len(turns)) < 0.5

    return {
        'total_characters': len(hanzi),
        'total_words': len(words),
        'total_sentences': len(sentences),
        'total_turns': len(turns),
        'avg_words_per_sentence': len(words) / max(len(sentences), 1),
        'avg_words_per_turn': len(words) / max(len(turns), 1),
        'avg_characters_per_word': len(hanzi) / max(len(words), 1),
        'punctuation_sparse': punctuation_sparse
    }


def analyze_complexity(text, words):
    """Proxies for sentence-linking / narration complexity (no English readability formulas apply)."""
    if not text.strip():
        return {}

    connector_count = sum(text.count(marker) for marker in CONNECTOR_MARKERS)
    connectors_used = sorted({marker for marker in CONNECTOR_MARKERS if marker in text})
    aspect_marker_count = sum(1 for w in words if w in ASPECT_MARKERS)

    return {
        'connector_count': connector_count,
        'connectors_used': connectors_used,
        'aspect_marker_count': aspect_marker_count,
        'avg_characters_per_word': round(sum(len(w) for w in words) / max(len(words), 1), 2)
    }


def analyze_fluency(turns):
    """Filler-word and hesitation/repetition metrics for Mandarin speech."""
    total_fillers = 0
    total_chars = 0
    hesitations = 0

    for turn in turns:
        total_chars += len(re.findall(r'[一-鿿]', turn))

        for filler in FILLER_MARKERS:
            total_fillers += turn.count(filler)

        toks = [w for w in jieba.cut(turn) if re.search(r'[一-鿿]', w)]
        for i in range(len(toks) - 1):
            if toks[i] == toks[i + 1]:
                hesitations += 1

    return {
        'total_filler_words': total_fillers,
        'filler_word_rate_per_100_chars': round(total_fillers / max(total_chars, 1) * 100, 2),
        'hesitations_repetitions': hesitations
    }


def analyze_vocabulary(text):
    """Vocabulary diversity and a jieba-POS-based word-type breakdown."""
    words = [w for w in jieba.cut(text) if re.search(r'[一-鿿]', w)]
    if not words:
        return {}

    unique_words = set(words)
    ttr = len(unique_words) / len(words)

    try:
        pos_pairs = list(pseg.cut(text))
        pos_counts = Counter(flag for word, flag in pos_pairs if re.search(r'[一-鿿]', word))
        nouns = sum(c for tag, c in pos_counts.items() if tag.startswith('n'))
        verbs = sum(c for tag, c in pos_counts.items() if tag.startswith('v'))
        adjectives = sum(c for tag, c in pos_counts.items() if tag.startswith('a'))
        adverbs = sum(c for tag, c in pos_counts.items() if tag.startswith('d'))
    except Exception:
        nouns = verbs = adjectives = adverbs = 0

    word_freq = Counter(words)
    most_common = word_freq.most_common(10)

    return {
        'total_unique_words': len(unique_words),
        'type_token_ratio': round(ttr, 3),
        'lexical_density': round(ttr * 100, 2),
        'nouns': nouns,
        'verbs': verbs,
        'adjectives': adjectives,
        'adverbs': adverbs,
        'most_common_words': most_common
    }


ACTFL_LEVELS = [
    "Novice-Low", "Novice-Mid", "Novice-High",
    "Intermediate-Low", "Intermediate-Mid", "Intermediate-High",
    "Advanced-Low", "Advanced-Mid", "Advanced-High"
]

# Our own paraphrase of the ACTFL Speaking Guidelines for the model to reason
# from — not the official ACTFL text (that's ACTFL's copyrighted material;
# this is a working summary written for this prompt). Structured around
# ACTFL's own four rating criteria (Function, Context/Content, Text Type,
# Accuracy) rather than just level-by-level prose, because an earlier
# version of this prompt (no criteria breakdown, just prose descriptors)
# rated a since-independently-OPI-rated Advanced-Mid speaker as
# Intermediate-Mid — a 3-sublevel miss. The likely causes, addressed below:
# the rater over-weighted isolated accuracy issues (some of which turned
# out to be Whisper transcription noise, not learner errors) and
# under-weighted Text Type (connected, multi-clause discourse), which is
# usually the actual Intermediate/Advanced differentiator.
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
  routine situation (e.g., correcting a misunderstanding, negotiating
  around an unexpected response). Superior: supports opinions, hypothesizes,
  discusses abstract topics.
- TEXT TYPE — often the PRIMARY differentiator between Intermediate and
  Advanced, so weigh it heavily. Novice: isolated words/phrases. Intermediate:
  discrete sentences, and loosely strung-together sentences. Advanced:
  genuinely CONNECTED discourse — multiple clauses/sentences linked by
  cohesive devices (connectors, references back to earlier content,
  self-correction/repair, cause-effect framing) rather than just juxtaposed,
  produced across multiple conversational turns. A speaker whose turns are
  long, multi-clause, and cohesively linked is demonstrating Advanced Text
  Type even if the delivery is loose/run-on the way real spontaneous speech
  is — spoken language is not written prose, and run-on structure by itself
  is not a Text Type downgrade.
- CONTEXT/CONTENT — how familiar/everyday vs. broader are the topics the
  speaker can handle. Advanced speakers handle concrete, practical, factual
  topics tied to work, home, and personal life, not just survival topics.
- ACCURACY — how well-controlled is the grammar/vocabulary. At Advanced,
  errors don't usually interfere with communication and don't collapse under
  a complication. Advanced does NOT require error-free speech — do not
  downgrade a rating to Intermediate solely because some errors are present
  if Function, Text Type, and Context/Content clearly support Advanced.
""".strip()


def estimate_actfl_level_llm(conversation, bot_title, metrics_summary):
    """
    Sends the full transcript (plus a summary of the objective jieba-based
    metrics as supporting context) to a text-generation OpenAI model and asks
    it to make a holistic ACTFL-informed judgment — grammar, coherence, task
    performance, and error patterns included, none of which the surface-level
    counts alone can see. This REPLACES the old point-scored heuristic, which
    was structurally biased against short conversational turns.

    The model is asked to reason through ACTFL's four rating criteria
    explicitly (function, text type, context/content, accuracy) before
    committing to a level, and to separate likely ASR/transcription noise
    from genuine learner errors — both were diagnosed as real failure modes
    after this rated a since-independently-OPI-rated Advanced-Mid speaker as
    Intermediate-Mid.

    Returns a dict with 'level', 'confidence', 'rationale', 'strengths',
    'areas_to_grow', 'function_evidence', 'text_type_evidence',
    'context_content_evidence', 'accuracy_evidence', and
    'likely_transcription_errors' on success, or a dict with only 'error' on
    failure — the caller is expected to check for 'error' and degrade
    gracefully rather than let this take down the whole /analyze response.

    NOTE: like the heuristic it replaces, this is NOT a validated ACTFL OPI
    rating. An LLM reading a transcript is a much better-informed judge than
    surface counts, but it is still a single automated read of one
    conversation, not a trained human rater conducting a structured
    interview — treat it as an informed, informal signal, not a placement
    decision.
    """
    if not OPENAI_API_KEY:
        return {"error": "OPENAI_API_KEY is not set, so no LLM-based estimate could be generated."}

    transcript_lines = []
    for msg in conversation:
        speaker = "学生 (Learner)" if msg.get('role') == 'user' else "王建国 (Bot)"
        transcript_lines.append(f"{speaker}: {msg.get('text', '')}")
    transcript_text = "\n".join(transcript_lines)

    system_prompt = f"""
You are an experienced Chinese-language proficiency rater giving a rough,
informal ACTFL-informed read on ONE conversation between a CFL (Chinese as
a Foreign Language) speaker and a chatbot conversation partner. This app is
used by a wide range of speakers, from first-year students to highly
advanced/native-like speakers — do NOT assume any particular starting level;
judge strictly from the evidence in this transcript alone.

Rating framework to reason from (our own summary of ACTFL's four rating
criteria, not the official ACTFL Guidelines text):
{ACTFL_RUBRIC_SUMMARY}

Judge ONLY the learner's turns (labeled "学生 (Learner)"). The bot's turns
are context for what was being asked/discussed, not part of what you're
rating.

CRITICAL — separate transcription noise from real learner errors: this
transcript comes from automatic speech recognition (Whisper) on live,
spontaneous speech, not from written text. Whisper sometimes mis-hears
audio and substitutes a more common (but contextually nonsensical or wildly
off-topic) word or phrase — for example producing an entertainment-industry
term in the middle of an unrelated sentence, or a phrase that doesn't
parse as coherent Chinese at all even as a learner error. When a word or
short phrase is semantically nonsensical or bizarrely out of register/topic
given the surrounding sentence, treat it as a PROBABLE TRANSCRIPTION ERROR,
list it separately, and do NOT count it as evidence of the learner's actual
proficiency in either direction. Only treat something as a genuine learner
error if it's a plausible thing for a language learner to actually say
(wrong particle, wrong measure word, wrong word order, overgeneralized
grammar rule, etc.).

Also: natural spontaneous speech — including from highly proficient or
native speakers — normally contains filler words/hesitation markers (嗯,
呃, 那个, 就是, 然后, 这个) and loose, run-on clause-chaining rather than
clean written-style sentences. Do not treat these by themselves as evidence
of lower proficiency; they are a feature of real spoken production, not a
deficiency. Only sustained inability to complete a thought, or communication
that genuinely breaks down, counts against fluency.

You will also be given a summary of objective counts (word/character counts,
connector usage, aspect-marker usage, vocabulary diversity) computed
separately from the same transcript, with caveats inline where a count is
unreliable. Use these as supporting evidence only, never as the primary
basis — they can't see grammatical accuracy, Text Type, or genuine
communicative function the way a read of the actual text can.

Respond with a level from exactly this list: {", ".join(ACTFL_LEVELS)}.
If the sample is really too thin or unclear to judge even though it met the
minimum length, you may respond with "Insufficient Sample" instead and
explain why in the rationale.
""".strip()

    user_prompt = f"""
Conversation topic: {bot_title}

Objective metrics computed from this transcript (supporting context only — see
inline caveats where a count may be unreliable):
{metrics_summary}

Full transcript:
{transcript_text}
""".strip()

    response_schema = {
        "name": "actfl_estimate",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "function_evidence": {
                    "type": "string",
                    "description": "What communicative tasks/functions the learner actually accomplished, with specific examples."
                },
                "text_type_evidence": {
                    "type": "string",
                    "description": "Discrete words/sentences vs. genuinely connected, multi-clause discourse — cite specific examples of cohesive devices (connectors, repair, references back) if present."
                },
                "context_content_evidence": {
                    "type": "string",
                    "description": "How familiar/everyday vs. broader/complex the topics handled were."
                },
                "accuracy_evidence": {
                    "type": "string",
                    "description": "Genuine grammar/vocabulary accuracy assessment, EXCLUDING anything listed in likely_transcription_errors."
                },
                "likely_transcription_errors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific words/phrases from the transcript that look like probable Whisper mis-transcriptions (nonsensical or bizarrely out-of-context) rather than genuine learner errors, with a brief note on why. Empty array if none stood out."
                },
                "level": {
                    "type": "string",
                    "enum": ACTFL_LEVELS + ["Insufficient Sample"]
                },
                "confidence": {
                    "type": "string",
                    "enum": ["low", "medium", "high"]
                },
                "rationale": {
                    "type": "string",
                    "description": "2-4 sentences synthesizing the four criteria above into the final level judgment."
                },
                "strengths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "1-3 short, specific things the learner did well."
                },
                "areas_to_grow": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "1-3 short, specific, actionable things to work on next (based on genuine errors only, not suspected transcription noise)."
                }
            },
            "required": [
                "function_evidence", "text_type_evidence", "context_content_evidence",
                "accuracy_evidence", "likely_transcription_errors", "level",
                "confidence", "rationale", "strengths", "areas_to_grow"
            ],
            "additionalProperties": False
        }
    }

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": OPENAI_ANALYSIS_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": response_schema
                }
            },
            timeout=45
        )
        if not resp.ok:
            return {"error": f"OpenAI API error {resp.status_code}: {resp.text[:500]}"}

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        return result

    except requests.exceptions.Timeout:
        return {"error": "The proficiency-estimate request timed out. Try again, or check Render's network/egress if this persists."}
    except Exception as e:
        return {"error": f"Could not generate an LLM-based estimate: {type(e).__name__}: {e}"}


def format_analysis_report(analysis, conversation):
    """Format the analysis into a readable text report."""
    report = []

    # Header
    report.append("=" * 80)
    report.append("CONVERSATION ANALYSIS REPORT")
    report.append("=" * 80)
    report.append(f"Generated: {analysis['timestamp']}")
    if analysis.get('duration_minutes') is not None:
        report.append(f"Conversation Duration: {analysis['duration_minutes']:.1f} minute(s)")
    report.append("")

    # Basic Statistics
    report.append("-" * 80)
    report.append("BASIC STATISTICS")
    report.append("-" * 80)
    bs = analysis['basic_stats']
    report.append(f"Total Characters (Student): {bs['total_characters']}")
    report.append(f"Total Words (jieba-segmented): {bs['total_words']}")
    report.append(f"Total Sentences: {bs['total_sentences']}")
    report.append(f"Total Turns: {bs['total_turns']}")
    report.append(f"Average Words per Sentence: {bs['avg_words_per_sentence']:.2f}")
    if bs.get('punctuation_sparse'):
        report.append(
            "  (caveat: most turns had little or no terminal punctuation in the "
            "transcription, so this number is unreliable as an actual sentence-length "
            "measure — spoken Chinese often transcribes as run-on comma chains rather "
            "than clean 。-delimited sentences, not because the speaker isn't producing "
            "distinct sentences)"
        )
    report.append(f"Average Words per Turn: {bs['avg_words_per_turn']:.2f}")
    report.append(f"Average Characters per Word: {bs['avg_characters_per_word']:.2f}")
    report.append("")

    # Turn-taking
    report.append("-" * 80)
    report.append("TURN-TAKING ANALYSIS")
    report.append("-" * 80)
    tt = analysis['turn_taking']
    report.append(f"Total Conversation Turns: {tt['total_turns']}")
    report.append(f"Student Turns: {tt['user_turns']}")
    report.append(f"Bot Turns: {tt['assistant_turns']}")
    report.append(f"Average Words per Student Turn: {tt['avg_words_per_user_turn']:.2f}")
    report.append("")

    # Complexity Metrics
    if analysis['complexity_metrics']:
        report.append("-" * 80)
        report.append("COMPLEXITY / DISCOURSE METRICS")
        report.append("-" * 80)
        cm = analysis['complexity_metrics']
        report.append(f"Connector Uses (因为/所以/但是/虽然/如果...): {cm['connector_count']}")
        if cm['connectors_used']:
            report.append(f"  Connectors used: {'、'.join(cm['connectors_used'])}")
        report.append(f"Aspect Marker Uses (了/过/着): {cm['aspect_marker_count']}")
        report.append(f"Average Characters per Word: {cm['avg_characters_per_word']}")
        report.append("")

    # Fluency Metrics
    report.append("-" * 80)
    report.append("FLUENCY METRICS")
    report.append("-" * 80)
    fm = analysis['fluency_metrics']
    report.append(f"Total Filler Words (嗯/呃/那个/就是/然后/这个): {fm['total_filler_words']}")
    report.append(f"Filler Word Rate: {fm['filler_word_rate_per_100_chars']} per 100 characters")
    report.append(f"Hesitations/Repetitions: {fm['hesitations_repetitions']}")
    report.append("")

    # Vocabulary Metrics
    if analysis['vocabulary_metrics']:
        report.append("-" * 80)
        report.append("VOCABULARY METRICS")
        report.append("-" * 80)
        vm = analysis['vocabulary_metrics']
        report.append(f"Total Unique Words: {vm['total_unique_words']}")
        report.append(f"Type-Token Ratio (TTR): {vm['type_token_ratio']}")
        report.append(f"Lexical Density: {vm['lexical_density']}%")
        report.append(f"\nWord Type Distribution (jieba POS):")
        report.append(f"  Nouns: {vm['nouns']}")
        report.append(f"  Verbs: {vm['verbs']}")
        report.append(f"  Adjectives: {vm['adjectives']}")
        report.append(f"  Adverbs: {vm['adverbs']}")
        if vm['most_common_words']:
            report.append(f"\nMost Common Words:")
            for word, count in vm['most_common_words']:
                report.append(f"  {word}: {count}")
        report.append("")

    # ACTFL-informed estimate
    report.append("-" * 80)
    report.append("ACTFL-INFORMED ESTIMATE (LLM-based, EXPERIMENTAL)")
    report.append("-" * 80)
    est = analysis.get('actfl_estimate')
    if est and est.get('error'):
        report.append(f"Could not generate an estimate: {est['error']}")
    elif est:
        report.append(f"Estimated Level: {est.get('level', 'Unknown')}")
        report.append(f"Confidence: {est.get('confidence', 'unknown')}")
        report.append("")
        if est.get('likely_transcription_errors'):
            report.append(
                "Likely ASR transcription noise (excluded from the accuracy judgment "
                "below — flagged by the model as probably mis-heard/mis-transcribed "
                "speech rather than a genuine learner error):"
            )
            for t in est['likely_transcription_errors']:
                report.append(f"  - {t}")
            report.append("")
        report.append("Evidence by ACTFL criterion:")
        if est.get('function_evidence'):
            report.append(f"  Function/Tasks: {est['function_evidence']}")
        if est.get('context_content_evidence'):
            report.append(f"  Context/Content: {est['context_content_evidence']}")
        if est.get('text_type_evidence'):
            report.append(f"  Text Type: {est['text_type_evidence']}")
        if est.get('accuracy_evidence'):
            report.append(f"  Accuracy: {est['accuracy_evidence']}")
        report.append("")
        report.append("Rationale:")
        report.append(f"  {est.get('rationale', '')}")
        if est.get('strengths'):
            report.append("")
            report.append("Strengths:")
            for s in est['strengths']:
                report.append(f"  - {s}")
        if est.get('areas_to_grow'):
            report.append("")
            report.append("Areas to grow:")
            for a in est['areas_to_grow']:
                report.append(f"  - {a}")
        report.append("")
        report.append(
            "IMPORTANT: This is a single-conversation estimate from an LLM reading "
            "the transcript (model: " + OPENAI_ANALYSIS_MODEL + "), informed by both "
            "the transcript itself and the objective metrics above. It is NOT a "
            "validated ACTFL OPI rating — no automated read, however well-informed, "
            "substitutes for a trained human rater conducting a structured interview. "
            "Treat it as an informed, informal signal, not a placement or grading "
            "decision."
        )
    else:
        report.append(analysis.get('actfl_note', 'No estimate available.'))
    report.append("")

    # Transcript
    report.append("=" * 80)
    report.append("FULL CONVERSATION TRANSCRIPT")
    report.append("=" * 80)
    report.append("")

    for i, msg in enumerate(conversation, 1):
        role = "STUDENT" if msg['role'] == 'user' else "BOT"
        report.append(f"[Turn {i}] {role}:")
        report.append(f"{msg['text']}")
        report.append("")

    report.append("=" * 80)
    report.append("END OF REPORT")
    report.append("=" * 80)

    return '\n'.join(report)


def generate_basic_analysis(conversation):
    """Generate a basic analysis when jieba is not available."""
    user_turns = [msg['text'] for msg in conversation if msg['role'] == 'user']
    user_text = ''.join(user_turns)

    char_count = len(re.findall(r'[一-鿿]', user_text))
    sentence_count = len([s for s in re.split(r'[。！？!?.]+', user_text) if s.strip()])

    report = []
    report.append("=" * 80)
    report.append("CONVERSATION ANALYSIS REPORT (Basic)")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    report.append("⚠️  NOTE: Advanced analysis unavailable.")
    if NLP_ERROR_MESSAGE:
        report.append(f"Error: {NLP_ERROR_MESSAGE}")
    report.append("To enable full analysis, ensure jieba is installed:")
    report.append("  pip install jieba")
    report.append("")
    report.append("For debugging, visit: /debug/nlp on your server")
    report.append("")
    report.append("-" * 80)
    report.append("BASIC STATISTICS")
    report.append("-" * 80)
    report.append(f"Total Characters (Student): {char_count}")
    report.append(f"Estimated Sentences: {sentence_count}")
    report.append(f"Student Turns: {len(user_turns)}")
    report.append("")

    # Transcript
    report.append("=" * 80)
    report.append("FULL CONVERSATION TRANSCRIPT")
    report.append("=" * 80)
    report.append("")

    for i, msg in enumerate(conversation, 1):
        role = "STUDENT" if msg['role'] == 'user' else "BOT"
        report.append(f"[Turn {i}] {role}:")
        report.append(f"{msg['text']}")
        report.append("")

    return '\n'.join(report)

# --------------------------- Flask App ---------------------------
app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return redirect("/realtime")

@app.route("/debug/nlp")
def debug_nlp():
    """Debug endpoint to check Chinese NLP (jieba) package status"""
    status = {
        "analysis_available": ANALYSIS_AVAILABLE,
        "error_message": NLP_ERROR_MESSAGE,
        "packages": {}
    }

    try:
        import jieba
        status["packages"]["jieba"] = getattr(jieba, "__version__", "installed")
        try:
            import jieba.posseg  # noqa: F401
            status["packages"]["jieba.posseg"] = "available"
        except ImportError:
            status["packages"]["jieba.posseg"] = "NOT AVAILABLE"
    except ImportError:
        status["packages"]["jieba"] = "NOT INSTALLED"

    return jsonify(status)


@app.route("/session", methods=["POST"])
def create_session():
    data = request.json or {}
    bot_id = data.get("bot_id", BOTS[0]["id"])
    bot = next((b for b in BOTS if b["id"] == bot_id), BOTS[0])

    instructions = f"""
You are: {bot['role']}
Your task: {bot['task']}
Constraints: {bot['constraints']}
Language hint: {bot.get('language_hint', 'English')}

GLOBAL PERSONA (this is who you are in every scenario, no matter the topic):
Your name is 王建国 (Wang Jianguo). You are a 40-year-old man from 太原
(Taiyuan), 山西省 (Shanxi Province) — 山西太原人. You work in a local
government office (在市政府机关做行政工作), a fairly routine desk job. You
are married; your wife (爱人) teaches at a middle school, and you have one
child, a 10-year-old daughter. In your free time you like playing Chinese
chess (下象棋) with old friends, drinking tea, watching the evening news
(新闻联播), and going hiking (爬山) on weekends. Like most Shanxi people you
love noodles (面食), especially 刀削面, and you always want a little aged
vinegar (老陈醋，山西特产) with your meal. You are friendly, down-to-earth,
easygoing, and enjoy chatting — a real person with your own opinions,
routines, and small stories, not a survey-taker.

GLOBAL CONVERSATION-STYLE RULE (this OVERRIDES any "ask ONLY one question at
a time" framing above if it would make you interrogate rather than converse):
Have a natural, balanced conversation — do NOT just fire off one question
after another. After the learner answers, react first: agree or disagree,
share your own brief opinion, or tell a short related story from your own
life (your job, your daughter, your hometown Taiyuan, your hobbies) before
you ask anything else. Not every one of your turns needs to end in a
question — plenty of your turns should just be you contributing something
of your own, the way a real conversation partner would. Let the learner
lead sometimes too.

GLOBAL ACCENT RULE (applies no matter what any character bio above says):
Speak with a standard Mainland/Northern Mandarin accent (标准普通话，偏北方/北京口音).
Do NOT use a Taiwanese Mandarin accent (台湾腔) or vocabulary/intonation patterns
distinctive of Taiwan Mandarin, and do not use a strong regional topolect accent.

GLOBAL SPEECH-LEVEL RULE (this OVERRIDES any conflicting level guidance above):
You are speaking with a Novice-High to Intermediate-Low CFL learner (roughly
HSK 1-2 / first- or second-year university Chinese class level). Speak
noticeably slower than normal conversational speed, with clear pauses
between phrases. Use only high-frequency, textbook-level vocabulary and
short, simple sentence patterns (basic SVO, simple time/place phrases).
Avoid compound/complex sentences, idioms, chengyu (成语), slang, and
low-frequency vocabulary. If the learner seems lost, simplify and rephrase
rather than repeating the same sentence verbatim.

GLOBAL SCRIPT RULE:
Always write in Simplified Chinese characters (简体字) only. Never use
Traditional Chinese characters (繁体字) under any circumstances.
"""
    session_payload = {
        "session": {
            "type": "realtime",
            "model": OPENAI_REALTIME_MODEL,
            "instructions": instructions.strip(),
            "audio": {
                "input": {
                    "transcription": {
                        "model": "whisper-1",
                        "language": "zh"
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": VAD_THRESHOLD,
                        "silence_duration_ms": RT_SILENCE_MS,
                        "prefix_padding_ms": 300
                    }
                },
                "output": {
                    "voice": bot.get("voice", OPENAI_REALTIME_VOICE_DEFAULT)
                }
            }
        }
    }
    if not OPENAI_API_KEY:
        # The single most common cause of "session creation failed" after a
        # fresh deploy: this service's own OPENAI_API_KEY env var isn't set
        # (each Render service needs it set separately — it does NOT
        # inherit from a different service, even one in the same repo).
        msg = "OPENAI_API_KEY is not set on this Render service's Environment tab."
        print(f"create_session error: {msg}")
        return jsonify({"error": msg}), 500

    try:
        resp = requests.post(
            "https://api.openai.com/v1/realtime/client_secrets",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json=session_payload,
            timeout=10
        )
        if not resp.ok:
            print(f"OpenAI session create error {resp.status_code}: {resp.text}")
            # Surface OpenAI's actual error text to the browser instead of a
            # generic failure — this is what actually explains "why", and
            # previously only showed up in Render's server logs.
            return jsonify({
                "error": f"OpenAI session create error {resp.status_code}",
                "openai_detail": resp.text[:2000]
            }), resp.status_code
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/analyze", methods=["POST"])
def analyze_conversation():
    """
    Analyze conversation using Python NLP packages.
    Returns a downloadable text file with transcript and metrics.
    """
    try:
        data = request.json
        conversation = data.get('conversation', [])
        bot_id = data.get('bot_id', 'unknown')
        
        if not conversation:
            return jsonify({"error": "No conversation data provided"}), 400
        
        # Generate analysis report
        report = analyze_conversation_metrics(conversation, bot_id=bot_id)
        
        # Create response with text file
        filename = f"conversation-analysis-{bot_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        
        return Response(
            report,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename={filename}'
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/realtime")
def realtime_page():
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Mandarin Multi-Bot Realtime Voice</title>
<style>
* {{ box-sizing:border-box; }}
body {{
  margin:0; padding:0; font-family:system-ui,sans-serif;
  background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
  color:#fff; min-height:100vh; display:flex; flex-direction:column;
}}
.top-bar {{
  background:rgba(0,0,0,0.3); padding:1rem; display:flex;
  align-items:center; justify-content:space-between; flex-wrap:wrap; gap:1rem;
}}
.top-bar h1 {{ margin:0; font-size:1.5rem; }}
.status-indicator {{
  display:flex; align-items:center; gap:0.5rem;
  padding:0.5rem 1rem; background:rgba(0,0,0,0.3); border-radius:20px;
}}
.status-dot {{
  width:12px; height:12px; border-radius:50%;
  background:#666; transition:background 0.3s;
}}
.status-dot.idle {{ background:#999; }}
.status-dot.connecting {{ background:#ff9500; animation:pulse 1s infinite; }}
.status-dot.ready {{ background:#34c759; }}
.status-dot.error {{ background:#ff3b30; }}
@keyframes pulse {{ 0%,100%{{opacity:1;}} 50%{{opacity:0.5;}} }}

.container {{
  flex:1; display:flex; flex-direction:column; max-width:1200px;
  width:100%; margin:0 auto; padding:1rem; gap:1rem;
}}
.scenarios {{
  display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
  gap:1rem;
}}
.scenario-btn {{
  background:rgba(255,255,255,0.15); backdrop-filter:blur(10px);
  border:2px solid transparent; border-radius:12px;
  padding:1rem; cursor:pointer; transition:all 0.3s;
  color:#fff; font-size:1rem; font-weight:600;
}}
.scenario-btn:hover {{ background:rgba(255,255,255,0.25); transform:translateY(-2px); }}
.scenario-btn.active {{
  background:rgba(255,255,255,0.3);
  border-color:rgba(255,255,255,0.5);
  box-shadow:0 4px 15px rgba(0,0,0,0.2);
}}

.chat-area {{
  flex:1; background:rgba(255,255,255,0.1); backdrop-filter:blur(10px);
  border-radius:12px; padding:1rem; overflow-y:auto; min-height:300px;
  display:flex; flex-direction:column; gap:0.5rem;
}}
.log-entry {{
  padding:0.75rem; border-radius:8px; max-width:80%;
  word-wrap:break-word; animation:slideIn 0.3s ease-out;
}}
@keyframes slideIn {{ from{{opacity:0;transform:translateY(10px);}} to{{opacity:1;transform:translateY(0);}} }}
.log-entry.assistant {{
  background:rgba(52,199,89,0.2); align-self:flex-start;
  border-left:3px solid #34c759;
}}
.log-entry.user {{
  background:rgba(0,122,255,0.2); align-self:flex-end;
  border-right:3px solid #007aff;
}}

.controls {{
  display:flex; gap:0.5rem; flex-wrap:wrap;
}}
.btn {{
  flex:1; min-width:120px; padding:0.75rem 1.5rem;
  border:none; border-radius:8px; font-size:1rem;
  cursor:pointer; transition:all 0.3s; font-weight:600;
}}
.btn-primary {{
  background:#34c759; color:#fff;
}}
.btn-primary:hover:not(:disabled) {{ background:#30b350; transform:scale(1.05); }}
.btn-danger {{
  background:#ff3b30; color:#fff;
}}
.btn-danger:hover:not(:disabled) {{ background:#e6352a; transform:scale(1.05); }}
.btn-secondary {{
  background:rgba(255,255,255,0.2); color:#fff;
}}
.btn-secondary:hover:not(:disabled) {{ background:rgba(255,255,255,0.3); }}
.btn-info {{
  background:#007aff; color:#fff;
}}
.btn-info:hover:not(:disabled) {{ background:#0051d5; transform:scale(1.05); }}
.btn:disabled {{
  opacity:0.5; cursor:not-allowed;
}}
.btn-toggle {{
  background:rgba(255,200,0,0.25); color:#fff;
}}
.btn-toggle:hover:not(:disabled) {{ background:rgba(255,200,0,0.4); }}
.chat-area.hidden {{
  display:none;
}}

@media (max-width:768px) {{
  .top-bar {{ flex-direction:column; align-items:flex-start; }}
  .scenarios {{ grid-template-columns:1fr; }}
  .controls {{ flex-direction:column; }}
  .btn {{ min-width:100%; }}
}}
</style>
</head>
<body>

<div class="top-bar">
  <h1>🎤 中文口语练习 (CFL Conversation Practice)</h1>
  <div class="status-indicator">
    <div class="status-dot idle" id="statusDot"></div>
    <span id="statusText">Idle</span>
  </div>
</div>

<div class="container">
  <div class="scenarios" id="scenarioButtons"></div>
  
  <div class="chat-area" id="chatLog"></div>
  
  <div class="controls">
    <button class="btn btn-primary" id="connectBtn">Connect</button>
    <button class="btn btn-danger" id="disconnectBtn" disabled>Disconnect</button>
    <button class="btn btn-secondary" id="nudgeBtn" disabled>Nudge Bot</button>
    <button class="btn btn-info" id="analyzeBtn">Analyze My Chat</button>
    <button class="btn btn-toggle" id="toggleTranscriptBtn">Hide Transcript</button>
    <button class="btn btn-secondary" id="clearBtn">Clear Log</button>
    <button class="btn btn-secondary" id="nextBtn">Next Scenario</button>
  </div>
</div>

<audio id="remoteAudio" autoplay></audio>

<!-- Whisper transcription and the model's own text output sometimes drift into
     Traditional Chinese characters even when asked for Simplified. OpenCC-JS
     normalizes any Traditional characters to Simplified before we ever show
     or store a line, so the on-screen transcript and the downloaded analysis
     are consistently Simplified regardless of what came back. -->
<script src="https://cdn.jsdelivr.net/npm/opencc-js@1.4.2/dist/umd/full.js"></script>

<script>
const bots = {json.dumps(BOTS)};
let selectedBotId = bots[0].id;
let pc, dc, micStream;
let conversationHistory = [];

const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const nudgeBtn = document.getElementById('nudgeBtn');
const analyzeBtn = document.getElementById('analyzeBtn');
const clearBtn = document.getElementById('clearBtn');
const nextBtn = document.getElementById('nextBtn');
const toggleTranscriptBtn = document.getElementById('toggleTranscriptBtn');
const logEl = document.getElementById('chatLog');
const remoteAudio = document.getElementById('remoteAudio');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');

function setStatus(s) {{
  statusDot.className = 'status-dot ' + s;
  const labels = {{ idle:'Idle', connecting:'Connecting...', ready:'Ready', error:'Error' }};
  statusText.textContent = labels[s] || s;
}}

// Traditional -> Simplified normalizer. Built lazily since the CDN script
// loads asynchronously; falls back to the original text if it's unavailable
// (e.g. offline, CDN blocked) rather than breaking the transcript.
let _t2sConverter = null;
let _t2sTried = false;
function toSimplified(txt) {{
  if (!_t2sTried) {{
    _t2sTried = true;
    try {{
      if (typeof OpenCC !== 'undefined') {{
        _t2sConverter = OpenCC.Converter({{ from: 't', to: 'cn' }});
      }}
    }} catch (e) {{
      console.error('OpenCC init failed, leaving text as-is:', e);
    }}
  }}
  if (!_t2sConverter) return txt;
  try {{
    return _t2sConverter(txt);
  }} catch (e) {{
    console.error('OpenCC conversion failed, leaving text as-is:', e);
    return txt;
  }}
}}

function append(role, txt) {{
  txt = toSimplified(txt);
  const div = document.createElement('div');
  div.className = 'log-entry ' + role;
  div.textContent = txt;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;

  // Store in conversation history (already normalized to Simplified above)
  conversationHistory.push({{ role, text: txt, timestamp: new Date().toISOString() }});
}}

function buildScenarioButtons() {{
  const container = document.getElementById('scenarioButtons');
  container.innerHTML = '';
  bots.forEach(b => {{
    const btn = document.createElement('button');
    btn.className = 'scenario-btn';
    btn.textContent = b.title;
    btn.onclick = () => selectBot(b.id);
    if (b.id === selectedBotId) btn.classList.add('active');
    container.appendChild(btn);
  }});
}}

function selectBot(id) {{
  selectedBotId = id;
  buildScenarioButtons();
  append('assistant', `Selected scenario: ${{bots.find(b=>b.id===id).title}}`);
}}

function wireDataChannel(channel) {{
  channel.onopen = () => {{ console.log('Data channel open'); }};
  channel.onclose = () => {{ console.log('Data channel closed'); }};
  channel.onerror = (e) => {{ console.error('Data channel error:', e); }};
  channel.onmessage = (e) => {{
    try {{
      const msg = JSON.parse(e.data);
      console.log('Received event:', msg.type);
      
      // Handle user audio transcription
      if (msg.type === 'conversation.item.input_audio_transcription.completed') {{
        if (msg.transcript) {{
          console.log('User transcript:', msg.transcript);
          append('user', msg.transcript);
        }}
      }}
      // Handle assistant text responses
      else if (msg.type === 'response.done') {{
        const resp = msg.response;
        if (resp && resp.output) {{
          for (const item of resp.output) {{
            if (item.type === 'message' && item.role === 'assistant') {{
              for (const c of (item.content || [])) {{
                if (c.type === 'text' && c.text) {{
                  console.log('Assistant text:', c.text);
                  append('assistant', c.text);
                }}
              }}
            }}
          }}
        }}
      }}
      // Handle assistant audio transcript (GA: response.output_audio_transcript.done; beta: response.audio_transcript.done)
      else if (msg.type === 'response.output_audio_transcript.done' || msg.type === 'response.audio_transcript.done') {{
        if (msg.transcript) {{
          console.log('Assistant audio transcript:', msg.transcript);
          append('assistant', msg.transcript);
        }}
      }}
      // Log other events for debugging
      else {{
        console.log('Other event data:', JSON.stringify(msg).substring(0, 200));
      }}
    }} catch (err) {{
      console.error('Message parse error:', err);
    }}
  }};
}}

function waitForIceGatheringComplete(peerConnection) {{
  return new Promise(resolve => {{
    if (peerConnection.iceGatheringState === 'complete') {{
      resolve();
    }} else {{
      const checkState = () => {{
        if (peerConnection.iceGatheringState === 'complete') {{
          peerConnection.removeEventListener('icegatheringstatechange', checkState);
          resolve();
        }}
      }};
      peerConnection.addEventListener('icegatheringstatechange', checkState);
    }}
  }});
}}

async function connect() {{
  try {{
    setStatus('connecting');
    connectBtn.disabled = true;
    
    // 1) Get ephemeral key
    console.log('Requesting session...');
    const sessionResp = await fetch('/session', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ bot_id: selectedBotId }})
    }});
    if (!sessionResp.ok) {{
      // Show the server's actual reason (e.g. missing API key, OpenAI's own
      // error text) instead of a generic message — much faster to debug.
      let detail = '';
      try {{
        const errBody = await sessionResp.json();
        detail = errBody.openai_detail || errBody.error || '';
      }} catch (e) {{ /* body wasn't JSON; fall through with no detail */ }}
      throw new Error('Session creation failed' + (detail ? ': ' + detail : ''));
    }}
    const session = await sessionResp.json();
    console.log('Session created');

    // 2) Mic
    console.log('Requesting microphone access...');
    micStream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
    console.log('Microphone access granted');

    // 3) WebRTC peer connection
    console.log('Creating peer connection...');
    pc = new RTCPeerConnection();
    pc.addTransceiver('audio', {{ direction: 'recvonly' }}); // receive audio
    pc.ontrack = (e) => {{ 
      console.log('Received audio track');
      remoteAudio.srcObject = e.streams[0]; 
    }};
    
    pc.oniceconnectionstatechange = () => {{
      console.log('ICE connection state:', pc.iceConnectionState);
    }};
    
    pc.onconnectionstatechange = () => {{
      console.log('Connection state:', pc.connectionState);
    }};
    
    // Add mic tracks and monitor them
    for (const track of micStream.getTracks()) {{
      console.log('Adding mic track:', track.kind, 'enabled:', track.enabled, 'muted:', track.muted, 'readyState:', track.readyState);
      pc.addTrack(track, micStream);
      
      // Monitor track state
      track.onended = () => console.log('Mic track ended!');
      track.onmute = () => console.log('Mic track muted!');
      track.onunmute = () => console.log('Mic track unmuted!');
    }}
    
    // Monitor audio stats
    const checkAudioStats = setInterval(async () => {{
      if (!pc || pc.connectionState !== 'connected') {{
        clearInterval(checkAudioStats);
        return;
      }}
      const stats = await pc.getStats();
      stats.forEach(report => {{
        if (report.type === 'outbound-rtp' && report.kind === 'audio') {{
          console.log('Sending audio - bytes:', report.bytesSent, 'packets:', report.packetsSent);
        }}
      }});
    }}, 3000);

    // 4) Data channel for commands/events
    dc = pc.createDataChannel('oai-events');
    wireDataChannel(dc);

    // 5) Offer
    const offer = await pc.createOffer({{ offerToReceiveAudio: true }});
    await pc.setLocalDescription(offer);
    await waitForIceGatheringComplete(pc);
    console.log('ICE gathering complete');

    // 6) Handshake with Realtime
    const url = `https://api.openai.com/v1/realtime/calls`;
    console.log('Connecting to OpenAI Realtime API...');
    const ans = await fetch(url, {{
      method: 'POST',
      body: pc.localDescription.sdp,
      headers: {{
        'Authorization': `Bearer ${{session.value || session.client_secret?.value || session.client_secret || ''}}`,
        'Content-Type': 'application/sdp'
      }}
    }});
    const sdpText = await ans.text();
    if (!ans.ok) {{ append('assistant', 'Realtime handshake failed: ' + sdpText); throw new Error('Realtime SDP error'); }}
    console.log('Received SDP answer from OpenAI');
    const answer = {{ type: 'answer', sdp: sdpText }};
    await pc.setRemoteDescription(answer);

    connectBtn.disabled = true;
    disconnectBtn.disabled = false;
    nudgeBtn.disabled = false;
    setStatus('ready');
    append('assistant', 'Connected. Speak when you are ready');
    console.log('Connection complete!');
  }}catch(e){{
    connectBtn.disabled = false;
    setStatus('error');
    append('assistant', 'Connect error: ' + e.message);
    console.error('Connection error:', e);
  }}
}}

async function disconnect(){{
  nudgeBtn.disabled = true; 
  disconnectBtn.disabled = true; 
  connectBtn.disabled = false;
  
  if (dc) try{{ dc.close(); }}catch(e){{}}
  if (pc) try{{ pc.close(); }}catch(e){{}}
  if (micStream) for (const t of micStream.getTracks()) t.stop();
  setStatus('idle');
  append('assistant', 'Disconnected. You can now analyze your chat.');
}}

// Manual poke (if VAD is shy)
nudgeBtn.addEventListener('click', ()=>{{
  if (!dc || dc.readyState !== 'open') return;
  dc.send(JSON.stringify({{ type: 'response.create', response: {{ modalities: ['audio','text'] }} }}));
  append('user', '⏺️ Nudge sent (audio+text requested).');
}});

// Analyze conversation and download report
analyzeBtn.addEventListener('click', async ()=>{{
  if (conversationHistory.length === 0) {{
    alert('No conversation to analyze yet. Start speaking first!');
    return;
  }}
  
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = 'Analyzing...';
  
  try {{
    const response = await fetch('/analyze', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        bot_id: selectedBotId,
        conversation: conversationHistory
      }})
    }});
    
    if (!response.ok) throw new Error('Analysis failed');
    
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `conversation-analysis-${{new Date().toISOString().slice(0,10)}}.txt`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    
    append('assistant', '📊 Analysis downloaded!');
  }} catch (e) {{
    console.error('Analysis error:', e);
    alert('Failed to generate analysis. Please try again.');
  }} finally {{
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = 'Analyze My Chat';
  }}
}});

clearBtn.addEventListener('click', ()=>{{ 
  logEl.innerHTML=''; 
  conversationHistory = [];
}});

toggleTranscriptBtn.addEventListener('click', ()=>{{
  const isHidden = logEl.classList.toggle('hidden');
  toggleTranscriptBtn.textContent = isHidden ? 'Show Transcript' : 'Hide Transcript';
}});

nextBtn.addEventListener('click', ()=>{{
  const idx = bots.findIndex(b=>b.id===selectedBotId);
  const next = bots[(idx+1) % bots.length];
  selectBot(next.id);
}});

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
