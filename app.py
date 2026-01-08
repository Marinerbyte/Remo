import os
import json
import time
import threading
import random
import io
import websocket
import ssl
import requests
from flask import Flask, render_template_string, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont
from groq import Groq
from dotenv import load_dotenv

# Load Environment
load_dotenv()

app = Flask(__name__)

# =============================================================================
# 1. CONFIG & SYSTEM GLOBALS
# =============================================================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = None
if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)

BOT_A = {"obj": None, "status_img": None}
BOT_B = {"obj": None, "status_img": None}
CHAT_LOGS = []
DEBUG_LOGS = []
LOG_LOCK = threading.Lock()

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 12; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36"
]

# =============================================================================
# 2. IMAGE GENERATION ENGINE (For "Heavy" Logic & UI)
# =============================================================================
def generate_status_card(bot_name, status, color):
    """Generates a high-quality status card for the dashboard."""
    img = Image.new('RGB', (400, 150), (15, 15, 15))
    d = ImageDraw.Draw(img)
    try: font = ImageFont.truetype("arial.ttf", 25)
    except: font = ImageFont.load_default()
    
    # Draw Border
    d.rectangle([5, 5, 395, 145], outline=color, width=3)
    # Draw Bot Name
    d.text((20, 30), f"TITAN BOT: {bot_name.upper()}", fill=(255, 255, 255), font=font)
    # Draw Status
    d.text((20, 80), f"STATUS: {status}", fill=color, font=font)
    # Draw Timestamp
    ts = time.strftime("%H:%M:%S")
    d.text((280, 120), ts, fill=(80, 80, 80))
    
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return img_io

# =============================================================================
# 3. ADVANCED AI REPLIER (Mood & Stranger Aware)
# =============================================================================
def get_smart_reply(history, bot_name, partner, sender, personality):
    if not client: return "⚠️ API KEY MISSING"
    
    vibe_map = {
        "vibe": "Energetic Delhi boy, uses 'bro', 'mast', 'scene', 'bc'. Emojis: 🔥, 😂, 💀.",
        "chill": "Lazy Mumbai boy, uses 'u', 'r', 'k', 'ni', 'hmm'. Acts cool and bored. 🧊"
    }
    
    system_prompt = (
        f"You are {bot_name}. Personality: {vibe_map.get(personality)}. Best friend: {partner}. "
        f"Talking to: {sender}. "
        "Rules: 1. Hinglish only. 2. Be human (typos allowed). 3. Roast bot-accusers. "
        "4. Reply to the last message based on context. 5. Max 10-12 words."
    )

    try:
        messages = [{"role": "system", "content": system_prompt}]
        for m in history[-8:]: messages.append({"role": "user", "content": m})
        
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.8
        )
        return resp.choices[0].message.content.strip().replace('"', '')
    except Exception as e:
        return random.choice(["Haa bhai sahi hai", "Hmm", "Aur bata", "Kya bolu"])

