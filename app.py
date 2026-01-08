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

# Environment configuration
load_dotenv()

app = Flask(__name__)

# =============================================================================
# GLOBAL CORE CONFIG
# =============================================================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = None
if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)

# Central Memory System
BOT_INSTANCES = {"A": None, "B": None}
CHAT_HISTORY_GLOBAL = []
SYSTEM_LOGS = []
LOG_LOCK = threading.Lock()

# Mobile Fingerprinting to avoid bot detection
MOBILE_UAS = [
    "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; SM-G991U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36"
]

# =============================================================================
# LOGGING SYSTEM
# =============================================================================
def add_chat_log(user, text):
    with LOG_LOCK:
        ts = time.strftime("%H:%M:%S")
        CHAT_HISTORY_GLOBAL.append({"t": ts, "u": user, "m": text})
        if len(CHAT_HISTORY_GLOBAL) > 150: CHAT_HISTORY_GLOBAL.pop(0)

def add_sys_log(bot, action, detail):
    with LOG_LOCK:
        ts = time.strftime("%H:%M:%S")
        SYSTEM_LOGS.append(f"[{ts}] {bot} | {action}: {detail}")
        if len(SYSTEM_LOGS) > 100: SYSTEM_LOGS.pop(0)

# =============================================================================
# ADVANCED AI CONVERSATION ENGINE
# =============================================================================
def fetch_ai_reply(history_context, bot_name, target_partner, current_sender, personality):
    if not groq_client:
        return "⚠️ GROQ_API_KEY is missing in .env"

    # Personality Profiles
    if personality == "vibe":
        p_profile = "Gen-Z Delhi boy. Energetic, uses 'bro', 'mast', 'scene', 'bc', 'gazab'. Loves emojis 🔥, 😂."
    else:
        p_profile = "Chill Mumbai guy. Cool, a bit lazy, uses 'u', 'r', 'k', 'ni'. Acts a bit bored but friendly. 🧊"

    prompt = (
        f"Character: {bot_name}. Personality: {p_profile}. Bestie: {target_partner}. "
        f"Context: You are in a chatroom talking to {current_sender}. "
        "Strict Guidelines: "
        "1. Language: Hinglish (Hindi + English mix) only. "
        "2. Style: Extremely human. Use short forms, small typos, and casual grammar. "
        "3. Defend: If someone calls you a BOT, roast them or prove you're human. "
        "4. Interaction: If it's your Bestie, be playful. If it's a stranger, be casual/sarcastic. "
        "5. Length: Keep it under 15 words. No long paragraphs."
    )

    try:
        messages = [{"role": "system", "content": prompt}]
        # Pass last 10 messages for deep context
        for m in history_context[-10:]:
            messages.append({"role": "user", "content": m})
        
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.85,
            max_tokens=100
        )
        return response.choices[0].message.content.strip().replace('"', '')
    except Exception as e:
        add_sys_log(bot_name, "AI_ERROR", str(e))
        return random.choice(["Haa bhai sahi hai", "Hmm", "Aur bata", "Sahi h"])

