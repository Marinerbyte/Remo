import os
import json
import time
import threading
import random
import websocket
import ssl
import requests
from flask import Flask, render_template_string, request, jsonify
from groq import Groq

app = Flask(__name__)

# =============================================================================
# CONFIG & GLOBALS
# =============================================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = None
if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)

BOTS = {}
BOT_LOCK = threading.Lock()
CHAT_LOGS = []

# Mobile User Agents (To look like Real Phones)
USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.74 Mobile Safari/537.36"
]

# =============================================================================
# INTELLIGENT AI ENGINE
# =============================================================================
def get_ai_reply(incoming_text, sender_name, history, bot_name, partner_name, personality_type):
    """
    Decides reply based on mood, context and emoji probability.
    """
    if not client: return "Bhai API Key missing hai."

    # --- 1. Personality Setup ---
    if personality_type == "vibe":
        base_prompt = (
            f"You are {bot_name}, a 21-year-old Gen-Z Indian boy from Delhi. "
            "You are energetic, use slangs like 'bhai', 'scene', 'gazab', 'lol'. "
        )
    else:
        base_prompt = (
            f"You are {bot_name}, a chill and slightly lazy guy from Mumbai. "
            "You speak in short sentences. You use 'u' instead of 'you', 'r' instead of 'are'. "
        )

    # --- 2. Dynamic Emoji Logic ---
    # Hum AI ko bolenge ki wo khud decide kare mood ke hisab se
    emoji_instruction = (
        "EMOJI RULES: "
        "1. Do NOT use emojis in every message. Keep it natural (approx 40% chance). "
        "2. Match the emoji to the vibe: "
        "   - Funny: 😂, 🤣, 💀 "
        "   - Agreeing: 🙌, 💯, ✅ "
        "   - Shocked/Serious: 😳, 😶 "
        "   - Flirting/Cool: 😉, 😎, 🔥 "
        "3. If the user is serious, DO NOT use laughing emojis."
    )

    # --- 3. Context & Defense Mechanism ---
    system_prompt = (
        f"{base_prompt} "
        f"Your best friend is {partner_name}. "
        f"You are talking to {sender_name}. "
        f"{emoji_instruction} "
        "BEHAVIOR: "
        "1. If someone calls you a BOT, roast them comfortably. Deny it. "
        "2. Keep replies Hinglish (Hindi + English). "
        "3. Reply length: Short (under 15 words). "
        "4. If {partner_name} insults you, insult them back playfully."
    )

    try:
        # Chat History Context
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history[-6:]: 
            messages.append({"role": "user", "content": msg})
        
        # Current Message
        messages.append({"role": "user", "content": f"{sender_name}: {incoming_text}"})

        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.85, # Thoda high taaki creative ho
            max_tokens=100
        )
        return completion.choices[0].message.content.replace('"', '').strip()
    except Exception as e:
        return random.choice(["Haa bhai", "Sahi baat h", "Lol", "Kya bolu ab"])

