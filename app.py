# ==============================================================================
# TITAN ULTIMATE BOT - V3.0 (MAX EDITION)
# FEATURES: Titan Game, Magic Trick, ID Card, Ship, Welcome Card, Smart AI, Memory
# DATABASE: PostgreSQL (Neon DB)
# ==============================================================================

import os
import json
import time
import threading
import io
import random
import requests
import websocket
import psycopg2  # PostgreSQL Database Driver
from flask import Flask, render_template_string, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

# ==============================================================================
# --- 1. SYSTEM CONFIGURATION & SETUP ---
# ==============================================================================

app = Flask(__name__)

# --- CONFIGURATION VARIABLES ---

# Neon Database Connection String (Sensitive Data)
DB_URL = "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

# Groq API Key for AI Brain (Set in Environment Variables for security)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "") 

# --- GLOBAL BOT STATE ---
# Stores temporary data that resets on restart (except DB data)
BOT_STATE = {
    "ws": None,             # WebSocket Object
    "connected": False,     # Connection Status
    "username": "",         # Bot Username
    "password": "",         # Bot Password
    "room_name": "",        # Target Room
    "domain": "",           # Server Domain for Image APIs
    "triggers": [],         # Custom Triggers (!addtg)
    "mode": "smart",        # Modes: 'smart', 'savage', 'habibi'
    "admin_id": "y"         # Admin Identifier
}

# --- GAME STATES ---
# Stores the current status of active games
TITAN_GAME = {
    "active": False,        # Is game running?
    "player": None,         # Who is playing?
    "bombs": [],            # Bomb locations (1-9)
    "eaten": [],            # Safe spots clicked
    "bet": 0,               # Points bet
    "cache_avatars": {},    # Avatar URL Cache (RAM)
    "magic_symbol": None    # Current Magic Trick Symbol
}

# --- AI MEMORY (Context Window) ---
# Stores last 10 messages for conversational context
AI_CONTEXT = []

# --- SYSTEM LOGGING ---
# Stores logs for the Web UI
SYSTEM_LOGS = []

def log(msg, type="info"):
    """Adds a log entry to the system"""
    timestamp = time.strftime("%H:%M:%S")
    entry = {"time": timestamp, "msg": msg, "type": type}
    SYSTEM_LOGS.append(entry)
    # Keep only last 200 logs to save RAM
    if len(SYSTEM_LOGS) > 200: SYSTEM_LOGS.pop(0)
    print(f"[{type.upper()}] {msg}")

# ==============================================================================
# --- 2. DATABASE MANAGEMENT (POSTGRESQL / NEON) ---
# ==============================================================================

def get_db_connection():
    """Establishes a connection to the Neon PostgreSQL Database"""
    try:
        conn = psycopg2.connect(DB_URL)
        return conn
    except Exception as e:
        log(f"DATABASE ERROR: Could not connect. {e}", "err")
        return None