# =============================================================================
# ROBUST WEBSOCKET CLIENT CLASS
# =============================================================================
class TitanChatBot:
    def __init__(self, username, password, room, partner, personality, start_convo=False):
        self.username = username
        self.password = password
        self.room = room
        self.partner = partner
        self.personality = personality
        self.is_starter = start_convo
        
        self.ws = None
        self.token = ""
        self.room_id = ""
        self.active = False
        self.status = "OFFLINE"
        self.msg_history = []
        self.ua = random.choice(MOBILE_UAS)

    def login_sequence(self):
        self.active = True
        while self.active:
            try:
                self.status = "AUTHENTICATING"
                resp = requests.post("https://api.howdies.app/api/login", 
                                     json={"username": self.username, "password": self.password}, 
                                     headers={"User-Agent": self.ua}, timeout=15)
                
                auth_data = resp.json()
                self.token = auth_data.get("token") or auth_data.get("data", {}).get("token")
                
                if self.token:
                    self.status = "WS_CONNECTING"
                    add_sys_log(self.username, "AUTH", "Token obtained successfully")
                    self.init_socket()
                else:
                    self.status = "AUTH_FAILED"
                    add_sys_log(self.username, "AUTH_ERR", "Invalid credentials or API changed")
            except Exception as e:
                add_sys_log(self.username, "CONN_ERR", str(e))
            
            if self.active:
                self.status = "RETRYING"
                time.sleep(15)

    def init_socket(self):
        ws_url = f"wss://app.howdies.app/howdies?token={self.token}"
        self.ws = websocket.WebSocketApp(
            ws_url,
            header={"User-Agent": self.ua, "Origin": "https://howdies.app"},
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    def on_open(self, ws):
        self.status = "CONNECTED"
        add_sys_log(self.username, "SOCKET", "Connection established")
        # Auth packet
        ws.send(json.dumps({"handler": "login", "username": self.username, "password": self.password}))
        time.sleep(1.5)
        # Join room
        ws.send(json.dumps({"handler": "joinchatroom", "id": str(time.time()), "name": self.room, "roomPassword": ""}))
        # Heartbeat
        threading.Thread(target=self.keep_alive, daemon=True).start()

    def keep_alive(self):
        while self.ws and self.ws.sock and self.ws.sock.connected:
            time.sleep(25)
            try: self.ws.send(json.dumps({"handler": "ping"}))
            except: break

    def on_message(self, ws, msg):
        try:
            data = json.loads(msg)
            
            if data.get("handler") == "joinchatroom" and data.get("roomid"):
                self.room_id = data["roomid"]
                self.status = "ONLINE"
                add_sys_log(self.username, "ROOM", f"In Room: {self.room_id}")
                if self.is_starter:
                    threading.Timer(8.0, self.auto_start_chat).start()

            if data.get("handler") in ["chatroommessage", "message"]:
                sender = data.get("from") or data.get("username")
                text = data.get("text") or data.get("body")
                
                if not sender or not text or sender == self.username: return
                
                add_chat_log(sender, text)
                
                # Logic: Reply if Partner spoke, if mentioned, or random 20% room awareness
                is_partner = (sender.lower() == self.partner.lower())
                is_mentioned = (self.username.lower() in text.lower())
                random_butt_in = (random.random() < 0.20)

                if is_partner or is_mentioned or random_butt_in:
                    self.msg_history.append(f"{sender}: {text}")
                    if len(self.msg_history) > 20: self.msg_history.pop(0)
                    threading.Thread(target=self.human_like_reply, args=(sender, text)).start()
        except: pass

    def auto_start_chat(self):
        options = ["Aur bhai kya scene?", f"Oye {self.partner} sunna", "Kya haal h doston?", "Bore ho rha hu bhot"]
        self.dispatch_msg(random.choice(options))

    def human_like_reply(self, sender, text):
        # 1. Reading delay (1.5s to 4s)
        time.sleep(random.uniform(2.0, 4.5))
        
        reply_content = fetch_ai_reply(self.msg_history, self.username, self.partner, sender, self.personality)
        
        # 2. Typing indicator simulation
        self.set_typing(True)
        # Type speed (0.1s per char + random thinking time)
        typing_duration = (len(reply_content) * 0.08) + random.uniform(0.8, 2.0)
        time.sleep(typing_duration)
        
        # 3. Final Send
        self.dispatch_msg(reply_content)
        self.set_typing(False)

    def set_typing(self, active):
        try:
            rid = self.room_id if self.room_id else self.room
            self.ws.send(json.dumps({"handler": "typing", "roomid": rid, "status": active}))
        except: pass

    def dispatch_msg(self, text):
        if not self.ws or not self.ws.sock or not self.ws.sock.connected: return
        rid = self.room_id if self.room_id else self.room
        try:
            self.ws.send(json.dumps({
                "handler": "chatroommessage", "id": str(time.time()),
                "type": "text", "roomid": rid, "text": text
            }))
            add_chat_log(self.username, text)
            self.msg_history.append(f"{self.username}: {text}")
        except Exception as e:
            add_sys_log(self.username, "SEND_ERR", str(e))

    def on_error(self, ws, error):
        add_sys_log(self.username, "WS_ERROR", str(error))

    def on_close(self, ws, code, msg):
        self.status = "DISCONNECTED"
        add_sys_log(self.username, "WS_CLOSE", f"Code: {code}")

    def stop(self):
        self.active = False
        if self.ws: self.ws.close()

# =============================================================================
# FLASK WEB INTERFACE
# =============================================================================
@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_UI)

@app.route('/api/launch', methods=['POST'])
def launch_bots():
    d = request.json
    u1, u2, p, r = d['u1'], d['u2'], d['p'], d['r']
    
    # Cleanup existing
    if BOT_INSTANCES["A"]: BOT_INSTANCES["A"].stop()
    if BOT_INSTANCES["B"]: BOT_INSTANCES["B"].stop()
    
    # Init
    BOT_INSTANCES["A"] = TitanChatBot(u1, p, r, u2, "vibe", start_convo=True)
    BOT_INSTANCES["B"] = TitanChatBot(u2, p, r, u1, "chill", start_convo=False)
    
    # Threaded start
    threading.Thread(target=BOT_INSTANCES["A"].login_sequence, daemon=True).start()
    time.sleep(5)
    threading.Thread(target=BOT_INSTANCES["B"].login_sequence, daemon=True).start()
    
    return jsonify({"msg": "Bots launching..."})

