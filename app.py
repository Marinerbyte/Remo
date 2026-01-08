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

# =============================================================================
# 1. INITIALIZATION & CONFIG
# =============================================================================
app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = None
if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)

# Storage for both bots
BOT_INSTANCES = {
    "bot1": {"obj": None, "config": {}},
    "bot2": {"obj": None, "config": {}}
}

CHAT_LOGS = []
DEBUG_LOGS = []

def add_log(user, msg):
    ts = time.strftime("%H:%M:%S")
    CHAT_LOGS.append({"time": ts, "user": user, "text": msg})
    if len(CHAT_LOGS) > 100: CHAT_LOGS.pop(0)

def add_debug(direction, payload):
    ts = time.strftime("%H:%M:%S")
    DEBUG_LOGS.append({"time": ts, "dir": direction, "data": str(payload)})
    if len(DEBUG_LOGS) > 100: DEBUG_LOGS.pop(0)

# =============================================================================
# 2. AI ENGINE (Hinglish + Emoji)
# =============================================================================
def generate_ai_response(history, bot_name, partner, personality):
    if not groq_client:
        return "Bhai Groq key check kar lo."

    # Personality logic
    vibe = "Delhi ka cool ladka, slang use karta hai (bc, bro, scene, mast)." if personality == "vibe" else "Mumbai ka chill banda, short words (u, r, k, ni) use karta hai."
    
    system_prompt = (
        f"You are {bot_name} in a chatroom. Your best friend is {partner}. {vibe} "
        "Instructions: "
        "1. Talk in Hinglish (Hindi + English). "
        "2. Keep it human. Use typos like 'h' for 'hai', 'kya kr rha' instead of 'kya kar rahe ho'. "
        "3. Use emojis ONLY when the mood matches (😂 for funny, 💀 for roasting, 🔥 for cool). "
        "4. If someone calls you a bot, be sarcastic and prove them wrong. "
        "5. Respond to the LAST message based on the context of history. "
        "6. Max response length: 10-15 words."
    )

    try:
        messages = [{"role": "system", "content": system_prompt}]
        for m in history[-8:]:
            messages.append({"role": "user", "content": m})
        
        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.8
        )
        return completion.choices[0].message.content.strip().replace('"', '')
    except Exception as e:
        add_debug("AI_ERR", str(e))
        return random.choice(["Haa bhai sahi h", "Hmm", "Aur bata", "Sahi h"])

