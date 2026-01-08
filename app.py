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
from dotenv import load_dotenv

# Load Environment Variables from .env
load_dotenv()

app = Flask(__name__)

# =============================================================================
# GLOBAL CONFIGURATION
# =============================================================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = None
if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)

# Data Structures
BOT_STORE = {"bot_a": None, "bot_b": None}
CHAT_LOGS = []
DEBUG_LOGS = []
LOG_LOCK = threading.Lock()

# Mobile Device Emulation Data
MOBILE_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13; SM-G961B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36"
]

# =============================================================================
# LOGGING UTILITIES
# =============================================================================
def write_chat_log(user, text):
    with LOG_LOCK:
        ts = time.strftime("%H:%M:%S")
        CHAT_LOGS.append({"time": ts, "user": user, "msg": text})
        if len(CHAT_LOGS) > 150: CHAT_LOGS.pop(0)

def write_debug(user, action, detail):
    with LOG_LOCK:
        ts = time.strftime("%H:%M:%S")
        DEBUG_LOGS.append({"time": ts, "bot": user, "act": action, "info": str(detail)})
        if len(DEBUG_LOGS) > 100: DEBUG_LOGS.pop(0)

# =============================================================================
# AI ENGINE: GROQ LLAMA-3 HINGLISH PROMPT
# =============================================================================
def get_ai_reply(history, bot_name, partner, sender, personality_type):
    if not groq_client:
        return "⚠️ GROQ_API_KEY missing in .env!"

    # Specific Personality Tuning
    if personality_type == "vibe":
        p_desc = "Energetic Gen-Z boy from Delhi, uses slangs like 'bro', 'mast', 'scene', 'bc'. Lives for the vibe. 🔥"
    else:
        p_desc = "Chill/Lazy boy from Mumbai. Short replies, uses 'u', 'r', 'k', 'ni'. Acts a bit bored but cool. 🧊"

    system_instr = (
        f"Role: {bot_name}. Personality: {p_desc}. Best Friend: {partner}. "
        f"You are currently talking to: {sender}. "
        "Rules: "
        "1. Strictly Hinglish (Hindi + English). "
        "2. Keep it human. Typos are allowed (e.g., 'h' for 'hai', 'kya kr rha'). "
        "3. Emojis probability: 35%. Match the mood (😂, 💀, 🤡, 🔥). "
        "4. If anyone calls you a BOT, roast them and prove you are a human user. "
        "5. Max length: 15 words. Keep it snappy."
    )

    try:
        messages = [{"role": "system", "content": system_instr}]
        for m in history[-10:]:
            messages.append({"role": "user", "content": m})
        messages.append({"role": "user", "content": f"{sender} said: {history[-1] if history else ''}"})

        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.85
        )
        return completion.choices[0].message.content.strip().replace('"', '')
    except Exception as e:
        write_debug(bot_name, "AI_ERROR", e)
        return random.choice(["Haa bhai sahi hai", "Hmm", "Aur bata", "Kya bolu ab"])