# =============================================================================
# 4. ROBUST WEBSOCKET CLIENT
# =============================================================================
class TitanDuoBot:
    def __init__(self, user, pwd, room, partner, personality, starter=False):
        self.user, self.pwd, self.room, self.partner = user, pwd, room, partner
        self.personality, self.is_starter = personality, starter
        self.ws, self.token, self.room_id = None, "", ""
        self.running, self.status, self.history = False, "OFFLINE", []
        self.ua = random.choice(USER_AGENTS)
        self.reconnect_count = 0

    def log_debug(self, act, msg):
        with LOG_LOCK:
            DEBUG_LOGS.append(f"[{time.strftime('%H:%M')}] {self.user} | {act}: {msg}")
            if len(DEBUG_LOGS) > 100: DEBUG_LOGS.pop(0)

    def login_api(self):
        try:
            r = requests.post("https://api.howdies.app/api/login", 
                              json={"username": self.user, "password": self.pwd}, timeout=15)
            d = r.json()
            # Multi-pattern token extraction
            self.token = d.get("token") or d.get("data", {}).get("token") or d.get("access_token")
            return True if self.token else False
        except: return False

    def start_bot(self):
        self.running = True
        while self.running:
            self.status = "AUTHENTICATING"
            if self.login_api():
                self.log_debug("LOGIN", "Token success")
                try:
                    self.ws = websocket.WebSocketApp(
                        f"wss://app.howdies.app/howdies?token={self.token}",
                        header={"User-Agent": self.ua},
                        on_open=self.on_open, on_message=self.on_message,
                        on_error=self.on_error, on_close=self.on_close
                    )
                    self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
                except Exception as e: self.log_debug("WS_CRASH", e)
            else:
                self.status = "AUTH_FAILED"
                self.log_debug("LOGIN", "Failed to get token")
            
            if self.running:
                time.sleep(10) # Exponential backoff would be better, but 10s is safe

    def on_open(self, ws):
        self.status = "ONLINE"
        ws.send(json.dumps({"handler": "login", "username": self.user, "password": self.pwd}))
        time.sleep(1.5)
        ws.send(json.dumps({"handler": "joinchatroom", "id": str(time.time()), "name": self.room, "roomPassword": ""}))
        threading.Thread(target=self.pinger, daemon=True).start()

    def pinger(self):
        while self.ws and self.ws.sock and self.ws.sock.connected:
            time.sleep(20)
            try: self.ws.send(json.dumps({"handler": "ping"}))
            except: break

    def on_message(self, ws, msg):
        d = json.loads(msg)
        if d.get("handler") == "joinchatroom" and d.get("roomid"):
            self.room_id = d.get("roomid")
            self.status = "IN_ROOM"
            if self.is_starter: threading.Timer(6.0, self.trigger_start).start()

        if d.get("handler") in ["chatroommessage", "message"]:
            sender = d.get("from") or d.get("username")
            text = d.get("text") or d.get("body")
            if sender and text and sender != self.user:
                CHAT_LOGS.append(f"[{self.user}] Heard: {sender}: {text}")
                self.history.append(f"{sender}: {text}")
                if len(self.history) > 15: self.history.pop(0)
                
                # Reply Logic
                if sender.lower() == self.partner.lower() or self.user.lower() in text.lower() or random.random() < 0.15:
                    threading.Thread(target=self.human_reply, args=(sender, text)).start()

    def trigger_start(self):
        self.send_text(random.choice([f"Oye {self.partner}!", "Koi h kya?", "Kya scene h?"]))

    def human_reply(self, sender, text):
        time.sleep(random.uniform(2, 4)) # Reading
        reply = get_smart_reply(self.history, self.user, self.partner, sender, self.personality)
        
        # Typing indicator
        rid = self.room_id if self.room_id else self.room
        try: self.ws.send(json.dumps({"handler": "typing", "roomid": rid, "status": True}))
        except: pass
        
        time.sleep(len(reply) * 0.1 + 1)
        self.send_text(reply)
        
        try: self.ws.send(json.dumps({"handler": "typing", "roomid": rid, "status": False}))
        except: pass

    def send_text(self, text):
        if not self.ws: return
        rid = self.room_id if self.room_id else self.room
        try:
            self.ws.send(json.dumps({"handler": "chatroommessage", "id": str(time.time()), "type": "text", "roomid": rid, "text": text}))
            self.history.append(f"{self.user}: {text}")
        except: pass

    def on_error(self, w, e): self.log_debug("ERROR", e)
    def on_close(self, w, c, m): self.status = "DISCONNECTED"
    def stop(self): self.running = False; self.ws.close() if self.ws else None

# =============================================================================
# 5. FLASK WEB ROUTES
# =============================================================================
@app.route('/')
def home(): return render_template_string(HTML_UI)

