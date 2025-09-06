# bot.py -- Final Campaign Bot with TikTok + Payment Validation

import discord
from discord import app_commands
from discord.ui import View
from discord.ext import commands
import sqlite3, random, string, requests, re
from datetime import datetime, timezone
from typing import Optional

# ----------------- CONFIG -----------------
BOT_TOKEN = "MTQxMzE2MjY1MTI3NzcyMTY3MQ.GpQ21B.YL_anFwauQu4TQGbOMfDJXlEawd2_7I-F3I4XE"
ADMIN_CHANNEL_ID = 1413430795426857000
DB_PATH = "campaign_bot.db"
YOUTUBE_API_KEY = "AIzaSyA_2Daxj69XBw7c03uNI5R5KL0auH14CbQ"

# ----------------- DISCORD CLIENT -----------------
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ----------------- DB INIT -----------------
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_id INTEGER,
        platform TEXT,
        handle TEXT,
        code TEXT,
        verified INTEGER DEFAULT 0,
        created_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS reels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_id INTEGER,
        url TEXT,
        created_at TEXT,
        views INTEGER DEFAULT 0
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_id INTEGER,
        address TEXT,
        created_at TEXT
    )""")
    con.commit(); con.close()
init_db()

# ----------------- DB HELPERS -----------------
def _get_conn(): return sqlite3.connect(DB_PATH)

def db_insert_account(discord_id, platform, handle, code):
    con=_get_conn();cur=con.cursor()
    cur.execute("INSERT INTO accounts(discord_id,platform,handle,code,verified,created_at) VALUES (?,?,?,?,0,?)",
                (discord_id,platform,handle,code,datetime.now(timezone.utc).isoformat()))
    con.commit();con.close()

def db_verify_account(discord_id, code):
    con=_get_conn();cur=con.cursor()
    cur.execute("SELECT id FROM accounts WHERE discord_id=? AND code=? AND verified=0",(discord_id,code))
    row=cur.fetchone()
    if not row: con.close(); return 0
    cur.execute("UPDATE accounts SET verified=1 WHERE id=?",(row[0],))
    con.commit();con.close(); return 1

def db_delete_account(discord_id, handle, platform):
    con=_get_conn();cur=con.cursor()
    cur.execute("DELETE FROM accounts WHERE discord_id=? AND handle=? AND platform=?",(discord_id,handle,platform))
    c=cur.rowcount; con.commit(); con.close(); return c

def db_get_accounts(discord_id):
    con=_get_conn();cur=con.cursor()
    cur.execute("SELECT platform,handle,verified FROM accounts WHERE discord_id=?",(discord_id,))
    r=cur.fetchall();con.close();return r

def db_add_reel(discord_id,url,views):
    con=_get_conn();cur=con.cursor()
    cur.execute("INSERT INTO reels(discord_id,url,created_at,views) VALUES (?,?,?,?)",
                (discord_id,url,datetime.now(timezone.utc).isoformat(),views))
    con.commit();con.close()

def db_get_reels(discord_id):
    con=_get_conn();cur=con.cursor()
    cur.execute("SELECT url,views FROM reels WHERE discord_id=?",(discord_id,))
    r=cur.fetchall();con.close();return r

def db_add_payment(discord_id,address):
    con=_get_conn();cur=con.cursor()
    cur.execute("INSERT INTO payments(discord_id,address,created_at) VALUES (?,?,?)",
                (discord_id,address,datetime.now(timezone.utc).isoformat()))
    con.commit();con.close()

def db_remove_payment(discord_id,address):
    con=_get_conn();cur=con.cursor()
    cur.execute("DELETE FROM payments WHERE discord_id=? AND address=?",(discord_id,address))
    d=cur.rowcount;con.commit();con.close();return d

def db_get_payments(discord_id):
    con=_get_conn();cur=con.cursor()
    cur.execute("SELECT address FROM payments WHERE discord_id=?",(discord_id,))
    r=cur.fetchall();con.close();return r

# ----------------- YOUTUBE HELPERS -----------------
YOUTUBE_VIDEO_ID_RE = re.compile(r'(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{8,})')
def extract_video_id(url): 
    m=YOUTUBE_VIDEO_ID_RE.search(url); return m.group(1) if m else None

def fetch_youtube_video_views(video_id:str)->int:
    try:
        r=requests.get(f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={video_id}&key={YOUTUBE_API_KEY}",timeout=8).json()
        if "items" in r and r["items"]:
            return int(r["items"][0]["statistics"].get("viewCount",0))
    except: pass
    return 0

# ----------------- UTILITIES -----------------
def generate_code(): return ''.join(random.choices(string.digits,k=6))

class RejectView(View):
    def __init__(self,who,what): super().__init__(timeout=None); self.who=who; self.what=what
    @discord.ui.button(label="❌ Reject",style=discord.ButtonStyle.danger)
    async def reject(self,interaction,button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Admins only",ephemeral=True);return
        await interaction.message.edit(content=f"❌ Rejected by {interaction.user.mention}",view=None)

async def send_admin_log(title,desc,fields=None,who=None,what=None):
    ch=bot.get_channel(ADMIN_CHANNEL_ID)
    if not ch: return
    emb=discord.Embed(title=title,description=desc,color=0x2ecc71)
    if fields:
        for n,v in fields: emb.add_field(name=n,value=v,inline=False)
    view=RejectView(who,what) if who and what else None
    await ch.send(embed=emb,view=view)

# ----------------- COMMANDS -----------------
@tree.command(name="register",description="Register your account")
@app_commands.choices(platform=[
    app_commands.Choice(name="YouTube",value="YouTube"),
    app_commands.Choice(name="Instagram",value="Instagram"),
    app_commands.Choice(name="TikTok",value="TikTok")
])
async def register(inter,platform:app_commands.Choice[str],handle:str):
    code=generate_code()
    db_insert_account(inter.user.id,platform.value,handle,code)
    try: await inter.user.send(f"Your verification code: `{code}`. Use /verify {code}")
    except: pass
    await send_admin_log("📥 New Register",f"<@{inter.user.id}> registered.",[("Platform",platform.value),("Handle",handle)],who=inter.user.id,what="register")
    await inter.response.send_message("✅ Registered",ephemeral=True)

@tree.command(name="verify",description="Verify with code")
async def verify(inter,code:str):
    ok=db_verify_account(inter.user.id,code)
    await inter.response.send_message("✅ Verified" if ok else "❌ Invalid",ephemeral=True)

@tree.command(name="add-account",description="Add another account")
@app_commands.choices(platform=[
    app_commands.Choice(name="YouTube",value="YouTube"),
    app_commands.Choice(name="Instagram",value="Instagram"),
    app_commands.Choice(name="TikTok",value="TikTok")
])
async def add_account(inter,platform:app_commands.Choice[str],handle:str):
    code=generate_code()
    db_insert_account(inter.user.id,platform.value,handle,code)
    await send_admin_log("➕ Account Added",f"<@{inter.user.id}> added account.",[("Platform",platform.value),("Handle",handle)],who=inter.user.id,what="add-account")
    await inter.response.send_message("✅ Added",ephemeral=True)

@tree.command(name="remove-account",description="Remove your account")
@app_commands.choices(platform=[
    app_commands.Choice(name="YouTube",value="YouTube"),
    app_commands.Choice(name="Instagram",value="Instagram"),
    app_commands.Choice(name="TikTok",value="TikTok")
])
async def remove_account(inter,platform:app_commands.Choice[str],handle:str):
    d=db_delete_account(inter.user.id,handle,platform.value)
    await inter.response.send_message("✅ Removed" if d else "❌ Not found",ephemeral=True)

@tree.command(name="submit",description="Submit your reel/video")
async def submit(inter,url:str):
    if not url.startswith("https://"):
        await inter.response.send_message("❌ URL must start with https://",ephemeral=True);return
    views=0
    if "youtube" in url or "youtu.be" in url:
        vid=extract_video_id(url)
        if not vid: await inter.response.send_message("❌ Invalid YouTube URL",ephemeral=True);return
        views=fetch_youtube_video_views(vid)
        if views==0: await inter.response.send_message("❌ Not a real YouTube video",ephemeral=True);return
    db_add_reel(inter.user.id,url,views)
    await send_admin_log("📤 Reel Submitted",f"<@{inter.user.id}> submitted a reel.",[("URL",url),("Views",str(views))],who=inter.user.id,what="submit")
    await inter.response.send_message("✅ Submitted",ephemeral=True)

@tree.command(name="payment",description="Add payment address (Solana)")
async def payment(inter,address:str):
    # basic Solana address validation: base58, length 32–44
    if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}",address):
        await inter.response.send_message("❌ Invalid Solana address",ephemeral=True);return
    db_add_payment(inter.user.id,address)
    await send_admin_log("💰 Payment Added",f"<@{inter.user.id}> added payment.",[("Address",address)],who=inter.user.id,what="payment")
    await inter.response.send_message("✅ Added",ephemeral=True)

@tree.command(name="remove-payment",description="Remove payment address")
async def remove_payment(inter,address:str):
    d=db_remove_payment(inter.user.id,address)
    await inter.response.send_message("✅ Removed" if d else "❌ Not found",ephemeral=True)

@tree.command(name="leaderboard",description="Top 10 members by reel views")
async def leaderboard(inter):
    con=_get_conn();cur=con.cursor()
    cur.execute("SELECT discord_id,SUM(views) FROM reels GROUP BY discord_id ORDER BY SUM(views) DESC LIMIT 10")
    rows=cur.fetchall();con.close()
    desc="\n".join([f"<@{uid}> — {v} views" for uid,v in rows]) or "No data"
    await inter.response.send_message(embed=discord.Embed(title="🏆 Leaderboard",description=desc,color=0x3498db))

@tree.command(name="stats",description="Show stats")
async def stats(inter,user:Optional[discord.User]=None):
    target=user or inter.user
    accs=db_get_accounts(target.id); reels=db_get_reels(target.id); pays=db_get_payments(target.id)
    desc=f"**Accounts:** {len(accs)}\n"+"\n".join([f"{p} {h} ({'✅' if v else '❌'})" for p,h,v in accs])
    desc+=f"\n\n**Reels:** {len(reels)}\n"+"\n".join([f"{u} ({v} views)" for u,v in reels[:5]])
    desc+=f"\n\n**Payments:** {', '.join([a[0] for a in pays]) or 'None'}"
    await inter.response.send_message(embed=discord.Embed(title=f"📊 Stats for {target}",description=desc,color=0x95a5a6))

@tree.command(name="help",description="Show help")
async def help_cmd(inter):
    cmds=["/register","/verify <code>","/add-account","/remove-account","/submit <url>","/payment <address>","/remove-payment","/leaderboard","/stats [user]","/help"]
    emb=discord.Embed(title="🤖 Bot Commands",description="\n".join(cmds),color=0x7289DA)
    await inter.response.send_message(embed=emb,ephemeral=True)

# ----------------- STARTUP -----------------
@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

bot.run(BOT_TOKEN)