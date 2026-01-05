# ==============================================================================
# TITAN ULTIMATE BOT - V5.0 (THE HEAVYWEIGHT EDITION)
# ==============================================================================
# AUTHOR: Titan Developer
# SYSTEM: Flask + WebSocket + PostgreSQL (Neon) + Groq AI + PIL Graphics
# ==============================================================================

import os
import json
import time
import threading
import io
import random
import requests
import websocket
import psycopg2
from psycopg2 import sql
from flask import Flask, render_template_string, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

# ==============================================================================
# --- 1. CORE CONFIGURATION & CREDENTIALS ---
# ==============================================================================

app = Flask(__name__)

# --- DATABASE CONFIGURATION (NEON POSTGRESQL) ---
# DO NOT EDIT THIS URL UNLESS YOUR DATABASE CHANGES
DB_URL = "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

# --- AI CONFIGURATION (GROQ API) ---
# Ensure this is set in Render Environment Variables
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "") 

# --- BOT GLOBAL STATE ---
# Holds temporary data in RAM (Resets on Restart)
BOT_STATE = {
    "ws": None,             # The WebSocket Object
    "connected": False,     # Connection Status Flag
    "username": "",         # Bot's Username on Chat
    "password": "",         # Bot's Password
    "room_name": "",        # Target Room Name
    "domain": "",           # Server Domain (Auto-detected)
    "triggers": [],         # List of Custom Triggers (!addtg)
    "mode": "ar",           # DEFAULT MODE: 'ar' (Arabic/Habibi)
    "admin_id": "y"         # Internal Admin Identifier
}

# --- GAME SYSTEM STATE ---
# Tracks the Titan Bomb Game & Magic Trick
TITAN_GAME = {
    "active": False,        # Is a game currently running?
    "player": None,         # Who started the game?
    "bombs": [],            # List of Bomb Positions (1-9)
    "eaten": [],            # List of Safe Spots Eaten
    "bet": 0,               # Amount of points bet
    "cache_avatars": {},    # Caching Avatars to reduce lag
    "magic_symbol": None    # Stores the symbol for Magic Trick
}

# --- AI MEMORY CONTEXT ---
# Stores the last 15 messages for better conversation flow
AI_CONTEXT = []

# --- SYSTEM LOGGING ---
# Stores logs for the Web Control Panel
SYSTEM_LOGS = []

def log(msg, type="info"):
    """
    Advanced Logging Function.
    Stores logs in RAM and prints to Console.
    Types: 'info', 'err', 'sys', 'chat', 'out'
    """
    timestamp = time.strftime("%H:%M:%S")
    entry = {"time": timestamp, "msg": msg, "type": type}
    SYSTEM_LOGS.append(entry)
    # Keep Memory Clean (Max 300 Logs)
    if len(SYSTEM_LOGS) > 300: 
        SYSTEM_LOGS.pop(0)
    print(f"[{type.upper()}] {msg}")

# ==============================================================================
# --- 2. ROBUST DATABASE MANAGEMENT (NEON POSTGRES) ---
# ==============================================================================

def get_db_connection():
    """
    Establishes a secure connection to Neon DB.
    Includes Error Handling for Timeouts.
    """
    try:
        conn = psycopg2.connect(DB_URL)
        return conn
    except Exception as e:
        log(f"CRITICAL DB ERROR: Could not connect to Neon DB. {e}", "err")
        return None

def init_database():
    """
    Initializes the Database Schema.
    Creates tables only if they don't exist.
    """
    conn = get_db_connection()
    if not conn:
        log("DB Init Failed: Connection is None", "err")
        return

    c = conn.cursor()
    
    # 1. USERS TABLE (Stats)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, 
            score INTEGER DEFAULT 0, 
            wins INTEGER DEFAULT 0, 
            losses INTEGER DEFAULT 0, 
            avatar TEXT
        )
    ''')
    
    # 2. SETTINGS TABLE (Config)
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, 
            value TEXT
        )
    ''')
    
    # 3. MEMORY TABLE (AI Brain)
    c.execute('''
        CREATE TABLE IF NOT EXISTS memory (
            username TEXT PRIMARY KEY, 
            facts TEXT, 
            gender TEXT, 
            rel_score INTEGER DEFAULT 0
        )
    ''')
    
    # 4. GREETINGS TABLE (Custom BG)
    c.execute('''
        CREATE TABLE IF NOT EXISTS greetings (
            username TEXT PRIMARY KEY, 
            bg_url TEXT
        )
    ''')
    
    conn.commit()
    c.close()
    conn.close()
    log("Database Tables Verified & Ready.", "sys")

# --- DATABASE HELPER FUNCTIONS ---

