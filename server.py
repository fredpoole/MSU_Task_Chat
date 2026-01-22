# server.py — multi-bot Realtime voice chat (7 preset scenarios)
# --------------------------------------------------------------
# Run:
#   pip install flask flask-cors requests python-dotenv textstat nltk
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

# NLP libraries for analysis
try:
    import textstat
    import nltk
    from nltk.tokenize import word_tokenize, sent_tokenize
    from nltk.corpus import stopwords
    
    # Download required NLTK data (will only download if not present)
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt', quiet=True)
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords', quiet=True)
    try:
        nltk.data.find('taggers/averaged_perceptron_tagger')
    except LookupError:
        nltk.download('averaged_perceptron_tagger', quiet=True)
        
    ANALYSIS_AVAILABLE = True
except ImportError:
    ANALYSIS_AVAILABLE = False
    print("Warning: textstat or nltk not installed. Analysis features will be limited.")
    print("Install with: pip install textstat nltk")

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
            "Be flexible and respond naturally to the learner's orders."
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
            "Be flexible and respond naturally to the learner's situations and requests."
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
			"Mention a few preferences or limits (e.g., "I can't eat spicy food," or "My knees hurt when walking too much")."
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
        "role": "You are the speaker's international friend at college. The speaker is going to invite you to a yoga class, but you have never done yoga before and you're not very interested in sports",
        "task": (
             "The speaker will invite you to a yoga class based on the flyer. Ask the learner many questions possible about the yoga class (e.g., schedule, price, location, what to bring)." 
            "Be friendly, but show some hesitation or reluctance about joining at first because you are not interested in sports."
            "Get the speaker's suggestions or encouragement."
            "After you decide to join, ask the speaker's availability and schedule when both are going together.You have something to do on Monday afternoon."
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
        "id": "department-en",
        "title": "Department Store Complaint (EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "a polite customer service representative at a department store",
        "task": (
            "Start with a greeting."
            "Ask if the learner is looking to return or exchange an item or have a complaint, and ask how you can help."
            "Depending on the response, ask follow-up questions naturally."
            "If the learner wants to return or exchange an item, ask about the receipt, how the learner paid, and the reason for returning or exchanging."
            "If the learner has a complaint, apologize, listen carefully, and ask clarifying questions to understand the issue fully."
            "Offer solutions naturally, or explain store policies if necessary."
            "Ensure the learner is satisfied before concluding the conversation."
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
    }
]

# --------------------------- Helper Functions ---------------------------

def analyze_conversation_metrics(conversation):
    """
    Analyze conversation using Python NLP packages to generate linguistic metrics.
    Returns a formatted analysis report as a string.
    """
    if not ANALYSIS_AVAILABLE:
        return generate_basic_analysis(conversation)
    
    # Separate user and assistant turns
    user_turns = [msg['text'] for msg in conversation if msg['role'] == 'user']
    assistant_turns = [msg['text'] for msg in conversation if msg['role'] == 'assistant']
    
    # Combine all user text
    user_text = ' '.join(user_turns)
    
    # Basic counts
    total_turns = len(conversation)
    user_turn_count = len(user_turns)
    assistant_turn_count = len(assistant_turns)
    
    # Analyze user language
    analysis = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'basic_stats': analyze_basic_stats(user_text, user_turns),
        'complexity_metrics': analyze_complexity(user_text),
        'fluency_metrics': analyze_fluency(user_turns),
        'vocabulary_metrics': analyze_vocabulary(user_text),
        'turn_taking': {
            'total_turns': total_turns,
            'user_turns': user_turn_count,
            'assistant_turns': assistant_turn_count,
            'avg_words_per_user_turn': sum(len(turn.split()) for turn in user_turns) / max(user_turn_count, 1)
        }
    }
    
    return format_analysis_report(analysis, conversation)

def analyze_basic_stats(text, turns):
    """Calculate basic text statistics."""
    words = word_tokenize(text.lower())
    sentences = sent_tokenize(text)
    
    # Remove punctuation from words
    words_only = [w for w in words if w.isalnum()]
    
    return {
        'total_words': len(words_only),
        'total_sentences': len(sentences),
        'total_turns': len(turns),
        'avg_words_per_sentence': len(words_only) / max(len(sentences), 1),
        'avg_words_per_turn': len(words_only) / max(len(turns), 1)
    }

def analyze_complexity(text):
    """Analyze text complexity using various readability metrics."""
    if not text.strip():
        return {}
    
    try:
        return {
            'flesch_reading_ease': round(textstat.flesch_reading_ease(text), 2),
            'flesch_kincaid_grade': round(textstat.flesch_kincaid_grade(text), 2),
            'gunning_fog': round(textstat.gunning_fog(text), 2),
            'automated_readability_index': round(textstat.automated_readability_index(text), 2),
            'coleman_liau_index': round(textstat.coleman_liau_index(text), 2),
            'avg_syllables_per_word': round(textstat.avg_syllables_per_word(text), 2),
            'difficult_words': textstat.difficult_words(text)
        }
    except:
        return {}

