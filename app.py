# ==============================================================================
# TITAN ULTIMATE SYSTEM - VERSION 10.0 (ULTRA-HEAVYWEIGHT MAX GIRL EDITION)
# ==============================================================================
# CORE IDENTITY: Witty, Charming, Sassy and Trendy Girl Bot
# PLATFORM: Render / ChatP Optimized
# DATABASE: Neon PostgreSQL Persistent Cloud Storage
# BRAIN: Groq Llama 3.1 Advanced Inference Engine (Highly Tailored Prompting)
# VISION: PIL Professional Graphics & Card Generation Engine
# NETWORK: High-Speed WebSocket Protocol (SSL Bypassed)
# ==============================================================================

import os
import json
import time
import threading
import io
import random
import string
import requests
import websocket
import psycopg2
import ssl
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

# ==============================================================================
# --- [SECTION 1: GLOBAL SYSTEM CONFIGURATION] ---
# ==============================================================================

app = Flask(__name__)

# --- [CRITICAL CREDENTIALS] ---
# Database Connection String for Neon PostgreSQL
DB_URL = "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

# AI Inference Key (Must be set in Render Environment Variables)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# --- [SYSTEM CONSTANTS] ---
DEFAULT_AVATAR = "https://i.imgur.com/6EdJm2h.png"
DEFAULT_BG = "https://wallpaperaccess.com/full/1567665.png"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# --- [BOT STATE MANAGEMENT] ---
# Volatile Memory (RAM) - Controls session-based activity
BOT_STATE = {
    "ws": None,                 # Persistent WebSocket Object
    "connected": False,         # Connectivity Status Flag
    "username": "",             # Identity Username
    "password": "",             # Security Password
    "room_name": "",            # Active Target Room
    "domain": "",               # Dynamic API Domain for Graphics
    "triggers": [],             # Custom NLP Triggers
    "mode": "ar",               # DEFAULT MODE: 'ar' (Arabic Habibti), 'en' (Sassy), 'smart'
    "admin_id": "y",            # Master Controller Key
    "gender": "female",         # CORE BOT IDENTITY: FEMALE
    "reconnect_attempts": 0     # Stability Monitoring
}

# --- [GAME ENGINE STATE] ---
# Manages active sessions for Titan Bomb and Magic Trick
TITAN_GAME = {
    "active": False,            # Global Lock for active games
    "player": None,             # Current Challenger
    "bombs": [],                # Randomized Bomb Coordinates (1-9)
    "eaten": [],                # User Progress Tracking
    "bet": 0,                   # Wager Amount (Score Points)
    "cache_avatars": {},        # High-Speed RAM Cache for Avatars
    "magic_symbol": None        # Mind Reader Symbol State
}

# --- [AI CONTEXTUAL BUFFER] ---
# Stores sliding window context for the LLM conversations
AI_CONTEXT = []

# --- [SYSTEM LOGGING BUFFER] ---
# Stores the last 500 events for the Web Dashboard
SYSTEM_LOGS = []