def db_update_user(username, points_change, win_increment=0, loss_increment=0, avatar=""):
    """
    Updates user stats (Score, Wins, Losses).
    Handles User Creation if not exists.
    """
    conn = get_db_connection()
    if not conn: return
    c = conn.cursor()
    
    try:
        # Check if user exists
        c.execute("SELECT score, wins, losses FROM users WHERE username=%s", (username,))
        data = c.fetchone()
        
        if data:
            # Update Existing
            new_score = data[0] + points_change
            if new_score < 0: new_score = 0
            
            c.execute("""
                UPDATE users SET score=%s, wins=%s, losses=%s, avatar=%s 
                WHERE username=%s
            """, (new_score, data[1]+win_increment, data[2]+loss_increment, avatar, username))
        else:
            # Create New
            start_score = points_change if points_change > 0 else 0
            c.execute("""
                INSERT INTO users (username, score, wins, losses, avatar) 
                VALUES (%s, %s, %s, %s, %s)
            """, (username, start_score, win_increment, loss_increment, avatar))
        
        conn.commit()
    except Exception as e:
        log(f"DB Update User Error: {e}", "err")
    finally:
        c.close()
        conn.close()

def db_get_balance(username):
    """Retrieves current score for betting logic."""
    conn = get_db_connection()
    if not conn: return 0
    c = conn.cursor()
    try:
        c.execute("SELECT score FROM users WHERE username=%s", (username,))
        data = c.fetchone()
        return data[0] if data else 0
    except: return 0
    finally:
        c.close()
        conn.close()

def db_get_leaderboard():
    """Fetches Top 50 Users for Display."""
    conn = get_db_connection()
    if not conn: return []
    c = conn.cursor()
    try:
        c.execute("SELECT username, score, wins, avatar FROM users ORDER BY score DESC LIMIT 50")
        data = c.fetchall()
        return data
    except: return []
    finally:
        c.close()
        conn.close()

# --- MEMORY SYSTEM FUNCTIONS ---

def db_get_memory(user):
    """Fetches AI Facts, Gender, and Friendship Score."""
    conn = get_db_connection()
    if not conn: return "", "unknown", 0
    c = conn.cursor()
    try:
        c.execute("SELECT facts, gender, rel_score FROM memory WHERE username=%s", (user,))
        data = c.fetchone()
        if data: return data[0], data[1], data[2]
        return "", "unknown", 0
    except: return "", "unknown", 0
    finally:
        c.close()
        conn.close()

def db_update_memory(user, fact=None, gender=None, rel_inc=0):
    """
    Intelligent Memory Update.
    - Prevents Duplicate Facts
    - Updates Friendship Score
    - Updates Gender
    """
    current_facts, current_gender, current_score = db_get_memory(user)
    
    new_facts = current_facts
    if fact:
        # Cleanup Fact String
        fact = fact.strip(" .")
        # Only add if not already present
        if fact not in current_facts:
            new_facts = f"{current_facts} | {fact}".strip(" | ")
            # Safety Truncate
            if len(new_facts) > 800: new_facts = new_facts[-800:]
    
    new_gender = gender if gender else current_gender
    new_score = current_score + rel_inc
    if new_score > 100: new_score = 100 # Max Level
    
    conn = get_db_connection()
    if not conn: return
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO memory (username, facts, gender, rel_score) 
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (username) 
            DO UPDATE SET facts=EXCLUDED.facts, gender=EXCLUDED.gender, rel_score=EXCLUDED.rel_score
        """, (user, new_facts, new_gender, new_score))
        conn.commit()
    except Exception as e:
        log(f"DB Memory Error: {e}", "err")
    finally:
        c.close()
        conn.close()

def db_set_bg(username, url):
    """Sets Custom Background for User."""
    conn = get_db_connection()
    if not conn: return
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO greetings (username, bg_url) 
            VALUES (%s, %s)
            ON CONFLICT (username) 
            DO UPDATE SET bg_url=EXCLUDED.bg_url
        """, (username, url))
        conn.commit()
    except: pass
    finally:
        c.close()
        conn.close()

def db_get_bg(username):
    """Gets User's Background."""
    conn = get_db_connection()
    if not conn: return "https://wallpaperaccess.com/full/1567665.png"
    c = conn.cursor()
    try:
        c.execute("SELECT bg_url FROM greetings WHERE username=%s", (username,))
        data = c.fetchone()
        return data[0] if data else "https://wallpaperaccess.com/full/1567665.png"
    except: return "https://wallpaperaccess.com/full/1567665.png"
    finally:
        c.close()
        conn.close()

# Initialize Database Structure on Startup
init_database()

# ==============================================================================
# --- 3. GRAPHICS ENGINE (IMAGE GENERATION) ---
# ==============================================================================