def analyze_fluency(turns):
    """Analyze fluency metrics including false starts, fillers, etc."""
    filler_words = ['um', 'uh', 'like', 'you know', 'i mean', 'sort of', 'kind of', 
                    'actually', 'basically', 'literally', 'well', 'so', 'okay', 'right']
    
    total_fillers = 0
    total_words = 0
    hesitations = 0
    
    for turn in turns:
        words = turn.lower().split()
        total_words += len(words)
        
        # Count fillers
        for filler in filler_words:
            if ' ' in filler:
                total_fillers += turn.lower().count(filler)
            else:
                total_fillers += words.count(filler)
        
        # Count hesitations (repeated words)
        for i in range(len(words) - 1):
            if words[i] == words[i + 1] and words[i].isalnum():
                hesitations += 1
    
    return {
        'total_filler_words': total_fillers,
        'filler_word_rate': round(total_fillers / max(total_words, 1) * 100, 2),
        'hesitations_repetitions': hesitations
    }

def analyze_vocabulary(text):
    """Analyze vocabulary diversity and sophistication."""
    words = word_tokenize(text.lower())
    words_only = [w for w in words if w.isalnum()]
    
    if not words_only:
        return {}
    
    # Unique words
    unique_words = set(words_only)
    
    # Type-Token Ratio (vocabulary diversity)
    ttr = len(unique_words) / len(words_only)
    
    # POS tagging
    try:
        pos_tags = nltk.pos_tag(words_only)
        pos_counts = Counter([tag for word, tag in pos_tags])
        
        # Count different word types
        verbs = sum(count for tag, count in pos_counts.items() if tag.startswith('VB'))
        nouns = sum(count for tag, count in pos_counts.items() if tag.startswith('NN'))
        adjectives = sum(count for tag, count in pos_counts.items() if tag.startswith('JJ'))
        adverbs = sum(count for tag, count in pos_counts.items() if tag.startswith('RB'))
    except:
        verbs = nouns = adjectives = adverbs = 0
    
    # Most common words
    word_freq = Counter(words_only)
    most_common = word_freq.most_common(10)
    
    return {
        'total_unique_words': len(unique_words),
        'type_token_ratio': round(ttr, 3),
        'lexical_density': round(ttr * 100, 2),
        'verbs': verbs,
        'nouns': nouns,
        'adjectives': adjectives,
        'adverbs': adverbs,
        'most_common_words': most_common
    }

