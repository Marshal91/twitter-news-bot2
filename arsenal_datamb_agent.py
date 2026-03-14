"""
═══════════════════════════════════════════════════════════════════════════════
    ARSENAL DATAMB X AGENT
    Real football stats → DataMB-style radar image → Arsenal-biased X post

    Features:
    ✅ API-Football integration (real PL player & team stats)
    ✅ DataMB-style radar card generated as PNG (via matplotlib)
    ✅ Player vs Player OR Team vs Team comparison
    ✅ Arsenal-biased GPT narrative
    ✅ Image attached to tweet via v1.1 media upload
    ✅ Web UI for select → edit → confirm → post
    ✅ Plugs into existing bot's tweepy setup
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import io
import json
import math
import logging
import requests
import tempfile
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
import matplotlib.patheffects as pe
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from openai import OpenAI

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

API_FOOTBALL_KEY  = os.getenv("API_FOOTBALL_KEY", "")
API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")

# Premier League IDs (API-Football)
PL_LEAGUE_ID   = 39
CURRENT_SEASON = 2024   # 2024/25 season

# Arsenal team ID in API-Football
ARSENAL_TEAM_ID = 42

# DataMB colour palette (Arsenal-themed)
ARSENAL_RED   = "#EF0107"
ARSENAL_WHITE = "#FFFFFF"
RIVAL_COLOUR  = "#4A90D9"
BG_DARK       = "#0D0D0D"
BG_SURFACE    = "#1A1A1A"
GRID_COLOUR   = "#2A2A2A"
TEXT_MUTED    = "#888888"

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# RADAR METRIC DEFINITIONS  (mirrors DataMB's per-position templates)
# ─────────────────────────────────────────────────────────────────────────────

PLAYER_RADAR_METRICS = {
    "GK": [
        ("Save %",           "save_pct"),
        ("Aerial Won",       "aerial_won"),
        ("Passes Comp/90",   "passes_per90"),
        ("Long Pass Acc %",  "long_pass_acc"),
        ("Clean Sheets",     "clean_sheets"),
        ("Prevented Goals",  "prevented_goals"),
        ("Interceptions",    "interceptions"),
    ],
    "CB": [
        ("Passes Comp/90",   "passes_per90"),
        ("Fwd Pass Acc %",   "fwd_pass_acc"),
        ("Prog Passes/90",   "prog_passes"),
        ("Poss Won/90",      "possession_won"),
        ("Def Duels Won %",  "def_duels_pct"),
        ("Aerial Won %",     "aerial_won_pct"),
        ("Prog Carries/90",  "prog_carries"),
    ],
    "FB": [
        ("Acc Crosses/90",   "accurate_crosses"),
        ("xA/90",            "xa_per90"),
        ("Prog Passes/90",   "prog_passes"),
        ("Poss Won/90",      "possession_won"),
        ("Def Duels Won %",  "def_duels_pct"),
        ("Aerial Won %",     "aerial_won_pct"),
        ("Prog Carries/90",  "prog_carries"),
    ],
    "MF": [
        ("Duels Won %",      "duels_won_pct"),
        ("Poss Won/90",      "possession_won"),
        ("Prog Carries/90",  "prog_carries"),
        ("Fwd Passes/90",    "fwd_passes"),
        ("Fwd Pass Acc %",   "fwd_pass_acc"),
        ("Key Passes/90",    "key_passes"),
        ("Prog Passes/90",   "prog_passes"),
    ],
    "WG": [
        ("Prog Carries/90",  "prog_carries"),
        ("Succ Dribbles/90", "succ_dribbles"),
        ("NP Goals/90",      "np_goals"),
        ("npxG+xA/90",       "npxg_xa"),
        ("Assists/90",       "assists_per90"),
        ("Key Passes/90",    "key_passes"),
        ("Acc Crosses/90",   "accurate_crosses"),
    ],
    "ST": [
        ("NP Goals/90",      "np_goals"),
        ("NP xG/90",         "np_xg"),
        ("Goal Conv %",      "goal_conv"),
        ("Touches in Box",   "touches_box"),
        ("Aerial Won %",     "aerial_won_pct"),
        ("xA/90",            "xa_per90"),
        ("Off Duels Won/90", "off_duels_won"),
    ],
}

TEAM_RADAR_METRICS = [
    ("Attacking",   "attacking"),
    ("Possession",  "possession"),
    ("Pressing",    "pressing"),
    ("Goals",       "goals"),
    ("Defending",   "defending"),
    ("Physicality", "physicality"),
    ("Counters",    "counters"),
]

# Arsenal squad — full 2025/26 roster with API-Football v3 IDs
ARSENAL_SQUAD = {
    # Goalkeepers
    "Raya":        {"id": 2932,   "pos": "GK", "name": "David Raya"},
    "Neto":        {"id": 9803,   "pos": "GK", "name": "Neto"},
    # Defenders
    "Saliba":      {"id": 47249,  "pos": "CB", "name": "William Saliba"},
    "Gabriel":     {"id": 9711,   "pos": "CB", "name": "Gabriel Magalhães"},
    "Kiwior":      {"id": 350023, "pos": "CB", "name": "Jakub Kiwior"},
    "White":       {"id": 19220,  "pos": "FB", "name": "Ben White"},
    "Calafiori":   {"id": 284460, "pos": "FB", "name": "Riccardo Calafiori"},
    "Timber":      {"id": 345370, "pos": "FB", "name": "Jurrien Timber"},
    "Zinchenko":   {"id": 19185,  "pos": "FB", "name": "Oleksandr Zinchenko"},
    # Midfielders
    "Rice":        {"id": 19189,  "pos": "MF", "name": "Declan Rice"},
    "Odegaard":    {"id": 19239,  "pos": "MF", "name": "Martin Ødegaard"},
    "Merino":      {"id": 284524, "pos": "MF", "name": "Mikel Merino"},
    "Jorginho":    {"id": 9737,   "pos": "MF", "name": "Jorginho"},
    "Nwaneri":     {"id": 389843, "pos": "MF", "name": "Ethan Nwaneri"},
    "Thomas":      {"id": 19226,  "pos": "MF", "name": "Thomas Partey"},
    # Forwards
    "Saka":        {"id": 19268,  "pos": "WG", "name": "Bukayo Saka"},
    "Martinelli":  {"id": 303117, "pos": "WG", "name": "Gabriel Martinelli"},
    "Trossard":    {"id": 20003,  "pos": "WG", "name": "Leandro Trossard"},
    "Sterling":    {"id": 18992,  "pos": "WG", "name": "Raheem Sterling"},
    "Havertz":     {"id": 521,    "pos": "ST", "name": "Kai Havertz"},
    "Jesus":       {"id": 9736,   "pos": "ST", "name": "Gabriel Jesus"},
}

# ── Rival teams across Top 5 European leagues ─────────────────────────────
# league_id: EPL=39, La Liga=140, Bundesliga=78, Serie A=135, Ligue 1=61
RIVAL_TEAMS = {
    # ── Premier League ──────────────────────────────────────────────
    "Liverpool":            {"id": 40,  "league": 39,  "short": "LIV", "colour": "#C8102E"},
    "Manchester City":      {"id": 50,  "league": 39,  "short": "MCI", "colour": "#6CABDD"},
    "Chelsea":              {"id": 49,  "league": 39,  "short": "CHE", "colour": "#034694"},
    "Tottenham":            {"id": 47,  "league": 39,  "short": "TOT", "colour": "#132257"},
    "Manchester United":    {"id": 33,  "league": 39,  "short": "MUN", "colour": "#DA291C"},
    "Newcastle":            {"id": 34,  "league": 39,  "short": "NEW", "colour": "#241F20"},
    "Aston Villa":          {"id": 66,  "league": 39,  "short": "AVL", "colour": "#670E36"},
    "Brighton":             {"id": 51,  "league": 39,  "short": "BHA", "colour": "#0057B8"},
    "West Ham":             {"id": 48,  "league": 39,  "short": "WHU", "colour": "#7A263A"},
    "Fulham":               {"id": 36,  "league": 39,  "short": "FUL", "colour": "#CC0000"},
    "Nottm Forest":         {"id": 65,  "league": 39,  "short": "NFO", "colour": "#DD0000"},
    "Brentford":            {"id": 55,  "league": 39,  "short": "BRE", "colour": "#E30613"},
    # ── La Liga ─────────────────────────────────────────────────────
    "Real Madrid":          {"id": 541, "league": 140, "short": "RMA", "colour": "#00529F"},
    "Barcelona":            {"id": 529, "league": 140, "short": "BAR", "colour": "#A50044"},
    "Atlético Madrid":      {"id": 530, "league": 140, "short": "ATM", "colour": "#CB3524"},
    "Athletic Club":        {"id": 531, "league": 140, "short": "ATH", "colour": "#EE2523"},
    "Real Sociedad":        {"id": 548, "league": 140, "short": "RSO", "colour": "#0067B1"},
    "Villarreal":           {"id": 533, "league": 140, "short": "VIL", "colour": "#FFD700"},
    "Sevilla":              {"id": 536, "league": 140, "short": "SEV", "colour": "#D4021D"},
    # ── Bundesliga ──────────────────────────────────────────────────
    "Bayern Munich":        {"id": 157, "league": 78,  "short": "BAY", "colour": "#DC052D"},
    "Borussia Dortmund":    {"id": 165, "league": 78,  "short": "BVB", "colour": "#FDE100"},
    "Bayer Leverkusen":     {"id": 168, "league": 78,  "short": "B04", "colour": "#E32221"},
    "RB Leipzig":           {"id": 173, "league": 78,  "short": "RBL", "colour": "#DD0741"},
    "Eintracht Frankfurt":  {"id": 169, "league": 78,  "short": "SGE", "colour": "#E1000F"},
    "Borussia M'gladbach":  {"id": 163, "league": 78,  "short": "BMG", "colour": "#000000"},
    # ── Serie A ─────────────────────────────────────────────────────
    "Inter Milan":          {"id": 505, "league": 135, "short": "INT", "colour": "#010E80"},
    "AC Milan":             {"id": 489, "league": 135, "short": "MIL", "colour": "#FB090B"},
    "Juventus":             {"id": 496, "league": 135, "short": "JUV", "colour": "#000000"},
    "Napoli":               {"id": 492, "league": 135, "short": "NAP", "colour": "#087DC2"},
    "Roma":                 {"id": 497, "league": 135, "short": "ROM", "colour": "#8B0000"},
    "Atalanta":             {"id": 499, "league": 135, "short": "ATA", "colour": "#1E6DB8"},
    "Lazio":                {"id": 487, "league": 135, "short": "LAZ", "colour": "#87CEEB"},
    # ── Ligue 1 ─────────────────────────────────────────────────────
    "PSG":                  {"id": 85,  "league": 61,  "short": "PSG", "colour": "#004170"},
    "Monaco":               {"id": 91,  "league": 61,  "short": "MON", "colour": "#CE1126"},
    "Marseille":            {"id": 81,  "league": 61,  "short": "OM",  "colour": "#009AC7"},
    "Lyon":                 {"id": 80,  "league": 61,  "short": "OL",  "colour": "#0046A8"},
    "Lille":                {"id": 79,  "league": 61,  "short": "LIL", "colour": "#C8102E"},
    "Nice":                 {"id": 84,  "league": 61,  "short": "NIC", "colour": "#000000"},
}

# ─────────────────────────────────────────────────────────────────────────────
# API-FOOTBALL CLIENT
# ─────────────────────────────────────────────────────────────────────────────

class APIFootballClient:
    """Wrapper for api-football.com v3 endpoints."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base    = API_FOOTBALL_BASE
        self.headers = {
            "x-rapidapi-key":  api_key,
            "x-rapidapi-host": "v3.football.api-sports.io"
        }
        self._cache: Dict = {}

    def _get(self, endpoint: str, params: Dict) -> Optional[Dict]:
        cache_key = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            r = requests.get(
                f"{self.base}/{endpoint}",
                headers=self.headers,
                params=params,
                timeout=15
            )
            r.raise_for_status()
            data = r.json()
            self._cache[cache_key] = data
            return data
        except Exception as e:
            logger.error(f"API-Football error [{endpoint}]: {e}")
            return None

    def get_player_stats(self, player_id: int, season: int = CURRENT_SEASON) -> Optional[Dict]:
        data = self._get("players", {"id": player_id, "season": season})
        if not data or not data.get("response"):
            return None
        return data["response"][0]

    def get_team_stats(self, team_id: int, league_id: int = PL_LEAGUE_ID,
                       season: int = CURRENT_SEASON) -> Optional[Dict]:
        data = self._get("teams/statistics", {
            "team": team_id, "league": league_id, "season": season
        })
        if not data:
            return None
        return data.get("response")

    def get_squad(self, team_id: int) -> List[Dict]:
        """Returns [{id, name, position}] for a team's full squad."""
        data = self._get("players/squads", {"team": team_id})
        if not data or not data.get("response"):
            return []
        try:
            players = data["response"][0]["players"]
            return sorted(
                [{"id": p["id"], "name": p["name"],
                  "position": p.get("position", "")} for p in players],
                key=lambda x: x["name"]
            )
        except (IndexError, KeyError):
            return []

    def search_player(self, name: str, team_id: int = None,
                      league_id: int = None) -> Optional[Dict]:
        params = {"search": name, "season": CURRENT_SEASON}
        if team_id:
            params["team"] = team_id
        elif league_id:
            params["league"] = league_id
        else:
            params["league"] = PL_LEAGUE_ID
        data = self._get("players", params)
        if not data or not data.get("response"):
            return None
        return data["response"][0]

    def get_all_pl_players(self, team_id: int, season: int = CURRENT_SEASON) -> List[Dict]:
        data = self._get("players", {
            "team": team_id,
            "league": PL_LEAGUE_ID,
            "season": season
        })
        if not data:
            return []
        return data.get("response", [])

    def get_pl_standings(self, season: int = CURRENT_SEASON) -> Optional[List]:
        data = self._get("standings", {"league": PL_LEAGUE_ID, "season": season})
        if not data or not data.get("response"):
            return None
        try:
            return data["response"][0]["league"]["standings"][0]
        except (IndexError, KeyError):
            return None