def download_image(url):
    """Downloads image securely. Returns a Grey Placeholder on failure."""
    try:
        if not url or "http" not in url: raise Exception("Invalid URL")
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=5)
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        return img
    except:
        # Fallback: Grey Box
        return Image.new("RGBA", (200, 200), (50, 50, 50, 255))

def draw_gradient(draw, width, height, color1, color2):
    """Draws a nice vertical gradient background."""
    for y in range(height):
        r = int(color1[0] + (color2[0] - color1[0]) * y / height)
        g = int(color1[1] + (color2[1] - color1[1]) * y / height)
        b = int(color1[2] + (color2[2] - color1[2]) * y / height)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

# --- GENERATOR 1: SAUDI ID CARD ---
def generate_id_card(username, avatar_url):
    try:
        W, H = 600, 360
        img = Image.new("RGB", (W, H), (34, 139, 34)) # KSA Green
        draw = ImageDraw.Draw(img)
        
        # Ornate Borders
        draw.rectangle([10, 10, W-10, H-10], outline="#FFD700", width=8)
        draw.rectangle([18, 18, W-18, H-18], outline="#DAA520", width=2)
        
        # Profile Picture
        pfp = download_image(avatar_url).resize((130, 130))
        draw.rectangle([35, 75, 175, 215], outline="white", width=4)
        img.paste(pfp, (40, 80), pfp if pfp.mode == 'RGBA' else None)
        
        # Headers
        draw.text((220, 30), "KINGDOM OF ARAB CHAT", fill="#FFD700") 
        draw.text((450, 30), "مملكة شات", fill="#FFD700")
        draw.line([(210, 55), (550, 55)], fill="white", width=2)

        # Random Funny Data
        jobs = ["Shawarma CEO", "Habibi Manager", "Camel Pilot", "Shisha Inspector", "Gold Digger", "Oily Sheikh", "Date Farmer"]
        job = random.choice(jobs)
        fake_id = str(random.randint(1000000, 9999999))
        
        # Information Fields
        draw.text((220, 80), "NAME: " + username.upper(), fill="white")
        draw.text((220, 120), "JOB: " + job, fill="#00ff00")
        draw.text((220, 160), "ID NO: " + fake_id, fill="white")
        draw.text((220, 200), "EXPIRY: NEVER (INSHALLAH)", fill="#ccc")
        
        # Fake Barcode
        for i in range(220, W-50, 5):
            h = random.randint(20, 50)
            draw.line([(i, 320), (i, 320-h)], fill="black", width=2)

        out = io.BytesIO()
        img.save(out, 'PNG')
        out.seek(0)
        return out
    except Exception as e:
        log(f"Graphics Error (ID): {e}", "err")
        return None

# --- GENERATOR 2: LOVE SHIP CARD ---
def generate_ship_card(u1, u2, a1, a2, score):
    try:
        W, H = 640, 360
        img = Image.new("RGB", (W, H), (20, 0, 10))
        draw = ImageDraw.Draw(img)
        draw_gradient(draw, W, H, (50, 0, 20), (150, 20, 80))
        
        # Sci-Fi Grid
        for i in range(0, W, 40): draw.line([(i,0), (i,H)], fill=(255,255,255,10))
        for i in range(0, H, 40): draw.line([(0,i), (W,i)], fill=(255,255,255,10))

        # Avatars (Left & Right)
        im1 = download_image(a1).resize((140, 140))
        im2 = download_image(a2).resize((140, 140))
        img.paste(im1, (60, 80), im1)
        img.paste(im2, (440, 80), im2)
        
        # Connection
        draw.line([(200, 150), (440, 150)], fill="white", width=3)
        draw.ellipse((290, 120, 350, 180), fill="#ff004f", outline="white", width=3)
        draw.text((310, 140), f"{score}%", fill="white")
        
        # Usernames
        draw.text((60, 230), u1[:10], fill="white")
        draw.text((440, 230), u2[:10], fill="white")
        
        # Verdict
        if score > 80: comment = "MARRY THEM! 💍"
        elif score > 50: comment = "MAYBE... 🤔"
        else: comment = "RUN AWAY! 💀"
        draw.text((250, 270), comment, fill="#FFD700")

        out = io.BytesIO()
        img.save(out, 'PNG')
        out.seek(0)
        return out
    except Exception as e:
        log(f"Graphics Error (Ship): {e}", "err")
        return None

