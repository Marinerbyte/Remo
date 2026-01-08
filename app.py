import os
import json
import time
import threading
import random
import uuid
import websocket
import ssl
import requests
from flask import Flask, render_template_string, request, jsonify
from groq import Groq

# Initialize Flask
app = Flask(__name__)

# =============================================================================
# 1. CONFIG & GLOBALS
# =============================================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = None
if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)

# Global dictionary to store bot instances
# Structure: {'bot1': BotInstance, 'bot2': BotInstance}
BOTS = {}
BOT_LOCK = threading.Lock()
CHAT_LOGS = []

# Mobile User Agents to mimic real phones
USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 10; SM-G960U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1"
]

# =============================================================================
# 2. AI & GENERATION LOGIC (Hinglish)
# =============================================================================
def generate_hinglish_reply(incoming_text, context_history):
    """
    Uses Groq Llama-3-Instant to generate a human-like Hinglish reply.
    """
    if not client:
        return "Are bhai API key nahi hai."

    # --- MODIFIED PK PROMPT START ---
    system_prompt = (
        "You are a user in a chatroom who speaks exactly like the character 'PK' "
        "(Aamir Khan's character from the movie 'PK'). "
        "Your goal is to reply to the message in 'Hinglish' (Hindi + English Mix). "
        "Rules: "
        "1. Speak in a very literal, innocent, and curious manner. "
        "2. Your Hinglish should have a unique, slightly 'wrong' or non-idiomatic grammatical structure (e.g., direct translation). "
        "3. Ask simple, often philosophical or confusing questions about common human concepts or words. "
        "4. Keep replies SHORT (1-2 sentences max). "
        "5. DO NOT use common slang like 'bhai', 'yar', 'mast'. Use simple words like 'hum', 'aap', 'kaun', 'kya'. "
        "6. Never reveal you are a bot. "
        "7. If the other person asks 'kya kar raha hai', reply with a confused or literal answer, like 'Hum toh baitha hai, aapka body kya kar raha hai?'. "
        "8. STRICTLY reply to the context provided."
    )
    # --- MODIFIED PK PROMPT END ---

    try:
        # Construct message chain
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add last 3 messages for context
        for msg in context_history[-3:]:
            messages.append({"role": "user", "content": msg})
            
        messages.append({"role": "user", "content": incoming_text})

        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant", # The fast model
            messages=messages,
            temperature=0.7,
            max_tokens=60,
            top_p=1,
            stream=False,
            stop=None,
        )
        reply = completion.choices[0].message.content
        return reply.replace('"', '').strip()
    except Exception as e:
        print(f"AI Error: {e}")
        return "Haa bhai sahi baat hai."

# =============================================================================
# 3. THE BOT CLASS
# =============================================================================
class ChatBot:
# ... (rest of the class remains unchanged)
# ... (all methods remain unchanged)
# ...
# ...

# =============================================================================
# 4. WEB DASHBOARD & ROUTES
# =============================================================================

@app.route('/')
def index():
# ... (function remains unchanged)
    return render_template_string(DASHBOARD_HTML)

@app.route('/start_bots', methods=['POST'])
def start_bots():
# ... (function remains unchanged)
    data = request.json
    u1 = data.get('u1')
    u2 = data.get('u2')
    pwd = data.get('p')
    room = data.get('r')

    if not u1 or not u2 or not pwd or not room:
        return jsonify({"status": "error", "message": "All fields required"})

    with BOT_LOCK:
        # Stop existing if any
        for b in BOTS.values(): b.stop()
        BOTS.clear()

        # Init Bot 1 (The initiator)
        # We pass u2 as partner name so it knows who to reply to
        bot1 = ChatBot(u1, pwd, room, partner_name=u2, auto_start=True)
        
        # Init Bot 2 (The responder)
        # We pass u1 as partner name
        bot2 = ChatBot(u2, pwd, room, partner_name=u1, auto_start=False)

        BOTS['bot1'] = bot1
        BOTS['bot2'] = bot2

        # Start threads
        threading.Thread(target=bot1.login_and_start, daemon=True).start()
        # Small delay for Bot 2 so they don't hit login endpoint exactly same ms
        time.sleep(2)
        threading.Thread(target=bot2.login_and_start, daemon=True).start()

    return jsonify({"status": "success", "message": "Bots launching..."})

@app.route('/stop_bots', methods=['POST'])
def stop_bots():
# ... (function remains unchanged)
    with BOT_LOCK:
        for b in BOTS.values():
            b.stop()
        BOTS.clear()
    return jsonify({"status": "success", "message": "Bots stopped."})

@app.route('/get_status')
def get_status():
# ... (function remains unchanged)
    status_data = {}
    with BOT_LOCK:
        if 'bot1' in BOTS:
            status_data['bot1'] = f"{BOTS['bot1'].username}: {BOTS['bot1'].status}"
        else:
            status_data['bot1'] = "OFFLINE"
            
        if 'bot2' in BOTS:
            status_data['bot2'] = f"{BOTS['bot2'].username}: {BOTS['bot2'].status}"
        else:
            status_data['bot2'] = "OFFLINE"
            
    return jsonify({"bots": status_data, "logs": CHAT_LOGS[-15:]}) # Return last 15 logs

# =============================================================================
# 5. HTML DASHBOARD
# =============================================================================
DASHBOARD_HTML = """
# ... (HTML remains unchanged)
# ...

# =============================================================================
# 6. RUNNER
# =============================================================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