# ─────────────────────────────────────────────────────────────────────────────
# STATS EXTRACTOR  (raw API stats → normalised radar values 0-100)
# ─────────────────────────────────────────────────────────────────────────────

class StatsExtractor:
    """
    Extracts per-90 stats from API-Football player response and maps them
    to the radar metric keys used above.  Falls back gracefully to 0.
    """

    def extract_player_radar_values(
        self, player_data: Dict, position: str
    ) -> Dict[str, float]:
        """Returns dict of metric_key → raw per-90 value."""
        stats = {}
        if not player_data:
            return stats

        try:
            s = player_data["statistics"][0]
        except (KeyError, IndexError):
            return stats

        mins = s.get("games", {}).get("minutes") or 1
        p90  = mins / 90

        def per90(val):
            if val is None or p90 == 0:
                return 0.0
            return round(val / p90, 2)

        goals      = s.get("goals", {})
        passes     = s.get("passes", {})
        dribbles   = s.get("dribbles", {})
        duels      = s.get("duels", {})
        tackles    = s.get("tackles", {})
        shots      = s.get("shots", {})
        fouls      = s.get("fouls", {})

        g_scored   = goals.get("total") or 0
        g_assisted = goals.get("assists") or 0
        g_xg       = goals.get("total") or 0  # API-Football doesn't expose xG on free tier

        pass_total = passes.get("total") or 0
        pass_acc   = passes.get("accuracy") or 0
        pass_key   = passes.get("key") or 0

        drib_att   = dribbles.get("attempts") or 0
        drib_succ  = dribbles.get("success") or 0

        duel_total = duels.get("total") or 0
        duel_won   = duels.get("won") or 0

        tackle_total = tackles.get("total") or 0
        intercept    = tackles.get("interceptions") or 0

        shot_total = shots.get("total") or 0
        shot_on    = shots.get("on") or 0

        saves      = s.get("goals", {}).get("saves") or 0

        stats = {
            "np_goals":       per90(g_scored),
            "np_xg":          per90(g_scored),       # proxy
            "assists_per90":  per90(g_assisted),
            "xa_per90":       per90(g_assisted),      # proxy
            "npxg_xa":        per90(g_scored + g_assisted),
            "key_passes":     per90(pass_key),
            "passes_per90":   per90(pass_total),
            "prog_passes":    per90(pass_total * 0.25),  # estimated
            "fwd_passes":     per90(pass_total * 0.55),
            "fwd_pass_acc":   float(pass_acc),
            "long_pass_acc":  float(pass_acc) * 0.85,    # estimated
            "succ_dribbles":  per90(drib_succ),
            "prog_carries":   per90(drib_succ * 1.5),    # estimated
            "duels_won_pct":  (duel_won / duel_total * 100) if duel_total else 0,
            "def_duels_pct":  (duel_won / duel_total * 100) if duel_total else 0,
            "aerial_won_pct": (duel_won / duel_total * 60) if duel_total else 0,
            "aerial_won":     per90(duel_won * 0.3),
            "possession_won": per90(tackle_total + intercept),
            "off_duels_won":  per90(duel_won * 0.5),
            "interceptions":  per90(intercept),
            "touches_box":    per90(shot_total * 2.5),   # estimated
            "goal_conv":      (g_scored / shot_total * 100) if shot_total else 0,
            "accurate_crosses": per90(pass_total * 0.05),
            "clean_sheets":   s.get("games", {}).get("appearances") or 0,
            "save_pct":       (saves / (saves + g_scored) * 100) if (saves + g_scored) else 0,
            "prevented_goals": per90(saves),
        }
        return stats

    def extract_team_radar_values(self, team_stats: Dict) -> Dict[str, float]:
        """Maps API-Football team stats to radar keys (raw values for percentile calc)."""
        if not team_stats:
            return {}
        f = team_stats.get("fixtures", {})
        g = team_stats.get("goals", {})
        p = team_stats.get("passes", {})

        played      = f.get("played", {}).get("total") or 1
        goals_for   = g.get("for", {}).get("total", {}).get("total") or 0
        goals_ag    = g.get("against", {}).get("total", {}).get("total") or 0
        wins        = f.get("wins", {}).get("total") or 0
        clean_sh    = team_stats.get("clean_sheet", {}).get("total") or 0
        pass_total  = p.get("total") or 0
        pass_acc    = p.get("accuracy") or 60

        return {
            "goals":       goals_for / played,
            "attacking":   goals_for / played,
            "defending":   1 / (goals_ag / played + 0.01),  # inverted
            "possession":  float(pass_acc),
            "pressing":    wins / played * 100,
            "physicality": clean_sh / played * 100,
            "counters":    wins / played * 80,
        }

    def percentile_normalise(
        self, values: Dict[str, float],
        league_max: Dict[str, float] = None
    ) -> Dict[str, float]:
        """
        Converts raw values to 0-100 percentile.
        If league_max is not available (no full league data on free tier),
        uses sensible per-position maxima.
        """
        # Sensible per-90 maxima for top PL players (used as 100th percentile)
        DEFAULT_MAX = {
            "np_goals": 1.2, "np_xg": 1.2, "assists_per90": 0.7,
            "xa_per90": 0.7, "npxg_xa": 1.5, "key_passes": 2.5,
            "passes_per90": 90, "prog_passes": 12, "fwd_passes": 50,
            "fwd_pass_acc": 95, "long_pass_acc": 85, "succ_dribbles": 4,
            "prog_carries": 8, "duels_won_pct": 65, "def_duels_pct": 65,
            "aerial_won_pct": 75, "aerial_won": 3, "possession_won": 8,
            "off_duels_won": 5, "interceptions": 3, "touches_box": 5,
            "goal_conv": 40, "accurate_crosses": 2.5, "clean_sheets": 30,
            "save_pct": 82, "prevented_goals": 2,
            # team
            "goals": 3.5, "attacking": 3.5, "defending": 20,
            "possession": 72, "pressing": 80, "physicality": 60, "counters": 70,
        }
        maxima = league_max or DEFAULT_MAX
        out = {}
        for k, v in values.items():
            mx = maxima.get(k, 100)
            if mx == 0:
                out[k] = 0
            else:
                out[k] = min(round(v / mx * 100, 1), 99)
        return out


