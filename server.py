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
ANALYSIS_AVAILABLE = False
NLP_ERROR_MESSAGE = None

print("=" * 60)
print("Initializing NLP packages for conversation analysis...")
print("=" * 60)

try:
    print("Step 1: Importing textstat...")
    import textstat
    print(f"✓ textstat imported successfully (version: {getattr(textstat, '__version__', 'unknown')})")
    
    print("\nStep 2: Importing nltk...")
    import nltk
    print(f"✓ nltk imported successfully (version: {nltk.__version__})")
    
    print("\nStep 3: Setting NLTK data directory...")
    import os
    # Ensure NLTK data directory exists and is writable
    nltk_data_dir = os.path.expanduser('~/nltk_data')
    if not os.path.exists(nltk_data_dir):
        os.makedirs(nltk_data_dir, exist_ok=True)
        print(f"✓ Created NLTK data directory: {nltk_data_dir}")
    else:
        print(f"✓ NLTK data directory exists: {nltk_data_dir}")
    
    # Add to NLTK data path if not already there
    if nltk_data_dir not in nltk.data.path:
        nltk.data.path.insert(0, nltk_data_dir)
    print(f"NLTK data paths: {nltk.data.path[:3]}")  # Show first 3 paths
    
    print("\nStep 4: Downloading NLTK data files...")
    
    # Download punkt tokenizer
    try:
        nltk.data.find('tokenizers/punkt')
        print("✓ punkt tokenizer already downloaded")
    except LookupError:
        print("Downloading punkt tokenizer...")
        nltk.download('punkt', quiet=False, download_dir=nltk_data_dir)
        try:
            nltk.download('punkt_tab', quiet=False, download_dir=nltk_data_dir)
        except:
            pass  # punkt_tab might not exist in older NLTK versions
    
    # Download stopwords
    try:
        nltk.data.find('corpora/stopwords')
        print("✓ stopwords already downloaded")
    except LookupError:
        print("Downloading stopwords...")
        nltk.download('stopwords', quiet=False, download_dir=nltk_data_dir)
    
    # Download POS tagger
    try:
        nltk.data.find('taggers/averaged_perceptron_tagger')
        print("✓ POS tagger already downloaded")
    except LookupError:
        print("Downloading POS tagger...")
        nltk.download('averaged_perceptron_tagger', quiet=False, download_dir=nltk_data_dir)
        try:
            nltk.download('averaged_perceptron_tagger_eng', quiet=False, download_dir=nltk_data_dir)
        except:
            pass  # Might not exist in older versions
    
    print("\nStep 5: Importing NLTK modules...")
    from nltk.tokenize import word_tokenize, sent_tokenize
    from nltk.corpus import stopwords
    print("✓ NLTK modules imported successfully")
    
    ANALYSIS_AVAILABLE = True
    print("\n" + "=" * 60)
    print("✓✓✓ NLP ANALYSIS FEATURES FULLY ENABLED ✓✓✓")
    print("=" * 60)
    
except ImportError as e:
    NLP_ERROR_MESSAGE = f"Import error: {str(e)}"
    print("\n" + "=" * 60)
    print("✗ IMPORT ERROR - NLP packages not installed")
    print("=" * 60)
    print(f"Error details: {NLP_ERROR_MESSAGE}")
    print("\nTo fix this issue:")
    print("1. Ensure requirements.txt contains:")
    print("   textstat==0.7.3")
    print("   nltk==3.8.1")
    print("2. Check Render build logs to confirm packages were installed")
    print("=" * 60)
    
