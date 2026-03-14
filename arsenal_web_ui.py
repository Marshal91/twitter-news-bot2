"""
═══════════════════════════════════════════════════════════════════════════════
    ARSENAL DATAMB X AGENT  —  Flask Web UI
    Run: python arsenal_web_ui.py
    Opens on: http://localhost:5000  (or your Render URL)
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import io
import base64
import logging
import threading
from flask import Flask, render_template_string, request, jsonify, send_file
import tweepy
from dotenv import load_dotenv

load_dotenv()

# ── Twitter clients (reuse from existing bot) ─────────────────────────────
TWITTER_API_KEY      = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET   = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET= os.getenv("TWITTER_ACCESS_SECRET")

auth = tweepy.OAuth1UserHandler(
    TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
)
twitter_api_v1 = tweepy.API(auth)
twitter_client_v2 = tweepy.Client(
    consumer_key=TWITTER_API_KEY,
    consumer_secret=TWITTER_API_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_SECRET,
)

from arsenal_datamb_agent import (
    ArsenalDataMBAgent,
    ARSENAL_SQUAD,
    RIVAL_TEAMS,
)

agent = ArsenalDataMBAgent(
    twitter_api=twitter_api_v1,
    twitter_client=twitter_client_v2,
)

# In-memory session store (one pending post at a time)
_pending: dict = {}
_lock = threading.Lock()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ─────────────────────────────────────────────────────────────────────────────
# HTML TEMPLATE  (single-file, dark Arsenal aesthetic)
# ─────────────────────────────────────────────────────────────────────────────

HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Arsenal DataMB X Agent</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;600;700&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --red:#EF0107;--red-dark:#9B0005;--gold:#DB9C33;
  --bg:#0A0A0A;--surface:#141414;--surface2:#1C1C1C;--surface3:#262626;
  --border:rgba(255,255,255,0.08);--text:#fff;--muted:rgba(255,255,255,0.45);
  --secondary:rgba(255,255,255,0.7);
}
body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;min-height:100vh}

/* HEADER */
.header{
  background:linear-gradient(135deg,#0A0A0A 0%,#1a0000 60%,#0d0000 100%);
  border-bottom:1px solid rgba(239,1,7,.25);
  padding:14px 24px;display:flex;align-items:center;gap:14px;
}
.header h1{font-family:'Oswald',sans-serif;font-size:20px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase}
.header p{font-size:11px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-top:2px}
.crest{width:40px;height:40px;flex-shrink:0}
.badge{margin-left:auto;background:var(--red);color:#fff;font-family:'Oswald',sans-serif;
  font-size:10px;font-weight:600;letter-spacing:1.5px;padding:4px 10px;border-radius:4px;text-transform:uppercase}

/* LAYOUT */
.container{max-width:1100px;margin:0 auto;padding:24px 16px;display:grid;grid-template-columns:340px 1fr;gap:20px}
@media(max-width:780px){.container{grid-template-columns:1fr}}

/* PANEL */
.panel{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px}
.section-label{font-family:'Oswald',sans-serif;font-size:11px;font-weight:600;letter-spacing:1.5px;
  text-transform:uppercase;color:var(--muted);margin-bottom:10px}

/* TABS */
.tab-row{display:flex;border-bottom:1px solid var(--border);margin-bottom:16px}
.tab{flex:1;padding:10px;font-family:'Oswald',sans-serif;font-size:12px;font-weight:600;
  letter-spacing:1px;text-transform:uppercase;color:var(--muted);background:none;border:none;
  cursor:pointer;border-bottom:2px solid transparent;transition:.2s}
.tab.active{color:var(--red);border-bottom-color:var(--red)}

/* FORM ELEMENTS */
select,input[type=text]{
  width:100%;background:var(--surface2);border:1px solid var(--border);border-radius:8px;
  color:var(--text);font-family:'DM Sans',sans-serif;font-size:13px;padding:9px 11px;
  outline:none;margin-bottom:10px;transition:border-color .2s;
}
select:hover,input[type=text]:hover,select:focus,input[type=text]:focus{border-color:rgba(239,1,7,.4)}
label{font-size:12px;color:var(--muted);display:block;margin-bottom:4px;text-transform:uppercase;
  font-family:'Oswald',sans-serif;letter-spacing:.8px}

.tone-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px}
.tone-btn{background:var(--surface2);border:1px solid var(--border);border-radius:8px;
  color:var(--secondary);font-size:12px;padding:8px;cursor:pointer;transition:.2s;text-align:center}
.tone-btn.active{border-color:var(--red);color:var(--text);background:rgba(239,1,7,.12)}
.tone-btn:hover{border-color:rgba(239,1,7,.3)}

.btn{border:none;border-radius:8px;font-family:'Oswald',sans-serif;font-size:13px;font-weight:600;
  letter-spacing:1px;text-transform:uppercase;cursor:pointer;padding:10px 18px;transition:.15s}
.btn-primary{background:var(--red);color:#fff;width:100%}
.btn-primary:hover{background:#c8000a}
.btn-primary:active{transform:scale(.97)}
.btn-primary:disabled{background:#555;cursor:not-allowed}
.btn-secondary{background:var(--surface3);color:var(--secondary);border:1px solid var(--border)}
.btn-secondary:hover{background:var(--surface2)}
.btn-post{background:#1DA1F2;color:#fff;width:100%;margin-top:10px}
.btn-post:hover{background:#1a8cd8}
.btn-post:disabled{background:#555;cursor:not-allowed}

/* RIGHT PANEL */
.preview-area{display:flex;flex-direction:column;gap:16px}
.radar-container{background:var(--surface2);border:1px solid var(--border);border-radius:10px;
  overflow:hidden;text-align:center;min-height:320px;display:flex;align-items:center;justify-content:center}
.radar-container img{width:100%;max-width:560px;display:block}
.radar-placeholder{color:var(--muted);font-size:14px;padding:40px}

.narrative-box{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px;position:relative}
.narrative-box textarea{
  width:100%;background:transparent;border:none;color:var(--secondary);
  font-family:'DM Sans',sans-serif;font-size:14px;line-height:1.65;
  resize:vertical;min-height:120px;outline:none;
}
.char-count{font-size:11px;color:var(--muted);text-align:right;margin-top:4px}

.status-bar{padding:10px 14px;border-radius:8px;font-size:13px;text-align:center;display:none}
.status-bar.success{background:rgba(0,200,100,.12);border:1px solid rgba(0,200,100,.3);color:#00c864;display:block}
.status-bar.error{background:rgba(239,1,7,.1);border:1px solid rgba(239,1,7,.3);color:#ff6b6b;display:block}
.status-bar.loading{background:rgba(255,255,255,.05);border:1px solid var(--border);color:var(--secondary);display:block}

/* STATS ROW */
.stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px}
.stat-card{background:var(--surface3);border:1px solid var(--border);border-radius:8px;padding:10px;text-align:center}
.stat-val{font-family:'Oswald',sans-serif;font-size:18px;font-weight:700;color:var(--text)}
.stat-lbl{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;margin-top:2px}

/* SPINNER */
.spinner{display:inline-block;width:14px;height:14px;border:2px solid rgba(255,255,255,.2);
  border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;vertical-align:middle;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}

/* METRIC BARS */
.metric-list{display:flex;flex-direction:column;gap:6px;margin-top:10px}
.metric-row{display:flex;align-items:center;gap:8px}
.metric-name{font-size:11px;color:var(--muted);width:100px;font-family:'Oswald',sans-serif;
  text-transform:uppercase;letter-spacing:.4px}
.metric-track{flex:1;height:5px;background:var(--surface3);border-radius:3px;overflow:hidden;position:relative}
.metric-fill-a{height:100%;background:var(--red);border-radius:3px;transition:width .8s cubic-bezier(.22,.68,0,1.2)}
.metric-fill-b{height:100%;background:#4A90D9;border-radius:3px;transition:width .8s cubic-bezier(.22,.68,0,1.2);
  position:absolute;top:0;left:0;opacity:.6}
.metric-pct{font-family:'Oswald',sans-serif;font-size:11px;font-weight:600;color:var(--text);width:26px;text-align:right}
.metric-pct-b{font-family:'Oswald',sans-serif;font-size:11px;color:#4A90D9;width:26px;text-align:right}

input[type=text]::placeholder{color:var(--muted)}
.hidden{display:none}
</style>
</head>
<body>

<div class="header">
  <svg class="crest" viewBox="0 0 40 40" fill="none">
    <circle cx="20" cy="20" r="19" fill="#EF0107" stroke="#9B0005" stroke-width="1"/>
    <path d="M20 5 L25 12 L33 10 L29 18 L35 24 L27 23 L25 31 L20 26 L15 31 L13 23 L5 24 L11 18 L7 10 L15 12 Z"
          fill="#DB9C33"/>
    <circle cx="20" cy="20" r="4" fill="#0A0A0A"/>
    <circle cx="20" cy="20" r="2.5" fill="#EF0107"/>
  </svg>
  <div>
    <h1>Arsenal DataMB X Agent</h1>
    <p>Real Stats · Radar Cards · Auto-Post to X</p>
  </div>
  <span class="badge">DataMB Style</span>
</div>

<div class="container">

  <!-- LEFT: Controls -->
  <div class="panel">
    <div class="tab-row">
      <button class="tab active" onclick="switchMode('player',this)">Player vs Player</button>
      <button class="tab" onclick="switchMode('team',this)">Team vs Team</button>
    </div>

    <!-- PLAYER MODE -->
    <div id="player-mode">
      <div class="section-label">Arsenal Player</div>
      <select id="arsenal-player">
        <option value="">— Select Arsenal Player —</option>
        {% for key, info in arsenal_squad.items() %}
        <option value="{{ key }}">{{ info.name }} ({{ info.pos }})</option>
        {% endfor %}
      </select>

      <div class="section-label">Rival Player</div>
      <input type="text" id="rival-player-name" placeholder="e.g. Mohamed Salah">

      <div class="section-label" style="margin-top:4px">Rival Team (helps search)</div>
      <select id="rival-player-team">
        <option value="">— Any team —</option>
        {% for name, info in rival_teams.items() %}
        <option value="{{ info.id }}">{{ name }}</option>
        {% endfor %}
      </select>
    </div>

    <!-- TEAM MODE -->
    <div id="team-mode" class="hidden">
      <div class="section-label">Arsenal vs</div>
      <select id="rival-team">
        <option value="">— Select Rival Team —</option>
        {% for name in rival_teams.keys() %}
        <option value="{{ name }}">{{ name }}</option>
        {% endfor %}
      </select>
    </div>

    <!-- TONE -->
    <div class="section-label" style="margin-top:6px">Narrative Tone</div>
    <div class="tone-grid">
      <button class="tone-btn active" data-tone="hype" onclick="setTone(this)">🔥 Hype</button>
      <button class="tone-btn" data-tone="analytical" onclick="setTone(this)">📊 Analytical</button>
      <button class="tone-btn" data-tone="banter" onclick="setTone(this)">😈 Banter</button>
      <button class="tone-btn" data-tone="historic" onclick="setTone(this)">🏆 Historic</button>
      <button class="tone-btn" data-tone="tactical" onclick="setTone(this)">🧠 Tactical</button>
    </div>

    <div class="section-label">Custom Note (optional)</div>
    <input type="text" id="custom-note" placeholder="e.g. Rice best CDM in Europe">

    <button class="btn btn-primary" id="generate-btn" onclick="generate()">
      Generate Radar + Post ↗
    </button>
  </div>

  <!-- RIGHT: Preview + Post -->
  <div class="preview-area">

    <!-- Radar Image -->
    <div class="panel" style="padding:0;overflow:hidden">
      <div class="radar-container" id="radar-container">
        <div class="radar-placeholder">⚽ Select players/teams and click Generate</div>
      </div>
    </div>

    <!-- Metric Bars -->
    <div class="panel hidden" id="metrics-panel">
      <div class="section-label" id="metrics-title">Percentile Rankings</div>
      <div class="metric-list" id="metric-bars"></div>
    </div>

    <!-- Narrative -->
    <div class="panel">
      <div class="section-label">X Post Draft</div>
      <div class="narrative-box">
        <textarea id="narrative-text" placeholder="Your Arsenal-biased post will appear here after generating..."></textarea>
        <div class="char-count"><span id="char-count">0</span> chars</div>
      </div>

      <div id="status-bar" class="status-bar"></div>

      <button class="btn btn-post" id="post-btn" onclick="confirmPost()" disabled>
        Post to X 🐦
      </button>
    </div>

  </div>
</div>

<script>
let currentMode = 'player';
let currentTone = 'hype';
let pendingImage = null;

function switchMode(mode, btn) {
  currentMode = mode;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('player-mode').classList.toggle('hidden', mode !== 'player');
  document.getElementById('team-mode').classList.toggle('hidden', mode !== 'team');
}

function setTone(btn) {
  document.querySelectorAll('.tone-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentTone = btn.dataset.tone;
}

document.getElementById('narrative-text').addEventListener('input', function() {
  document.getElementById('char-count').textContent = this.value.length;
});

async function generate() {
  const btn = document.getElementById('generate-btn');
  const radarBox = document.getElementById('radar-container');
  const statusBar = document.getElementById('status-bar');

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Fetching stats...';
  statusBar.className = 'status-bar loading';
  statusBar.textContent = '⏳ Fetching real PL stats from API-Football...';
  radarBox.innerHTML = '<div class="radar-placeholder">⏳ Generating radar card...</div>';

  let payload = { tone: currentTone, custom_note: document.getElementById('custom-note').value };

  if (currentMode === 'player') {
    payload.mode = 'player';
    payload.arsenal_player = document.getElementById('arsenal-player').value;
    payload.rival_player   = document.getElementById('rival-player-name').value;
    payload.rival_team_id  = document.getElementById('rival-player-team').value || null;
    if (!payload.arsenal_player) {
      showStatus('error', '❌ Please select an Arsenal player');
      btn.disabled = false; btn.textContent = 'Generate Radar + Post ↗';
      return;
    }
  } else {
    payload.mode = 'team';
    payload.rival_team = document.getElementById('rival-team').value;
    if (!payload.rival_team) {
      showStatus('error', '❌ Please select a rival team');
      btn.disabled = false; btn.textContent = 'Generate Radar + Post ↗';
      return;
    }
  }

  try {
    const resp = await fetch('/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await resp.json();

    if (data.error) {
      showStatus('error', '❌ ' + data.error);
    } else {
      // Show radar image
      radarBox.innerHTML = `<img src="data:image/png;base64,${data.image_b64}" alt="Radar Chart">`;
      pendingImage = data.image_b64;

      // Narrative
      const textarea = document.getElementById('narrative-text');
      textarea.value = data.narrative;
      document.getElementById('char-count').textContent = data.narrative.length;

      // Metric bars
      renderMetricBars(data.labels, data.values_a, data.values_b,
                       data.arsenal_name, data.rival_name);

      document.getElementById('post-btn').disabled = false;
      showStatus('success', '✅ Radar generated! Edit the post draft, then click Post to X.');
    }
  } catch(e) {
    showStatus('error', '❌ Network error: ' + e.message);
  }

  btn.disabled = false;
  btn.innerHTML = 'Generate Radar + Post ↗';
}

function renderMetricBars(labels, valsA, valsB, nameA, nameB) {
  const panel = document.getElementById('metrics-panel');
  const title = document.getElementById('metrics-title');
  const container = document.getElementById('metric-bars');

  title.textContent = nameA + (nameB ? ' (🔴) vs ' + nameB + ' (🔵)' : ' · Percentile Rankings');
  container.innerHTML = '';

  labels.forEach((lbl, i) => {
    const a = Math.round(valsA[i] || 0);
    const b = valsB ? Math.round(valsB[i] || 0) : null;

    const row = document.createElement('div');
    row.className = 'metric-row';

    if (b !== null) {
      row.innerHTML = `
        <span class="metric-name">${lbl}</span>
        <div class="metric-track">
          <div class="metric-fill-b" style="width:${b}%"></div>
          <div class="metric-fill-a" style="width:${a}%;position:absolute;top:0;left:0"></div>
        </div>
        <span class="metric-pct" style="color:var(--red)">${a}</span>
        <span class="metric-pct-b">${b}</span>
      `;
    } else {
      row.innerHTML = `
        <span class="metric-name">${lbl}</span>
        <div class="metric-track"><div class="metric-fill-a" style="width:${a}%"></div></div>
        <span class="metric-pct">${a}</span>
      `;
    }
    container.appendChild(row);
  });

  panel.classList.remove('hidden');
}

async function confirmPost() {
  if (!pendingImage) { showStatus('error', '❌ Generate a radar first'); return; }

  const narrative = document.getElementById('narrative-text').value.trim();
  if (!narrative) { showStatus('error', '❌ Post text cannot be empty'); return; }

  const btn = document.getElementById('post-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Posting...';
  showStatus('loading', '⏳ Uploading image and posting to X...');

  try {
    const resp = await fetch('/post', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ narrative, image_b64: pendingImage })
    });
    const data = await resp.json();
    if (data.success) {
      showStatus('success',
        `✅ Posted! View: https://twitter.com/user/status/${data.tweet_id}`);
      btn.textContent = '✅ Posted!';
    } else {
      showStatus('error', '❌ Post failed: ' + data.error);
      btn.disabled = false;
      btn.textContent = 'Post to X 🐦';
    }
  } catch(e) {
    showStatus('error', '❌ ' + e.message);
    btn.disabled = false;
    btn.textContent = 'Post to X 🐦';
  }
}

function showStatus(type, msg) {
  const bar = document.getElementById('status-bar');
  bar.className = 'status-bar ' + type;
  bar.textContent = msg;
}
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(
        HTML,
        arsenal_squad=ARSENAL_SQUAD,
        rival_teams=RIVAL_TEAMS,
    )


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    mode        = data.get("mode", "player")
    tone        = data.get("tone", "hype")
    custom_note = data.get("custom_note", "")

    if mode == "player":
        arsenal_key    = data.get("arsenal_player", "")
        rival_name     = data.get("rival_player", "")
        rival_team_id  = data.get("rival_team_id")

        result = agent.build_player_comparison(
            arsenal_key=arsenal_key,
            rival_name=rival_name,
            rival_team_id=int(rival_team_id) if rival_team_id else None,
            tone=tone,
            custom_note=custom_note,
        )
    else:
        rival_team = data.get("rival_team", "")
        result = agent.build_team_comparison(
            rival_team_key=rival_team,
            tone=tone,
            custom_note=custom_note,
        )

    if "error" in result:
        return jsonify({"error": result["error"]})

    # Store in pending (thread-safe)
    with _lock:
        _pending["image_bytes"] = result["image_bytes"]

    img_b64 = base64.b64encode(result["image_bytes"]).decode("utf-8")

    return jsonify({
        "image_b64":   img_b64,
        "narrative":   result["narrative"],
        "labels":      result["labels"],
        "values_a":    result["values_a"],
        "values_b":    result.get("values_b"),
        "arsenal_name": result["arsenal_name"],
        "rival_name":  result.get("rival_name"),
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
        with _lock:
            image_bytes = _pending.get("image_bytes")
        if not image_bytes:
            return jsonify({"success": False, "error": "No image available"})

    result = agent.post_to_x(narrative, image_bytes)
    return jsonify(result)


@app.route("/health")
def health():
    return "Arsenal DataMB X Agent: RUNNING", 200


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