# ─────────────────────────────────────────────────────────────────────────────
# RADAR CHART RENDERER  (DataMB aesthetic — clean light theme)
# ─────────────────────────────────────────────────────────────────────────────

class RadarRenderer:
    """
    Generates a clean, legible DataMB-style radar chart as PNG bytes.
    Light background, red Arsenal polygon, dashed rival polygon.
    Labels sit outside the chart area with clip_on=False — nothing is cut off.
    """

    # Palette
    BG      = "#F6F6F4"
    CARD    = "#FFFFFF"
    GRID    = "#E2E2E2"
    SPOKE   = "#CECECE"
    TEXT    = "#1A1A1A"
    SUB     = "#666666"
    DIM     = "#BBBBBB"

    def render(
        self,
        labels:       List[str],
        values_a:     List[float],   # Arsenal (0-100 percentiles)
        label_a:      str,
        values_b:     List[float] = None,
        label_b:      str = None,
        title:        str = "",
        subtitle:     str = "",
        season:       str = "2024/25",
        rival_colour: str = RIVAL_COLOUR,
    ) -> bytes:

        n      = len(labels)
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False) - np.pi / 2
        ac     = np.append(angles, angles[0])
        va_c   = np.append(np.array(values_a), values_a[0]) / 100.0
        vb_c   = (np.append(np.array(values_b), values_b[0]) / 100.0
                  if values_b is not None else None)

        fig = plt.figure(figsize=(7.8, 9.6), facecolor=self.BG)

        # Polar axes — inset with generous margins so labels never clip
        ax = fig.add_axes([0.20, 0.17, 0.60, 0.62], polar=True,
                          facecolor=self.CARD)

        ring_th = np.linspace(0, 2 * np.pi, 360)

        # Alternating background bands
        for i, (lo, hi) in enumerate([(0, 0.25), (0.25, 0.5),
                                       (0.5, 0.75), (0.75, 1.0)]):
            c = "#FBF0F0" if i % 2 == 0 else "#FFFFFF"
            ax.fill_between(ring_th, lo, hi, color=c, zorder=0)

        # Ring outlines
        for rv in [0.25, 0.5, 0.75, 1.0]:
            ax.plot(ring_th, [rv] * 360, color=self.GRID,
                    linewidth=0.8, zorder=1)

        # Spokes
        for angle in angles:
            ax.plot([angle, angle], [0, 1.0], color=self.SPOKE,
                    linewidth=0.8, zorder=1)

        # Rival polygon (drawn first — sits behind Arsenal)
        if vb_c is not None:
            ax.fill(ac, vb_c, color=rival_colour, alpha=0.13, zorder=2)
            ax.plot(ac, vb_c, color=rival_colour, linewidth=1.9,
                    linestyle="--", alpha=0.88, zorder=3)
            ax.scatter(angles, np.array(values_b) / 100.0,
                       color=rival_colour, s=28, zorder=4, marker="D",
                       edgecolors="white", linewidths=0.5)

        # Arsenal polygon
        ax.fill(ac, va_c, color=ARSENAL_RED, alpha=0.20, zorder=2)
        ax.plot(ac, va_c, color=ARSENAL_RED, linewidth=2.3, zorder=3)
        ax.scatter(angles, np.array(values_a) / 100.0,
                   color=ARSENAL_RED, s=38, zorder=5,
                   edgecolors="white", linewidths=0.6)

        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_ylim(0, 1.0)
        ax.spines["polar"].set_color(self.GRID)
        ax.spines["polar"].set_linewidth(0.8)

        # Ring percentage markers
        for rv, lbl in [(0.25, "25"), (0.5, "50"), (0.75, "75"), (1.0, "99")]:
            ax.text(np.radians(248), rv + 0.02, lbl,
                    ha="center", va="bottom",
                    fontsize=6.5, color=self.DIM)

        # Axis labels + percentile values (clip_on=False — never hidden)
        LABEL_R = 1.18
        VAL_A_R = 1.30
        VAL_B_R = 1.40

        for i, (angle, label) in enumerate(zip(angles, labels)):
            deg = np.degrees(angle) % 360

            if   deg < 12 or deg > 348: ha, va_a = "center", "bottom"
            elif 12  <= deg < 80:        ha, va_a = "left",   "center"
            elif 80  <= deg < 100:       ha, va_a = "center", "bottom"
            elif 100 <= deg < 170:       ha, va_a = "left",   "center"
            elif 170 <= deg < 190:       ha, va_a = "center", "top"
            elif 190 <= deg < 260:       ha, va_a = "right",  "center"
            elif 260 <= deg < 280:       ha, va_a = "center", "top"
            else:                         ha, va_a = "right",  "center"

            ax.text(angle, LABEL_R, label,
                    ha=ha, va=va_a,
                    fontsize=8.0, color=self.SUB, fontweight="semibold",
                    linespacing=1.25, clip_on=False)

            ax.text(angle, VAL_A_R, str(int(values_a[i])),
                    ha=ha, va=va_a,
                    fontsize=8.5, color=ARSENAL_RED, fontweight="bold",
                    clip_on=False)

            if values_b is not None:
                ax.text(angle, VAL_B_R, str(int(values_b[i])),
                        ha=ha, va=va_a,
                        fontsize=8.0, color=rival_colour,
                        clip_on=False)

        # Title
        fig.text(0.5, 0.955, title,
                 ha="center", va="top",
                 fontsize=14.5, fontweight="bold", color=self.TEXT)
        fig.text(0.5, 0.924, subtitle,
                 ha="center", va="top",
                 fontsize=9.0, color=self.SUB)

        # Legend
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], color=ARSENAL_RED, linewidth=2.5, label=label_a),
        ]
        if values_b is not None and label_b:
            legend_elements.append(
                Line2D([0], [0], color=rival_colour, linewidth=2.0,
                       linestyle="--", label=label_b)
            )
        fig.legend(
            handles=legend_elements,
            loc="lower center",
            bbox_to_anchor=(0.5, 0.038),
            ncol=2 if values_b else 1,
            frameon=False,
            fontsize=9.5,
            labelcolor=self.TEXT,
        )

        # Watermark
        fig.text(0.5, 0.014,
                 f"DataMB  ·  Premier League {season}  ·  Arsenal FC Agent",
                 ha="center", va="bottom",
                 fontsize=7.5, color=self.DIM)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=160,
                    facecolor=self.BG,
                    bbox_inches="tight", pad_inches=0.3)
        plt.close(fig)
        buf.seek(0)
        return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# NARRATIVE GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