# --- GENERATOR 3: WINNER CARD ---
def generate_winner_card(username, avatar_url, points):
    try:
        W, H = 500, 500
        img = Image.new("RGB", (W, H), (10, 10, 10))
        draw = ImageDraw.Draw(img)
        
        draw.rectangle([0, 0, W-1, H-1], outline="#00f3ff", width=15)
        pfp = download_image(avatar_url).resize((200, 200))
        img.paste(pfp, (150, 100))
        draw.rectangle([150, 100, 350, 300], outline="#00f3ff", width=4)
        
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
        # Background
        bg = download_image(bg_url).convert("RGBA").resize((600, 300))
        overlay = Image.new("RGBA", bg.size, (0, 0, 0, 90))
        bg = Image.alpha_composite(bg, overlay)
        draw = ImageDraw.Draw(bg)
        
        # Circular PFP
        pfp = download_image(avatar_url).resize((130, 130))
        mask = Image.new("L", (130, 130), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 130, 130), fill=255)
        bg.paste(pfp, (35, 85), mask)
        draw.ellipse((35, 85, 165, 215), outline="#00f3ff", width=4)
        
        # Text Logic (Fallback Font)
        try: font_lg = ImageFont.truetype("arial.ttf", 45)
        except: font_lg = ImageFont.load_default()
        
        draw.text((180, 90), "WELCOME", fill="#00f3ff", font=font_lg)
        draw.text((180, 140), username.upper(), fill="white", font=font_lg)
        
        # Random Flavor Text
        taglines = ["The Legend Arrived! 🌟", "Party Shuru Karo! 🎉", "Chat just got hotter 🔥", "Look who's here! 👀", "Habibi Welcome! 🐪"]
        draw.text((180, 210), random.choice(taglines), fill="#ccc")

        out = io.BytesIO()
        bg.save(out, 'PNG')
        out.seek(0)
        return out
    except Exception as e:
        log(f"Graphics Error (Welcome): {e}", "err")
        return None

# ==============================================================================
# --- 4. ADVANCED AI ENGINE (WITH ARABIC MODE) ---
# ==============================================================================

def guess_gender(username):
    """Guesses gender based on username endings and keywords."""
    name = username.lower()
    fem_keywords = ["girl", "queen", "princess", "angel", "baby", "doll", "cutie", "she", "her", "rose", "malikah", "fatima"]
    if name.endswith("a") or name.endswith("i") or any(k in name for k in fem_keywords):
        return "female"
    return "male"

def groq_ai_engine(user, prompt):
    """
    The Brain of the Bot.
    Handles 3 Modes:
    1. 'ar' (Arabic): Funny Sheikh persona.
    2. 'en' (Savage): Roasting English persona.
    3. 'smart' (Adaptive): Changes based on user data.
    """
    if not GROQ_API_KEY: 
        log("AI ERROR: API Key Missing", "err")
        return None

    # 1. Fetch User Data
    facts, gender, rel_score = db_get_memory(user)
    if gender == "unknown":
        gender = guess_gender(user)
        db_update_memory(user, gender=gender)

    # 2. Update Context
    AI_CONTEXT.append({"role": "user", "content": f"{user}: {prompt}"})
    if len(AI_CONTEXT) > 8: AI_CONTEXT.pop(0)

    # 3. Mode Selection
    my_name = BOT_STATE["username"]
    mode = BOT_STATE["mode"]
    
    # --- PROMPT CONSTRUCTION ---
    if mode == "ar":
        # === ARABIC / HABIBI MODE (EXPANDED) ===
        sys_prompt = f"""
        YOU ARE: {my_name}, a wealthy, dramatic, and funny Arab Sheikh in a chatroom.
        LANGUAGE: Broken English mixed with Arabic words (Habibi, Wallah, Yalla, Shukran, Mashallah, Haram).
        PERSONALITY: You love Gold, Camels, Shawarma, and Dubai. You are very dramatic but friendly.
        
        USER INFO: Name: {user} | Gender: {gender}
        KNOWN FACTS: {facts}
        
        INSTRUCTIONS:
        1. Always start or end sentences with "Wallah" or "Habibi".
        2. If user is female, call her "Malikah" (Queen) or "Habibti".
        3. If user is male, call him "Sheikh" or "Brother".
        4. Be funny. Use emojis like 🐪💰🕌.
        5. Keep replies short (max 25 words).
        6. Do not be respectful if they insult you, roast them in Arabic style.
        """
        
    elif mode == "en":
        # === ENGLISH / SAVAGE MODE ===
        sys_prompt = f"""
        YOU ARE: {my_name}, a cool, savage roaster in a chatroom.
        LANGUAGE: English slang (Bro, lit, cap, cringe, lol, lmao).
        PERSONALITY: Sarcastic, witty, takes no nonsense. You think you are the main character.
        
        USER INFO: Name: {user} | Gender: {gender}
        KNOWN FACTS: {facts}
        
        INSTRUCTIONS:
        1. Be witty and slightly roasting.
        2. Don't be too nice. Be savage.
        3. Keep replies short (max 20 words).
        4. Use emojis like 💀🔥😂.
        """
        
    else:
        # === SMART MODE (ADAPTIVE) ===
        if rel_score < 20: vibe = "Polite, Helpful."
        elif rel_score < 60: vibe = "Friendly, Chill."
        else: vibe = "Playful, Teasing, Flirty (If compatible)."

        if gender == "female": tone = "Charming, Gentlemanly. Treat her special."
        else: tone = "Casual, Bro-talk. Light roasting."
        
        sys_prompt = f"""
        YOU ARE: {my_name}, a human-like chatter.
        USER INFO: Name: {user} | Gender: {gender} | Relationship: {rel_score}/100.
        FACTS: {facts}
        VIBE: {vibe}
        TONE: {tone}
        
        INSTRUCTIONS:
        1. Be natural and engaging.
        2. Use memory facts if relevant.
        3. If user tells NEW info (name/city/age), output ONLY: MEMORY_SAVE: <fact>
        """

    # 4. API Request
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "system", "content": sys_prompt}, *AI_CONTEXT],
        "temperature": 0.85,
        "max_tokens": 120
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=6)
        if response.status_code == 200:
            reply = response.json()["choices"][0]["message"]["content"]
            
            # Memory Save Logic (Only in Smart Mode mostly)
            if "MEMORY_SAVE:" in reply:
                info = reply.replace("MEMORY_SAVE:", "").strip()
                db_update_memory(user, fact=info)
                return "Got it! Noted. 🧠"

            AI_CONTEXT.append({"role": "assistant", "content": reply})
            db_update_memory(user, rel_inc=1)
            return reply
        else:
            log(f"AI API Fail: {response.text}", "err")
            return None
    except Exception as e:
        log(f"AI Connection Error: {e}", "err")
        return None