# =============================================================================
# BOT CORE
# =============================================================================
class ChatBot:
    def __init__(self, username, password, room, partner_name, personality):
        self.username = username
        self.password = password
        self.room = room
        self.partner_name = partner_name
        self.personality = personality
        self.token = ""
        self.room_id = ""
        self.ws = None
        self.running = False
        self.status = "OFFLINE"
        self.ua = random.choice(USER_AGENTS)
        self.history = []

    def log(self, msg):
        ts = time.strftime("%H:%M")
        CHAT_LOGS.append(f"[{ts}] {self.username}: {msg}")
        if len(CHAT_LOGS) > 50: CHAT_LOGS.pop(0)

    def login(self):
        self.status = "LOGGING IN..."
        try:
            # Login Request
            r = requests.post("https://api.howdies.app/api/login", 
                              json={"username": self.username, "password": self.password}, timeout=10)
            d = r.json()
            
            # Smart Token Extractor (Handles different API responses)
            self.token = d.get("token") or d.get("data", {}).get("token")
            
            if self.token:
                self.status = "CONNECTING..."
                threading.Thread(target=self.connect_ws, daemon=True).start()
            else:
                self.status = "BAD AUTH"
        except: 
            self.status = "NET ERROR"

    def connect_ws(self):
        # Headers mimic a real browser/phone
        headers = {"User-Agent": self.ua, "Origin": "https://howdies.app"}
        self.ws = websocket.WebSocketApp(
            f"wss://app.howdies.app/howdies?token={self.token}",
            header=headers,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=lambda w,e: self.log(f"Err: {e}"),
            on_close=self.on_close
        )
        self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    def on_open(self, ws):
        self.running = True
        self.status = "ONLINE"
        # Auth Packet
        ws.send(json.dumps({"handler": "login", "username": self.username, "password": self.password}))
        time.sleep(1)
        # Join Room
        ws.send(json.dumps({"handler": "joinchatroom", "id": str(time.time()), "name": self.room, "roomPassword": ""}))
        # Keep Alive
        threading.Thread(target=self.pinger, daemon=True).start()

    def pinger(self):
        while self.running and self.ws.sock and self.ws.sock.connected:
            time.sleep(20)
            try: self.ws.send(json.dumps({"handler": "ping"}))
            except: break

    def send_typing(self, active=True):
        """Sends 'Typing...' status to room"""
        try:
            rid = self.room_id if self.room_id else self.room
            self.ws.send(json.dumps({"handler": "typing", "roomid": rid, "status": active}))
        except: pass

    def send_msg_human_like(self, text):
        if not self.ws: return
        rid = self.room_id if self.room_id else self.room
        
        # 1. Reading Time (Human reads previous msg)
        time.sleep(random.uniform(1.5, 3.5))
        
        # 2. Typing Time (Based on length)
        self.send_typing(True)
        # 0.1s per char + random thinking time
        typing_duration = (len(text) * 0.1) + random.uniform(0.5, 1.5)
        time.sleep(typing_duration)
        
        # 3. Send
        try:
            pkt = {"handler": "chatroommessage", "id": str(time.time()), "type": "text", "roomid": rid, "text": text}
            self.ws.send(json.dumps(pkt))
            self.send_typing(False)
            self.log(f"Sent: {text}")
            self.history.append(f"{self.username}: {text}")
        except: pass

    def on_message(self, ws, msg):
        try:
            d = json.loads(msg)
            # Capture Room ID
            if d.get("handler") == "joinchatroom" and d.get("roomid"):
                self.room_id = d.get("roomid")
            
            # Listen to Chat
            if d.get("handler") in ["chatroommessage", "message"]:
                sender = d.get("from") or d.get("username")
                text = d.get("text") or d.get("body")
                
                if not sender or not text or sender == self.username: return
                
                # --- TRIGGER LOGIC ---
                is_partner = (sender.lower() == self.partner_name.lower())
                is_mentioned = (self.username.lower() in text.lower())
                is_stranger = not is_partner
                
                # Decide to Reply
                should_reply = False
                
                if is_partner: 
                    should_reply = True # Always reply to partner
                elif is_mentioned:
                    should_reply = True # Always reply if mentioned
                elif is_stranger and random.random() < 0.15: 
                    should_reply = True # 15% chance to butt in randomly

                if should_reply:
                    # Save context
                    self.history.append(f"{sender}: {text}")
                    if len(self.history) > 10: self.history.pop(0)
                    
                    # Process in background (so WS doesn't freeze)
                    threading.Thread(target=self.process_and_reply, args=(text, sender)).start()
        except: pass

    def process_and_reply(self, text, sender):
        # Extra delay if interrupting a stranger
        if sender != self.partner_name: time.sleep(random.uniform(1, 3))
        
        reply = get_ai_reply(text, sender, self.history, self.username, self.partner_name, self.personality)
        self.send_msg_human_like(reply)

    def on_close(self, w, c, m):
        self.status = "OFFLINE"
        self.running = False

    def stop(self):
        self.running = False
        if self.ws: self.ws.close()