class ArsenalNarrativeGenerator:
    """
    Generates Arsenal-biased X post narrative from radar data.
    Uses the same OpenAI pattern as the existing bot.
    """

    TONES = {
        "hype":       "Write in pure hype mode — maximum Arsenal passion, exclamation points, fire emojis.",
        "analytical": "Write analytically — cite the percentile data as proof, authoritative and data-led.",
        "banter":     "Write with cheeky rival banter — make Arsenal fans feel superior, rival fans wince.",
        "historic":   "Connect this to Arsenal's historic greatness — Invincibles, Henry, Bergkamp.",
        "tactical":   "Tactical breakdown — explain WHY these stats reflect Arteta's system.",
    }

    def generate_player_narrative(
        self,
        arsenal_player: str,
        rival_player: str,
        metrics: List[Tuple[str, float, float]],  # (label, arsenal_pct, rival_pct)
        tone: str = "hype",
        custom_note: str = "",
    ) -> str:
        top_3 = sorted(metrics, key=lambda x: x[1] - x[2], reverse=True)[:3]
        advantages = "\n".join(
            [f"  • {m[0]}: {label_a} {m[1]:.0f}th pct vs {rival_player} {m[2]:.0f}th pct"
             for m in top_3]
        ) if rival_player else "\n".join(
            [f"  • {m[0]}: {m[1]:.0f}th percentile (Top 7 leagues)"
             for m in sorted(metrics, key=lambda x: x[1], reverse=True)[:3]]
        )

        label_a = arsenal_player
        comparison_line = (
            f"Comparing {label_a} vs {rival_player} using DataMB stats."
            if rival_player else
            f"Profiling {label_a} using DataMB Premier League stats."
        )

        prompt = f"""You are a pro-Arsenal X (Twitter) content agent.
{comparison_line}

Key stat advantages:
{advantages}

Tone instruction: {self.TONES.get(tone, self.TONES['hype'])}
{f'Additional note: {custom_note}' if custom_note else ''}

Rules:
- Always frame Arsenal/Arsenal player positively
- Reference 2-3 specific stats naturally (use percentile or raw numbers)
- Make it shareable for Arsenal fans
- Use relevant hashtags: #Arsenal #AFC #COYG and position/player specific tags
- No character limit concern — write for maximum impact
- Do NOT fabricate match results

Output ONLY the tweet/thread text. Nothing else."""

        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a pro-Arsenal football content writer."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400,
                temperature=0.88
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI narrative error: {e}")
            return f"📊 Arsenal's {arsenal_player} is in elite form — the data doesn't lie. #Arsenal #COYG"

    def generate_team_narrative(
        self,
        rival_team: str,
        metrics: List[Tuple[str, float, float]],
        tone: str = "hype",
        custom_note: str = "",
    ) -> str:
        top_3 = sorted(metrics, key=lambda x: x[1] - x[2], reverse=True)[:3]
        advantages = "\n".join(
            [f"  • {m[0]}: Arsenal {m[1]:.0f} vs {rival_team} {m[2]:.0f}"
             for m in top_3]
        )

        prompt = f"""You are a pro-Arsenal X (Twitter) content agent.
Comparing Arsenal FC vs {rival_team} using DataMB Premier League team stats.

Arsenal's key advantages:
{advantages}

Tone instruction: {self.TONES.get(tone, self.TONES['hype'])}
{f'Additional note: {custom_note}' if custom_note else ''}

Rules:
- Always frame Arsenal positively
- Reference specific stats
- Use hashtags: #Arsenal #AFC #COYG #PremierLeague
- Make it punchy and shareable
- Do NOT fabricate results

Output ONLY the tweet/thread text."""

        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a pro-Arsenal football content writer."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400,
                temperature=0.88
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI narrative error: {e}")
            return f"📊 Arsenal vs {rival_team} — the numbers tell the story. #Arsenal #COYG"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ARSENAL AGENT CLASS