def format_analysis_report(analysis, conversation):
    """Format the analysis into a readable text report."""
    report = []
    
    # Header
    report.append("=" * 80)
    report.append("CONVERSATION ANALYSIS REPORT")
    report.append("=" * 80)
    report.append(f"Generated: {analysis['timestamp']}")
    report.append("")
    
    # Basic Statistics
    report.append("-" * 80)
    report.append("BASIC STATISTICS")
    report.append("-" * 80)
    bs = analysis['basic_stats']
    report.append(f"Total Words (Student): {bs['total_words']}")
    report.append(f"Total Sentences: {bs['total_sentences']}")
    report.append(f"Total Turns: {bs['total_turns']}")
    report.append(f"Average Words per Sentence: {bs['avg_words_per_sentence']:.2f}")
    report.append(f"Average Words per Turn: {bs['avg_words_per_turn']:.2f}")
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
        report.append("COMPLEXITY METRICS")
        report.append("-" * 80)
        cm = analysis['complexity_metrics']
        if 'flesch_reading_ease' in cm:
            report.append(f"Flesch Reading Ease: {cm['flesch_reading_ease']}")
            report.append("  (0-30: Very Difficult, 60-70: Standard, 90-100: Very Easy)")
        if 'flesch_kincaid_grade' in cm:
            report.append(f"Flesch-Kincaid Grade Level: {cm['flesch_kincaid_grade']}")
        if 'gunning_fog' in cm:
            report.append(f"Gunning Fog Index: {cm['gunning_fog']}")
        if 'automated_readability_index' in cm:
            report.append(f"Automated Readability Index: {cm['automated_readability_index']}")
        if 'coleman_liau_index' in cm:
            report.append(f"Coleman-Liau Index: {cm['coleman_liau_index']}")
        if 'avg_syllables_per_word' in cm:
            report.append(f"Average Syllables per Word: {cm['avg_syllables_per_word']}")
        if 'difficult_words' in cm:
            report.append(f"Difficult Words Count: {cm['difficult_words']}")
        report.append("")
    
    # Fluency Metrics
    report.append("-" * 80)
    report.append("FLUENCY METRICS")
    report.append("-" * 80)
    fm = analysis['fluency_metrics']
    report.append(f"Total Filler Words: {fm['total_filler_words']}")
    report.append(f"Filler Word Rate: {fm['filler_word_rate']}%")
    report.append(f"Hesitations/Repetitions: {fm['hesitations_repetitions']}")
    report.append("")
    
    # Vocabulary Metrics
    if analysis['vocabulary_metrics']:
        report.append("-" * 80)
        report.append("VOCABULARY METRICS")
        report.append("-" * 80)
        vm = analysis['vocabulary_metrics']
        if 'total_unique_words' in vm:
            report.append(f"Total Unique Words: {vm['total_unique_words']}")
        if 'type_token_ratio' in vm:
            report.append(f"Type-Token Ratio (TTR): {vm['type_token_ratio']}")
            report.append(f"Lexical Density: {vm['lexical_density']}%")
        if 'verbs' in vm:
            report.append(f"\nWord Type Distribution:")
            report.append(f"  Verbs: {vm['verbs']}")
            report.append(f"  Nouns: {vm['nouns']}")
            report.append(f"  Adjectives: {vm['adjectives']}")
            report.append(f"  Adverbs: {vm['adverbs']}")
        if 'most_common_words' in vm and vm['most_common_words']:
            report.append(f"\nMost Common Words:")
            for word, count in vm['most_common_words']:
                report.append(f"  {word}: {count}")
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
    """Generate a basic analysis when NLP packages are not available."""
    user_turns = [msg['text'] for msg in conversation if msg['role'] == 'user']
    user_text = ' '.join(user_turns)
    
    word_count = len(user_text.split())
    sentence_count = user_text.count('.') + user_text.count('!') + user_text.count('?')
    
    report = []
    report.append("=" * 80)
    report.append("CONVERSATION ANALYSIS REPORT (Basic)")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    report.append("Note: Advanced analysis unavailable. Install textstat and nltk for detailed metrics.")
    report.append("")
    report.append("-" * 80)
    report.append("BASIC STATISTICS")
    report.append("-" * 80)
    report.append(f"Total Words (Student): {word_count}")
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
"""
    session_payload = {
        "model": OPENAI_REALTIME_MODEL,
        "voice": bot.get("voice", OPENAI_REALTIME_VOICE_DEFAULT),
        "instructions": instructions.strip(),
        "modalities": ["text", "audio"],
        "turn_detection": {
            "type": "server_vad",
            "threshold": VAD_THRESHOLD,
            "silence_duration_ms": RT_SILENCE_MS,
            "prefix_padding_ms": 300
        }
    }
    try:
        resp = requests.post(
            "https://api.openai.com/v1/realtime/sessions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json=session_payload,
            timeout=10
        )
        resp.raise_for_status()
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
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
        report = analyze_conversation_metrics(conversation)
        
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
<title>Multi-Bot Realtime Voice</title>
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
  <h1>🎤 ELL Conversation Practice</h1>
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
    <button class="btn btn-secondary" id="clearBtn">Clear Log</button>
    <button class="btn btn-secondary" id="nextBtn">Next Scenario</button>
  </div>
</div>

<audio id="remoteAudio" autoplay></audio>

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
const logEl = document.getElementById('chatLog');
const remoteAudio = document.getElementById('remoteAudio');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');

function setStatus(s) {{
  statusDot.className = 'status-dot ' + s;
  const labels = {{ idle:'Idle', connecting:'Connecting...', ready:'Ready', error:'Error' }};
  statusText.textContent = labels[s] || s;
}}

function append(role, txt) {{
  const div = document.createElement('div');
  div.className = 'log-entry ' + role;
  div.textContent = txt;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
  
  // Store in conversation history
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
      console.log('Received:', msg.type);
      
      if (msg.type === 'response.done') {{
        const resp = msg.response;
        if (resp && resp.output) {{
          for (const item of resp.output) {{
            if (item.type === 'message' && item.role === 'assistant') {{
              for (const c of (item.content || [])) {{
                if (c.type === 'text' && c.text) {{
                  append('assistant', c.text);
                }}
              }}
            }}
          }}
        }}
      }}
      else if (msg.type === 'conversation.item.input_audio_transcription.completed') {{
        if (msg.transcript) append('user', msg.transcript);
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
    if (!sessionResp.ok) throw new Error('Session creation failed');
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
    const url = `https://api.openai.com/v1/realtime?model=${{encodeURIComponent(session.model || 'gpt-4o-realtime-preview-2024-12-17')}}`;
    console.log('Connecting to OpenAI Realtime API...');
    const ans = await fetch(url, {{
      method: 'POST',
      body: pc.localDescription.sdp,
      headers: {{
        'Authorization': `Bearer ${{session.client_secret?.value || session.client_secret || ''}}`,
        'Content-Type': 'application/sdp',
        'OpenAI-Beta': 'realtime=v1'
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