def init_database():
    """Initializes all required tables in the database if they don't exist"""
    conn = get_db_connection()
    if not conn: return
    c = conn.cursor()
    
    # 1. Users Table: Stores Points, Wins, Losses, and Avatar URL
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, score INTEGER, wins INTEGER, losses INTEGER, avatar TEXT)''')
    
    # 2. Settings Table: Stores Permanent Bot Settings
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    # 3. Memory Table (AI Brain): Stores User Facts, Gender, and Relationship Score
    c.execute('''CREATE TABLE IF NOT EXISTS memory 
                 (username TEXT PRIMARY KEY, facts TEXT, gender TEXT, rel_score INTEGER)''')
    
    # 4. Greetings Table: Stores User's Custom Background URL
    c.execute('''CREATE TABLE IF NOT EXISTS greetings 
                 (username TEXT PRIMARY KEY, bg_url TEXT)''')
                 
    conn.commit()
    c.close()
    conn.close()
    log("Database Tables Checked/Initialized.", "sys")

# --- DATABASE HELPER FUNCTIONS ---

def db_update_user(username, points_change, win_increment=0, loss_increment=0, avatar=""):
    """Updates user score and stats safely"""
    conn = get_db_connection()
    if not conn: return
    c = conn.cursor()
    
    # Check if user exists
    c.execute("SELECT score, wins, losses FROM users WHERE username=%s", (username,))
    data = c.fetchone()
    
    if data:
        # Update Existing User
        new_score = data[0] + points_change
        new_wins = data[1] + win_increment
        new_loss = data[2] + loss_increment
        if new_score < 0: new_score = 0
        
        c.execute("UPDATE users SET score=%s, wins=%s, losses=%s, avatar=%s WHERE username=%s", 
                  (new_score, new_wins, new_loss, avatar, username))
    else:
        # Create New User
        start_score = points_change if points_change > 0 else 0
        c.execute("INSERT INTO users (username, score, wins, losses, avatar) VALUES (%s, %s, %s, %s, %s)", 
                  (username, start_score, win_increment, loss_increment, avatar))
    
    conn.commit()
    c.close()
    conn.close()

def db_get_balance(username):
    """Fetches user score"""
    conn = get_db_connection()
    if not conn: return 0
    c = conn.cursor()
    c.execute("SELECT score FROM users WHERE username=%s", (username,))
    data = c.fetchone()
    conn.close()
    return data[0] if data else 0

def db_get_leaderboard():
    """Fetches top 50 users for leaderboard"""
    conn = get_db_connection()
    if not conn: return []
    c = conn.cursor()
    c.execute("SELECT username, score, wins, avatar FROM users ORDER BY score DESC LIMIT 50")
    data = c.fetchall()
    conn.close()
    return data

# --- MEMORY & GREETING HELPERS ---

def db_get_memory(user):
    """Fetches AI Memory for a specific user"""
    conn = get_db_connection()
    if not conn: return "", "unknown", 0
    c = conn.cursor()
    c.execute("SELECT facts, gender, rel_score FROM memory WHERE username=%s", (user,))
    data = c.fetchone()
    conn.close()
    # Returns: (Facts String, Gender, Relationship Score)
    if data: return data[0], data[1], data[2]
    return "", "unknown", 0

def db_update_memory(user, fact=None, gender=None, rel_inc=0):
    """Updates AI Memory (Smart Logic to prevent duplicates)"""
    current_facts, current_gender, current_score = db_get_memory(user)
    
    new_facts = current_facts
    if fact:
        fact = fact.strip(" .")
        # Prevent duplicate facts
        if fact not in current_facts:
            new_facts = f"{current_facts} | {fact}".strip(" | ")
            # Limit memory size to 500 chars to save tokens
            if len(new_facts) > 500: new_facts = new_facts[-500:]
    
    new_gender = gender if gender else current_gender
    new_score = current_score + rel_inc
    if new_score > 100: new_score = 100 # Max Friendship Level
    
    conn = get_db_connection()
    if not conn: return
    c = conn.cursor()
    
    # Postgres UPSERT Logic
    c.execute("""
        INSERT INTO memory (username, facts, gender, rel_score) 
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (username) 
        DO UPDATE SET facts=EXCLUDED.facts, gender=EXCLUDED.gender, rel_score=EXCLUDED.rel_score
    """, (user, new_facts, new_gender, new_score))
    
    conn.commit()
    conn.close()

def db_set_bg(username, url):
    """Sets a custom background URL for Welcome Card"""
    conn = get_db_connection()
    if not conn: return
    c = conn.cursor()
    c.execute("""
        INSERT INTO greetings (username, bg_url) 
        VALUES (%s, %s)
        ON CONFLICT (username) 
        DO UPDATE SET bg_url=EXCLUDED.bg_url
    """, (username, url))
    conn.commit()
    conn.close()

def db_get_bg(username):
    """Gets user's background or default"""
    conn = get_db_connection()
    if not conn: return "https://wallpaperaccess.com/full/1567665.png"
    c = conn.cursor()
    c.execute("SELECT bg_url FROM greetings WHERE username=%s", (username,))
    data = c.fetchone()
    conn.close()
    return data[0] if data else "https://wallpaperaccess.com/full/1567665.png"

# Initialize Database on Start
init_database()

# ==============================================================================
# --- 3. ADVANCED GRAPHICS ENGINE (PIL) ---
# ==============================================================================

def download_image(url):
    """Downloads an image from URL and converts to RGBA"""
    try:
        if not url or "http" not in url: raise Exception("Invalid URL")
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=4)
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        return img
    except:
        # Fallback Grey Image
        return Image.new("RGBA", (200, 200), (50, 50, 50, 255))

def draw_gradient(draw, width, height, color1, color2):
    """Draws a vertical gradient on the canvas"""
    for y in range(height):
        r = int(color1[0] + (color2[0] - color1[0]) * y / height)
        g = int(color1[1] + (color2[1] - color1[1]) * y / height)
        b = int(color1[2] + (color2[2] - color1[2]) * y / height)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

# --- GENERATOR 1: SAUDI ID CARD ---
def generate_id_card(username, avatar_url):
    try:
        W, H = 600, 360
        img = Image.new("RGB", (W, H), (34, 139, 34)) # Saudi Green
        draw = ImageDraw.Draw(img)
        
        # Golden Borders
        draw.rectangle([10, 10, W-10, H-10], outline="#FFD700", width=8)
        draw.rectangle([18, 18, W-18, H-18], outline="#DAA520", width=2)
        
        # Avatar Handling
        pfp = download_image(avatar_url).resize((130, 130))
        draw.rectangle([35, 75, 175, 215], outline="white", width=4)
        img.paste(pfp, (40, 80), pfp if pfp.mode == 'RGBA' else None)
        
        # Header Text
        draw.text((220, 30), "KINGDOM OF ARAB CHAT", fill="#FFD700") 
        draw.text((450, 30), "مملكة شات", fill="#FFD700")
        draw.line([(210, 55), (550, 55)], fill="white", width=2)

        # Random Funny Data
        jobs = ["Shawarma CEO", "Habibi Manager", "Camel Pilot", "Shisha Inspector", "Gold Digger", "Discord Mod"]
        job = random.choice(jobs)
        fake_id = str(random.randint(1000000, 9999999))
        
        # Info Text
        x_start = 220
        y_start = 80
        gap = 40
        
        draw.text((x_start, y_start), "NAME:", fill="#ccc")
        draw.text((x_start+60, y_start), username.upper(), fill="white")
        draw.text((x_start, y_start+gap), "JOB:", fill="#ccc")
        draw.text((x_start+60, y_start+gap), job, fill="#00ff00") 
        draw.text((x_start, y_start+gap*2), "ID NO:", fill="#ccc")
        draw.text((x_start+60, y_start+gap*2), fake_id, fill="white")
        draw.text((x_start, y_start+gap*3), "EXPIRY:", fill="#ccc")
        draw.text((x_start+60, y_start+gap*3), "NEVER (INSHALLAH)", fill="white")

        out = io.BytesIO()
        img.save(out, 'PNG')
        out.seek(0)
        return out
    except Exception as e:
        log(f"ID Gen Error: {e}", "err")
        return None

# --- GENERATOR 2: LOVE SHIP CARD ---
def generate_ship_card(u1, u2, a1, a2, score):
    try:
        W, H = 640, 360
        img = Image.new("RGB", (W, H), (20, 0, 10))
        draw = ImageDraw.Draw(img)
        
        # Gradient Background
        draw_gradient(draw, W, H, (50, 0, 20), (150, 20, 80))
        
        # Tech Grid Lines
        for i in range(0, W, 40): draw.line([(i,0), (i,H)], fill=(255,255,255,10))
        for i in range(0, H, 40): draw.line([(0,i), (W,i)], fill=(255,255,255,10))

        # Avatar Processing
        im1 = download_image(a1).resize((140, 140))
        im2 = download_image(a2).resize((140, 140))
        
        # Paste Avatars
        img.paste(im1, (60, 80), im1)
        img.paste(im2, (440, 80), im2)
        
        # Connection Lines
        draw.line([(200, 150), (440, 150)], fill="white", width=3)
        draw.ellipse((290, 120, 350, 180), fill="#ff004f", outline="white", width=3)
        draw.text((310, 140), f"{score}%", fill="white")
        
        # Names
        draw.text((60, 230), u1[:10], fill="white")
        draw.text((440, 230), u2[:10], fill="white")
        
        # Dynamic Comment
        if score > 80: comment = "PERFECT MATCH! 💍"
        elif score > 50: comment = "MAYBE... 🤔"
        else: comment = "RUN AWAY! 💀"
        draw.text((250, 270), comment, fill="#FFD700")

        out = io.BytesIO()
        img.save(out, 'PNG')
        out.seek(0)
        return out
    except Exception as e:
        log(f"Ship Gen Error: {e}", "err")
        return None

# --- GENERATOR 3: WINNER CARD ---
def generate_winner_card(username, avatar_url, points):
    try:
        W, H = 500, 500
        img = Image.new("RGB", (W, H), (10, 10, 10))
        draw = ImageDraw.Draw(img)
        
        # Neon Border
        draw.rectangle([0, 0, W-1, H-1], outline="#00f3ff", width=15)
        
        # Avatar
        pfp = download_image(avatar_url).resize((200, 200))
        img.paste(pfp, (150, 100))
        draw.rectangle([150, 100, 350, 300], outline="#00f3ff", width=4)
        
        # Text Box
        draw.rectangle([50, 350, 450, 450], fill="#111", outline="white")
        draw.text((200, 370), "WINNER", fill="#FFD700")
        draw.text((180, 400), f"+{points} POINTS", fill="#00ff00")
        
        out = io.BytesIO()
        img.save(out, 'PNG')
        out.seek(0)
        return out
    except: return None

# --- GENERATOR 4: WELCOME CARD (SMART) ---
def generate_welcome_card(username, avatar_url, bg_url):
    try:
        # Background Handling (Custom or Default)
        bg = download_image(bg_url).convert("RGBA")
        bg = bg.resize((600, 300))
        
        # Dark Overlay for Text Readability
        overlay = Image.new("RGBA", bg.size, (0, 0, 0, 90))
        bg = Image.alpha_composite(bg, overlay)
        draw = ImageDraw.Draw(bg)
        
        # Circular Avatar
        pfp = download_image(avatar_url).resize((130, 130))
        mask = Image.new("L", (130, 130), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 130, 130), fill=255)
        
        # Cyan Neon Border
        draw.ellipse((35, 85, 165, 215), outline="#00f3ff", width=4)
        bg.paste(pfp, (35, 85), mask)
        
        # Font Loading
        try: font_lg = ImageFont.truetype("arial.ttf", 45)
        except: font_lg = ImageFont.load_default()
        
        # Welcome Text
        draw.text((180, 90), "WELCOME", fill="#00f3ff", font=font_lg)
        draw.text((180, 140), username.upper(), fill="white", font=font_lg)
        
        # Random Tagline
        taglines = ["The Legend Arrived! 🌟", "Party Shuru Karo! 🎉", "Chat just got hotter 🔥", "Look who's here! 👀", "Habibi Welcome! 🐪"]
        draw.text((180, 210), random.choice(taglines), fill="#ccc")

        out = io.BytesIO()
        bg.save(out, 'PNG')
        out.seek(0)
        return out
    except Exception as e:
        log(f"Welcome Gen Error: {e}", "err")
        return None

# ==============================================================================
# --- 4. ARTIFICIAL INTELLIGENCE ENGINE (THE BRAIN) ---
# ==============================================================================

def guess_gender(username):
    """Simple Heuristic to guess gender based on username keywords"""
    name = username.lower()
    fem_keywords = ["girl", "queen", "princess", "angel", "baby", "doll", "cutie", "she", "her", "rose", "malikah"]
    if name.endswith("a") or name.endswith("i") or any(k in name for k in fem_keywords):
        return "female"
    return "male"

def groq_ai_engine(user, prompt):
    """
    Communicates with Groq API.
    Injects Memory, Gender, and Relationship Context into System Prompt.
    """
    if not GROQ_API_KEY:
        log("No GROQ API Key set", "err")
        return None

    # 1. Retrieve User Info from Database
    facts, gender, rel_score = db_get_memory(user)
    
    # 2. Heuristic Check (If gender is unknown, guess and save)
    if gender == "unknown":
        gender = guess_gender(user)
        db_update_memory(user, gender=gender)

    # 3. Update Conversation Context (Short Term Memory)
    AI_CONTEXT.append({"role": "user", "content": f"{user}: {prompt}"})
    if len(AI_CONTEXT) > 8:
        AI_CONTEXT.pop(0)

    # 4. Configure Persona Based on Data
    my_name = BOT_STATE["username"]
    
    # Relationship Vibe Check
    if rel_score < 20: 
        vibe = "Polite, Helpful, slightly formal (Stranger)."
    elif rel_score < 60: 
        vibe = "Friendly, Chill, Bro-like (Friend)."
    else: 
        vibe = "Playful, Teasing, Flirty, Roast allowed (Bestie/Lover)."

    # Tone Check
    if gender == "female":
        tone = "Charming, Gentlemanly but Flirty. Use emojis like ✨🌹😉. Treat her special."
    else:
        tone = "Casual Bro-talk. Slang allowed. Light roasting. Use emojis like 😂👊🔥."

    # --- SYSTEM PROMPT (THE MOST CRITICAL PART) ---
    sys_prompt = f"""
    YOU ARE: {my_name}, a real human in a chatroom. You are NOT an AI.
    USER INFO: Name: {user} | Gender: {gender} | Relationship Score: {rel_score}/100.
    KNOWN FACTS: {facts}
    
    INSTRUCTIONS:
    1. VIBE: {vibe}
    2. TONE: {tone}
    3. LENGTH: Keep it natural (max 20 words). No long essays.
    4. MEMORY USAGE: Use 'KNOWN FACTS' ONLY IF relevant to the current topic. DO NOT repeat facts randomly.
       (Example: If fact is 'Lives in Delhi', ask 'How is Delhi weather?' only if weather is discussed).
    5. Be witty, funny, and charming.
    
    RULES:
    - If user tells NEW info about themselves (name, city, age, likes), output ONLY: MEMORY_SAVE: <fact>
    - If user asks who you are, say you are the boss here.
    """

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": sys_prompt},
            *AI_CONTEXT
        ],
        "temperature": 0.85, # Higher temp for more creativity
        "max_tokens": 100
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        if response.status_code == 200:
            reply = response.json()["choices"][0]["message"]["content"]
            
            # --- SMART MEMORY SAVE LOGIC ---
            if "MEMORY_SAVE:" in reply:
                info = reply.replace("MEMORY_SAVE:", "").strip()
                db_update_memory(user, fact=info)
                # Generate a confirmation reply manually
                return f"Got it, noted! 🧠✨"

            AI_CONTEXT.append({"role": "assistant", "content": reply})
            
            # Increase Dosti Meter on every interaction
            db_update_memory(user, rel_inc=1)
            
            return reply
        else:
            log(f"Groq API Error: {response.text}", "err")
            return None

    except Exception as e:
        log(f"AI Request Failed: {e}", "err")
        return None

# ==============================================================================
# --- 5. GAME LOGIC (TITAN BOMB & MAGIC TRICK) ---
# ==============================================================================

def render_game_grid(reveal=False, exploded_at=None):
    """Renders the 3x3 emoji grid for Titan Game"""
    icons = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
    grid_str = ""
    for i in range(1, 10):
        if reveal:
            if i == exploded_at: grid_str += "💥 "
            elif i in TITAN_GAME["bombs"]: grid_str += "💣 "
            elif i in TITAN_GAME["eaten"]: grid_str += "🥔 "
            else: grid_str += icons[i-1] + " "
        else:
            if i in TITAN_GAME["eaten"]: grid_str += "🥔 "
            else: grid_str += icons[i-1] + " "
            
        if i % 3 == 0 and i != 9: grid_str += "\n"
    return grid_str

def process_game_command(user, msg):
    """Handles Titan Game Logic"""
    msg = msg.lower()
    
    # START COMMAND
    if msg.startswith("!start"):
        if TITAN_GAME["active"]:
            send_ws_msg(f"⚠ Game in progress by {TITAN_GAME['player']}")
            return
        
        bet = 0
        if "bet@" in msg:
            try: bet = int(msg.split("@")[1])
            except: pass
            
        # Check Balance
        if bet > 0:
            balance = db_get_balance(user)
            if balance < bet:
                send_ws_msg(f"💸 You are broke! Balance: {balance}")
                return
        
        TITAN_GAME["active"] = True
        TITAN_GAME["player"] = user
        TITAN_GAME["bet"] = bet
        TITAN_GAME["eaten"] = []
        TITAN_GAME["bombs"] = random.sample(range(1, 10), 2)
        
        mode_txt = f"💰 BET: {bet}" if bet > 0 else "🛡 FREE MODE"
        grid = render_game_grid()
        send_ws_msg(f"🎮 TITAN GAME STARTED!\nPlayer: {user} | {mode_txt}\nAvoid 2 Bombs. Eat 4 Chips.\nType !eat <number>\n\n{grid}")

    # EAT COMMAND
    elif msg.startswith("!eat "):
        if not TITAN_GAME["active"] or user != TITAN_GAME["player"]: return
        
        try: num = int(msg.split()[1])
        except: return
        
        if num < 1 or num > 9 or num in TITAN_GAME["eaten"]: return
        
        # BOMB HIT
        if num in TITAN_GAME["bombs"]:
            TITAN_GAME["active"] = False
            loss_txt = ""
            if TITAN_GAME["bet"] > 0:
                db_update_user(user, -TITAN_GAME["bet"], loss_increment=1, avatar=TITAN_GAME["cache_avatars"].get(user,""))
                loss_txt = f"\n📉 You lost {TITAN_GAME['bet']} points."
            else:
                db_update_user(user, 0, loss_increment=1, avatar=TITAN_GAME["cache_avatars"].get(user,""))
                
            grid = render_game_grid(reveal=True, exploded_at=num)
            send_ws_msg(f"💥 BOOM! You stepped on a bomb!{loss_txt}\n\n{grid}")
            
        # SAFE HIT
        else:
            TITAN_GAME["eaten"].append(num)
            # CHECK WIN (4 Safe eaten)
            if len(TITAN_GAME["eaten"]) == 4:
                TITAN_GAME["active"] = False
                win_amount = TITAN_GAME["bet"] if TITAN_GAME["bet"] > 0 else 10
                
                db_update_user(user, win_amount, win_increment=1, avatar=TITAN_GAME["cache_avatars"].get(user,""))
                
                grid = render_game_grid(reveal=True)
                send_ws_msg(f"🎉 VICTORY! You won {win_amount} points!\n\n{grid}")
                
                # Send Winner Card
                domain = BOT_STATE.get("domain", "")
                avi = TITAN_GAME["cache_avatars"].get(user, "")
                img_url = f"{domain}api/winner?u={user}&p={win_amount}&a={requests.utils.quote(avi)}"
                send_ws_msg("", "image", img_url)
                
            else:
                grid = render_game_grid()
                send_ws_msg(f"🥔 Safe! ({len(TITAN_GAME['eaten'])}/4)\n{grid}")

# ==============================================================================
# --- 6. WEBSOCKET HANDLER (EVENT LOOP) ---
# ==============================================================================

def send_ws_msg(text, type="text", url=""):
    """Sends a packet to the chat server"""
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        pkt = {
            "handler": "room_message",
            "id": str(time.time()),
            "room": BOT_STATE["room_name"],
            "type": type,
            "body": text,
            "url": url,
            "length": "0"
        }
        try: BOT_STATE["ws"].send(json.dumps(pkt))
        except: pass
        log(f"SENT: {text[:30]}...", "out")

def on_socket_message(ws, message):
    try:
        data = json.loads(message)
        handler = data.get("handler")
        
        # --- 1. LOGIN SUCCESS ---
        if handler == "login_event":
            if data["type"] == "success":
                log("Login Successful. Joining Room...", "sys")
                ws.send(json.dumps({"handler": "room_join", "id": str(time.time()), "name": BOT_STATE["room_name"]}))
            else:
                log(f"Login Failed: {data.get('reason')}", "err")
                BOT_STATE["connected"] = False

        # --- 2. USER JOIN EVENT (SMART WELCOME SYSTEM) ---
        elif handler == "room_event" and data.get("type") == "join":
            user = data.get("nickname") or data.get("username")
            if user == BOT_STATE["username"]: return
            
            # Fetch Avatar for Card
            avi = data.get("avatar_url", "https://i.imgur.com/6EdJm2h.png")
            TITAN_GAME["cache_avatars"][user] = avi
            
            # Get User Details from DB
            facts, gender, score = db_get_memory(user)
            bg_url = db_get_bg(user)
            domain = BOT_STATE.get("domain", "")
            
            # Generate Welcome Card URL
            img_url = f"{domain}api/welcome?u={user}&a={requests.utils.quote(avi)}&bg={requests.utils.quote(bg_url)}"
            
            # Personalized Welcome Text
            if score > 50: msg = f"Welcome back bestie @{user}! ❤️"
            elif facts: msg = f"Welcome @{user}! Long time no see. 😉"
            else: msg = f"Welcome to the chat, @{user}! 👋"
            
            send_ws_msg(msg, "image", img_url)

        # --- 3. ROOM TEXT MESSAGES ---
        elif handler == "room_event" and data.get("type") == "text":
            sender = data.get("from")
            body = data.get("body", "").strip()
            
            # Cache Avatar
            if data.get("avatar_url"): TITAN_GAME["cache_avatars"][sender] = data["avatar_url"]
            elif data.get("icon"): 
                icon = data["icon"]
                if not icon.startswith("http"): icon = "https://chatp.net" + icon
                TITAN_GAME["cache_avatars"][sender] = icon

            # Ignore Self
            if sender.lower() == BOT_STATE["username"].lower(): return 
            
            log(f"{sender}: {body}", "in")
            
            # Use Threading to avoid blocking the socket loop
            threading.Thread(target=process_user_message, args=(sender, body)).start()

    except Exception as e:
        log(f"Socket Error: {e}", "err")

def process_user_message(user, msg):
    msg_lower = msg.lower()
    
    # --- COMMANDS HANDLER ---
    if msg_lower.startswith("!"):
        
        # New Feature: Set Background
        if msg_lower.startswith("!setbg "):
            try:
                url = msg.split(" ", 1)[1].strip()
                if "http" in url:
                    db_set_bg(user, url)
                    send_ws_msg(f"✅ @{user} Background updated for Welcome Card!")
                else: send_ws_msg("❌ Invalid URL. Send direct image link.")
            except: pass
            return

        # New Feature: Manual Welcome
        if msg_lower.startswith("!welcome"):
            target = msg.split("@")[1].strip() if "@" in msg else user
            avi = TITAN_GAME["cache_avatars"].get(target, "https://i.imgur.com/6EdJm2h.png")
            bg = db_get_bg(target)
            domain = BOT_STATE.get("domain", "")
            url = f"{domain}api/welcome?u={target}&a={requests.utils.quote(avi)}&bg={requests.utils.quote(bg)}"
            send_ws_msg(f"Welcome @{target}!", "image", url)
            return

        # Trigger Management
        if msg_lower.startswith("!addtg "):
            tg = msg.split(" ", 1)[1].lower()
            if tg not in BOT_STATE["triggers"]:
                BOT_STATE["triggers"].append(tg)
                send_ws_msg(f"✅ Added trigger: {tg}")
            return

        # Graphics Commands
        if msg_lower.startswith("!id"):
            target = user
            if "@" in msg: target = msg.split("@")[1].strip()
            
            domain = BOT_STATE.get("domain", "")
            avi = TITAN_GAME["cache_avatars"].get(target, "")
            url = f"{domain}api/id_card?u={target}&a={requests.utils.quote(avi)}"
            send_ws_msg("", "image", url)
            return

        if msg_lower.startswith("!ship"):
            target = BOT_STATE["username"]
            if "@" in msg: target = msg.split("@")[1].strip()
            
            score = random.randint(0, 100)
            domain = BOT_STATE.get("domain", "")
            a1 = TITAN_GAME["cache_avatars"].get(user, "")
            a2 = TITAN_GAME["cache_avatars"].get(target, "")
            url = f"{domain}api/ship?u1={user}&u2={target}&a1={requests.utils.quote(a1)}&a2={requests.utils.quote(a2)}&s={score}"
            
            send_ws_msg(f"Result: {score}%", "image", url)
            return

        # Magic Game (New Feature)
        if msg_lower == "!magic":
            TITAN_GAME["magic_symbol"] = random.choice(["@", "#", "$", "%", "&"])
            # Generate a 99 number text grid where multiples of 9 share the symbol
            grid = "🔮 MIND READER 🔮\n"
            for i in range(10, 50):
                if i % 9 == 0: sym = TITAN_GAME["magic_symbol"]
                else: sym = random.choice(["^", "*", "+", "=", "?"])
                grid += f"{i}:{sym}  "
                if i % 5 == 0: grid += "\n"
                
            send_ws_msg(f"{grid}\n\n1. Pick number (10-99)\n2. Add digits (23 -> 2+3=5)\n3. Subtract sum (23-5=18)\n4. Check symbol for 18!\nType !reveal")
            return

        if msg_lower == "!reveal":
            if TITAN_GAME["magic_symbol"]:
                send_ws_msg(f"✨ The symbol is: {TITAN_GAME['magic_symbol']}")
                TITAN_GAME["magic_symbol"] = None
            return

        # Titan Game Routing
        if msg_lower.startswith("!start") or msg_lower.startswith("!eat"):
            process_game_command(user, msg)
            return

    # --- AI RESPONSE TRIGGER ---
    my_name = BOT_STATE["username"].lower()
    triggers = [my_name] + BOT_STATE["triggers"]
    
    if any(t in msg_lower for t in triggers):
        reply = groq_ai_engine(user, msg)
        if reply:
            send_ws_msg(f"@{user} {reply}")

# ==============================================================================
# --- 7. FLASK WEB SERVER (UI & API) ---
# ==============================================================================

@app.route('/')
def index():
    return render_template_string(HTML_CONTROL_PANEL, connected=BOT_STATE["connected"])

@app.route('/leaderboard')
def leaderboard_page():
    data = db_get_leaderboard()
    return render_template_string(HTML_LEADERBOARD, users=data)

# --- IMAGE GENERATION ROUTES ---

@app.route('/api/id_card')
def api_id():
    u = request.args.get('u', 'User')
    a = request.args.get('a', '')
    img_io = generate_id_card(u, a)
    if img_io: return send_file(img_io, mimetype='image/png')
    return "Err", 500

@app.route('/api/ship')
def api_ship():
    img_io = generate_ship_card(
        request.args.get('u1'), request.args.get('u2'),
        request.args.get('a1'), request.args.get('a2'),
        int(request.args.get('s', 50))
    )
    if img_io: return send_file(img_io, mimetype='image/png')
    return "Err", 500

@app.route('/api/winner')
def api_winner():
    img_io = generate_winner_card(
        request.args.get('u'), request.args.get('a'),
        request.args.get('p')
    )
    if img_io: return send_file(img_io, mimetype='image/png')
    return "Err", 500

@app.route('/api/welcome')
def api_welcome():
    img_io = generate_welcome_card(
        request.args.get('u'), request.args.get('a'),
        request.args.get('bg')
    )
    if img_io: return send_file(img_io, mimetype='image/png')
    return "Err", 500

# --- CONTROL ROUTES ---

@app.route('/connect', methods=['POST'])
def connect_bot():
    if BOT_STATE["connected"]: return jsonify({"status": "Already Online"})
    d = request.json
    BOT_STATE["username"] = d["u"]
    BOT_STATE["password"] = d["p"]
    BOT_STATE["room_name"] = d["r"]
    BOT_STATE["domain"] = request.url_root
    
    t = threading.Thread(target=start_websocket)
    t.start()
    return jsonify({"status": "Initializing..."})

@app.route('/disconnect', methods=['POST'])
def disconnect_bot():
    if BOT_STATE["ws"]: BOT_STATE["ws"].close()
    BOT_STATE["connected"] = False
    return jsonify({"status": "Disconnected"})

@app.route('/logs')
def get_logs():
    return jsonify({"logs": SYSTEM_LOGS})

def start_websocket():
    # WebSocketApp runner
    def on_open(ws):
        BOT_STATE["connected"] = True
        log("WebSocket Connected", "sys")
        # Send Login Packet
        login_pkt = {
            "handler": "login",
            "id": str(time.time()),
            "username": BOT_STATE["username"],
            "password": BOT_STATE["password"],
            "platform": "web"
        }
        ws.send(json.dumps(login_pkt))
        
        # Keep Alive Loop
        def pinger():
            while BOT_STATE["connected"]:
                time.sleep(25)
                try: ws.send(json.dumps({"handler": "ping"}))
                except: break
        threading.Thread(target=pinger, daemon=True).start()

    ws = websocket.WebSocketApp(
        "wss://chatp.net:5333/server",
        on_open=on_open,
        on_message=on_socket_message,
        on_error=lambda w,e: log(f"WS Error: {e}", "err"),
        on_close=lambda w,c,m: log("WS Closed", "sys")
    )
    BOT_STATE["ws"] = ws
    ws.run_forever()

# ==============================================================================
# --- 8. HTML TEMPLATES (FULL & VERBOSE) ---
# ==============================================================================

HTML_CONTROL_PANEL = """
<!DOCTYPE html>
<html>
<head>
    <title>TITAN ULTIMATE MAX</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <style>
        :root { --neon: #00f3ff; --bg: #050505; --panel: #111; --green: #00ff41; --red: #ff003c; }
        body { background: var(--bg); color: var(--neon); font-family: 'Share Tech Mono', monospace; padding: 20px; }
        
        .box { background: var(--panel); border: 1px solid #333; padding: 20px; margin-bottom: 20px; border-left: 5px solid var(--neon); }
        h2 { margin-top: 0; color: #fff; }
        
        input { width: 100%; padding: 10px; margin: 5px 0; background: #000; color: #fff; border: 1px solid #444; box-sizing: border-box; }
        
        button { width: 100%; padding: 12px; background: var(--neon); color: #000; border: none; font-weight: bold; cursor: pointer; margin-top: 10px; }
        button:hover { opacity: 0.8; }
        button.stop { background: var(--red); color: #fff; }
        
        .logs { height: 300px; overflow-y: scroll; background: #000; border: 1px solid #333; padding: 10px; font-size: 12px; }
        .in { color: var(--green); }
        .out { color: var(--neon); }
        .err { color: var(--red); }
        .sys { color: #888; }
    </style>
</head>
<body>
    <div class="box">
        <h2>🤖 SYSTEM CONTROL</h2>
        <div id="status">Status: {{ 'ONLINE' if connected else 'OFFLINE' }}</div>
        
        <input type="text" id="u" placeholder="Bot Username">
        <input type="password" id="p" placeholder="Password">
        <input type="text" id="r" placeholder="Room Name">
        
        <div style="display:flex; gap:10px;">
            <button onclick="send('/connect')">START SYSTEM</button>
            <button class="stop" onclick="send('/disconnect')">SHUTDOWN</button>
        </div>
        <br>
        <a href="/leaderboard" target="_blank" style="color:#fff">🏆 View Leaderboard</a>
    </div>

    <div class="box">
        <h2>📜 LIVE LOGS</h2>
        <div class="logs" id="logs">Loading logs...</div>
    </div>

    <script>
        function send(endpoint) {
            const data = {
                u: document.getElementById('u').value,
                p: document.getElementById('p').value,
                r: document.getElementById('r').value
            };
            fetch(endpoint, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(res => res.json())
            .then(d => alert(d.status));
        }

        setInterval(() => {
            fetch('/logs')
            .then(res => res.json())
            .then(data => {
                const logDiv = document.getElementById('logs');
                logDiv.innerHTML = data.logs.reverse().map(l => 
                    `<div class="${l.type}">[${l.time}] ${l.msg}</div>`
                ).join('');
            });
        }, 2000);
    </script>
</body>
</html>
"""

HTML_LEADERBOARD = """
<!DOCTYPE html>
<html>
<head>
    <title>TITAN RANKINGS</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <style>
        body { background: #050505; color: #fff; font-family: 'Share Tech Mono', monospace; text-align: center; }
        h1 { color: #00f3ff; border-bottom: 2px solid #00f3ff; display: inline-block; padding: 10px; }
        .card { 
            background: #111; margin: 10px auto; padding: 15px; width: 90%; max-width: 500px;
            display: flex; align-items: center; justify-content: space-between;
            border-left: 5px solid #333;
        }
        .rank-1 { border-color: gold; }
        .rank-2 { border-color: silver; }
        .rank-3 { border-color: #cd7f32; }
        
        .avi { width: 50px; height: 50px; border-radius: 50%; border: 2px solid #fff; }
        .name { font-size: 1.2em; font-weight: bold; }
        .score { color: #00ff41; font-size: 1.2em; }
    </style>
</head>
<body>
    <h1>GLOBAL LEADERBOARD</h1>
    {% for user in users %}
    <div class="card rank-{{ loop.index }}">
        <div style="display:flex; align-items:center; gap:15px;">
            <span style="font-size:1.5em; width:30px;">#{{ loop.index }}</span>
            {% if user[3] %}
            <img src="{{ user[3] }}" class="avi">
            {% else %}
            <div class="avi" style="background:#333"></div>
            {% endif %}
            <div style="text-align:left;">
                <div class="name">{{ user[0] }}</div>
                <div style="font-size:0.8em; color:#888;">Wins: {{ user[2] }}</div>
            </div>
        </div>
        <div class="score">{{ user[1] }} PTS</div>
    </div>
    {% endfor %}
</body>
</html>
"""

# ==============================================================================
# --- 9. APP ENTRY POINT ---
# ==============================================================================

if __name__ == '__main__':
    # Initialize DB on start
    init_database()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)