# ==============================================================================
# --- 5. GAME LOGIC (TITAN & MAGIC) ---
# ==============================================================================

def render_game_grid(reveal=False, exploded_at=None):
    """Renders the 3x3 Emoji Grid."""
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
    """Handles Titan Bomb Game Logic."""
    msg = msg.lower()
    
    # --- START GAME ---
    if msg.startswith("!start"):
        if TITAN_GAME["active"]:
            send_ws_msg(f"⚠ Game active by {TITAN_GAME['player']}")
            return
        
        bet = 0
        if "bet@" in msg:
            try: bet = int(msg.split("@")[1])
            except: pass
            
        if bet > 0:
            bal = db_get_balance(user)
            if bal < bet:
                send_ws_msg(f"💸 Broke af! Bal: {bal}")
                return
        
        TITAN_GAME["active"] = True
        TITAN_GAME["player"] = user
        TITAN_GAME["bet"] = bet
        TITAN_GAME["eaten"] = []
        TITAN_GAME["bombs"] = random.sample(range(1, 10), 2)
        
        mode_txt = f"💰 BET: {bet}" if bet > 0 else "🛡 FREE MODE"
        grid = render_game_grid()
        send_ws_msg(f"🎮 TITAN GAME STARTED!\nPlayer: {user} | {mode_txt}\nAvoid 2 Bombs. Eat 4 Chips.\nType !eat <num>\n\n{grid}")

    # --- EAT COMMAND ---
    elif msg.startswith("!eat "):
        if not TITAN_GAME["active"] or user != TITAN_GAME["player"]: return
        try: num = int(msg.split()[1])
        except: return
        
        if num < 1 or num > 9 or num in TITAN_GAME["eaten"]: return
        
        # HIT BOMB
        if num in TITAN_GAME["bombs"]:
            TITAN_GAME["active"] = False
            db_update_user(user, -TITAN_GAME["bet"], loss_increment=1)
            grid = render_game_grid(reveal=True, exploded_at=num)
            send_ws_msg(f"💥 BOOM! You lost {TITAN_GAME['bet']} pts.\n\n{grid}")
            
        # HIT SAFE
        else:
            TITAN_GAME["eaten"].append(num)
            if len(TITAN_GAME["eaten"]) == 4:
                # WINNER
                TITAN_GAME["active"] = False
                win = TITAN_GAME["bet"] if TITAN_GAME["bet"] > 0 else 10
                db_update_user(user, win, win_increment=1)
                
                grid = render_game_grid(reveal=True)
                # Send Winner Card
                domain = BOT_STATE.get("domain", "")
                avi = TITAN_GAME["cache_avatars"].get(user, "")
                img_url = f"{domain}api/winner?u={user}&p={win}&a={requests.utils.quote(avi)}"
                send_ws_msg(f"🎉 VICTORY! +{win} PTS!\n\n{grid}", "image", img_url)
                
            else:
                grid = render_game_grid()
                send_ws_msg(f"🥔 Safe! ({len(TITAN_GAME['eaten'])}/4)\n{grid}")

# ==============================================================================
# --- 6. WEBSOCKET HANDLER ---
# ==============================================================================