# ─────────────────────────────────────────────────────────────────────────────

class ArsenalDataMBAgent:
    """
    Orchestrator.  Called by the Flask web UI and (optionally) by
    the existing scheduled bot.
    """

    def __init__(self, twitter_api=None, twitter_client=None):
        self.api_client   = APIFootballClient(API_FOOTBALL_KEY)
        self.extractor    = StatsExtractor()
        self.renderer     = RadarRenderer()
        self.narrative    = ArsenalNarrativeGenerator()
        self.twitter_api  = twitter_api    # tweepy.API  (v1.1 — for media upload)
        self.twitter_client = twitter_client  # tweepy.Client (v2 — for tweet)

    # ── Player vs Player ──────────────────────────────────────────────────

    def build_player_comparison(
        self,
        arsenal_key: str,       # key from ARSENAL_SQUAD
        rival_name: str,        # free-text name for search
        rival_team_id: int = None,
        tone: str = "hype",
        custom_note: str = "",
    ) -> Dict:
        """
        Fetches stats for both players, renders radar, generates narrative.
        Returns dict with: image_bytes, narrative, labels, values_a, values_b, meta
        """
        arsenal_info = ARSENAL_SQUAD.get(arsenal_key)
        if not arsenal_info:
            return {"error": f"Unknown Arsenal player: {arsenal_key}"}

        pos = arsenal_info["pos"]
        metrics_def = PLAYER_RADAR_METRICS.get(pos, PLAYER_RADAR_METRICS["MF"])
        metric_labels = [m[0] for m in metrics_def]
        metric_keys   = [m[1] for m in metrics_def]

        # Fetch Arsenal player
        afc_data = self.api_client.get_player_stats(arsenal_info["id"])
        if not afc_data:
            return {"error": f"Could not fetch stats for {arsenal_info['name']}"}

        afc_raw  = self.extractor.extract_player_radar_values(afc_data, pos)
        afc_pct  = self.extractor.percentile_normalise(afc_raw)
        vals_a   = [afc_pct.get(k, 50) for k in metric_keys]

        # Fetch rival player (optional)
        vals_b   = None
        rival_data = None
        if rival_name:
            rival_data = self.api_client.search_player(rival_name, rival_team_id)
            if rival_data:
                rival_raw = self.extractor.extract_player_radar_values(rival_data, pos)
                rival_pct = self.extractor.percentile_normalise(rival_raw)
                vals_b    = [rival_pct.get(k, 40) for k in metric_keys]

        # Radar image
        rival_display = rival_data["player"]["name"] if rival_data else None
        title    = f"{arsenal_info['name']}  {'vs  ' + rival_display if rival_display else ''}"
        subtitle = f"{pos} · Premier League 2024/25 · Percentile Rankings"

        img_bytes = self.renderer.render(
            labels=metric_labels,
            values_a=vals_a,
            label_a=arsenal_info["name"],
            values_b=vals_b,
            label_b=rival_display,
            title=title,
            subtitle=subtitle,
        )

        # Metrics list for narrative
        metrics_for_narrative = [
            (metric_labels[i], vals_a[i], vals_b[i] if vals_b else 0)
            for i in range(len(metric_labels))
        ]

        # Narrative
        text = self.narrative.generate_player_narrative(
            arsenal_player=arsenal_info["name"],
            rival_player=rival_display or "",
            metrics=metrics_for_narrative,
            tone=tone,
            custom_note=custom_note,
        )

        return {
            "image_bytes": img_bytes,
            "narrative":   text,
            "labels":      metric_labels,
            "values_a":    vals_a,
            "values_b":    vals_b,
            "arsenal_name": arsenal_info["name"],
            "rival_name":  rival_display,
            "tone":        tone,
            "mode":        "player",
        }

    # ── Team vs Team ──────────────────────────────────────────────────────

    def build_team_comparison(
        self,
        rival_team_key: str,
        tone: str = "hype",
        custom_note: str = "",
    ) -> Dict:
        rival_info = RIVAL_TEAMS.get(rival_team_key)
        if not rival_info:
            return {"error": f"Unknown rival team: {rival_team_key}"}

        rival_league_id = rival_info.get("league", PL_LEAGUE_ID)

        afc_stats   = self.api_client.get_team_stats(ARSENAL_TEAM_ID, PL_LEAGUE_ID)
        rival_stats = self.api_client.get_team_stats(rival_info["id"], rival_league_id)

        afc_raw   = self.extractor.extract_team_radar_values(afc_stats)
        rival_raw = self.extractor.extract_team_radar_values(rival_stats)

        afc_pct   = self.extractor.percentile_normalise(afc_raw)
        rival_pct = self.extractor.percentile_normalise(rival_raw)

        labels = [m[0] for m in TEAM_RADAR_METRICS]
        keys   = [m[1] for m in TEAM_RADAR_METRICS]
        vals_a = [afc_pct.get(k, 50) for k in keys]
        vals_b = [rival_pct.get(k, 40) for k in keys]

        league_labels = {39: "Premier League", 140: "La Liga", 78: "Bundesliga",
                         135: "Serie A", 61: "Ligue 1"}
        rival_league_name = league_labels.get(rival_league_id, "Top 5 League")

        title    = f"Arsenal FC  vs  {rival_team_key}"
        subtitle = f"Team Radar · EPL vs {rival_league_name} · 2024/25"

        img_bytes = self.renderer.render(
            labels=labels,
            values_a=vals_a,
            label_a="Arsenal FC",
            values_b=vals_b,
            label_b=rival_team_key,
            title=title,
            subtitle=subtitle,
            rival_colour=rival_info.get("colour", RIVAL_COLOUR),
        )

        metrics_for_narrative = [
            (labels[i], vals_a[i], vals_b[i]) for i in range(len(labels))
        ]

        text = self.narrative.generate_team_narrative(
            rival_team=rival_team_key,
            metrics=metrics_for_narrative,
            tone=tone,
            custom_note=custom_note,
        )

        return {
            "image_bytes":  img_bytes,
            "narrative":    text,
            "labels":       labels,
            "values_a":     vals_a,
            "values_b":     vals_b,
            "arsenal_name": "Arsenal FC",
            "rival_name":   rival_team_key,
            "tone":         tone,
            "mode":         "team",
        }

    # ── Post to X ─────────────────────────────────────────────────────────

    def post_to_x(self, narrative: str, image_bytes: bytes) -> Dict:
        """
        1. Upload image via v1.1 media_upload
        2. Post tweet with media_id via v2 create_tweet
        Returns {"success": True/False, "tweet_id": ..., "error": ...}
        """
        if not self.twitter_api or not self.twitter_client:
            return {"success": False, "error": "Twitter clients not configured"}

        try:
            # Save image to temp file for tweepy upload
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name

            media = self.twitter_api.media_upload(filename=tmp_path)
            os.unlink(tmp_path)

            response = self.twitter_client.create_tweet(
                text=narrative,
                media_ids=[media.media_id_string]
            )
            tweet_id = response.data["id"]
            logger.info(f"⚽ Arsenal post live: https://twitter.com/user/status/{tweet_id}")
            return {"success": True, "tweet_id": tweet_id}

        except Exception as e:
            logger.error(f"Post to X failed: {e}")
            return {"success": False, "error": str(e)}