# =============================================================================
# WEB INTERFACE
# =============================================================================
@app.route('/')
def home(): return render_template_string(HTML_UI)

@app.route('/action', methods=['POST'])
def action():
    data = request.json
    act = data.get('act')
    
    if act == 'start':
        u1, u2, p, r = data['u1'], data['u2'], data['p'], data['r']
        with BOT_LOCK:
            for b in BOTS.values(): b.stop()
            BOTS.clear()
            # Bot 1 (Vibe)
            BOTS['b1'] = ChatBot(u1, p, r, u2, "vibe")
            # Bot 2 (Chill)
            BOTS['b2'] = ChatBot(u2, p, r, u1, "chill")
            
            BOTS['b1'].login()
            time.sleep(3) # Stagger login
            BOTS['b2'].login()
            
            # Start conversation trigger
            threading.Timer(8, lambda: BOTS['b1'].send_msg_human_like(f"Oye {u2}, kidhar reh gaya?")).start()
            
        return jsonify({"msg": "Bots Started!"})

    elif act == 'stop':
        with BOT_LOCK:
            for b in BOTS.values(): b.stop()
        return jsonify({"msg": "Bots Stopped!"})

@app.route('/stats')
def stats():
    s = {k: v.status for k,v in BOTS.items()}
    return jsonify({"status": s, "logs": CHAT_LOGS[::-1]})

HTML_UI = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>TITAN AI CHAT</title>
    <style>
        body { background: #000; color: #0f0; font-family: 'Courier New', monospace; padding: 20px; }
        .box { border: 1px solid #0f0; padding: 20px; max-width: 500px; margin: auto; }
        input { background: #111; border: 1px solid #0f0; color: #fff; width: 100%; padding: 10px; margin: 5px 0; box-sizing: border-box; }
        button { background: #0f0; color: #000; padding: 10px; width: 48%; border: none; font-weight: bold; cursor: pointer; margin-top: 10px; }
        .stop { background: #f00; color: #fff; }
        #logs { height: 300px; overflow-y: scroll; border-top: 1px solid #333; margin-top: 20px; font-size: 12px; color: #fff; }
        .st-row { margin-bottom: 5px; }
    </style>
</head>
<body>
    <div class="box">
        <h2 style="text-align:center">TITAN V2.0</h2>
        <input id="u1" placeholder="Bot 1 Username (The Vibe)">
        <input id="u2" placeholder="Bot 2 Username (The Chill)">
        <input id="p" type="password" placeholder="Password">
        <input id="r" placeholder="Room Name">
        
        <div style="display:flex; justify-content:space-between">
            <button onclick="doAct('start')">CONNECT</button>
            <button class="stop" onclick="doAct('stop')">DISCONNECT</button>
        </div>

        <div style="margin-top:15px; text-align:center">
            <div id="s1" class="st-row">Bot 1: WAIT</div>
            <div id="s2" class="st-row">Bot 2: WAIT</div>
        </div>

        <div id="logs">Waiting for logs...</div>
    </div>
    <script>
        function doAct(a) {
            fetch('/action', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({
                    act:a, u1:document.getElementById('u1').value, 
                    u2:document.getElementById('u2').value, 
                    p:document.getElementById('p').value, r:document.getElementById('r').value
                })
            }).then(r=>r.json()).then(d=>alert(d.msg));
        }
        setInterval(() => {
            fetch('/stats').then(r=>r.json()).then(d => {
                document.getElementById('s1').innerText = "Bot 1: " + (d.status.b1 || 'OFF');
                document.getElementById('s2').innerText = "Bot 2: " + (d.status.b2 || 'OFF');
                document.getElementById('logs').innerHTML = d.logs.join('<br>');
            });
        }, 2000);
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