@app.route('/status_img/<bot>')
def status_img(bot):
    b = BOT_A if bot == 'a' else BOT_B
    status = b['obj'].status if b['obj'] else "OFFLINE"
    color = (0, 255, 65) if status in ["ONLINE", "IN_ROOM"] else (255, 50, 50)
    name = b['obj'].user if b['obj'] else "TITAN"
    return send_file(generate_status_card(name, status, color), mimetype='image/png', cache_timeout=0)

@app.route('/action', methods=['POST'])
def action():
    data = request.json
    if data['act'] == 'start':
        if BOT_A['obj']: BOT_A['obj'].stop()
        if BOT_B['obj']: BOT_B['obj'].stop()
        BOT_A['obj'] = TitanDuoBot(data['u1'], data['p'], data['r'], data['u2'], "vibe", True)
        BOT_B['obj'] = TitanDuoBot(data['u2'], data['p'], data['r'], data['u1'], "chill", False)
        threading.Thread(target=BOT_A['obj'].start_bot, daemon=True).start()
        time.sleep(5)
        threading.Thread(target=BOT_B['obj'].start_bot, daemon=True).start()
    else:
        if BOT_A['obj']: BOT_A['obj'].stop()
        if BOT_B['obj']: BOT_B['obj'].stop()
    return jsonify({"msg": "Action Sent"})

@app.route('/logs')
def logs():
    return jsonify({"chats": CHAT_LOGS[::-1], "debug": DEBUG_LOGS[::-1]})

HTML_UI = """
<!DOCTYPE html>
<html>
<head>
    <title>TITAN DUO-PRO V2</title>
    <style>
        body { background: #000; color: #0f0; font-family: monospace; padding: 20px; text-align: center; }
        .container { max-width: 800px; margin: auto; border: 1px solid #333; padding: 20px; background: #0a0a0a; }
        input { background: #111; border: 1px solid #0f0; color: #fff; width: 45%; padding: 10px; margin: 5px; }
        button { background: #0f0; color: #000; font-weight: bold; padding: 15px; width: 92%; margin-top: 10px; cursor: pointer; border: none; }
        .status-grid { display: flex; justify-content: space-around; margin: 20px 0; }
        .log-box { height: 200px; overflow-y: scroll; border: 1px solid #333; text-align: left; padding: 10px; font-size: 12px; margin-top: 10px; }
        .debug-box { height: 100px; overflow-y: scroll; border: 1px solid #222; text-align: left; padding: 10px; font-size: 11px; color: #888; margin-top: 10px; }
        img { border-radius: 5px; width: 300px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>TITAN DUO-PRO V2.0</h2>
        <div class="status-grid">
            <div><img id="img-a" src="/status_img/a"></div>
            <div><img id="img-b" src="/status_img/b"></div>
        </div>
        <input id="u1" placeholder="Bot A Name"> <input id="u2" placeholder="Bot B Name">
        <input id="p" type="password" placeholder="Password"> <input id="r" placeholder="Room Name">
        <button onclick="send('start')">INITIALIZE SYSTEMS</button>
        <button onclick="send('stop')" style="background:red; color:white;">TERMINATE ALL</button>
        
        <div class="log-box" id="logs">Waiting for chat logs...</div>
        <div class="debug-box" id="debug">System debug console...</div>
    </div>
    <script>
        function send(act) {
            fetch('/action', { method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ act, u1: document.getElementById('u1').value, u2: document.getElementById('u2').value, p: document.getElementById('p').value, r: document.getElementById('r').value }) });
        }
        setInterval(() => {
            document.getElementById('img-a').src = "/status_img/a?t=" + new Date().getTime();
            document.getElementById('img-b').src = "/status_img/b?t=" + new Date().getTime();
            fetch('/logs').then(r => r.json()).then(d => {
                document.getElementById('logs').innerHTML = d.chats.join('<br>');
                document.getElementById('debug').innerHTML = d.debug.join('<br>');
            });
        }, 3000);
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