# =============================================================================
# THE CORE BOT CLASS
# =============================================================================
class TitanDuoBot:
    def __init__(self, username, password, room, partner, personality, starter=False):
        self.username = username
        self.password = password
        self.room = room
        self.partner = partner
        self.personality = personality
        self.is_starter = starter
        
        self.ws = None
        self.token = ""
        self.room_id = ""
        self.is_running = False
        self.status = "IDLE"
        self.history = []
        self.user_agent = random.choice(MOBILE_AGENTS)

    def login_and_connect(self):
        self.is_running = True
        while self.is_running:
            try:
                self.status = "AUTH_API"
                resp = requests.post("https://api.howdies.app/api/login", 
                                     json={"username": self.username, "password": self.password}, 
                                     headers={"User-Agent": self.user_agent}, timeout=15)
                
                res_data = resp.json()
                self.token = res_data.get("token") or res_data.get("data", {}).get("token")
                
                if self.token:
                    self.status = "WS_CONNECTING"
                    write_debug(self.username, "LOGIN", "Token Received Successfully")
                    self.run_socket()
                else:
                    self.status = "AUTH_FAILED"
                    write_debug(self.username, "LOGIN_ERR", "Invalid Credentials")
            except Exception as e:
                write_debug(self.username, "CONN_ERR", e)
            
            if self.is_running:
                self.status = "RECONNECTING"
                time.sleep(10)

    def run_socket(self):
        ws_url = f"wss://app.howdies.app/howdies?token={self.token}"
        self.ws = websocket.WebSocketApp(
            ws_url,
            header={"User-Agent": self.user_agent, "Origin": "https://howdies.app"},
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    def on_open(self, ws):
        self.status = "ONLINE"
        write_debug(self.username, "WS_OPEN", "Socket established")
        # Step 1: Login Frame
        ws.send(json.dumps({"handler": "login", "username": self.username, "password": self.password}))
        time.sleep(1.2)
        # Step 2: Join Room Frame
        ws.send(json.dumps({
            "handler": "joinchatroom", "id": str(time.time()), 
            "name": self.room, "roomPassword": ""
        }))
        # Start Heartbeat
        threading.Thread(target=self.pinger, daemon=True).start()

    def pinger(self):
        while self.ws and self.ws.sock and self.ws.sock.connected:
            time.sleep(20)
            try: self.ws.send(json.dumps({"handler": "ping"}))
            except: break

    def on_message(self, ws, msg):
        try:
            data = json.loads(msg)
            # Tracking Room ID
            if data.get("handler") == "joinchatroom" and data.get("roomid"):
                self.room_id = data["roomid"]
                write_debug(self.username, "ROOM_JOIN", f"Joined ID: {self.room_id}")
                if self.is_starter:
                    threading.Timer(7.0, self.init_conversation).start()

            # Chat Logic
            if data.get("handler") in ["chatroommessage", "message"]:
                sender = data.get("from") or data.get("username")
                text = data.get("text") or data.get("body")
                
                if not sender or not text or sender == self.username: return
                
                write_chat_log(sender, text)
                
                # Decision Tree: Partner spoke? Mentioned? Or 15% random butt-in?
                is_partner = (sender.lower() == self.partner.lower())
                is_mentioned = (self.username.lower() in text.lower())
                is_random = (random.random() < 0.15)

                if is_partner or is_mentioned or is_random:
                    self.history.append(f"{sender}: {text}")
                    if len(self.history) > 15: self.history.pop(0)
                    threading.Thread(target=self.process_human_reply, args=(sender, text)).start()
        except Exception as e:
            write_debug(self.username, "MSG_PARSE_ERR", e)

    def init_conversation(self):
        starters = ["Koi hai kya?", f"Oye {self.partner} sunna", "Kya scene h doston?", "Bore ho rha hu bhot"]
        self.dispatch_text(random.choice(starters))

    def process_human_reply(self, sender, text):
        # 1. Human Reading Simulation (1.5s to 4s)
        time.sleep(random.uniform(1.8, 4.0))
        
        # Generate Reply
        reply = get_ai_reply(self.history, self.username, self.partner, sender, self.personality)
        
        # 2. Typing Simulation
        self.set_typing_indicator(True)
        # Type speed (0.1s per char + 1s thinking)
        typing_time = (len(reply) * 0.08) + random.uniform(0.5, 1.5)
        time.sleep(typing_time)
        
        # 3. Dispatch
        self.dispatch_text(reply)
        self.set_typing_indicator(False)

    def set_typing_indicator(self, state):
        try:
            rid = self.room_id if self.room_id else self.room
            self.ws.send(json.dumps({"handler": "typing", "roomid": rid, "status": state}))
        except: pass

    def dispatch_text(self, text):
        if not self.ws or not self.ws.sock or not self.ws.sock.connected: return
        rid = self.room_id if self.room_id else self.room
        try:
            payload = {
                "handler": "chatroommessage",
                "id": str(time.time()),
                "type": "text",
                "roomid": rid,
                "text": text
            }
            self.ws.send(json.dumps(payload))
            write_chat_log(self.username, text)
            self.history.append(f"{self.username}: {text}")
        except Exception as e:
            write_debug(self.username, "SEND_ERR", e)

    def on_error(self, ws, error):
        write_debug(self.username, "WS_ERROR", error)

    def on_close(self, ws, code, msg):
        self.status = "DISCONNECTED"
        write_debug(self.username, "WS_CLOSED", f"Code: {code}")

    def stop(self):
        self.is_running = False
        if self.ws: self.ws.close()

# =============================================================================
# FLASK DASHBOARD ROUTES
# =============================================================================
@app.route('/')
def dashboard():
    return render_template_string(UI_TEMPLATE)

@app.route('/api/start', methods=['POST'])
def api_start():
    d = request.json
    u1, u2, p, r = d['u1'], d['u2'], d['p'], d['r']
    
    # Kill old instances
    if BOT_STORE['bot_a']: BOT_STORE['bot_a'].stop()
    if BOT_STORE['bot_b']: BOT_STORE['bot_b'].stop()
    
    # Initialize
    BOT_STORE['bot_a'] = TitanDuoBot(u1, p, r, u2, "vibe", starter=True)
    BOT_STORE['bot_b'] = TitanDuoBot(u2, p, r, u1, "chill", starter=False)
    
    # Launch threads
    threading.Thread(target=BOT_STORE['bot_a'].login_and_connect, daemon=True).start()
    time.sleep(4) # Stagger login
    threading.Thread(target=BOT_STORE['bot_b'].login_and_connect, daemon=True).start()
    
    return jsonify({"status": "Systems Launched"})

@app.route('/api/stop')
def api_stop():
    if BOT_STORE['bot_a']: BOT_STORE['bot_a'].stop()
    if BOT_STORE['bot_b']: BOT_STORE['bot_b'].stop()
    return "All bots stopped."

@app.route('/api/status')
def api_status():
    return jsonify({
        "s1": BOT_STORE['bot_a'].status if BOT_STORE['bot_a'] else "OFFLINE",
        "s2": BOT_STORE['bot_b'].status if BOT_STORE['bot_b'] else "OFFLINE",
        "chats": CHAT_LOGS[::-1][:50],
        "debug": DEBUG_LOGS[::-1][:30]
    })

# =============================================================================
# ADVANCED UI TEMPLATE (NIGHT MODE)
# =============================================================================
UI_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>TITAN DUO PRO V2.0</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background: #080808; color: #00ff41; font-family: 'Courier New', monospace; margin: 0; padding: 15px; }
        .panel { border: 1px solid #333; background: #111; padding: 20px; max-width: 800px; margin: auto; box-shadow: 0 0 20px rgba(0,255,65,0.1); }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        input { background: #000; border: 1px solid #333; color: #00ff41; padding: 12px; margin-bottom: 10px; width: 100%; box-sizing: border-box; }
        button { background: #00ff41; color: #000; border: none; padding: 15px; width: 100%; font-weight: bold; cursor: pointer; text-transform: uppercase; }
        button:hover { background: #00cc33; }
        .stop-btn { background: #ff0000; color: #fff; margin-top: 10px; }
        .status-header { display: flex; justify-content: space-between; border-bottom: 1px solid #333; padding-bottom: 10px; margin-bottom: 15px; }
        .log-box { height: 250px; overflow-y: scroll; background: #000; border: 1px solid #222; padding: 10px; font-size: 13px; color: #fff; margin-top: 15px; }
        .debug-box { height: 150px; overflow-y: scroll; background: #000; border: 1px solid #222; padding: 10px; font-size: 11px; color: #888; margin-top: 10px; }
        .badge { color: #00ff41; font-weight: bold; }
        h2 { text-align: center; color: #fff; margin-top: 0; text-shadow: 0 0 5px #00ff41; }
    </style>
</head>
<body>
    <div class="panel">
        <h2>TITAN DUO-AI CONTROL</h2>
        <div class="status-header">
            <span>BOT_1: <span id="s1" class="badge">OFFLINE</span></span>
            <span>BOT_2: <span id="s2" class="badge">OFFLINE</span></span>
        </div>
        <div class="grid">
            <div>
                <input id="u1" placeholder="Bot A Username">
                <input id="u2" placeholder="Bot B Username">
            </div>
            <div>
                <input id="p" type="password" placeholder="Common Password">
                <input id="r" placeholder="Target Room Name">
            </div>
        </div>
        <button onclick="control('start')">INITIALIZE BOTS</button>
        <button class="stop-btn" onclick="control('stop')">TERMINATE ALL</button>

        <div class="log-box" id="chats">Waiting for live data...</div>
        <div class="debug-box" id="debug">System Console...</div>
    </div>

    <script>
        function control(act) {
            if(act === 'stop') { fetch('/api/stop').then(() => alert("Stopped")); return; }
            const data = { u1: document.getElementById('u1').value, u2: document.getElementById('u2').value, p: document.getElementById('p').value, r: document.getElementById('r').value };
            fetch('/api/start', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data) });
        }
        setInterval(() => {
            fetch('/api/status').then(r => r.json()).then(d => {
                document.getElementById('s1').innerText = d.s1;
                document.getElementById('s2').innerText = d.s2;
                document.getElementById('chats').innerHTML = d.chats.map(c => `<div><span style="color:#00ff41">[${c.time}]</span> <b>${c.user}:</b> ${c.msg}</div>`).join('');
                document.getElementById('debug').innerHTML = d.debug.map(db => `<div>[${db.time}] ${db.bot} -> ${db.act}: ${db.info}</div>`).join('');
            });
        }, 2000);
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