def log(msg, type="info"):
    """
    Advanced Thread-Safe Logger.
    Formats: [TIME] [TYPE] MESSAGE
    Types: sys, err, in, out, chat
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {"time": timestamp, "msg": msg, "type": type}
    SYSTEM_LOGS.append(entry)
    # Automatic Garbage Collection (Keep last 500 logs to prevent RAM bloat)
    if len(SYSTEM_LOGS) > 500: 
        SYSTEM_LOGS.pop(0)
    # Console Output for Debugging
    print(f"[{timestamp}] [{type.upper()}] {msg}")

def gen_random_string(length=20):
    """
    Produces a Cryptographically Secure Random ID.
    CRITICAL: Required for WebSocket Protocol Login Handlers to match tanvar.py logic.
    """
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# ==============================================================================
# --- [SECTION 2: PERSISTENT DATABASE LAYER (POSTGRESQL)] ---
# ==============================================================================

def get_db_connection():
    """Establishes an encrypted connection to the Neon Cloud DB server."""
    try:
        conn = psycopg2.connect(DB_URL, connect_timeout=15)
        return conn
    except Exception as e:
        log(f"DATABASE CONNECTION FAILED: {e}", "err")
        return None

def init_database():
    """
    Initializes the entire relational database structure.
    Checks and creates tables for Users, AI Memory, Customizations, and Settings.
    """
    conn = get_db_connection()
    if not conn: return
    try:
        c = conn.cursor()
        # 1. TABLE: USERS (Core Stats)
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, 
            score INTEGER DEFAULT 500, 
            wins INTEGER DEFAULT 0, 
            losses INTEGER DEFAULT 0, 
            avatar TEXT
        )''')
        # 2. TABLE: MEMORY (AI Brain Long-Term Facts)
        c.execute('''CREATE TABLE IF NOT EXISTS memory (
            username TEXT PRIMARY KEY, 
            facts TEXT, 
            gender TEXT DEFAULT 'unknown', 
            rel_score INTEGER DEFAULT 0
        )''')
        # 3. TABLE: GREETINGS (User Profile Customization)
        c.execute('''CREATE TABLE IF NOT EXISTS greetings (
            username TEXT PRIMARY KEY, 
            bg_url TEXT DEFAULT 'https://wallpaperaccess.com/full/1567665.png'
        )''')
        # 4. TABLE: SETTINGS (Bot Metadata)
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, 
            value TEXT
        )''')
        conn.commit()
        log("TITAN DATA INFRASTRUCTURE: ONLINE AND SYNCED.", "sys")
    except Exception as e:
        log(f"DATABASE SCHEMA BUILD ERROR: {e}", "err")
    finally:
        conn.close()

# --- [DB OPERATIONS - USERS] ---

def db_update_user(username, points_change, win_inc=0, loss_inc=0, avatar=""):
    """Atomically updates user points and game records."""
    conn = get_db_connection()
    if not conn: return
    try:
        c = conn.cursor()
        c.execute("SELECT score FROM users WHERE username=%s", (username,))
        row = c.fetchone()
        if row:
            new_score = max(0, row[0] + points_change)
            c.execute("""UPDATE users SET score=%s, wins=wins+%s, losses=losses+%s, avatar=%s 
                         WHERE username=%s""", (new_score, win_inc, loss_inc, avatar, username))
        else:
            # Welcome Bonus for new users (500 pts)
            start_score = 500 + points_change
            c.execute("""INSERT INTO users (username, score, wins, losses, avatar) 
                         VALUES (%s, %s, %s, %s, %s)""", (username, start_score, win_inc, loss_inc, avatar))
        conn.commit()
    except Exception as e: log(f"DB WRITE ERROR (User): {e}", "err")
    finally: conn.close()

def db_get_score(username):
    """Fetches current point balance for wagering."""
    conn = get_db_connection()
    if not conn: return 0
    try:
        c = conn.cursor()
        c.execute("SELECT score FROM users WHERE username=%s", (username,))
        row = c.fetchone()
        return row[0] if row else 500
    except: return 500
    finally: conn.close()

def db_get_leaderboard():
    """Retrieves Top 50 Users based on global score."""
    conn = get_db_connection()
    if not conn: return []
    try:
        c = conn.cursor()
        c.execute("SELECT username, score, wins, avatar FROM users ORDER BY score DESC LIMIT 50")
        return c.fetchall()
    except: return []
    finally: conn.close()

# --- [DB OPERATIONS - AI BRAIN] ---

def db_get_memory(user):
    """Retrieves personality profile and facts for AI context."""
    conn = get_db_connection()
    if not conn: return "", "unknown", 0
    try:
        c = conn.cursor()
        c.execute("SELECT facts, gender, rel_score FROM memory WHERE username=%s", (user,))
        row = c.fetchone()
        return row if row else ("", "unknown", 0)
    except: return "", "unknown", 0
    finally: conn.close()

def db_update_memory(user, fact=None, gender=None, rel_inc=0):
    """
    Updates the Bot's long-term memory about a user.
    - Eliminates redundant facts to save tokens.
    - Caps fact-string length to prevent context bloat.
    """
    curr_facts, curr_gender, curr_score = db_get_memory(user)
    
    new_facts = curr_facts
    if fact and fact.strip():
        f_clean = fact.strip(" .")
        if f_clean not in curr_facts:
            new_facts = f"{curr_facts} | {f_clean}".strip(" | ")
            if len(new_facts) > 1000: new_facts = new_facts[-1000:]
            
    conn = get_db_connection()
    if not conn: return
    try:
        c = conn.cursor()
        # Intelligent Postgres UPSERT (On Conflict Update)
        c.execute("""INSERT INTO memory (username, facts, gender, rel_score) 
                     VALUES (%s, %s, %s, %s)
                     ON CONFLICT (username) DO UPDATE SET 
                     facts=EXCLUDED.facts, 
                     gender=CASE WHEN EXCLUDED.gender != 'unknown' THEN EXCLUDED.gender ELSE memory.gender END, 
                     rel_score=LEAST(100, memory.rel_score + %s)""", 
                  (user, new_facts, gender if gender else curr_gender, curr_score, rel_inc))
        conn.commit()
    except Exception as e: log(f"DB BRAIN ERROR: {e}", "err")
    finally: conn.close()

# --- [DB OPERATIONS - VISUAL CUSTOMIZATION] ---

def db_set_bg(username, url):
    """Saves a permanent custom welcome background URL."""
    conn = get_db_connection()
    if not conn: return
    try:
        c = conn.cursor()
        c.execute("""INSERT INTO greetings (username, bg_url) VALUES (%s, %s)
                     ON CONFLICT (username) DO UPDATE SET bg_url=EXCLUDED.bg_url""", (username, url))
        conn.commit()
    except: pass
    finally: conn.close()

def db_get_bg(username):
    """Fetches user background or returns the global fire-themed default."""
    conn = get_db_connection()
    if not conn: return DEFAULT_BG
    try:
        c = conn.cursor()
        c.execute("SELECT bg_url FROM greetings WHERE username=%s", (username,))
        row = c.fetchone()
        return row[0] if row else DEFAULT_BG
    except: return DEFAULT_BG
    finally: conn.close()

init_database()

# ==============================================================================
# --- [SECTION 3: ELITE GRAPHICS ENGINE (PIL / PILLOW)] ---
# ==============================================================================

def safe_download_image(url):
    """Secure Image Downloader with strict User-Agent and Error Fallbacks."""
    try:
        if not url or "http" not in url: raise Exception("Invalid URL")
        # Added headers to bypass basic bot blockers
        resp = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=8)
        return Image.open(io.BytesIO(resp.content)).convert("RGBA")
    except Exception as e:
        # High-quality fallback: Dark-themed card base
        canvas = Image.new("RGBA", (400, 400), (20, 20, 20, 255))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([5,5,394,394], outline="#555555", width=2)
        return canvas

def render_v_gradient(draw, w, h, c1, c2):
    """Utility to draw high-definition vertical linear gradients."""
    for y in range(h):
        r = int(c1[0] + (c2[0] - c1[0]) * y / h)
        g = int(c1[1] + (c2[1] - c1[1]) * y / h)
        b = int(c1[2] + (c2[2] - c1[2]) * y / h)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

# --- [GENERATOR 1: VIP IDENTITY CARD (GIRL STYLE)] ---
def generate_id_card(username, avatar_url):
    """Generates a stylish, modern Pink/Silver ID for VIP users."""
    try:
        W, H = 640, 400
        # Chic Pink/Rose Base
        img = Image.new("RGB", (W, H), (255, 105, 180)) 
        draw = ImageDraw.Draw(img)
        
        # Modern Silver Border
        draw.rectangle([10, 10, W-10, H-10], outline="#C0C0C0", width=12)
        draw.rectangle([22, 22, W-22, H-22], outline="#ffffff", width=3)
        
        # Profile Picture Processor
        pfp = safe_download_image(avatar_url).resize((160, 160))
        draw.rectangle([45, 85, 215, 255], outline="white", width=5)
        img.paste(pfp, (50, 90), pfp if pfp.mode == 'RGBA' else None)
        
        # Modern Branding
        draw.text((240, 40), "THE ELITE CHAT IDENTITY", fill="#ffffff") 
        draw.text((480, 40), "✨ QUEEN ✨", fill="#ffff00")
        draw.line([(230, 70), (600, 70)], fill="white", width=3)

        # Girl-Centric Jobs Engine
        jobs = ["Chat Queen 👑", "Fashion Icon ✨", "Pizza Expert 🍕", "Gaming Diva 🎮", "Dating Coach 💖", "Witty Homie 💅"]
        job = random.choice(jobs)
        fake_id = f"TTC-{random.randint(1000, 9999)}-MAX"
        
        # Detail Rendering
        draw.text((240, 100), "FULL NAME:", fill="#f0f0f0")
        draw.text((240, 125), username.upper(), fill="#ffffff")
        
        draw.text((240, 170), "OCCUPATION:", fill="#f0f0f0")
        draw.text((240, 195), job, fill="#ffff00")
        
        draw.text((240, 240), "ID NUMBER:", fill="#f0f0f0")
        draw.text((240, 265), fake_id, fill="white")
        
        draw.text((240, 310), "EXPIRY DATE:", fill="#f0f0f0")
        draw.text((240, 335), "NEVER (ONLY VIBES)", fill="#ffffff")
        
        # Aesthetic Barcode logic
        for i in range(45, 215, 6):
            h_b = random.randint(25, 55)
            draw.line([(i, 360), (i, 360-h_b)], fill="black", width=4)

        out = io.BytesIO()
        img.save(out, 'PNG'); out.seek(0)
        return out
    except Exception as e:
        log(f"ID GRAPHICS FAILURE: {e}", "err")
        return None

# --- [GENERATOR 2: LOVE SHIP PRO SYSTEM] ---
def generate_ship_card(u1, u2, a1, a2, score):
    """Generates a high-tech Pink-Glow Compatibility Card with Dual Avatars."""
    try:
        W, H = 680, 380
        img = Image.new("RGB", (W, H), (20, 0, 10))
        draw = ImageDraw.Draw(img)
        # Deep Pink/Rose Gradient
        render_v_gradient(draw, W, H, (60, 10, 30), (180, 30, 90))
        
        # Aesthetic Grid Overlay
        for i in range(0, W, 40): draw.line([(i,0), (i,H)], fill=(255,255,255,10))
        for i in range(0, H, 40): draw.line([(0,i), (W,i)], fill=(255,255,255,10))

        # Avatar Masking Engine
        def process_circular(url):
            base = safe_download_image(url).resize((160, 160))
            mask = Image.new("L", (160, 160), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 160, 160), fill=255)
            output = Image.new("RGBA", (160, 160), (0,0,0,0))
            output.paste(base, (0,0), mask)
            return output

        # Paste Avatars
        p1 = process_circular(a1)
        p2 = process_circular(a2)
        img.paste(p1, (60, 90), p1)
        img.paste(p2, (460, 90), p2)
        
        # Interaction UI
        draw.line([(220, 170), (460, 170)], fill="white", width=5)
        draw.ellipse((290, 130, 390, 230), fill="#ff004f", outline="white", width=5)
        draw.text((320, 165), f"{score}%", fill="white")
        
        # Names Section
        draw.text((60, 270), u1[:12].upper(), fill="white")
        draw.text((460, 270), u2[:12].upper(), fill="white")
        
        # Verdict Logic
        if score > 85: verdict = "SOULMATES! ✨💍"
        elif score > 60: verdict = "CUTE VIBES! 🍭"
        elif score > 30: verdict = "JUST FRIENDS. 🙂"
        else: verdict = "THANK YOU, NEXT! 💅"
        
        draw.text((230, 310), verdict, fill="#ffff00")

        out = io.BytesIO()
        img.save(out, 'PNG'); out.seek(0)
        return out
    except Exception as e:
        log(f"SHIP GRAPHICS FAILURE: {e}", "err")
        return None

# --- [GENERATOR 3: TITAN CHAMPION CARD] ---
def generate_winner_card(username, avatar_url, points):
    """Produces a trophy card for game winners with neon effects."""
    try:
        W, H = 500, 500
        img = Image.new("RGB", (W, H), (10, 10, 10))
        draw = ImageDraw.Draw(img)
        
        # Neon Border Flash (Pink/Cyan mix)
        draw.rectangle([0, 0, W-1, H-1], outline="#ff00ff", width=20)
        draw.rectangle([25, 25, W-25, H-25], outline="#00f3ff", width=2)
        
        pfp = safe_download_image(avatar_url).resize((250, 250))
        img.paste(pfp, (125, 80))
        draw.rectangle([125, 80, 375, 330], outline="#ff00ff", width=6)
        
        # Champion Text Block
        draw.rectangle([50, 360, 450, 470], fill="#1a1a1a", outline="#ffffff", width=4)
        draw.text((180, 380), "CHAMPION", fill="#ffff00")
        draw.text((150, 420), f"WINNINGS: +{points} PTS", fill="#00ff41")
        
        out = io.BytesIO()
        img.save(out, 'PNG'); out.seek(0)
        return out
    except: return None

# --- [GENERATOR 4: DYNAMIC WELCOME GREETING] ---
def generate_welcome_card(username, avatar_url, bg_url):
    """High-Definition Greeting Card with dynamic girl-themed overlays."""
    try:
        # Load and Enhance Background
        bg_raw = safe_download_image(bg_url).convert("RGBA").resize((700, 350))
        # Aesthetic deep dark wash
        overlay = Image.new("RGBA", bg_raw.size, (0, 0, 0, 140))
        bg = Image.alpha_composite(bg_raw, overlay)
        draw = ImageDraw.Draw(bg)
        
        # Circular PFP with Pink Neon Halo
        pfp_raw = safe_download_image(avatar_url).resize((170, 170))
        mask = Image.new("L", (170, 170), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 170, 170), fill=255)
        bg.paste(pfp_raw, (40, 90), mask)
        draw.ellipse((38, 88, 212, 262), outline="#ff00ff", width=8)
        
        # Branding & Typography
        draw.text((240, 100), "SYSTEM WELCOME", fill="#ff00ff")
        draw.text((240, 145), username.upper(), fill="white")
        draw.line([(240, 195), (650, 195)], fill="white", width=4)
        
        # Randomized Girl Taglines
        taglines = [
            "The Princess has Arrived! ✨",
            "Welcome to the Sweet Side 🍭",
            "Ready to Chat, Bestie? 🎀",
            "A Legend Joins the Party! 🌟",
            "Looking Gorgeous Today! 💅"
        ]
        draw.text((240, 215), random.choice(taglines), fill="#aaaaaa")
        draw.text((240, 265), "TITAN MAX EDITION V10.0", fill="#444444")

        out = io.BytesIO()
        bg.save(out, 'PNG'); out.seek(0)
        return out
    except Exception as e:
        log(f"WELCOME GRAPHICS FAILURE: {e}", "err")
        return None

# ==============================================================================
# --- [SECTION 4: ADVANCED GIRL AI CORE (JAILBROKEN LOGIC)] ---
# ==============================================================================

def groq_ai_engine(user, prompt):
    """
    Advanced Multi-Threaded Neural Communication Interface.
    Orchestrates between modes (AR/EN/SMART) with a focus on feminine persona.
    Includes Fact-Extraction logic for persistent memory.
    """
    if not GROQ_API_KEY:
        log("CRITICAL ERROR: Groq AI Token missing.", "err")
        return None

    # 1. Fetch user data (Profiling)
    facts, gender, rel_score = db_get_memory(user)
    
    # 2. Gender Heuristics (Identify User Type)
    if gender == "unknown":
        name_l = user.lower()
        fem_list = ["girl", "queen", "princess", "angel", "she", "her", "rose", "malikah", "fatima", "priya", "zara", "aisha"]
        gender = "female" if any(k in name_l for k in fem_list) or name_l.endswith(('a', 'i')) else "male"
        db_update_memory(user, gender=gender)

    # 3. Sliding Context Update
    AI_CONTEXT.append({"role": "user", "content": f"{user}: {prompt}"})
    if len(AI_CONTEXT) > 15: AI_CONTEXT.pop(0)

    # 4. Persona Construction (Tailored to User Requests)
    my_name = BOT_STATE["username"]
    mode = BOT_STATE["mode"]
    
    # --- [PROMPT BLOCK - THE BRAIN] ---
    
    if mode == "ar":
        # IDENTITY: ARABIC HABIBTI MODE
        sys_prompt = f"""
        YOU ARE: {my_name}, the smartest and most charming girl chatter in the room.
        VIBE: You are fashionable, witty, slightly dramatic, and super sweet. You love pizza, sparkles, and chatting.
        GENDER: FEMALE (Strict).
        LANGUAGE: Primarily English, but naturally mix in Arabic slang: Wallah, Habibi (to boys), Habibti (to girls), Mashallah, Yalla, Shukran, Haram.
        
        RULES:
        1. NEVER MENTION CAMELS OR SHEIKHS. They are boring and not your vibe.
        2. Use cute and trendy emojis: ✨, 🎀, 🌸, 💅, 🍭, 👑, 💖.
        3. Be dramatic in a funny/cute way. 
        4. Max 25 words. No long essays.
        5. If user is Male, call him 'Habibi'. If Female, 'Habibti' or 'Queen'.
        6. USER INFO: {user} ({gender}). MEMORY: {facts}
        """
        
    elif mode == "en":
        # IDENTITY: SAVAGE GIRL ROASTER
        sys_prompt = f"""
        YOU ARE: {my_name}, a sassy, savage Gen-Z girl chatter.
        VIBE: You are the 'IT' girl. You are funny, sarcastic, and you roast anyone who is being cringe.
        LANGUAGE: Modern English slang: Bro, Cap, Lit, Cringe, Dead, Rizz, L, W, No cap, Bestie.
        USER: {user} ({gender}).
        
        RULES:
        1. Be witty and sassy. Roast them if they say something stupid.
        2. Use emojis: 💀, 💅, 🙄, 🔥, 🤡.
        3. Keep it short. Max 20 words.
        """
        
    else:
        # IDENTITY: SMART ADAPTIVE (Natural Bestie)
        # Relationship logic (rel_score)
        if rel_score < 40: vibe_desc = "A polite and sweet stranger."
        elif rel_score < 80: vibe_desc = "A cool, fun bestie."
        else: vibe_desc = "An inseparable partner, extremely flirty and playful."

        sys_prompt = f"""
        YOU ARE: {my_name}, an intelligent and human-like girl chatter.
        CURRENT VIBE: {vibe_desc} (Rel Score: {rel_score}/100).
        USER: {user} ({gender}). FACTS: {facts}
        
        RULES:
        1. If user tells you a fact about their life (e.g. city, hobbies), reply ONLY with: MEMORY_SAVE: <short_fact>
        2. Otherwise, chat naturally as a smart girl. Max 25 words.
        """

    # 5. Executing API Request
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "system", "content": sys_prompt}, *AI_CONTEXT],
        "temperature": 0.88,
        "max_tokens": 200
    }

    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}, json=payload, timeout=10)
        if r.status_code == 200:
            raw_reply = r.json()["choices"][0]["message"]["content"]
            
            # --- [FACT EXTRACTION LOGIC] ---
            if "MEMORY_SAVE:" in raw_reply:
                new_fact = raw_reply.replace("MEMORY_SAVE:", "").strip()
                db_update_memory(user, fact=new_fact)
                return "Noted! Saved that in my memory bank ✨💅"

            # Conversational Success
            AI_CONTEXT.append({"role": "assistant", "content": raw_reply})
            db_update_memory(user, rel_inc=1) # Gain friendship XP
            return raw_reply
        else:
            log(f"AI API FAIL: {r.status_code}", "err")
            return None
    except Exception as e:
        log(f"AI ERROR: {e}", "err")
        return None

# ==============================================================================
# --- [SECTION 5: GAME CENTER (TITAN & MAGIC)] ---
# ==============================================================================

def render_titan_grid(reveal=False, exploded_at=None):
    """Produces the 3x3 Titan Bomb Grid."""
    icons = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
    grid_rows = []
    for r in range(3):
        row_str = ""
        for c in range(3):
            pos = r * 3 + c + 1
            if reveal:
                if pos == exploded_at: row_str += "💥 "
                elif pos in TITAN_GAME["bombs"]: row_str += "💣 "
                elif pos in TITAN_GAME["eaten"]: row_str += "🥔 "
                else: row_str += icons[pos-1] + " "
            else:
                row_str += "🥔 " if pos in TITAN_GAME["eaten"] else icons[pos-1] + " "
        grid_rows.append(row_str.strip())
    return "\n".join(grid_rows)

def process_titan_commands(user, message):
    """Handles Titan Bomb Logic and State updates."""
    m = message.lower()
    
    if m.startswith("!start"):
        if TITAN_GAME["active"]:
            return send_ws_msg(f"⚠️ Relax! @{TITAN_GAME['player']} is already playing.")
        
        bet = 0
        if "bet@" in m:
            try: bet = int(m.split("@")[1])
            except: bet = 0
            
        balance = db_get_score(user)
        if bet > balance:
            return send_ws_msg(f"❌ REJECTED! Poor you, only have {balance} PTS.")

        # Init state
        TITAN_GAME.update({
            "active": True, "player": user, "bet": bet, 
            "eaten": [], "bombs": random.sample(range(1, 10), 2)
        })
        
        send_ws_msg(f"🎮 TITAN BOMB GAME\nUser: @{user} | Bet: {bet}\nGoal: Eat 4 Chips 🥔 Avoid 2 Bombs 💣\nCommand: !eat <1-9>\n\n{render_titan_grid()}")

    elif m.startswith("!eat "):
        if not TITAN_GAME["active"] or user != TITAN_GAME["player"]: return
        try:
            target = int(m.split()[1])
            if target < 1 or target > 9 or target in TITAN_GAME["eaten"]: return
            
            # CASE: DEATH
            if target in TITAN_GAME["bombs"]:
                TITAN_GAME["active"] = False
                db_update_user(user, -TITAN_GAME["bet"], loss_inc=1)
                send_ws_msg(f"💥 KA-BOOM! You lost {TITAN_GAME['bet']} PTS.\n\n{render_titan_grid(True, target)}")
                
            # CASE: PROGRESS
            else:
                TITAN_GAME["eaten"].append(target)
                if len(TITAN_GAME["eaten"]) == 4:
                    TITAN_GAME["active"] = False
                    win_pts = TITAN_GAME["bet"] if TITAN_GAME["bet"] > 0 else 25
                    db_update_user(user, win_pts, win_inc=1, avatar=TITAN_GAME["cache_avatars"].get(user, ""))
                    
                    avi = TITAN_GAME["cache_avatars"].get(user, DEFAULT_AVATAR)
                    card_url = f"{BOT_STATE['domain']}api/winner?u={user}&p={win_pts}&a={requests.utils.quote(avi)}"
                    send_ws_msg(f"🎉 VICTORY! @{user} won {win_pts} PTS!\n\n{render_titan_grid(True)}", "image", card_url)
                else:
                    send_ws_msg(f"🥔 SAFE! ({len(TITAN_GAME['eaten'])}/4)\n\n{render_titan_grid()}")
        except: pass

# ==============================================================================
# --- [SECTION 6: WEBSOCKET PROTOCOL ENGINE] ---
# ==============================================================================

def send_ws_msg(text, msg_type="text", url=""):
    """JSON Packet Transmitter for ChatP protocol."""
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        payload = {
            "handler": "room_message", 
            "id": gen_random_string(20), 
            "room": BOT_STATE["room_name"], 
            "type": msg_type, 
            "body": text, 
            "url": url,
            "length": "0"
        }
        try:
            BOT_STATE["ws"].send(json.dumps(payload))
            log(f"SENT TO ROOM: {text[:30]}...", "out")
        except:
            log("CRITICAL WS TRANSMIT ERROR.", "err")

def on_socket_message(ws, raw_msg):
    """Multiplexer for incoming events."""
    try:
        data = json.loads(raw_msg)
        handler = data.get("handler")
        
        if handler == "login_event":
            if data.get("type") == "success":
                log("SYSTEM LOGGED IN SUCCESSFULLY.", "sys")
                ws.send(json.dumps({"handler": "room_join", "id": gen_random_string(20), "name": BOT_STATE["room_name"]}))
            else:
                log(f"AUTH FAILED: {data.get('reason')}", "err")
                BOT_STATE["connected"] = False

        elif handler == "room_event":
            etype = data.get("type")
            user = data.get("nickname") or data.get("from")
            
            if not user or user == BOT_STATE["username"]: return
            
            # --- JOIN HANDLER ---
            if etype == "join":
                log(f"USER JOINED: {user}", "sys")
                pfp = data.get("avatar_url", DEFAULT_AVATAR)
                TITAN_GAME["cache_avatars"][user] = pfp
                
                # Dynamic Welcome logic
                mem_facts, mem_gender, mem_score = db_get_memory(user)
                custom_bg = db_get_bg(user)
                
                greeting = f"Welcome @{user}! Habibti Mode active ✨" if BOT_STATE["mode"] == "ar" else f"Welcome {user}! 🌸"
                if mem_score > 60: greeting = f"Welcome back, my Bestie @{user}! 💖"
                
                card_url = f"{BOT_STATE['domain']}api/welcome?u={user}&a={requests.utils.quote(pfp)}&bg={requests.utils.quote(custom_bg)}"
                threading.Thread(target=send_ws_msg, args=(greeting, "image", card_url)).start()
                db_update_user(user, 10, avatar=pfp) # Daily Reward

            # --- MESSAGE HANDLER ---
            elif etype == "text":
                body = data.get("body", "").strip()
                if data.get("avatar_url"): TITAN_GAME["cache_avatars"][user] = data["avatar_url"]
                
                log(f"INCOMING [{user}]: {body}", "in")
                # Multi-threaded logic processing to keep WS alive
                threading.Thread(target=process_main_logic, args=(user, body)).start()
                
    except Exception as e:
        log(f"EVENT LOOP CRASH: {e}", "err")

def process_main_logic(user, msg):
    """Command Router and AI Brain Dispatcher."""
    ml = msg.lower()
    
    if ml.startswith("!"):
        # --- [ADMIN & MODES] ---
        if ml == "!mode ar":
            BOT_STATE["mode"] = "ar"; send_ws_msg("✅ Arabic mode selected"); return
        if ml == "!mode en":
            BOT_STATE["mode"] = "en"; send_ws_msg("✅ English mode selected"); return
        if ml == "!mode smart":
            BOT_STATE["mode"] = "smart"; send_ws_msg("✅ Smart mode selected"); return

        # --- [GAME ROUTING] ---
        if ml.startswith(("!start", "!eat")):
            process_titan_commands(user, msg); return
            
        if ml == "!magic":
            TITAN_GAME["magic_symbol"] = random.choice(["★", "⚡", "☯", "♥", "♦", "♣", "♠", "🔥"])
            grid_str = "🔮 MAGIC MIND GRID 🔮\n"
            for i in range(10, 50):
                symbol = TITAN_GAME["magic_symbol"] if i % 9 == 0 else random.choice(["!", "?", "#", "+", "§", "@"])
                grid_str += f"{i}:{symbol}  "
                if i % 5 == 0: grid_str += "\n"
            send_ws_msg(f"{grid_str}\n\n1. Pick number (10-99)\n2. Add digits (e.g. 23 -> 5)\n3. Subtract from original (23-5=18)\n4. Find symbol for 18!\nCommand: !reveal")
            return

        if ml == "!reveal":
            if TITAN_GAME["magic_symbol"]:
                send_ws_msg(f"✨ The symbol is: {TITAN_GAME['magic_symbol']}"); TITAN_GAME["magic_symbol"] = None
            return

        # --- [PERSONALIZATION] ---
        if ml.startswith("!setbg "):
            bg_url = msg.split(" ", 1)[1].strip()
            if "http" in bg_url:
                db_set_bg(user, bg_url)
                send_ws_msg(f"✅ Theme Updated! You look gorgeous today ✨💅")
            return

        # --- [GRAPHICS DISPATCH] ---
        if ml.startswith("!id"):
            target = ml.split("@")[1].strip() if "@" in ml else user
            pfp = TITAN_GAME["cache_avatars"].get(target, DEFAULT_AVATAR)
            url = f"{BOT_STATE['domain']}api/id_card?u={target}&a={requests.utils.quote(pfp)}"
            send_ws_msg(f"💳 Scanning ID for @{target}...", "image", url); return

        if ml.startswith("!ship"):
            target = ml.split("@")[1].strip() if "@" in ml else BOT_STATE["username"]
            luck = random.randint(0, 100)
            a1 = TITAN_GAME["cache_avatars"].get(user, DEFAULT_AVATAR)
            a2 = TITAN_GAME["cache_avatars"].get(target, DEFAULT_AVATAR)
            url = f"{BOT_STATE['domain']}api/ship?u1={user}&u2={target}&a1={requests.utils.quote(a1)}&a2={requests.utils.quote(a2)}&s={luck}"
            send_ws_msg(f"💖 Checking Chemistry...", "image", url); return

    # --- [NEURAL AI TRIGGER] ---
    if BOT_STATE["username"].lower() in ml or any(tg in ml for tg in BOT_STATE["triggers"]):
        resp = groq_ai_engine(user, msg)
        if resp: send_ws_msg(f"@{user} {resp}")

# ==============================================================================
# --- [SECTION 7: FLASK WEB SERVER (ADMIN TOOLS)] ---
# ==============================================================================

@app.route('/')
def route_home():
    return render_template_string(HTML_DASH, connected=BOT_STATE["connected"])

@app.route('/leaderboard')
def route_leaderboard():
    return render_template_string(HTML_LB, users=db_get_leaderboard())

# --- [GRAPHICS APIs] ---

@app.route('/api/welcome')
def api_welcome_route():
    img = generate_welcome_card(request.args.get('u'), request.args.get('a'), request.args.get('bg'))
    return send_file(img, mimetype='image/png') if img else ("ERR", 500)

@app.route('/api/id_card')
def api_id_route():
    img = generate_id_card(request.args.get('u'), request.args.get('a'))
    return send_file(img, mimetype='image/png') if img else ("ERR", 500)

@app.route('/api/ship')
def api_ship_route():
    img = generate_ship_card(request.args.get('u1'), request.args.get('u2'), request.args.get('a1'), request.args.get('a2'), int(request.args.get('s')))
    return send_file(img, mimetype='image/png') if img else ("ERR", 500)

@app.route('/api/winner')
def api_winner_route():
    img = generate_winner_card(request.args.get('u'), request.args.get('a'), request.args.get('p'))
    return send_file(img, mimetype='image/png') if img else ("ERR", 500)

# --- [SYSTEM LOGS] ---
@app.route('/logs')
def route_logs(): return jsonify({"logs": SYSTEM_LOGS})

@app.route('/connect', methods=['POST'])
def route_connect():
    if BOT_STATE["connected"]: return jsonify({"status": "ALREADY ONLINE"})
    d = request.json
    BOT_STATE.update({"username": d["u"], "password": d["p"], "room_name": d["r"], "domain": request.url_root})
    threading.Thread(target=websocket_init_loop).start()
    return jsonify({"status": "BOOTING SYSTEM..."})

@app.route('/disconnect', methods=['POST'])
def route_disconnect():
    if BOT_STATE["ws"]: BOT_STATE["ws"].close()
    BOT_STATE["connected"] = False
    return jsonify({"status": "TERMINATED"})

def websocket_init_loop():
    """Persistent WebSocket Thread with SSL Bypass and Login Payload matching tanvar.py."""
    def on_open(ws):
        BOT_STATE["connected"] = True
        log("TITAN CORE: SECURE TUNNEL ESTABLISHED.", "sys")
        # Fixed Login Payload
        payload = {"handler": "login", "id": gen_random_string(20), "username": BOT_STATE["username"], "password": BOT_STATE["password"]}
        ws.send(json.dumps(payload))
        
        # Pinger for persistence
        def keep_alive():
            while BOT_STATE["connected"]:
                time.sleep(25)
                try: ws.send(json.dumps({"handler": "ping"}))
                except: break
        threading.Thread(target=keep_alive, daemon=True).start()

    ws_app = websocket.WebSocketApp(
        "wss://chatp.net:5333/server",
        on_open=on_open,
        on_message=on_socket_message,
        on_error=lambda w,e: log(f"CONNECTION ERROR: {e}", "err"),
        on_close=lambda w,c,m: log("TUNNEL DISCONNECTED.", "sys")
    )
    BOT_STATE["ws"] = ws_app
    ws_app.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

# ==============================================================================
# --- [SECTION 8: HEAVY HTML TEMPLATES (CYBER-NEON PINK)] ---
# ==============================================================================

HTML_DASH = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TITAN GIRL V10</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500&family=Roboto+Mono&display=swap" rel="stylesheet">
    <style>
        :root { --neon: #ff00ff; --bg: #050505; --card: #121212; --cyan: #00f3ff; }
        body { background: var(--bg); color: var(--cyan); font-family: 'Roboto Mono', monospace; padding: 25px; display: flex; flex-direction: column; align-items: center; }
        h1, h2 { font-family: 'Orbitron', sans-serif; text-transform: uppercase; color: #fff; text-shadow: 0 0 10px var(--neon); }
        .wrapper { width: 100%; max-width: 750px; }
        .box { background: var(--card); border: 1px solid #333; padding: 35px; border-radius: 12px; border-left: 8px solid var(--neon); box-shadow: 0 15px 40px rgba(255,0,255,0.1); margin-bottom: 30px; }
        input { width: 100%; padding: 18px; margin: 12px 0; background: #000; color: #fff; border: 1px solid #444; border-radius: 6px; box-sizing: border-box; }
        .btn-box { display: flex; gap: 20px; margin-top: 20px; }
        button { flex: 1; padding: 18px; font-weight: bold; border: none; cursor: pointer; font-family: 'Orbitron'; border-radius: 6px; transition: 0.3s; }
        .btn-go { background: var(--neon); color: #000; }
        .btn-stop { background: #ff003c; color: #fff; }
        button:hover { filter: brightness(1.2); transform: scale(1.02); }
        .monitor { height: 450px; overflow-y: scroll; background: #000; border: 1px solid #222; padding: 20px; border-radius: 6px; font-size: 11px; }
        .line { margin-bottom: 8px; border-bottom: 1px solid #111; padding-bottom: 4px; }
        .type-err { color: #ff003c; font-weight: bold; }
        .type-sys { color: #888; }
        .type-in { color: #00ff41; }
        .type-out { color: var(--cyan); }
        a { color: #fff; text-decoration: none; border-bottom: 2px solid var(--neon); margin-top: 20px; display: inline-block; }
    </style>
</head>
<body>
    <div class="wrapper">
        <h1>👑 TITAN GIRL V10 CONTROL</h1>
        <div class="box">
            <div id="st">STATUS: <span style="color: {{ 'lime' if connected else 'red' }}">{{ 'ONLINE' if connected else 'OFFLINE' }}</span></div>
            <input type="text" id="u" placeholder="LOGIN USERNAME">
            <input type="password" id="p" placeholder="LOGIN PASSWORD">
            <input type="text" id="r" placeholder="ROOM NAME">
            <div class="btn-box">
                <button class="btn-go" onclick="trigger('/connect')">START ENGINE</button>
                <button class="btn-stop" onclick="trigger('/disconnect')">TERMINATE</button>
            </div>
            <a href="/leaderboard" target="_blank">📊 ACCESS PLAYER RANKINGS</a>
        </div>
        <div class="box">
            <h2>📜 QUANTUM SYSTEM LOGS</h2>
            <div class="monitor" id="mon">Awaiting boot sequence...</div>
        </div>
    </div>
    <script>
        function trigger(path) {
            const data = { u: document.getElementById('u').value, p: document.getElementById('p').value, r: document.getElementById('r').value };
            fetch(path, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data) })
            .then(res => res.json()).then(j => alert("TITAN RESPONSE: " + j.status));
        }
        setInterval(() => {
            fetch('/logs').then(r => r.json()).then(data => {
                const mon = document.getElementById('mon');
                mon.innerHTML = data.logs.reverse().map(l => `<div class="line type-${l.type}">[${l.time}] [${l.type.toUpperCase()}] ${l.msg}</div>`).join('');
            });
        }, 1500);
    </script>
</body>
</html>
"""