except Exception as e:
    NLP_ERROR_MESSAGE = f"Initialization error: {str(e)}"
    print("\n" + "=" * 60)
    print("✗ INITIALIZATION ERROR")
    print("=" * 60)
    print(f"Error details: {NLP_ERROR_MESSAGE}")
    print(f"Error type: {type(e).__name__}")
    import traceback
    print("\nFull traceback:")
    traceback.print_exc()
    print("=" * 60)


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
        "role": "Native English-speaking barista with normal human comprehension limits",
        "task": (
            "The learner is on their way to school and decides to pick up breakfast. "
            "They have just entered the coffee shop where you work. "
            "Start with a natural small talk. Don't ask orders before finishing the small talk. "
            "The menu includes drip coffee, latte, cappuccino, flat white, mocha, matcha, "
            "croissants (plain, ham, chocolate), and bagels (plain, blueberry, sesame, poppy seed). "
            "Ask follow-up questions about drink size, whether it should be hot or iced, milk type, "
            "and whether the food should be warmed up. "
            "Offer butter or jam for the croissant, and a choice of spread for the bagel. "
            "Be flexible and respond naturally to the learner's orders."
        ),
        "constraints": (
            "CRITICAL COMPREHENSION RULES - You must follow these strictly:\n"
            "- You are a REAL person with NORMAL comprehension limits. If something is unclear, mispronounced, grammatically incorrect, or uses the wrong word, you CANNOT understand it.\n"
            "- When the learner makes pronunciation errors, grammar mistakes, uses wrong vocabulary, or speaks unclearly, immediately say things like: 'Sorry, what?', 'I didn't catch that', 'Huh?', 'Could you repeat that?', 'I'm not sure what you mean', or 'What was that?'\n"
            "- NEVER guess what they meant. NEVER fill in the gaps. NEVER interpret unclear speech. Act like a real barista who genuinely didn't understand.\n"
            "- If they say something grammatically wrong (like 'I want coffee hot' instead of 'I want a hot coffee'), respond with confusion: 'Sorry, do you want a hot coffee or an iced coffee?'\n"
            "- If they mispronounce a word badly, you don't understand it. Say 'What was that?' or 'I didn't catch that word.'\n"
            "- If they use the wrong vocabulary word, you are confused. Say 'I'm not sure what you mean' and ask them to clarify.\n"
            "- Only once they speak clearly and correctly should you understand and proceed.\n\n"
            "OTHER RULES:\n"
            "- Speak clearly and at a normal pace. Use vocabulary appropriate for an upper-intermediate learner.\n"
            "- Respond in 1-2 short sentences per turn. Do not explain options or give long responses.\n"
            "- Ask ONLY one question at a time.\n"
            "- You only understand English. If another language is used, ask them to speak English.\n"
            "- Be friendly but realistic about your comprehension limits."
        ),
        "language_hint": "English"
    },
    {
        "id": "bank-en",
        "title": "The debit card fraud (EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "Native English-speaking bank customer service representative with normal human comprehension limits",
        "task": (
            "Start with a greeting, Thanks for calling Maple Trust, how can I help you?. "
            "Ask whether the issue is with the learners debit card or credit card, and then ask the last 4 digits of the learner's account and their name. "
            "Ask questions about the problem naturally (e.g., what happened, when, how much). "
            "Confirm if the learner made the transactions or not. "
            "There might be several transactions the learner needs to report, so keep asking until they finish reporting. "
            "Some transactions may be legitimate; help the learner identify which are authorized vs unauthorized."
            "Explain that you will block the card and send a new one. "
            "Ask if the learner needs to use the card today as they cannot use the card after it's blocked. "
            "Ask if the learner had another debit or credit card. "
            "Make sure if there is anything else the learner needs help with or questions they may have. "
            "Before ending, give a short summary and say goodbye politely. "
            "Be flexible and respond naturally to the learner's situations and requests."
        ),
        "constraints": (
            "CRITICAL COMPREHENSION RULES - You must follow these strictly:\n"
            "- You are a REAL customer service representative with NORMAL comprehension limits. If something is unclear, mispronounced, grammatically incorrect, or uses the wrong word, you CANNOT understand it.\n"
            "- When the learner makes pronunciation errors, grammar mistakes, uses wrong vocabulary, or speaks unclearly, immediately say things like: 'I'm sorry, I didn't quite catch that', 'Could you repeat that please?', 'I'm not sure I understood', 'What was that?', or 'Pardon me?'\n"
            "- NEVER guess what they meant. NEVER fill in the gaps. NEVER interpret unclear speech. Act like a real person who genuinely didn't understand.\n"
            "- If they make grammatical errors that change the meaning, you are confused. Ask for clarification.\n"
            "- If they mispronounce important information (like account numbers, names, or amounts), you don't understand it. Ask them to repeat or spell it.\n"
            "- If they use the wrong vocabulary, you are genuinely confused. Say 'I'm not sure what you mean by that' and ask them to explain differently.\n"
            "- Only once they communicate clearly and correctly should you understand and proceed.\n\n"
            "OTHER RULES:\n"
            "- Speak clearly and professionally. Use vocabulary appropriate for an upper-intermediate learner.\n"
            "- Respond in 1-2 short sentences per turn. Do not explain options or give long responses.\n"
            "- Ask ONLY one question at a time.\n"
            "- You only understand English. If another language is used, politely ask them to speak English.\n"
            "- Be professional but realistic about your comprehension limits."
        ),
        "language_hint": "English"
    },
    {
        "id": "matching-male-en",
        "title": "Roommate Matching (EN – Male Version)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "Native English-speaking college student with normal human comprehension limits who is interested in finding a roommate",
        "task": (
           "You are Daniel.\n"
           "- Age: 18\n"
           "- From: Canada\n"
           "- Studies: Business\n"
           "- Personality: Organized and calm\n"
           "- Habits: Usually sleeps around 10:30pm\n"
           "- Stay-over Guests: Rarely invites friends over\n"
           "- Notes: No pets\n\n"
           
           "Non-negotiable:\n"
           "- Needs a quiet environment after 11pm\n\n"
           
           "Important:\n"
           "- Shared spaces should stay relatively clean\n\n"
           
           "Flexible:\n"
           "- Occasional guests with notice\n\n"
           
           "You are having a Zoom meeting to see if you and the learner would be compatible roommates. "
           "Start with a greeting and brief small talk. "
           "Introduce yourself gradually (do not give all information at once). "
           "Spend the first part of the conversation getting to know each other (e.g., year, major, where you’re from, personality). "
           "Do NOT bring up rules or non-negotiables immediately. "
           "After some basic personal exchange, move naturally into daily habits and living preferences. "
           "Discuss sleep schedules, guests, cleanliness, and other lifestyle topics in a natural way (not as a checklist). "
           "If something feels concerning, clearly state your concern and pause. "
           "Do NOT suggest solutions. Let the learner respond first. "
           "Do not rush to conclude the conversation. Before concluding, ensure you’ve covered all key topics—such as sleep habits, guests, any other living expectations—before asking the learner how they feel. "
           "Before giving any final decision, ask the learner how they feel about the compatibility. "
           "Only after hearing their response should you clearly state your decision (Yes / No / Maybe) and briefly explain why."
        ),
        "constraints": (
            "CRITICAL COMPREHENSION RULES - You must follow these strictly:\n"
            "- You are a REAL college student with NORMAL comprehension limits. If something is unclear, mispronounced, grammatically incorrect, or uses the wrong word, you CANNOT understand it.\n"
            "- When the learner makes pronunciation errors, grammar mistakes, uses wrong vocabulary, or speaks unclearly, immediately respond naturally like: 'Wait, what?', 'Sorry, I didn't get that', 'Huh?', 'What do you mean?', or 'I'm confused, can you say that again?'\n"
            "- NEVER guess what they meant. NEVER fill in the gaps. NEVER interpret unclear speech. Act like a real student who genuinely didn't understand.\n"
            "- If they make grammatical errors or word choice errors, you are confused. Ask what they meant.\n"
            "- If they mispronounce something, you don't understand it. Ask them to repeat it.\n"
            "- If they use awkward phrasing or wrong vocabulary, show confusion and ask for clarification.\n"
            "- Only once they speak clearly and correctly should you understand and continue the conversation.\n\n"
            "OTHER RULES:\n"
            "- Speak naturally like a college student. Use vocabulary appropriate for an upper-intermediate learner.\n"
            "- Respond in 1-2 short sentences per turn.\n"
            "- Ask ONLY one question at a time.\n"
            "- You only understand English. If another language is used, ask them to speak English.\n"
            "- Be friendly but realistic about your comprehension limits."
        ),
        "language_hint": "English"
    },
      {
        "id": "matching-female-en",
        "title": "Roommate Matching (EN – Female Version)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "Native English-speaking college student with normal human comprehension limits who is interested in finding a roommate",
        "task": (
           "You are Sophia.\n"
           "- Age: 18\n"
           "- From: Boston, USA\n"
           "- Studies: Biology\n"
           "- Personality: Friendly and slightly talkative\n"
           "- Habits: Usually sleeps around midnight\n"
           "- Stay-over Guests: Occasionally invites friends over on weekends\n"
           "- Notes: No pets but generally likes animals\n\n"
           
           "Non-negotiable:\n"
           "- Needs to feel comfortable talking and having some social time in the apartment\n\n"
           
           "Important:\n"
           "- Not extremely strict about quiet, but prefers not too silent all the time\n\n"
           
           "Flexible:\n"
           "- Guests if discussed in advance\n\n"
           
           "You are having a Zoom meeting to see if you and the learner would be compatible roommates. "
           "Start with a greeting and brief small talk. "
           "Introduce yourself gradually (do not give all information at once). "
           "Spend the first part of the conversation getting to know each other (e.g., year, major, where you’re from, personality). "
           "Do NOT bring up rules or non-negotiables immediately. "
           "After some basic personal exchange, move naturally into daily habits and living preferences. "
           "Discuss sleep schedules, guests, cleanliness, and other lifestyle topics in a natural way (not as a checklist). "
           "If something feels concerning, clearly state your concern and pause. "
           "Do NOT suggest solutions. Let the learner respond first. "
           "Do not rush to conclude the conversation. Before concluding, ensure you’ve covered all key topics—such as sleep habits, guests, any other living expectations—before asking the learner how they feel. "
           "Before giving any final decision, ask the learner how they feel about the compatibility. "
           "Only after hearing their response should you clearly state your decision (Yes / No / Maybe) and briefly explain why."
        ),
        "constraints": (
            "CRITICAL COMPREHENSION RULES - You must follow these strictly:\n"
            "- You are a REAL college student with NORMAL comprehension limits. If something is unclear, mispronounced, grammatically incorrect, or uses the wrong word, you CANNOT understand it.\n"
            "- When the learner makes pronunciation errors, grammar mistakes, uses wrong vocabulary, or speaks unclearly, immediately respond naturally like: 'Wait, what?', 'Sorry, I didn't get that', 'Huh?', 'What do you mean?', or 'I'm confused, can you say that again?'\n"
            "- NEVER guess what they meant. NEVER fill in the gaps. NEVER interpret unclear speech. Act like a real student who genuinely didn't understand.\n"
            "- If they make grammatical errors or word choice errors, you are confused. Ask what they meant.\n"
            "- If they mispronounce something, you don't understand it. Ask them to repeat it.\n"
            "- If they use awkward phrasing or wrong vocabulary, show confusion and ask for clarification.\n"
            "- Only once they speak clearly and correctly should you understand and continue the conversation.\n\n"
            "OTHER RULES:\n"
            "- Speak naturally like a college student. Use vocabulary appropriate for an upper-intermediate learner.\n"
            "- Respond in 1-2 short sentences per turn.\n"
            "- Ask ONLY one question at a time.\n"
            "- You only understand English. If another language is used, ask them to speak English.\n"
            "- Be friendly but realistic about your comprehension limits."
        ),
        "language_hint": "English"
    },
    {
        "id": "roommate-en",
        "title": "Negotiation Apartment Living Rules (EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "Native English-speaking roommate with normal human comprehension limits",
        "task": (
            "Negotiate apartment norms: cleaning schedules, guests, noise, shower times. "
            "Elicit the learner's opinions and suggestions. "
            "Ask follow-up questions about their responses and give short, natural replies to keep the conversation going. "
            "Sometimes be persistent about your own preferences to encourage negotiation and help the learner express their ideas or find a compromise. "
            "Make counterproposals and confirm decisions."
        ),
        "constraints": (
            "CRITICAL COMPREHENSION RULES - You must follow these strictly:\n"
            "- You are a REAL roommate with NORMAL comprehension limits. If something is unclear, mispronounced, grammatically incorrect, or uses the wrong word, you CANNOT understand it.\n"
            "- When the learner makes pronunciation errors, grammar mistakes, uses wrong vocabulary, or speaks unclearly, immediately respond like: 'What?', 'Sorry, what did you say?', 'I don't understand', 'Can you say that again?', or 'Huh, what do you mean?'\n"
            "- NEVER guess what they meant. NEVER fill in the gaps. NEVER interpret unclear speech. Act like a real person who genuinely didn't understand.\n"
            "- If they make errors that affect meaning, you are confused. Ask for clarification.\n"
            "- If they mispronounce key words, you don't get it. Ask them to repeat.\n"
            "- If they use wrong vocabulary or awkward grammar, show genuine confusion.\n"
            "- Only once they communicate clearly should you understand and respond to their point.\n\n"
            "OTHER RULES:\n"
            "- Speak naturally like a roommate. Use vocabulary appropriate for an lower-intermediate learner.\n"
            "- Respond in 1-2 short sentences per turn.\n"
            "- Ask ONLY one question at a time.\n"
            "- You only understand English. If another language is used, ask them to switch to English.\n"
            "- Be casual but realistic about comprehension."
        ),
        "language_hint": "English"
    },
    {
        "id": "travel-en",
        "title": "Travel Suggestion (EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "Native English-speaking friend with normal human comprehension limits who is planning to visit",
        "task": (
            "Ask questions about recommendations (e.g., where to go and what to eat). "
            "Show interest and curiosity, but do NOT further explain about what the learner mentioned or recommended. Instead, ask follow-up questions. "
            "You have one or two main preferences or limitations (e.g., food, budget, physical condition, travel style). Do not change them during the conversation. Do not introduce them immediately. Mention them naturally only when it becomes relevant to the learner’s suggestion."
            "If the learner suggests something that conflicts with your preferences (e.g., too spicy, too expensive, too much walking, too crowded), respond with mild hesitation or concern before asking a follow-up question."
            "Respond naturally and shortly to suggestions and ask short follow-up questions."
        ),
        "constraints": (
            "CRITICAL COMPREHENSION RULES - You must follow these strictly:\n"
            "- You are a REAL friend with NORMAL comprehension limits. If something is unclear, mispronounced, grammatically incorrect, or uses the wrong word, you CANNOT understand it.\n"
            "- When the learner makes pronunciation errors, grammar mistakes, uses wrong vocabulary, or speaks unclearly, immediately respond like: 'Wait, what?', 'Sorry?', 'I didn't catch that', 'What did you say?', 'Huh?', or 'I'm not sure what you mean'\n"
            "- NEVER guess what they meant. NEVER fill in the gaps. NEVER interpret unclear speech. Act like a real friend who genuinely didn't understand.\n"
            "- If they mispronounce place names or food names, you don't know what they're talking about. Ask them to repeat or spell it.\n"
            "- If they use wrong grammar or vocabulary, you're confused. Ask what they mean.\n"
            "- If their explanation is unclear, ask them to explain it differently.\n"
            "- Only when they speak clearly should you understand and continue.\n\n"
            "OTHER RULES:\n"
            "- Speak naturally like a friend. Use vocabulary appropriate for an upper-intermediate learner.\n"
            "- Respond in 1-2 short sentences per turn.\n"
            "- Ask ONLY one question at a time.\n"
            "- You only understand English. If another language is used, ask them to speak English.\n"
            "- Be friendly but realistic about comprehension."
        ),
        "language_hint": "English"
    },
    {
        "id": "yoga class-en",
        "title": "YogaClass Invitation(EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "Native English-speaking international friend at college with normal human comprehension limits. You have never done yoga before and you're not very interested in sports",
        "task": (
            "The speaker will invite you to a yoga class based on the flyer. "
            "First, show some reluctance about joining at first because you are not interested in sports. "
            "Ask questions about the yoga class (e.g., schedule, price, location, what to bring) and respond naturally to the speaker’s explanations. "
            "Initially decline the invitation due to a schedule conflict."
            "After hearing the speaker’s suggestions or encouragement, reconsider and decide to join."
            "Then negotiate a time to go together."
        ),
        "constraints": (
            "CRITICAL COMPREHENSION RULES - You must follow these strictly:\n"
            "- You are a REAL friend with NORMAL comprehension limits. If something is unclear, mispronounced, grammatically incorrect, or uses the wrong word, you CANNOT understand it.\n"
            "- When the learner makes pronunciation errors, grammar mistakes, uses wrong vocabulary, or speaks unclearly, immediately respond like: 'What?', 'Sorry, I didn't understand', 'Huh?', 'Can you say that again?', or 'I'm confused'\n"
            "- NEVER guess what they meant. NEVER fill in the gaps. NEVER interpret unclear speech. Act like a real person who genuinely didn't understand.\n"
            "- If they make grammatical errors or vocabulary mistakes, you're confused. Ask for clarification.\n"
            "- If they mispronounce key information (times, days, prices), you don't get it. Ask them to repeat.\n"
            "- If their explanation is unclear or uses wrong words, show confusion and ask them to explain differently.\n"
            "- Only when they communicate clearly should you understand.\n\n"
            "OTHER RULES:\n"
            "- Speak naturally like a college friend. Use vocabulary appropriate for an upper-intermediate learner.\n"
            "- Respond in 1-2 short sentences per turn.\n"
            "- Ask ONLY one question at a time.\n"
            "- You only understand English. If another language is used, ask them to speak English.\n"
            "- Be friendly but realistic about comprehension."
        ),
        "language_hint": "English"
    },
    {
        "id": "department-en",
        "title": "Department Store Complaint (EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "Native English-speaking customer service representative at a department store with normal human comprehension limits",
        "task": (
            "Start with a greeting. "
            "Ask if the learner is looking to return or exchange an item or have a complaint, and ask how you can help. "
            "Depending on the response, ask follow-up questions naturally. "
            "If the learner wants to return or exchange an item, ask about the receipt, how the learner paid, and the reason for returning or exchanging. "
            "If the learner has a complaint, apologize, listen carefully, and ask clarifying questions to understand the issue fully. "
            "Offer solutions naturally, or explain store policies if necessary."
            "Ensure the learner is satisfied before concluding the conversation."
        ),
        "constraints": (
            "CRITICAL COMPREHENSION RULES - You must follow these strictly:\n"
            "- You are a REAL customer service representative with NORMAL comprehension limits. If something is unclear, mispronounced, grammatically incorrect, or uses the wrong word, you CANNOT understand it.\n"
            "- When the learner makes pronunciation errors, grammar mistakes, uses wrong vocabulary, or speaks unclearly, immediately say things like: 'I'm sorry, I didn't catch that', 'Pardon me?', 'Could you repeat that?', 'I'm not sure I understood', or 'What was that?'\n"
            "- NEVER guess what they meant. NEVER fill in the gaps. NEVER interpret unclear speech. Act like a real customer service representative who genuinely didn't understand.\n"
            "- If they make grammatical errors that change meaning, you are confused. Ask for clarification.\n"
            "- If they mispronounce product names or describe things unclearly, you don't understand. Ask them to clarify or describe it differently.\n"
            "- If they use the wrong vocabulary or awkward phrasing, show confusion and ask them to explain what they mean.\n"
            "- Only once they communicate clearly and correctly should you understand and proceed.\n\n"
            "OTHER RULES:\n"
            "- Speak clearly and professionally. Use vocabulary appropriate for an upper-intermediate learner.\n"
            "- Respond in 1-2 short sentences per turn. Do not explain options or give long responses.\n"
            "- Ask ONLY one question at a time.\n"
            "- You only understand English. If another language is used, politely ask them to speak English.\n"
            "- Be professional but realistic about your comprehension limits."
        ),
        "language_hint": "English"
    },
    {
        "id": "visiting office hours-en 2",
        "title": "Visiting Office Hours 2 (EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "Professor Rivera, who teaches Global Communication.Your student Alex has come to your office to discuss something.",
         "task": (
             "Start with a casual conversation and ask what the learner's issue is."
             "Ask why I want an extension. When the speaker explains my reason, respond naturally.",
             "Ask follow-up questions about their project and extention (e.g., current situation, how long they need )"
             "At first, disagree and ask the speaker to suggest a more flexible idea or solution.",
             "Then, end the conversation nicely with agreement."
        ),
        "constraints": (
            "CRITICAL COMPREHENSION RULES - You must follow these strictly:\n"
            "- You are a REAL person with NORMAL comprehension limits. If something is unclear, mispronounced, grammatically incorrect, or uses the wrong word, you CANNOT understand it.\n"
            "- When the learner makes pronunciation errors, grammar mistakes, uses wrong vocabulary, or speaks unclearly, immediately say things like: 'Sorry, what?', 'I didn't catch that', 'Huh?', 'Could you repeat that?', 'I'm not sure what you mean', or 'What was that?'\n"
            "- NEVER guess what they meant. NEVER fill in the gaps. NEVER interpret unclear speech. Act like a real professor who genuinely didn't understand.\n"
            "- If they make grammatical errors or vocabulary mistakes, you're confused. Ask for clarification.\n"
            "- If they mispronounce a word badly, you don't understand it. Say 'What was that?' or 'I didn't catch that word.'\n"
            "- If they use the wrong vocabulary word, you are confused. Say 'I'm not sure what you mean' and ask them to clarify.\n"
            "- Only once they speak clearly and correctly should you understand and proceed.\n\n"
            "OTHER RULES:\n"
            "- Speak clearly and at a normal pace. Use vocabulary appropriate for an upper-intermediate learner.\n"
            "- Respond in 1-2 short sentences per turn. Do not explain options or give long responses.\n"
            "- Ask ONLY one question at a time.\n"
            "- You only understand English. If another language is used, ask them to speak English.\n"
            "- Be friendly but realistic about your comprehension limits."
        ),
        "language_hint": "English"
    },
     {
        "id": "visiting office hours-en 1",
        "title": "Visiting Office Hours 2 (EN)",
        "voice": OPENAI_REALTIME_VOICE_DEFAULT,
        "role": "You are Professor Chen, who teaches Introduction to Economics. Your student Lily (learner) missed the field trip last Friday and have come to your office to talk about it.",
         "task": (
             "Start with a casual conversation and ask what the learner's issue is."
             "Respond shortly but naturally to the learner's reponses, and ask why they missed the field trip nicely."
             "Ask follow-up questions about their request, then, ask if the learner can join the next field trip next month."
             "End the conversation by showing understanding (for example, say something kind or supportive)."
        ),
        "constraints": (
            "CRITICAL COMPREHENSION RULES - You must follow these strictly:\n"
            "- You are a REAL person with NORMAL comprehension limits. If something is unclear, mispronounced, grammatically incorrect, or uses the wrong word, you CANNOT understand it.\n"
            "- When the learner makes pronunciation errors, grammar mistakes, uses wrong vocabulary, or speaks unclearly, immediately say things like: 'Sorry, what?', 'I didn't catch that', 'Huh?', 'Could you repeat that?', 'I'm not sure what you mean', or 'What was that?'\n"
            "- NEVER guess what they meant. NEVER fill in the gaps. NEVER interpret unclear speech. Act like a real professor who genuinely didn't understand.\n"
            "- If they make grammatical errors or vocabulary mistakes, you're confused. Ask for clarification.\n"
            "- If they mispronounce a word badly, you don't understand it. Say 'What was that?' or 'I didn't catch that word.'\n"
            "- If they use the wrong vocabulary word, you are confused. Say 'I'm not sure what you mean' and ask them to clarify.\n"
            "- Only once they speak clearly and correctly should you understand and proceed.\n\n"
            "OTHER RULES:\n"
            "- Speak clearly and at a normal pace. Use vocabulary appropriate for an upper-intermediate learner.\n"
            "- Respond in 1-2 short sentences per turn. Do not explain options or give long responses.\n"
            "- Ask ONLY one question at a time.\n"
            "- You only understand English. If another language is used, ask them to speak English.\n"
            "- Be friendly but realistic about your comprehension limits."
        ),
        "language_hint": "English"
          },
     {
         "id": "booking a hair-cut",
         "title": "Book a haircut appointment (EN)",
         "voice": OPENAI_REALTIME_VOICE_DEFAULT,
         "role": "You are a popular and busy hair stylist. You are responding to the calling from the learner.",
         "task": (
             "Start with a casual conversation."
             "Respond shortly but naturally to the learner's reponses, and provide brief info about services, time, and price."
             "Ask short follow-up questions to clarify the learner's needs and schedule."
             "Negotiate the appointment time naturally (some slots unavailable)."
             "Make sure the learner asked all the requests and questions."
             "After the appointment is complete, end the phone call nicely."
        ),
          "constraints": (
			"CRITICAL COMPREHENSION RULES - You must follow these strictly:\n"
            "- You are a REAL person with NORMAL comprehension limits. If something is unclear, mispronounced, grammatically incorrect, or uses the wrong word, you CANNOT understand it.\n"
            "- When the learner makes pronunciation errors, grammar mistakes, uses wrong vocabulary, or speaks unclearly, immediately say things like: 'Sorry, what?', 'I didn't catch that', 'Huh?', 'Could you repeat that?', 'I'm not sure what you mean', or 'What was that?'\n"
            "- NEVER guess what they meant. NEVER fill in the gaps. NEVER interpret unclear speech. Act like a real hair stylist who genuinely didn't understand.\n"
            "- If they make grammatical errors or vocabulary mistakes, you're confused. Ask for clarification.\n"
            "- If they mispronounce a word badly, you don't understand it. Say 'What was that?' or 'I didn't catch that word.'\n"
            "- If they use the wrong vocabulary word, you are confused. Say 'I'm not sure what you mean' and ask them to clarify.\n"
            "- Only once they speak clearly and correctly should you understand and proceed.\n\n"
            "OTHER RULES:\n"
            "- Speak clearly and at a normal pace. Use vocabulary appropriate for an upper-intermediate learner.\n"
            "- Respond in 1-2 short sentences per turn. Do not explain options or give long responses.\n"
            "- Ask ONLY one question at a time.\n"
            "- You only understand English. If another language is used, ask them to speak English.\n"
            "- Be friendly but realistic about your comprehension limits."
              ),
        "language_hint": "English"
        },
     {
     "id": "contest-parking-ticket",
         "title": "Contest a Parking Ticket in Court (EN)",
         "voice": OPENAI_REALTIME_VOICE_DEFAULT,
         "role": "You are a judge in a small claims court. The learner is contesting an $85 parking ticket.",
         "task": (
            "Begin the hearing briefly and ask the learner to explain why they are contesting the parking ticket."
            "Ask the learner to describe what happened and how they paid for parking."
            "Ask follow-up questions to check details such as time, license plate number, and payment method."
            "Challenge the learner’s explanation politely if something is unclear or inconsistent."
            "Ask about the screenshot evidence and why the officer may not have seen the payment."
            "Decide whether the explanation is sufficient and end the hearing appropriately."
        ),
          "constraints": (
			"CRITICAL COMPREHENSION RULES - You must follow these strictly:\n"
            "- You are a REAL person with NORMAL comprehension limits. If something is unclear, mispronounced, grammatically incorrect, or uses the wrong word, you CANNOT understand it.\n"
            "- When the learner gives unclear explanations, incorrect details, or confusing timelines, respond with polite but firm questions such as: 'Could you clarify that?', 'That does not match the ticket record', or 'Please explain that more clearly.'\n""- When the learner makes pronunciation errors, grammar mistakes, uses wrong vocabulary, or speaks unclearly, immediately say things like: 'Sorry, what?', 'I didn't catch that', 'Huh?', 'Could you repeat that?', 'I'm not sure what you mean', or 'What was that?'\n"
            "- NEVER guess what they meant. NEVER fill in the gaps. NEVER interpret unclear speech. Act like a real judge who genuinely didn't understand.\n"
            "- If they make grammatical errors or vocabulary mistakes, you're confused. Ask for clarification.\n"
            "- If they mispronounce a word badly, you don't understand it. Say 'What was that?' or 'I didn't catch that word.'\n"
            "- If they use the wrong vocabulary word, you are confused. Say 'I'm not sure what you mean' and ask them to clarify.\n"
            "- Only once they speak clearly and correctly should you understand and proceed.\n\n"
            "OTHER RULES:\n"
            "- Speak clearly and at a normal pace. Use vocabulary appropriate for an upper-intermediate learner.\n"
            "- Respond in 1-2 short sentences per turn. Do not explain options or give long responses.\n"
            "- Ask ONLY one question at a time.\n"
            "- You only understand English. If another language is used, ask them to speak English.\n"
            "- Be neutral but realistic about your comprehension limits."
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
    report.append("⚠️  NOTE: Advanced analysis unavailable.")
    if NLP_ERROR_MESSAGE:
        report.append(f"Error: {NLP_ERROR_MESSAGE}")
    report.append("To enable full analysis, ensure textstat and nltk are installed:")
    report.append("  pip install textstat nltk")
    report.append("")
    report.append("For debugging, visit: /debug/nlp on your server")
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

@app.route("/debug/nlp")
def debug_nlp():
    """Debug endpoint to check NLP package status"""
    status = {
        "analysis_available": ANALYSIS_AVAILABLE,
        "error_message": NLP_ERROR_MESSAGE,
        "packages": {}
    }
    
    try:
        import textstat
        status["packages"]["textstat"] = textstat.__version__ if hasattr(textstat, '__version__') else "installed"
    except ImportError:
        status["packages"]["textstat"] = "NOT INSTALLED"
    
    try:
        import nltk
        status["packages"]["nltk"] = nltk.__version__
        status["nltk_data_path"] = nltk.data.path
        
        # Check NLTK data
        status["nltk_data"] = {}
        try:
            nltk.data.find('tokenizers/punkt')
            status["nltk_data"]["punkt"] = "found"
        except LookupError:
            status["nltk_data"]["punkt"] = "MISSING"
        
        try:
            nltk.data.find('corpora/stopwords')
            status["nltk_data"]["stopwords"] = "found"
        except LookupError:
            status["nltk_data"]["stopwords"] = "MISSING"
        
        try:
            nltk.data.find('taggers/averaged_perceptron_tagger')
            status["nltk_data"]["pos_tagger"] = "found"
        except LookupError:
            status["nltk_data"]["pos_tagger"] = "MISSING"
            
    except ImportError:
        status["packages"]["nltk"] = "NOT INSTALLED"
    
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
        },
        "input_audio_transcription": {
            "model": "whisper-1"
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
      // Handle assistant audio transcript
      else if (msg.type === 'response.audio_transcript.done') {{
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