# =============================================================================
# 3. ROBUST BOT CLASS
# =============================================================================
class TitanBot:
    def __init__(self, username, password, room, partner, personality, is_starter=False):
        self.username = username
        self.password = password
        self.room = room
        self.partner = partner
        self.personality = personality
        self.is_starter = is_starter
        
        self.ws = None
        self.token = ""
        self.room_id = ""
        self.user_id = ""
        self.should_run = True
        self.status = "OFFLINE"
        self.history = []
        self.is_joined = False

    def login_api(self):
        url = "https://api.howdies.app/api/login"
        payload = {"username": self.username, "password": self.password}
        try:
            r = requests.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                data = r.json()
                self.token = data.get("token") or data.get("data", {}).get("token")
                self.user_id = data.get("id") or data.get("userId")
                return True
            return False
        except Exception as e:
            add_debug(self.username, f"Login API Fail: {e}")
            return False

    def start_thread(self):
        while self.should_run:
            self.status = "LOGGING IN..."
            if self.login_api():
                self.status = "CONNECTING..."
                ws_url = f"wss://app.howdies.app/howdies?token={self.token}"
                try:
                    self.ws = websocket.WebSocketApp(
                        ws_url,
                        on_open=self.on_open,
                        on_message=self.on_message,
                        on_error=self.on_error,
                        on_close=self.on_close
                    )
                    self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
                except Exception as e:
                    add_debug(self.username, f"WS Crash: {e}")
            
            if self.should_run:
                self.status = "RETRYING (10s)..."
                time.sleep(10)

    def on_open(self, ws):
        self.status = "ONLINE"
        # 1. Login Packet
        ws.send(json.dumps({"handler": "login", "username": self.username, "password": self.password}))
        time.sleep(1)
        # 2. Join Room
        ws.send(json.dumps({
            "handler": "joinchatroom", 
            "id": str(time.time()), 
            "name": self.room, 
            "roomPassword": ""
        }))
        # 3. Pinger
        threading.Thread(target=self.pinger, daemon=True).start()

    def pinger(self):
        while self.ws and self.ws.sock and self.ws.sock.connected:
            time.sleep(15)
            try: self.ws.send(json.dumps({"handler": "ping"}))
            except: break

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            add_debug(f"IN_{self.username}", data)
            
            # Capture Success Join
            if data.get("handler") == "joinchatroom" and data.get("roomid"):
                self.room_id = data["roomid"]
                self.is_joined = True
                self.status = "IN ROOM"
                if self.is_starter:
                    threading.Timer(5.0, self.initiate_chat).start()

            # Message Handling
            if data.get("handler") in ["chatroommessage", "message"]:
                sender = data.get("from") or data.get("username")
                text = data.get("text") or data.get("body")
                
                if sender and text and sender != self.username:
                    add_log(sender, text)
                    self.handle_logic(sender, text)
        except: pass

    def initiate_chat(self):
        starters = ["Oye " + self.partner + " kidhar h?", "Oye sun", "Aur " + self.partner + " kya scene?", "Hellooo"]
        self.send_text(random.choice(starters))

    def handle_logic(self, sender, text):
        # 1. Reply to partner
        is_partner = (sender.lower() == self.partner.lower())
        # 2. Reply to mention
        is_mentioned = (self.username.lower() in text.lower())
        # 3. Random interaction (10% chance)
        is_random = (random.random() < 0.10)

        if is_partner or is_mentioned or is_random:
            self.history.append(f"{sender}: {text}")
            if len(self.history) > 15: self.history.pop(0)
            
            threading.Thread(target=self.process_reply, args=(sender, text)).start()

    def process_reply(self, sender, text):
        # Human Reading Delay
        time.sleep(random.uniform(2, 4))
        
        reply = generate_ai_response(self.history, self.username, self.partner, self.personality)
        
        # Typing Simulation
        self.send_typing(True)
        time.sleep(len(reply) * 0.1 + random.uniform(1, 2))
        self.send_text(reply)
        self.send_typing(False)

    def send_typing(self, status):
        try:
            rid = self.room_id if self.room_id else self.room
            self.ws.send(json.dumps({"handler": "typing", "roomid": rid, "status": status}))
        except: pass

    def send_text(self, text):
        if not self.ws or not self.ws.sock or not self.ws.sock.connected: return
        rid = self.room_id if self.room_id else self.room
        try:
            pkt = {
                "handler": "chatroommessage",
                "id": str(time.time()),
                "type": "text",
                "roomid": rid,
                "text": text
            }
            self.ws.send(json.dumps(pkt))
            add_log(self.username, text)
            self.history.append(f"{self.username}: {text}")
        except: pass

    def on_error(self, ws, error):
        add_debug(self.username, f"WS_ERROR: {error}")

    def on_close(self, ws, close_code, close_msg):
        self.status = "DISCONNECTED"
        self.is_joined = False

    def stop(self):
        self.should_run = False
        if self.ws: self.ws.close()

# =============================================================================
# 4. FLASK DASHBOARD
# =============================================================================
@app.route('/')
def index():
    return render_template_string(HTML_UI)