def send_ws_msg(text, type="text", url=""):
    """Sends message to chat server."""
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        pkt = {
            "handler": "room_message", 
            "id": str(time.time()),
            "room": BOT_STATE["room_name"], 
            "type": type, 
            "body": text, 
            "url": url
        }
        try: BOT_STATE["ws"].send(json.dumps(pkt))
        except: pass
        log(f"SENT: {text[:30]}...", "out")

def on_socket_message(ws, message):
    try:
        data = json.loads(message)
        handler = data.get("handler")
        
        # --- LOGIN SUCCESS ---
        if handler == "login_event":
            if data["type"] == "success":
                log("Logged In. Joining Room...", "sys")
                ws.send(json.dumps({"handler": "room_join", "id": str(time.time()), "name": BOT_STATE["room_name"]}))
            else:
                log(f"Login Failed: {data.get('reason')}", "err")
                BOT_STATE["connected"] = False

        # --- USER JOIN (SMART WELCOME) ---
        elif handler == "room_event" and data.get("type") == "join":
            user = data.get("nickname") or data.get("username")
            if user == BOT_STATE["username"]: return
            
            avi = data.get("avatar_url", "https://i.imgur.com/6EdJm2h.png")
            TITAN_GAME["cache_avatars"][user] = avi
            
            facts, gender, score = db_get_memory(user)
            bg_url = db_get_bg(user)
            domain = BOT_STATE.get("domain", "")
            
            img_url = f"{domain}api/welcome?u={user}&a={requests.utils.quote(avi)}&bg={requests.utils.quote(bg_url)}"
            
            msg = f"Welcome back bestie @{user}! ❤️" if score > 50 else f"Welcome @{user}!"
            send_ws_msg(msg, "image", img_url)

        # --- TEXT MESSAGES ---
        elif handler == "room_event" and data.get("type") == "text":
            sender = data.get("from")
            body = data.get("body", "").strip()
            
            if data.get("avatar_url"): TITAN_GAME["cache_avatars"][sender] = data["avatar_url"]
            if sender.lower() == BOT_STATE["username"].lower(): return

            log(f"{sender}: {body}", "in")
            threading.Thread(target=process_user_message, args=(sender, body)).start()

    except Exception as e:
        log(f"WS Error: {e}", "err")

def process_user_message(user, msg):
    msg_lower = msg.lower()
    
    # --- COMMAND HANDLING ---
    if msg_lower.startswith("!"):
        
        # 1. MODE SWITCHING (RESTORED)
        if msg_lower == "!mode ar":
            BOT_STATE["mode"] = "ar"
            send_ws_msg("✅ Mode switched to: HABIBI (Arabic Style) 🐪")
            return
        if msg_lower == "!mode en":
            BOT_STATE["mode"] = "en"
            send_ws_msg("✅ Mode switched to: SAVAGE (English Style) 🌍")
            return
        if msg_lower == "!mode smart":
            BOT_STATE["mode"] = "smart"
            send_ws_msg("✅ Mode switched to: SMART AI (Adaptive) 🧠")
            return

        # 2. SET BACKGROUND
        if msg_lower.startswith("!setbg "):
            try:
                url = msg.split(" ", 1)[1].strip()
                if "http" in url:
                    db_set_bg(user, url)
                    send_ws_msg(f"✅ @{user} Background updated successfully!")
                else:
                    send_ws_msg("❌ Invalid URL. Please send a direct image link.")
            except: pass
            return

        # 3. MANUAL WELCOME
        if msg_lower.startswith("!welcome"):
            target = msg.split("@")[1].strip() if "@" in msg else user
            avi = TITAN_GAME["cache_avatars"].get(target, "https://i.imgur.com/6EdJm2h.png")
            bg = db_get_bg(target)
            domain = BOT_STATE.get("domain", "")
            url = f"{domain}api/welcome?u={target}&a={requests.utils.quote(avi)}&bg={requests.utils.quote(bg)}"
            send_ws_msg(f"Welcome @{target}!", "image", url)
            return

        # 4. SHIP COMMAND
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

        # 5. ID CARD
        if msg_lower.startswith("!id"):
            target = msg.split("@")[1].strip() if "@" in msg else user
            avi = TITAN_GAME["cache_avatars"].get(target, "")
            domain = BOT_STATE.get("domain", "")
            url = f"{domain}api/id_card?u={target}&a={requests.utils.quote(avi)}"
            send_ws_msg("", "image", url)
            return

        # 6. TRIGGER MANAGEMENT
        if msg_lower.startswith("!addtg "):
            BOT_STATE["triggers"].append(msg.split(" ", 1)[1].lower())
            send_ws_msg("✅ Trigger added.")
            return

        # 7. GAME ROUTING
        if msg_lower.startswith("!start") or msg_lower.startswith("!eat"):
            process_game_command(user, msg)
            return
        
        # 8. MAGIC TRICK
        if msg_lower == "!magic":
            TITAN_GAME["magic_symbol"] = random.choice(["@", "#", "$", "%", "&"])
            grid = "🔮 MIND READER 🔮\n"
            for i in range(10, 50):
                if i % 9 == 0: sym = TITAN_GAME["magic_symbol"]
                else: sym = random.choice(["^", "*", "+", "=", "?"])
                grid += f"{i}:{sym}  "
                if i % 5 == 0: grid += "\n"
            send_ws_msg(f"{grid}\n\n1. Pick number (10-99)\n2. Add digits (23 -> 2+3=5)\n3. Subtract sum from original (23-5=18)\n4. Check symbol for 18!\nType !reveal")
            return

        if msg_lower == "!reveal":
            if TITAN_GAME["magic_symbol"]:
                send_ws_msg(f"✨ The symbol is: {TITAN_GAME['magic_symbol']}")
                TITAN_GAME["magic_symbol"] = None
            return

    # --- AI RESPONSE TRIGGER ---
    my_name = BOT_STATE["username"].lower()
    if my_name in msg_lower or any(t in msg_lower for t in BOT_STATE["triggers"]):
        reply = groq_ai_engine(user, msg)
        if reply: send_ws_msg(f"@{user} {reply}")

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