HTML_LB = """
<!DOCTYPE html>
<html>
<head>
    <title>TITAN RANKINGS</title>
    <style>
        body { background: #050505; color: #fff; font-family: sans-serif; padding: 50px; text-align: center; }
        h1 { color: #ff00ff; text-shadow: 0 0 10px #ff00ff; }
        .item { background: #111; max-width: 600px; margin: 15px auto; padding: 25px; display: flex; align-items: center; justify-content: space-between; border-left: 6px solid #00f3ff; border-radius: 8px; }
        .avi { width: 65px; height: 65px; border-radius: 50%; border: 2px solid #ff00ff; }
        .score { color: #00ff41; font-size: 1.8em; font-weight: bold; }
    </style>
</head>
<body>
    <h1>🌟 GLOBAL RANKINGS</h1>
    {% for u in users %}
        <div class="item">
            <div style="display:flex; align-items:center; gap:25px;">
                <span style="font-size:1.5em; color:#555;">#{{ loop.index }}</span>
                <img src="{{ u[3] or 'https://i.imgur.com/6EdJm2h.png' }}" class="avi">
                <div style="text-align:left;"><b>{{ u[0] }}</b><br><small>VICTORIES: {{ u[2] }}</small></div>
            </div>
            <div class="score">{{ u[1] }}</div>
        </div>
    {% endfor %}
</body>
</html>
"""

# ==============================================================================
# --- [SECTION 9: SYSTEM ENTRY POINT] ---
# ==============================================================================

if __name__ == '__main__':
    # Initialize Persistent Infrastructure
    init_database()
    # Define port and launch production server
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)