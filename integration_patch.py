"""
═══════════════════════════════════════════════════════════════════════════════
    INTEGRATION PATCH
    Adds Arsenal DataMB agent as a scheduled post type to your existing bot.
    
    HOW TO USE:
    1. Place arsenal_datamb_agent.py in same folder as your main bot
    2. Add this file's content into your main bot OR import it
    3. Set API_FOOTBALL_KEY in your .env
    4. Add "datamb_arsenal" slots to POSTING_SCHEDULE (see example below)
═══════════════════════════════════════════════════════════════════════════════
"""

# ── ADD TO YOUR .env FILE ────────────────────────────────────────────────────
# API_FOOTBALL_KEY=your_key_here   # free at api-football.com (100 calls/day)

# ── ADD TO POSTING SCHEDULE (your main bot) ───────────────────────────────────
#
# POSTING_SCHEDULE = [
#     ...existing entries...
#     ("07:00", "datamb_arsenal"),   # Morning DataMB player/team card
#     ("15:30", "datamb_arsenal"),   # Afternoon DataMB card
# ]

# ── ADD TO YOUR CompleteCryptoArsenalBot.__init__ ─────────────────────────────
#
# from arsenal_datamb_agent import ArsenalDataMBAgent, ARSENAL_SQUAD, RIVAL_TEAMS
# self.datamb_agent = ArsenalDataMBAgent(
#     twitter_api=twitter_api,          # your existing tweepy.API
#     twitter_client=twitter_client,    # your existing tweepy.Client
# )
# self.datamb_player_keys = list(ARSENAL_SQUAD.keys())
# self.datamb_rival_teams = list(RIVAL_TEAMS.keys())

# ── ADD TO run_posting_cycle ─────────────────────────────────────────────────
#
# elif post_type == 'datamb_arsenal':
#     return self.run_datamb_cycle()

# ── ADD THIS METHOD TO CompleteCryptoArsenalBot ───────────────────────────────

import random
import logging
logger = logging.getLogger(__name__)

DATAMB_TONES = ["hype", "analytical", "banter", "historic", "tactical"]

# Schedules: alternate player vs team posts
DATAMB_POST_SEQUENCE = [
    {"mode": "player"},
    {"mode": "team"},
    {"mode": "player"},
    {"mode": "team"},
]
_datamb_seq_index = 0


def run_datamb_cycle(self):
    """
    Runs one DataMB Arsenal post cycle.
    Alternates between player comparisons and team comparisons.
    Add this method to CompleteCryptoArsenalBot.
    """
    global _datamb_seq_index

    tone = random.choice(DATAMB_TONES)
    mode_entry = DATAMB_POST_SEQUENCE[_datamb_seq_index % len(DATAMB_POST_SEQUENCE)]
    _datamb_seq_index += 1

    try:
        if mode_entry["mode"] == "player":
            # Pick a random Arsenal player
            arsenal_key = random.choice(self.datamb_player_keys)

            # Pick a plausible rival player based on position
            from arsenal_datamb_agent import ARSENAL_SQUAD, RIVAL_TEAMS
            pos = ARSENAL_SQUAD[arsenal_key]["pos"]

            # Position-keyed rival player suggestions
            rival_map = {
                "GK": [("Alisson",        40),  ("Ederson",       50),  ("Flekken",       34)],
                "CB": [("Virgil van Dijk", 40),  ("Ruben Dias",    50),  ("John Stones",   50)],
                "FB": [("Trent Alexander-Arnold", 40), ("Andy Robertson", 40)],
                "MF": [("Rodri",          50),   ("Bruno Fernandes", 33), ("Martin Ødegaard", 42)],
                "WG": [("Mohamed Salah",  40),   ("Son Heung-min", 47),  ("Cole Palmer",   49)],
                "ST": [("Erling Haaland", 50),   ("Darwin Nunez", 40),   ("Alexander Isak", 34)],
            }
            rivals_for_pos = rival_map.get(pos, [("Mohamed Salah", 40)])
            rival_name, rival_team_id = random.choice(rivals_for_pos)

            logger.info(f"⚽ DataMB: {ARSENAL_SQUAD[arsenal_key]['name']} vs {rival_name} | tone={tone}")
            result = self.datamb_agent.build_player_comparison(
                arsenal_key=arsenal_key,
                rival_name=rival_name,
                rival_team_id=rival_team_id,
                tone=tone,
            )

        else:
            rival_team = random.choice(self.datamb_rival_teams)
            logger.info(f"⚽ DataMB: Arsenal vs {rival_team} | tone={tone}")
            result = self.datamb_agent.build_team_comparison(
                rival_team_key=rival_team,
                tone=tone,
            )

        if "error" in result:
            logger.error(f"DataMB cycle error: {result['error']}")
            return False

        post_result = self.datamb_agent.post_to_x(
            narrative=result["narrative"],
            image_bytes=result["image_bytes"],
        )

        if post_result["success"]:
            logger.info(f"✅ DataMB post live: {post_result['tweet_id']}")
            return True
        else:
            logger.error(f"DataMB post failed: {post_result['error']}")
            return False

    except Exception as e:
        logger.error(f"DataMB cycle exception: {e}")
        return False


# ── REQUIREMENTS TO ADD TO requirements.txt ──────────────────────────────────
ADDITIONAL_REQUIREMENTS = """
# Add these to your existing requirements.txt:
matplotlib==3.9.2
numpy==1.26.4
flask==3.0.3
"""

# ── RENDER SERVICE CONFIG ─────────────────────────────────────────────────────
#
# Add a SECOND Render web service (alongside your existing bot):
#
# Name:        arsenal-datamb-ui
# Runtime:     Python 3
# Build cmd:   pip install -r requirements.txt
# Start cmd:   python arsenal_web_ui.py
# Port:        5001
# Env vars:    (same as your bot: TWITTER_*, OPENAI_API_KEY, API_FOOTBALL_KEY)
#
# Your existing bot continues running unchanged.
# The web UI is a separate process at e.g. https://arsenal-datamb-ui.onrender.com

print("Integration patch loaded. See comments for setup instructions.")