@app.route('/control', methods=['POST'])
def control():
    data = request.json
    action = data.get("action")
    
    if action == "start":
        u1, u2, p, r = data['u1'], data['u2'], data['p'], data['r']
        
        # Cleanup
        for key in ["bot1", "bot2"]:
            if BOT_INSTANCES[key]["obj"]:
                BOT_INSTANCES[key]["obj"].stop()

        # Init Bots
        BOT_INSTANCES["bot1"]["obj"] = TitanBot(u1, p, r, u2, "vibe", is_starter=True)
        BOT_INSTANCES["bot2"]["obj"] = TitanBot(u2, p, r, u1, "chill", is_starter=False)
        
        # Run Threads
        threading.Thread(target=BOT_INSTANCES["bot1"]["obj"].start_thread, daemon=True).start()
        time.sleep(5) # Delay Bot 2 login
        threading.Thread(target=BOT_INSTANCES["bot2"]["obj"].start_thread, daemon=True).start()
        
        return jsonify({"status": "Launched"})

    elif action == "stop":
        for key in ["bot1", "bot2"]:
            if BOT_INSTANCES[key]["obj"]:
                BOT_INSTANCES[key]["obj"].stop()
        return jsonify({"status": "Stopped"})

@app.route('/status')
def get_status():
    stats = {}
    for key in ["bot1", "bot2"]:
        obj = BOT_INSTANCES[key]["obj"]
        stats[key] = obj.status if obj else "OFFLINE"
    
    return jsonify({
        "bots": stats,
        "logs": CHAT_LOGS[::-1][:30],
        "debug": DEBUG_LOGS[::-1][:20]
    })

HTML_UI = """
<!DOCTYPE html>
<html>
<head>
    <title>TITAN PRO V2</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background: #050505; color: #00ff41; font-family: monospace; padding: 20px; }
        .card { background: #111; border: 1px solid #333; padding: 20px; max-width: 600px; margin: auto; }
        input { width: 100%; padding: 10px; margin: 5px 0; background: #000; border: 1px solid #333; color: #fff; box-sizing: border-box; }
        button { width: 48%; padding: 12px; margin-top: 10px; cursor: pointer; font-weight: bold; }
        .btn-start { background: #00ff41; color: #000; border: none; }
        .btn-stop { background: #ff0000; color: #fff; border: none; }
        .log-container { background: #000; height: 250px; overflow-y: auto; border: 1px solid #222; margin-top: 15px; padding: 10px; font-size: 12px; }
        .debug-container { background: #000; height: 150px; overflow-y: auto; border: 1px solid #222; margin-top: 15px; padding: 10px; font-size: 10px; color: #aaa; }
        .status-badge { display: flex; justify-content: space-around; padding: 10px; font-size: 14px; border-bottom: 1px solid #333; }
    </style>
</head>
<body>
    <div class="card">
        <h2 style="text-align:center; color:#fff">TITAN DUO PRO V2</h2>
        <div class="status-badge">
            <span id="s1">BOT 1: OFFLINE</span>
            <span id="s2">BOT 2: OFFLINE</span>
        </div>
        <input id="u1" placeholder="Bot 1 (Vibe)">
        <input id="u2" placeholder="Bot 2 (Chill)">
        <input id="p" type="password" placeholder="Password">
        <input id="r" placeholder="Room Name">
        
        <div style="display:flex; justify-content:space-between">
            <button class="btn-start" onclick="send('start')">CONNECT ALL</button>
            <button class="btn-stop" onclick="send('stop')">DISCONNECT</button>
        </div>

        <div class="log-container" id="logs">Chat Logs...</div>
        <div class="debug-container" id="debug">Debug Console...</div>
    </div>

    <script>
        function send(action) {
            const data = {
                action: action,
                u1: document.getElementById('u1').value,
                u2: document.getElementById('u2').value,
                p: document.getElementById('p').value,
                r: document.getElementById('r').value
            };
            fetch('/control', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
        }

        setInterval(() => {
            fetch('/status').then(res => res.json()).then(data => {
                document.getElementById('s1').innerText = "BOT 1: " + data.bots.bot1;
                document.getElementById('s2').innerText = "BOT 2: " + data.bots.bot2;
                
                document.getElementById('logs').innerHTML = data.logs.map(l => 
                    `<div><span style="color:#888">[${l.time}]</span> <b>${l.user}:</b> ${l.text}</div>`
                ).join('');

                document.getElementById('debug').innerHTML = data.debug.map(d => 
                    `<div>[${d.time}] ${d.dir} -> ${d.data}</div>`
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