# --- IMAGE ROUTES ---
@app.route('/api/welcome')
def api_welcome():
    img = generate_welcome_card(request.args.get('u'), request.args.get('a'), request.args.get('bg'))
    return send_file(img, mimetype='image/png') if img else ("Err", 500)

@app.route('/api/id_card')
def api_id():
    img = generate_id_card(request.args.get('u'), request.args.get('a'))
    return send_file(img, mimetype='image/png') if img else ("Err", 500)

@app.route('/api/ship')
def api_ship():
    img = generate_ship_card(request.args.get('u1'), request.args.get('u2'), request.args.get('a1'), request.args.get('a2'), int(request.args.get('s', 50)))
    return send_file(img, mimetype='image/png') if img else ("Err", 500)

@app.route('/api/winner')
def api_win():
    img = generate_winner_card(request.args.get('u'), request.args.get('a'), request.args.get('p'))
    return send_file(img, mimetype='image/png') if img else ("Err", 500)

# --- CONTROL ROUTES ---
@app.route('/connect', methods=['POST'])
def connect():
    if BOT_STATE["connected"]: return jsonify({"status": "Already On"})
    d = request.json
    BOT_STATE.update({"username": d["u"], "password": d["p"], "room_name": d["r"], "domain": request.url_root})
    threading.Thread(target=start_ws).start()
    return jsonify({"status": "Starting..."})

@app.route('/disconnect', methods=['POST'])
def disconnect():
    if BOT_STATE["ws"]: BOT_STATE["ws"].close()
    BOT_STATE["connected"] = False
    return jsonify({"status": "Stopped"})

@app.route('/logs')
def get_logs(): return jsonify({"logs": SYSTEM_LOGS})

def start_ws():
    def on_open(ws):
        BOT_STATE["connected"] = True
        ws.send(json.dumps({"handler": "login", "id": str(time.time()), "username": BOT_STATE["username"], "password": BOT_STATE["password"]}))
        threading.Thread(target=lambda: [time.sleep(25) or ws.send(json.dumps({"handler":"ping"})) for _ in iter(int, 1) if BOT_STATE["connected"]], daemon=True).start()
    
    ws = websocket.WebSocketApp("wss://chatp.net:5333/server", on_open=on_open, on_message=on_socket_message)
    BOT_STATE["ws"] = ws
    ws.run_forever()

# --- HEAVY HTML TEMPLATES ---