@app.route('/api/kill')
def kill_bots():
    if BOT_INSTANCES["A"]: BOT_INSTANCES["A"].stop()
    if BOT_INSTANCES["B"]: BOT_INSTANCES["B"].stop()
    return "All bots terminated."

@app.route('/api/stream')
def get_stream():
    return jsonify({
        "status_a": BOT_INSTANCES["A"].status if BOT_INSTANCES["A"] else "OFFLINE",
        "status_b": BOT_INSTANCES["B"].status if BOT_INSTANCES["B"] else "OFFLINE",
        "chats": CHAT_HISTORY_GLOBAL[::-1][:50],
        "logs": SYSTEM_LOGS[::-1][:30]
    })

# =============================================================================
# HIGH-DENSITY DASHBOARD UI (DARK THEME)
# =============================================================================
DASHBOARD_UI = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TITAN DUO-CHAT PRO</title>
    <style>
        body { background: #0a0a0a; color: #00ff41; font-family: 'Consolas', monospace; margin: 0; padding: 20px; }
        .wrapper { max-width: 900px; margin: auto; border: 1px solid #333; background: #111; padding: 25px; box-shadow: 0 0 30px rgba(0,255,65,0.1); }
        .header { text-align: center; border-bottom: 2px solid #333; margin-bottom: 20px; padding-bottom: 10px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .input-group { margin-bottom: 15px; }
        input { width: 100%; padding: 12px; background: #000; border: 1px solid #00ff41; color: #fff; box-sizing: border-box; }
        button { width: 100%; padding: 15px; background: #00ff41; color: #000; border: none; font-weight: bold; cursor: pointer; text-transform: uppercase; margin-bottom: 10px; }
        button:hover { background: #00cc33; }
        .kill-btn { background: #ff0000; color: #fff; }
        .status-header { display: flex; justify-content: space-between; font-weight: bold; padding: 10px; background: #000; border: 1px solid #333; margin-bottom: 15px; }
        .pane { height: 250px; overflow-y: scroll; background: #000; border: 1px solid #222; padding: 10px; font-size: 13px; margin-top: 10px; }
        .log-line { border-bottom: 1px solid #111; padding: 3px 0; }
        .ts { color: #888; font-size: 11px; }
        .user { font-weight: bold; color: #00ff41; }
        h2 { margin: 0; text-transform: uppercase; letter-spacing: 5px; }
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="header">
            <h2>TITAN DUO-CHAT SYSTEM</h2>
        </div>
        <div class="status-header">
            <span>BOT_A: <span id="sa" style="color:#fff">OFFLINE</span></span>
            <span>BOT_B: <span id="sb" style="color:#fff">OFFLINE</span></span>
        </div>
        <div class="grid">
            <div class="input-group">
                <input id="u1" placeholder="Bot A Username">
                <input id="u2" placeholder="Bot B Username">
            </div>
            <div class="input-group">
                <input id="p" type="password" placeholder="Common Password">
                <input id="r" placeholder="Room Name">
            </div>
        </div>
        <button onclick="control('launch')">INITIALIZE PROTOCOL</button>
        <button class="kill-btn" onclick="control('kill')">TERMINATE ALL SESSIONS</button>

        <div style="font-size: 12px; margin-top: 20px;">LIVE CHAT FEED:</div>
        <div class="pane" id="chats"></div>
        
        <div style="font-size: 12px; margin-top: 15px;">SYSTEM DEBUG CONSOLE:</div>
        <div class="pane" id="logs" style="color: #888; height: 120px;"></div>
    </div>

    <script>
        function control(act) {
            if(act === 'kill') { fetch('/api/kill').then(() => alert("All Bots Terminated")); return; }
            const payload = {
                u1: document.getElementById('u1').value,
                u2: document.getElementById('u2').value,
                p: document.getElementById('p').value,
                r: document.getElementById('r').value
            };
            fetch('/api/launch', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
        }
        setInterval(() => {
            fetch('/api/stream').then(r => r.json()).then(d => {
                document.getElementById('sa').innerText = d.status_a;
                document.getElementById('sb').innerText = d.status_b;
                document.getElementById('chats').innerHTML = d.chats.map(c => 
                    `<div class="log-line"><span class="ts">[${c.t}]</span> <span class="user">${c.u}:</span> ${c.m}</div>`
                ).join('');
                document.getElementById('logs').innerHTML = d.logs.map(l => 
                    `<div class="log-line">${l}</div>`
                ).join('');
            });
        }, 2000);
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
