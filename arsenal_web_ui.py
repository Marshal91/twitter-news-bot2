"""
Arsenal DataMB X Agent — Web UI + Auto-Scheduler
Run:  gunicorn arsenal_web_ui:app --workers 1 --threads 2 --bind 0.0.0.0:$PORT
"""

import os, base64, random, logging, threading, time, json
from datetime import datetime
from logging.handlers import RotatingFileHandler

import pytz, tweepy
from dotenv import load_dotenv
from flask import Flask, render_template_string, request, jsonify

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[
        RotatingFileHandler("logs/arsenal_agent.log", maxBytes=5*1024*1024, backupCount=3),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Twitter clients ───────────────────────────────────────────────────────────
auth = tweepy.OAuth1UserHandler(
    os.getenv("TWITTER_API_KEY"), os.getenv("TWITTER_API_SECRET"),
    os.getenv("TWITTER_ACCESS_TOKEN"), os.getenv("TWITTER_ACCESS_SECRET"),
)
twitter_api_v1    = tweepy.API(auth)
twitter_client_v2 = tweepy.Client(
    consumer_key=os.getenv("TWITTER_API_KEY"),
    consumer_secret=os.getenv("TWITTER_API_SECRET"),
    access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
    access_token_secret=os.getenv("TWITTER_ACCESS_SECRET"),
)

from arsenal_datamb_agent import ArsenalDataMBAgent, ARSENAL_SQUAD, RIVAL_TEAMS

agent = ArsenalDataMBAgent(twitter_api=twitter_api_v1, twitter_client=twitter_client_v2)

# ── Schedule config ───────────────────────────────────────────────────────────
SCHEDULE = [
    ("08:00", "player"),
    ("13:00", "team"),
    ("18:00", "player"),
]

TONES = ["hype", "analytical", "banter", "historic", "tactical"]

RIVAL_PLAYER_MAP = {
    "GK": [("Alisson", 40), ("Ederson", 50), ("Andre Onana", 33)],
    "CB": [("Virgil van Dijk", 40), ("Ruben Dias", 50), ("John Stones", 50)],
    "FB": [("Trent Alexander-Arnold", 40), ("Andy Robertson", 40), ("Reece James", 49)],
    "MF": [("Rodri", 50), ("Bruno Fernandes", 33), ("Kobbie Mainoo", 33)],
    "WG": [("Mohamed Salah", 40), ("Son Heung-min", 47), ("Cole Palmer", 49)],
    "ST": [("Erling Haaland", 50), ("Darwin Nunez", 40), ("Alexander Isak", 34)],
}

# ── Shared state ──────────────────────────────────────────────────────────────
_state = {
    "daily_count": 0,
    "last_posted_at": None,
    "last_post_type": None,
    "last_tweet_id": None,
    "last_reset_date": datetime.now(pytz.UTC).date().isoformat(),
    "log": [],
}
_state_lock   = threading.Lock()
_pending      = {}
_pending_lock = threading.Lock()


def _log(msg):
    ts = datetime.now(pytz.UTC).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"[{ts}] {msg}"
    logger.info(entry)
    with _state_lock:
        _state["log"].append(entry)
        _state["log"] = _state["log"][-10:]


def _reset_daily():
    today = datetime.now(pytz.UTC).date().isoformat()
    with _state_lock:
        if _state["last_reset_date"] != today:
            _state["daily_count"] = 0
            _state["last_reset_date"] = today
            _log("Daily counter reset")


def _record_post(tweet_id, post_type):
    with _state_lock:
        _state["last_posted_at"] = datetime.now(pytz.UTC).isoformat()
        _state["last_post_type"] = post_type
        _state["last_tweet_id"]  = tweet_id
        _state["daily_count"]   += 1


# ── Scheduled post helpers ────────────────────────────────────────────────────
def _run_player_post():
    key  = random.choice(list(ARSENAL_SQUAD.keys()))
    pos  = ARSENAL_SQUAD[key]["pos"]
    pool = RIVAL_PLAYER_MAP.get(pos, RIVAL_PLAYER_MAP["MF"])
    rival_name, rival_team_id = random.choice(pool)
    tone = random.choice(TONES)
    _log(f"Scheduled player: {ARSENAL_SQUAD[key]['name']} vs {rival_name} | {tone}")
    result = agent.build_player_comparison(
        arsenal_key=key, rival_name=rival_name,
        rival_team_id=rival_team_id, tone=tone,
    )
    if "error" in result:
        _log(f"Build failed: {result['error']}"); return False
    r = agent.post_to_x(result["narrative"], result["image_bytes"])
    if r["success"]:
        _log(f"Player post live: {r['tweet_id']}")
        _record_post(r["tweet_id"], "player")
        return True
    _log(f"Post failed: {r['error']}"); return False


def _run_team_post():
    rival = random.choice(list(RIVAL_TEAMS.keys()))
    tone  = random.choice(TONES)
    _log(f"Scheduled team: Arsenal vs {rival} | {tone}")
    result = agent.build_team_comparison(rival_team_key=rival, tone=tone)
    if "error" in result:
        _log(f"Build failed: {result['error']}"); return False
    r = agent.post_to_x(result["narrative"], result["image_bytes"])
    if r["success"]:
        _log(f"Team post live: {r['tweet_id']}")
        _record_post(r["tweet_id"], "team")
        return True
    _log(f"Post failed: {r['error']}"); return False


def scheduler_loop():
    logger.info("Scheduler started")
    last_minute = None
    while True:
        try:
            _reset_daily()
            minute = datetime.now(pytz.UTC).strftime("%H:%M")
            if minute != last_minute:
                for slot_time, slot_mode in SCHEDULE:
                    if slot_time == minute:
                        _log(f"Firing {slot_mode} post at {minute} UTC")
                        _run_player_post() if slot_mode == "player" else _run_team_post()
                last_minute = minute
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        time.sleep(30)


# ── HTML template ─────────────────────────────────────────────────────────────
# NOTE: CSS percentage values use %% to avoid Python string formatting conflicts

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Arsenal DataMB X Agent</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --red:#EF0107;--gold:#DB9C33;
  --bg:#0A0A0A;--surface:#141414;--surface2:#1C1C1C;--surface3:#262626;
  --border:rgba(255,255,255,0.08);--text:#fff;--muted:rgba(255,255,255,0.45);
  --secondary:rgba(255,255,255,0.7);
}
body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;min-height:100vh}
.header{background:linear-gradient(135deg,#0A0A0A,#1a0000 60%%,#0d0000);
  border-bottom:1px solid rgba(239,1,7,.25);padding:14px 24px;
  display:flex;align-items:center;gap:14px}
.header h1{font-family:'Oswald',sans-serif;font-size:20px;font-weight:700;
  letter-spacing:1.5px;text-transform:uppercase}
.header p{font-size:11px;color:var(--gold);letter-spacing:2px;
  text-transform:uppercase;margin-top:2px}
.crest{width:40px;height:40px;flex-shrink:0}
.badge{margin-left:auto;background:var(--red);color:#fff;
  font-family:'Oswald',sans-serif;font-size:10px;font-weight:600;
  letter-spacing:1.5px;padding:4px 10px;border-radius:4px;text-transform:uppercase}
.container{max-width:1160px;margin:0 auto;padding:20px 16px;
  display:grid;grid-template-columns:340px 1fr;gap:20px;align-items:start}
@media(max-width:800px){.container{grid-template-columns:1fr}}
.panel{background:var(--surface);border:1px solid var(--border);
  border-radius:12px;padding:20px}
.section-label{font-family:'Oswald',sans-serif;font-size:11px;font-weight:600;
  letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
.tab-row{display:flex;border-bottom:1px solid var(--border);margin-bottom:16px}
.tab{flex:1;padding:10px;font-family:'Oswald',sans-serif;font-size:12px;
  font-weight:600;letter-spacing:1px;text-transform:uppercase;color:var(--muted);
  background:none;border:none;cursor:pointer;border-bottom:2px solid transparent;transition:.2s}
.tab.active{color:var(--red);border-bottom-color:var(--red)}
select,input[type=text]{width:100%%;background:var(--surface2);
  border:1px solid var(--border);border-radius:8px;color:var(--text);
  font-family:'DM Sans',sans-serif;font-size:13px;padding:9px 11px;
  outline:none;margin-bottom:10px;transition:border-color .2s;appearance:auto}
select:focus,input[type=text]:focus{border-color:rgba(239,1,7,.45)}
select option{background:#1C1C1C;color:#fff}
select optgroup{background:#141414;color:var(--gold)}
input[type=text]::placeholder{color:var(--muted)}
.tone-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px}
.tone-btn{background:var(--surface2);border:1px solid var(--border);
  border-radius:8px;color:var(--secondary);font-size:12px;padding:8px;
  cursor:pointer;transition:.2s;text-align:center}
.tone-btn.active{border-color:var(--red);color:var(--text);background:rgba(239,1,7,.12)}
.tone-btn:hover:not(.active){border-color:rgba(239,1,7,.3)}
.btn{border:none;border-radius:8px;font-family:'Oswald',sans-serif;
  font-size:13px;font-weight:600;letter-spacing:1px;text-transform:uppercase;
  cursor:pointer;padding:10px 18px;transition:.15s}
.btn-red{background:var(--red);color:#fff;width:100%%;margin-top:4px}
.btn-red:hover{background:#c8000a}
.btn-red:active{transform:scale(.97)}
.btn-red:disabled{background:#444;color:#888;cursor:not-allowed}
.btn-blue{background:#1DA1F2;color:#fff;width:100%%;margin-top:10px}
.btn-blue:hover{background:#1a8cd8}
.btn-blue:disabled{background:#444;color:#888;cursor:not-allowed}
.preview-area{display:flex;flex-direction:column;gap:16px}
.radar-container{background:var(--surface2);border:1px solid var(--border);
  border-radius:10px;overflow:hidden;text-align:center;min-height:300px;
  display:flex;align-items:center;justify-content:center}
.radar-container img{width:100%%;max-width:580px;display:block}
.radar-placeholder{color:var(--muted);font-size:14px;padding:40px;line-height:1.8}
.narrative-box{background:var(--surface2);border:1px solid var(--border);
  border-radius:10px;padding:14px}
.narrative-box textarea{width:100%%;background:transparent;border:none;
  color:var(--secondary);font-family:'DM Sans',sans-serif;font-size:14px;
  line-height:1.65;resize:vertical;min-height:120px;outline:none}
.char-count{font-size:11px;color:var(--muted);text-align:right;margin-top:4px}
.status-bar{padding:10px 14px;border-radius:8px;font-size:13px;
  text-align:center;display:none;margin-top:10px}
.status-bar.success{background:rgba(0,200,100,.1);
  border:1px solid rgba(0,200,100,.3);color:#00c864;display:block}
.status-bar.error{background:rgba(239,1,7,.1);
  border:1px solid rgba(239,1,7,.3);color:#ff6b6b;display:block}
.status-bar.loading{background:rgba(255,255,255,.04);
  border:1px solid var(--border);color:var(--secondary);display:block}
.metric-list{display:flex;flex-direction:column;gap:7px;margin-top:8px}
.metric-row{display:flex;align-items:center;gap:8px}
.metric-name{font-size:11px;color:var(--muted);width:100px;
  font-family:'Oswald',sans-serif;text-transform:uppercase;
  letter-spacing:.4px;flex-shrink:0}
.metric-track{flex:1;height:5px;background:var(--surface3);
  border-radius:3px;overflow:hidden;position:relative}
.mf-a{height:100%%;background:var(--red);border-radius:3px;
  transition:width .8s cubic-bezier(.22,.68,0,1.2)}
.mf-b{height:100%%;background:#4A90D9;border-radius:3px;
  transition:width .8s cubic-bezier(.22,.68,0,1.2);
  position:absolute;top:0;left:0;opacity:.55}
.metric-pct{font-family:'Oswald',sans-serif;font-size:11px;
  font-weight:600;color:var(--red);width:26px;text-align:right}
.metric-pct-b{font-family:'Oswald',sans-serif;font-size:11px;
  color:#4A90D9;width:26px;text-align:right}
.sched-panel{background:var(--surface);border:1px solid var(--border);
  border-radius:12px;padding:20px}
.sched-slots{display:flex;flex-direction:column;gap:8px;margin-bottom:16px}
.sched-slot{display:flex;align-items:center;gap:10px;padding:8px 12px;
  background:var(--surface2);border-radius:8px;border:1px solid var(--border)}
.sched-time{font-family:'Oswald',sans-serif;font-size:13px;
  font-weight:600;color:var(--red);width:52px}
.sched-type{font-size:12px;color:var(--secondary);flex:1}
.sched-dot{width:8px;height:8px;border-radius:50%%;background:#444;flex-shrink:0}
.sched-dot.next{background:var(--gold);animation:pulse 1.5s ease-in-out infinite}
@keyframes pulse{0%%,100%%{opacity:1}50%%{opacity:.4}}
.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}
.stat-box{background:var(--surface2);border:1px solid var(--border);
  border-radius:8px;padding:10px;text-align:center}
.stat-val{font-family:'Oswald',sans-serif;font-size:20px;font-weight:700;color:var(--text)}
.stat-lbl{font-size:10px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.8px;margin-top:2px}
.log-box{background:var(--surface2);border:1px solid var(--border);
  border-radius:8px;padding:10px 12px;font-size:11px;color:var(--muted);
  font-family:monospace;max-height:160px;overflow-y:auto;line-height:1.7}
.log-box div{border-bottom:1px solid rgba(255,255,255,.04);padding:2px 0}
.log-box div:last-child{border:none}
.spinner{display:inline-block;width:13px;height:13px;
  border:2px solid rgba(255,255,255,.2);border-top-color:#fff;
  border-radius:50%%;animation:spin .7s linear infinite;
  vertical-align:middle;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
.player-loading{font-size:12px;color:var(--muted);padding:4px 0 8px;display:none}
.hidden{display:none}
</style>
</head>
<body>

<div class="header">
  <svg class="crest" viewBox="0 0 40 40" fill="none">
    <circle cx="20" cy="20" r="19" fill="#EF0107" stroke="#9B0005" stroke-width="1"/>
    <path d="M20 5L25 12L33 10L29 18L35 24L27 23L25 31L20 26L15 31L13 23L5 24L11 18L7 10L15 12Z" fill="#DB9C33"/>
    <circle cx="20" cy="20" r="4" fill="#0A0A0A"/>
    <circle cx="20" cy="20" r="2.5" fill="#EF0107"/>
  </svg>
  <div>
    <h1>Arsenal DataMB X Agent</h1>
    <p>Real Stats &middot; Radar Cards &middot; Auto-Post to X</p>
  </div>
  <span class="badge">Live</span>
</div>

<div class="container">
  <div style="display:flex;flex-direction:column;gap:16px">

    <div class="panel">
      <div class="tab-row">
        <button class="tab active" id="tab-player" onclick="switchMode('player')">Player vs Player</button>
        <button class="tab"        id="tab-team"   onclick="switchMode('team')">Team vs Team</button>
      </div>

      <!-- PLAYER MODE -->
      <div id="mode-player">
        <div class="section-label">Arsenal Player</div>
        <select id="arsenal-player">
          <option value="">&#8212; Select Arsenal player &#8212;</option>
          <optgroup label="Goalkeepers">
            %(gk_options)s
          </optgroup>
          <optgroup label="Defenders">
            %(def_options)s
          </optgroup>
          <optgroup label="Midfielders">
            %(mid_options)s
          </optgroup>
          <optgroup label="Forwards">
            %(fwd_options)s
          </optgroup>
        </select>

        <div class="section-label">Rival Team</div>
        <select id="rival-team-for-player" onchange="loadRivalPlayers(this.value)">
          <option value="">&#8212; Select rival team first &#8212;</option>
          <optgroup label="Premier League">%(pl_options)s</optgroup>
          <optgroup label="La Liga">%(laliga_options)s</optgroup>
          <optgroup label="Bundesliga">%(bundesliga_options)s</optgroup>
          <optgroup label="Serie A">%(seriea_options)s</optgroup>
          <optgroup label="Ligue 1">%(ligue1_options)s</optgroup>
        </select>

        <div class="section-label">Rival Player</div>
        <div class="player-loading" id="player-loading">
          <span class="spinner"></span>Loading squad...
        </div>
        <select id="rival-player-select" style="display:none">
          <option value="">&#8212; Select rival player &#8212;</option>
        </select>
        <input type="text" id="rival-player-manual" placeholder="Or type player name manually">
      </div>

      <!-- TEAM MODE -->
      <div id="mode-team" class="hidden">
        <div class="section-label">Arsenal vs</div>
        <select id="rival-team-team">
          <option value="">&#8212; Select rival team &#8212;</option>
          <optgroup label="Premier League">%(pl_team_options)s</optgroup>
          <optgroup label="La Liga">%(laliga_team_options)s</optgroup>
          <optgroup label="Bundesliga">%(bundesliga_team_options)s</optgroup>
          <optgroup label="Serie A">%(seriea_team_options)s</optgroup>
          <optgroup label="Ligue 1">%(ligue1_team_options)s</optgroup>
        </select>
      </div>

      <div class="section-label">Narrative Tone</div>
      <div class="tone-grid">
        <button class="tone-btn active" data-tone="hype"       onclick="setTone(this)">&#128293; Hype</button>
        <button class="tone-btn"        data-tone="analytical" onclick="setTone(this)">&#128202; Analytical</button>
        <button class="tone-btn"        data-tone="banter"     onclick="setTone(this)">&#128520; Banter</button>
        <button class="tone-btn"        data-tone="historic"   onclick="setTone(this)">&#127942; Historic</button>
        <button class="tone-btn"        data-tone="tactical"   onclick="setTone(this)">&#129504; Tactical</button>
      </div>

      <div class="section-label">Custom Note (optional)</div>
      <input type="text" id="custom-note" placeholder="e.g. Rice best CDM in Europe">
      <button class="btn btn-red" id="gen-btn" onclick="generate()">Generate Radar + Post &nearr;</button>
    </div>

    <!-- Schedule panel -->
    <div class="sched-panel">
      <div class="section-label">Auto-Schedule (UTC)</div>
      <div class="sched-slots" id="sched-slots"></div>
      <div class="stat-row">
        <div class="stat-box"><div class="stat-val" id="stat-today">&#8212;</div><div class="stat-lbl">Today</div></div>
        <div class="stat-box"><div class="stat-val" id="stat-last">&#8212;</div><div class="stat-lbl">Last post</div></div>
        <div class="stat-box"><div class="stat-val" id="stat-next">&#8212;</div><div class="stat-lbl">Next slot</div></div>
      </div>
      <div class="section-label">Activity log</div>
      <div class="log-box" id="log-box">Waiting for activity...</div>
    </div>
  </div>

  <!-- Right column -->
  <div class="preview-area">
    <div class="panel" style="padding:0;overflow:hidden">
      <div class="radar-container" id="radar-box">
        <div class="radar-placeholder">&#9917; Select a player or team<br>comparison and click Generate</div>
      </div>
    </div>
    <div class="panel hidden" id="metrics-panel">
      <div class="section-label" id="metrics-title">Percentile Rankings</div>
      <div class="metric-list" id="metric-bars"></div>
    </div>
    <div class="panel">
      <div class="section-label">X Post Draft</div>
      <div class="narrative-box">
        <textarea id="narrative-text" placeholder="Your Arsenal post will appear here..."></textarea>
        <div class="char-count"><span id="char-count">0</span> chars</div>
      </div>
      <div id="status-bar" class="status-bar"></div>
      <button class="btn btn-blue" id="post-btn" onclick="confirmPost()" disabled>Post to X &#128038;</button>
    </div>
  </div>
</div>

<script>
var SCHEDULE = %(schedule_json)s;
var currentMode = 'player';
var currentTone = 'hype';
var pendingImage = null;

function switchMode(mode) {
  currentMode = mode;
  document.getElementById('tab-player').classList.toggle('active', mode === 'player');
  document.getElementById('tab-team').classList.toggle('active',   mode === 'team');
  document.getElementById('mode-player').classList.toggle('hidden', mode !== 'player');
  document.getElementById('mode-team').classList.toggle('hidden',   mode !== 'team');
}

function setTone(btn) {
  document.querySelectorAll('.tone-btn').forEach(function(b){b.classList.remove('active');});
  btn.classList.add('active');
  currentTone = btn.dataset.tone;
}

document.getElementById('narrative-text').addEventListener('input', function(){
  document.getElementById('char-count').textContent = this.value.length;
});

async function loadRivalPlayers(teamId) {
  var sel     = document.getElementById('rival-player-select');
  var loading = document.getElementById('player-loading');
  var manual  = document.getElementById('rival-player-manual');
  if (!teamId) { sel.style.display='none'; return; }
  loading.style.display = 'block';
  sel.style.display = 'none';
  try {
    var resp = await fetch('/squad/' + teamId);
    var data = await resp.json();
    sel.innerHTML = '<option value="">&#8212; Select rival player &#8212;</option>';
    if (data.players && data.players.length) {
      var groups = {Goalkeeper:[],Defender:[],Midfielder:[],Attacker:[],Other:[]};
      data.players.forEach(function(p){
        var g = groups[p.position] ? p.position : 'Other';
        groups[g].push(p);
      });
      ['Goalkeeper','Defender','Midfielder','Attacker','Other'].forEach(function(pos){
        if (!groups[pos].length) return;
        var grp = document.createElement('optgroup');
        grp.label = pos;
        groups[pos].forEach(function(p){
          var opt = document.createElement('option');
          opt.value = p.name; opt.textContent = p.name;
          grp.appendChild(opt);
        });
        sel.appendChild(grp);
      });
      sel.style.display = 'block';
    } else {
      manual.placeholder = 'Type rival player name (squad not found)';
    }
  } catch(e) { manual.placeholder = 'Type rival player name'; }
  loading.style.display = 'none';
}

async function generate() {
  var btn   = document.getElementById('gen-btn');
  var radar = document.getElementById('radar-box');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Fetching stats...';
  showStatus('loading', 'Fetching stats from API-Football...');
  radar.innerHTML = '<div class="radar-placeholder">Building radar card...</div>';

  var payload = { tone: currentTone, custom_note: document.getElementById('custom-note').value };

  if (currentMode === 'player') {
    payload.mode = 'player';
    var sel = document.getElementById('arsenal-player');
    var opt = sel.options[sel.selectedIndex];
    payload.arsenal_player_id   = opt ? parseInt(opt.value) : 0;
    payload.arsenal_player_name = opt ? opt.dataset.name : '';
    payload.arsenal_pos         = opt ? opt.dataset.pos  : 'MF';
    var selVal    = document.getElementById('rival-player-select').value;
    var manualVal = document.getElementById('rival-player-manual').value.trim();
    payload.rival_player  = selVal || manualVal;
    payload.rival_team_id = document.getElementById('rival-team-for-player').value || null;
    if (!payload.arsenal_player_id) { showStatus('error','Select an Arsenal player'); resetBtn(); return; }
  } else {
    payload.mode       = 'team';
    payload.rival_team = document.getElementById('rival-team-team').value;
    if (!payload.rival_team) { showStatus('error','Select a rival team'); resetBtn(); return; }
  }

  try {
    var resp = await fetch('/generate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)
    });
    var data = await resp.json();
    if (data.error) {
      showStatus('error', data.error);
    } else {
      radar.innerHTML = '<img src="data:image/png;base64,' + data.image_b64 + '" alt="Radar">';
      pendingImage = data.image_b64;
      document.getElementById('narrative-text').value = data.narrative;
      document.getElementById('char-count').textContent = data.narrative.length;
      renderMetricBars(data.labels, data.values_a, data.values_b, data.arsenal_name, data.rival_name);
      document.getElementById('post-btn').disabled = false;
      showStatus('success', 'Radar ready! Edit the draft then click Post to X.');
    }
  } catch(e) { showStatus('error', e.message); }
  resetBtn();
}

function resetBtn() {
  var btn = document.getElementById('gen-btn');
  btn.disabled = false; btn.textContent = 'Generate Radar + Post \u2197';
}

function renderMetricBars(labels, vA, vB, nameA, nameB) {
  document.getElementById('metrics-title').textContent =
    nameA + (nameB ? ' vs ' + nameB : ' \u00b7 Percentile Rankings');
  var box = document.getElementById('metric-bars');
  box.innerHTML = '';
  labels.forEach(function(lbl, i) {
    var a = Math.round(vA[i]||0), b = vB ? Math.round(vB[i]||0) : null;
    var row = document.createElement('div'); row.className='metric-row';
    if (b !== null) {
      row.innerHTML = '<span class="metric-name">'+lbl+'</span>'
        +'<div class="metric-track">'
        +'<div class="mf-b" style="width:'+b+'%%"></div>'
        +'<div class="mf-a" style="width:'+a+'%%;position:absolute;top:0;left:0"></div>'
        +'</div>'
        +'<span class="metric-pct">'+a+'</span><span class="metric-pct-b">'+b+'</span>';
    } else {
      row.innerHTML = '<span class="metric-name">'+lbl+'</span>'
        +'<div class="metric-track"><div class="mf-a" style="width:'+a+'%%"></div></div>'
        +'<span class="metric-pct">'+a+'</span>';
    }
    box.appendChild(row);
  });
  document.getElementById('metrics-panel').classList.remove('hidden');
}

async function confirmPost() {
  if (!pendingImage) { showStatus('error','Generate a radar first'); return; }
  var narrative = document.getElementById('narrative-text').value.trim();
  if (!narrative) { showStatus('error','Post text is empty'); return; }
  var btn = document.getElementById('post-btn');
  btn.disabled=true; btn.innerHTML='<span class="spinner"></span>Posting...';
  showStatus('loading','Uploading image and posting to X...');
  try {
    var resp = await fetch('/post',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({narrative:narrative,image_b64:pendingImage})
    });
    var data = await resp.json();
    if (data.success) {
      showStatus('success','Posted! https://twitter.com/i/status/'+data.tweet_id);
      btn.textContent='Posted!'; refreshStatus();
    } else {
      showStatus('error',data.error); btn.disabled=false; btn.textContent='Post to X';
    }
  } catch(e) { showStatus('error',e.message); btn.disabled=false; btn.textContent='Post to X'; }
}

function showStatus(type, msg) {
  var bar = document.getElementById('status-bar');
  bar.className='status-bar '+type; bar.textContent=msg;
}

function renderScheduleSlots(state) {
  var nowUTC = new Date().toLocaleTimeString('en-GB',{timeZone:'UTC',hour:'2-digit',minute:'2-digit'});
  var nextSlot=null, minDiff=Infinity;
  SCHEDULE.forEach(function(s){
    var parts=s[0].split(':'), np=nowUTC.split(':');
    var diff=(parseInt(parts[0])*60+parseInt(parts[1]))-(parseInt(np[0])*60+parseInt(np[1]));
    if(diff<0)diff+=1440; if(diff<minDiff){minDiff=diff;nextSlot=s[0];}
  });
  document.getElementById('sched-slots').innerHTML=SCHEDULE.map(function(s){
    return '<div class="sched-slot">'
      +'<span class="sched-time">'+s[0]+'</span>'
      +'<span class="sched-type">'+(s[1]==='player'?'Player vs player':'Team vs team')+' &mdash; auto</span>'
      +'<span class="sched-dot'+(s[0]===nextSlot?' next':'')+'"></span></div>';
  }).join('');
  document.getElementById('stat-today').textContent = state.daily_count||0;
  document.getElementById('stat-last').textContent  = state.last_posted_at
    ? new Date(state.last_posted_at).toLocaleTimeString('en-GB',{timeZone:'UTC',hour:'2-digit',minute:'2-digit'})+' UTC'
    : '&#8212;';
  document.getElementById('stat-next').textContent  = nextSlot ? nextSlot+' UTC' : '&#8212;';
  if (state.log&&state.log.length) {
    document.getElementById('log-box').innerHTML =
      state.log.slice().reverse().map(function(l){return '<div>'+l+'</div>';}).join('');
  }
}

async function refreshStatus(){
  try{ var r=await fetch('/status'); renderScheduleSlots(await r.json()); }catch(e){}
}
refreshStatus();
setInterval(refreshStatus,15000);
</script>
</body>
</html>
"""


# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)


@app.route("/")
def index():
    # Build Arsenal player options from live squad cache
    def afc_opts(api_positions):
        return "\n".join(
            f'<option value="{p["id"]}" data-pos="{p["pos"]}" data-name="{p["name"]}">'
            f'{p["name"]} ({p["pos"]})</option>'
            for p in agent.arsenal_squad
            if p.get("api_pos", p["pos"]) in api_positions
        )

    # Build rival team options from live cache
    def team_player_opts(league_id):
        return "\n".join(
            f'<option value="{info["id"]}">{name}</option>'
            for name, info in sorted(agent.rival_teams.items())
            if info.get("league") == league_id
        )

    def team_opts(league_id):
        return "\n".join(
            f'<option value="{name}">{name}</option>'
            for name, info in sorted(agent.rival_teams.items())
            if info.get("league") == league_id
        )

    html = HTML % {
        "gk_options":              afc_opts(["Goalkeeper"]),
        "def_options":             afc_opts(["Defender"]),
        "mid_options":             afc_opts(["Midfielder"]),
        "fwd_options":             afc_opts(["Attacker"]),
        "pl_options":              team_player_opts(39),
        "laliga_options":          team_player_opts(140),
        "bundesliga_options":      team_player_opts(78),
        "seriea_options":          team_player_opts(135),
        "ligue1_options":          team_player_opts(61),
        "pl_team_options":         team_opts(39),
        "laliga_team_options":     team_opts(140),
        "bundesliga_team_options": team_opts(78),
        "seriea_team_options":     team_opts(135),
        "ligue1_team_options":     team_opts(61),
        "schedule_json":           json.dumps(SCHEDULE),
    }
    return html


@app.route("/squad/<int:team_id>")
def squad(team_id):
    """Returns live squad for any team via cache."""
    players = agent.cache.get_squad(team_id)
    return jsonify({"players": players})


@app.route("/generate", methods=["POST"])
def generate():
    data        = request.get_json()
    mode        = data.get("mode", "player")
    tone        = data.get("tone", "hype")
    custom_note = data.get("custom_note", "")

    if mode == "player":
        rival_team_id = data.get("rival_team_id")
        result = agent.build_player_comparison(
            arsenal_player_id=int(data.get("arsenal_player_id", 0)),
            arsenal_player_name=data.get("arsenal_player_name", ""),
            arsenal_pos=data.get("arsenal_pos", "MF"),
            rival_name=data.get("rival_player", ""),
            rival_team_id=int(rival_team_id) if rival_team_id else None,
            tone=tone,
            custom_note=custom_note,
        )
    else:
        result = agent.build_team_comparison(
            rival_team_key=data.get("rival_team", ""),
            tone=tone,
            custom_note=custom_note,
        )

    if "error" in result:
        return jsonify({"error": result["error"]})

    with _pending_lock:
        _pending["image_bytes"] = result["image_bytes"]

    return jsonify({
        "image_b64":    base64.b64encode(result["image_bytes"]).decode(),
        "narrative":    result["narrative"],
        "labels":       result["labels"],
        "values_a":     result["values_a"],
        "values_b":     result.get("values_b"),
        "arsenal_name": result["arsenal_name"],
        "rival_name":   result.get("rival_name"),
    })


@app.route("/post", methods=["POST"])
def post():
    data      = request.get_json()
    narrative = data.get("narrative", "").strip()
    img_b64   = data.get("image_b64", "")
    if not narrative:
        return jsonify({"success": False, "error": "Empty narrative"})
    try:
        image_bytes = base64.b64decode(img_b64)
    except Exception:
        with _pending_lock:
            image_bytes = _pending.get("image_bytes")
        if not image_bytes:
            return jsonify({"success": False, "error": "No image available"})
    result = agent.post_to_x(narrative, image_bytes)
    if result["success"]:
        _record_post(result["tweet_id"], "manual")
        _log(f"Manual post: {result['tweet_id']}")
    return jsonify(result)


@app.route("/status")
def status():
    with _state_lock:
        return jsonify(dict(_state))


@app.route("/health")
def health():
    with _state_lock:
        count = _state["daily_count"]
    return f"Arsenal DataMB Agent RUNNING | posts today: {count}", 200


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=scheduler_loop, daemon=True).start()
    logger.info("Arsenal DataMB X Agent starting")
    logger.info(f"Schedule: {SCHEDULE}")
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