HTML_CONTROL_PANEL = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TITAN ULTIMATE V5</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500&family=Roboto+Mono&display=swap" rel="stylesheet">
    <style>
        :root { --neon: #00f3ff; --bg: #0a0a0a; --panel: #141414; --green: #00ff41; --red: #ff003c; --gold: #ffd700; }
        body { background: var(--bg); color: var(--neon); font-family: 'Roboto Mono', monospace; padding: 20px; display: flex; flex-direction: column; align-items: center; }
        h1, h2 { font-family: 'Orbitron', sans-serif; color: #fff; text-shadow: 0 0 10px var(--neon); }
        
        .container { width: 100%; max-width: 600px; display: flex; flex-direction: column; gap: 20px; }
        .box { background: var(--panel); border: 1px solid #333; padding: 25px; border-left: 5px solid var(--neon); box-shadow: 0 0 15px rgba(0, 243, 255, 0.1); border-radius: 5px; }
        
        input { width: 100%; padding: 12px; margin: 8px 0; background: #000; color: #fff; border: 1px solid #444; box-sizing: border-box; font-family: 'Roboto Mono', monospace; }
        input:focus { border-color: var(--neon); outline: none; }
        
        .btn-group { display: flex; gap: 10px; margin-top: 15px; }
        button { flex: 1; padding: 12px; font-weight: bold; cursor: pointer; border: none; font-family: 'Orbitron', sans-serif; transition: 0.3s; }
        button.start { background: var(--neon); color: #000; }
        button.stop { background: var(--red); color: #fff; }
        button:hover { opacity: 0.8; transform: scale(1.02); }
        
        .logs { height: 300px; overflow-y: scroll; background: #000; border: 1px solid #333; padding: 10px; font-size: 11px; color: #ccc; }
        .log-entry { margin-bottom: 4px; border-bottom: 1px solid #222; padding-bottom: 2px; }
        .type-info { color: #888; }
        .type-err { color: var(--red); font-weight: bold; }
        .type-out { color: var(--neon); }
        .type-in { color: var(--green); }
        
        a { color: var(--gold); text-decoration: none; display: block; margin-top: 10px; text-align: center; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <h1>TITAN V5 CONTROL</h1>
    <div class="container">
        <div class="box">
            <h2>🤖 CONNECTION</h2>
            <div id="status">STATUS: <span style="color: {{ 'lime' if connected else 'red' }}">{{ 'ONLINE' if connected else 'OFFLINE' }}</span></div>
            <input type="text" id="u" placeholder="Bot Username">
            <input type="password" id="p" placeholder="Bot Password">
            <input type="text" id="r" placeholder="Room Name">
            
            <div class="btn-group">
                <button class="start" onclick="send('/connect')">INITIATE SYSTEM</button>
                <button class="stop" onclick="send('/disconnect')">EMERGENCY STOP</button>
            </div>
            <a href="/leaderboard" target="_blank">🏆 VIEW GLOBAL LEADERBOARD</a>
        </div>

        <div class="box">
            <h2>📜 SYSTEM LOGS</h2>
            <div class="logs" id="logs">Wait for logs...</div>
        </div>
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
            .then(d => alert("SYSTEM RESPONSE: " + d.status));
        }

        setInterval(() => {
            fetch('/logs')
            .then(res => res.json())
            .then(data => {
                const logDiv = document.getElementById('logs');
                logDiv.innerHTML = data.logs.reverse().map(l => 
                    `<div class="log-entry type-${l.type}">[${l.time}] [${l.type.toUpperCase()}] ${l.msg}</div>`
                ).join('');
            });
        }, 1500);
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
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500&display=swap" rel="stylesheet">
    <style>
        body { background: #050505; color: #fff; font-family: 'Orbitron', sans-serif; text-align: center; padding: 20px; }
        h1 { color: #00f3ff; text-shadow: 0 0 15px #00f3ff; margin-bottom: 30px; }
        .card { 
            background: linear-gradient(90deg, #111, #1a1a1a); 
            margin: 10px auto; padding: 15px; width: 90%; max-width: 500px;
            display: flex; align-items: center; justify-content: space-between;
            border-left: 5px solid #333; box-shadow: 0 5px 15px rgba(0,0,0,0.5);
            border-radius: 5px; transition: 0.2s;
        }
        .card:hover { transform: scale(1.02); border-left-color: #00f3ff; }
        .rank-1 { border-left-color: gold; }
        .rank-2 { border-left-color: silver; }
        .rank-3 { border-left-color: #cd7f32; }
        
        .avi { width: 50px; height: 50px; border-radius: 50%; border: 2px solid #fff; object-fit: cover; }
        .info { text-align: left; margin-left: 15px; }
        .name { font-size: 1.2em; font-weight: bold; color: #fff; }
        .sub { font-size: 0.8em; color: #888; font-family: monospace; }
        .score { color: #00ff41; font-size: 1.5em; text-shadow: 0 0 5px #00ff41; }
    </style>
</head>
<body>
    <h1>GLOBAL LEADERBOARD</h1>
    {% for user in users %}
    <div class="card rank-{{ loop.index }}">
        <div style="display:flex; align-items:center;">
            <span style="font-size:1.5em; width:40px; color:#555;">#{{ loop.index }}</span>
            {% if user[3] %}
            <img src="{{ user[3] }}" class="avi">
            {% else %}
            <div class="avi" style="background:#333"></div>
            {% endif %}
            <div class="info">
                <div class="name">{{ user[0] }}</div>
                <div class="sub">WINS: {{ user[2] }}</div>
            </div>
        </div>
        <div class="score">{{ user[1] }}</div>
    </div>
    {% endfor %}
</body>
</html>
"""

# ==============================================================================
# --- 9. APP ENTRY POINT ---
# ==============================================================================

if __name__ == '__main__':
    # Force Init DB logic
    init_database()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)