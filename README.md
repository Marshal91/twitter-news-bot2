# ═══════════════════════════════════════════════════════════════════════
#  ARSENAL DATAMB X AGENT — SETUP README
# ═══════════════════════════════════════════════════════════════════════

## FILES
# arsenal_datamb_agent.py  — Core agent (stats, radar, narrative, X post)
# arsenal_web_ui.py        — Flask web UI (runs on Render)
# integration_patch.py     — How to wire into your existing bot

## STEP 1 — Get API-Football key (FREE)
# 1. Go to https://dashboard.api-football.com/register
# 2. Free tier: 100 calls/day (enough for ~10-15 radar posts/day with caching)
# 3. Add to .env:
#    API_FOOTBALL_KEY=your_key_here

## STEP 2 — Add to requirements.txt
matplotlib==3.9.2
numpy==1.26.4
flask==3.0.3
# (tweepy, openai, python-dotenv already in your existing requirements.txt)

## STEP 3 — Deploy web UI as separate Render service
# Build: pip install -r requirements.txt
# Start: python arsenal_web_ui.py
# Port:  5001
# Same env vars as your existing bot + API_FOOTBALL_KEY

## STEP 4 — (Optional) Add DataMB posts to your existing bot scheduler
# See integration_patch.py for exact code to add

## HOW THE WEB UI WORKS
# 1. Open your Render URL
# 2. Choose Player vs Player OR Team vs Team tab
# 3. Select Arsenal player from dropdown
# 4. Type rival player name (e.g. "Mohamed Salah")
# 5. Pick a tone (Hype / Analytical / Banter / Historic / Tactical)
# 6. Click "Generate Radar + Post"
#    → Real PL stats fetched from API-Football
#    → DataMB-style radar PNG generated
#    → Arsenal-biased narrative written by GPT-4o-mini
# 7. Edit the draft post text if needed
# 8. Click "Post to X" → image + text auto-posted to your X account

## STAT ACCURACY NOTE
# API-Football free tier provides:
#   ✅ Goals, assists, passes, dribbles, duels, tackles, shots, saves
#   ❌ xG/xA (expected goals — Pro tier only on most providers)
#   ❌ Progressive passes/carries (Opta/StatsBomb metric — not in free APIs)
# For xG and progressive metrics, the agent uses calibrated estimates
# based on available data. Percentile values are normalised against
# sensible per-90 maxima for elite PL players.
# For a production system with full DataMB-level accuracy, upgrade to:
#   - StatsBomb Open Data (free for research)
#   - FBref.com scraping (research use)
#   - Opta/Stats Perform API (paid, used by DataMB itself)

## TWITTER IMAGE POSTING NOTE
# Image upload requires the v1.1 endpoint (twitter_api.media_upload)
# Your existing bot already has this set up via tweepy.API(auth).
# The web UI reuses the exact same twitter_api_v1 and twitter_client_v2
# instances — no additional Twitter API tier needed.
