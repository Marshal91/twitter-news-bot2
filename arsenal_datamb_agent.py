"""
═══════════════════════════════════════════════════════════════════════════════
    ARSENAL DATAMB X AGENT
    Real football stats → DataMB-style radar image → Arsenal-biased X post

    Data sources:
    ✅ FBref (team stats) — xG, xGA, PPDA, possession, progressive passes/carries
    ✅ API-Football (player stats + squad lists)
    ✅ DataMB-style radar card (stat table + radar polygon)
    ✅ Arsenal-biased GPT narrative → auto-post to X with image
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import io
import re
import json
import logging
import requests
import tempfile
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime, timedelta
from io import StringIO
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
CURRENT_SEASON       = 2025   # 2025/26 — for squad/player stats endpoints
STANDINGS_SEASON     = 2024   # 2024/25 — free tier caps at 2024 for standings

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
# UNDERSTAT TEAM STATS SCRAPER
# Primary: Understat (xG, xGA, PPDA, possession via deep completions)
# Fallback: Static GW29 2025/26 snapshot (updated periodically)
# ─────────────────────────────────────────────────────────────────────────────

UNDERSTAT_URL = "https://understat.com/league/EPL"

UNDERSTAT_NAME_MAP = {
    "Manchester City":   "Manchester City",
    "Manchester United": "Manchester United",
    "Arsenal":           "Arsenal",
    "Liverpool":         "Liverpool",
    "Chelsea":           "Chelsea",
    "Tottenham":         "Tottenham",
    "Newcastle United":  "Newcastle",
    "Aston Villa":       "Aston Villa",
    "Brighton":          "Brighton",
    "West Ham":          "West Ham",
    "Fulham":            "Fulham",
    "Brentford":         "Brentford",
    "Crystal Palace":    "Crystal Palace",
    "Everton":           "Everton",
    "Nottingham Forest": "Nottingham Forest",
    "Wolves":            "Wolves",
    "Leicester":         "Leicester",
    "Ipswich":           "Ipswich",
    "Southampton":       "Southampton",
    "Bournemouth":       "Bournemouth",
}

# Club colours for radar rival polygon
EPL_COLOURS = {
    "Liverpool":           "#C8102E",
    "Manchester City":     "#6CABDD",
    "Chelsea":             "#034694",
    "Tottenham":           "#132257",
    "Manchester United":   "#DA291C",
    "Newcastle":           "#241F20",
    "Newcastle United":    "#241F20",
    "Aston Villa":         "#670E36",
    "Brighton":            "#0057B8",
    "West Ham":            "#7A263A",
    "Fulham":              "#CC0000",
    "Brentford":           "#E30613",
    "Crystal Palace":      "#1B458F",
    "Everton":             "#003399",
    "Nottingham Forest":   "#DD0000",
    "Wolves":              "#FDB913",
    "Leicester":           "#003090",
    "Ipswich":             "#3A64A3",
    "Southampton":         "#D71920",
    "Bournemouth":         "#DA291C",
    "Arsenal":             "#EF0107",
}

LAST_FETCH_PATH = "team_stats_last_fetch.json"


class TeamStatsScraper:
    """
    Fetches PL team stats from Understat (xG, xGA, PPDA, deep completions).
    On every successful fetch: saves result to disk.
    On failure: loads from disk (last known good). No hardcoded data.
    Cache TTL: 6 hours in-memory.
    """

    HEADERS = {
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection":      "keep-alive",
    }
    CACHE_TTL_HOURS = 6

    def __init__(self):
        self._cache:      Optional[Dict] = None
        self._cache_time: Optional[datetime] = None

    def _pct_rank(self, values: Dict[str, float], higher_is_better: bool = True) -> Dict[str, float]:
        s = pd.Series(list(values.values()), index=list(values.keys()))
        ranked = s.rank(pct=True, method="average") * 99
        if not higher_is_better:
            ranked = 99 - ranked
        return ranked.round(1).to_dict()

    def _save_to_disk(self, data: Dict) -> None:
        try:
            payload = {"fetched_at": datetime.now().isoformat(), "data": data}
            with open(LAST_FETCH_PATH, "w") as f:
                json.dump(payload, f)
            logger.info(f"TeamStats: saved {len(data)} teams to disk")
        except Exception as e:
            logger.warning(f"TeamStats: disk save failed: {e}")

    def _load_from_disk(self) -> Optional[Dict]:
        try:
            if not os.path.exists(LAST_FETCH_PATH):
                return None
            with open(LAST_FETCH_PATH) as f:
                payload = json.load(f)
            data = payload.get("data", {})
            if data and "Arsenal" in data:
                logger.info(f"TeamStats: loaded from disk (fetched {payload.get('fetched_at', '?')})")
                return data
        except Exception as e:
            logger.warning(f"TeamStats: disk load failed: {e}")
        return None

    def _fetch_understat(self) -> Optional[Dict]:
        try:
            session = requests.Session()
            session.headers.update(self.HEADERS)
            # Warm up session with homepage first
            session.get("https://understat.com", timeout=10)
            r = session.get(UNDERSTAT_URL, headers=self.HEADERS, timeout=20)
            r.raise_for_status()

            html = r.text
            logger.info(f"Understat: page length={len(html)}")

            # Try multiple extraction patterns — Understat has changed format before
            patterns = [
                r"teamsData\s*=\s*JSON\.parse\('(.+?)'\)",
                r'teamsData\s*=\s*JSON\.parse\("(.+?)"\)',
                r"teamsData\s*=\s*JSON\.parse\(\'(.+?)\'\)",
                r'var teamsData\s*=\s*JSON\.parse\(\'(.+?)\'\)',
                r'"teamsData"\s*:\s*JSON\.parse\(\'(.+?)\'\)',
            ]

            raw_str = None
            for pat in patterns:
                match = re.search(pat, html, re.DOTALL)
                if match:
                    raw_str = match.group(1)
                    logger.info(f"Understat: matched pattern '{pat[:40]}'")
                    break

            if not raw_str:
                # Try finding any JSON blob with team history data
                match = re.search(r'JSON\.parse\(\'(\\x.{20,}?)\'\)', html)
                if match:
                    raw_str = match.group(1)
                    logger.info("Understat: matched generic JSON.parse pattern")

            if not raw_str:
                logger.warning(f"Understat: no teamsData found. Page snippet: {html[2000:2500]}")
                return None

            # Decode escape sequences
            try:
                decoded = raw_str.encode("utf-8").decode("unicode_escape")
            except Exception:
                decoded = raw_str

            data = json.loads(decoded)
            logger.info(f"Understat: {len(data)} teams parsed")
            return data

        except Exception as e:
            logger.warning(f"Understat fetch failed: {e}")
            return None

    def _parse_understat(self, data: Dict) -> Dict[str, Dict]:
        raw = {}
        for team_name, team_data in data.items():
            history = team_data.get("history", [])
            if not history:
                continue
            xg     = sum(float(m.get("xG",  0)) for m in history)
            xga    = sum(float(m.get("xGA", 0)) for m in history)
            npxg   = sum(float(m.get("npxG",  xg))  for m in history)
            npxga  = sum(float(m.get("npxGA", xga)) for m in history)
            scored = sum(int(m.get("scored", 0)) for m in history)
            missed = sum(int(m.get("missed", 0)) for m in history)
            pts    = sum(int(m.get("pts",    0)) for m in history)
            deep   = sum(int(m.get("deep",   0)) for m in history)
            ppda_att = sum(float(m.get("ppda", {}).get("att", 0)) if isinstance(m.get("ppda"), dict) else 0 for m in history)
            ppda_def = sum(float(m.get("ppda", {}).get("def", 1)) if isinstance(m.get("ppda"), dict) else 1 for m in history)
            ppda = ppda_att / ppda_def if ppda_def > 0 else 99
            mapped = UNDERSTAT_NAME_MAP.get(team_name, team_name)
            raw[mapped] = {
                "xG": npxg, "xGA": npxga,
                "Goals": scored, "GoalsAg": missed,
                "Pts": pts, "Deep": deep, "PPDA": ppda,
            }
        if not raw:
            return {}
        pcts = {}
        for m in ["xG", "Goals", "Pts", "Deep"]:
            pcts[m] = self._pct_rank({t: raw[t][m] for t in raw}, higher_is_better=True)
        for m in ["xGA", "GoalsAg", "PPDA"]:
            pcts[m] = self._pct_rank({t: raw[t][m] for t in raw}, higher_is_better=False)
        return {
            team: {
                "goals":       pcts["Goals"].get(team, 0),
                "attacking":   pcts["xG"].get(team, 0),
                "defending":   pcts["xGA"].get(team, 0),
                "possession":  pcts["Deep"].get(team, 0),
                "pressing":    pcts["PPDA"].get(team, 0),
                "physicality": pcts["GoalsAg"].get(team, 0),
                "counters":    pcts["Pts"].get(team, 0),
            }
            for team in raw
        }

    def _fetch_fbref_direct(self) -> Optional[Dict]:
        """
        Scrapes FBref team stats pages directly using pd.read_html.
        Inspired by the bs4/requests FBref scraping pattern.
        Fetches: standard stats (xG, xGA, Goals) + possession (Poss%, PrgP, PrgC).
        """
        FBREF_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
        NAME_MAP = {
            "Manchester Utd":  "Manchester United",
            "Newcastle Utd":   "Newcastle",
            "Nott'ham Forest": "Nottingham Forest",
            "Leicester City":  "Leicester",
            "Ipswich Town":    "Ipswich",
        }

        def read_fbref_table(url, table_id):
            try:
                import time
                r = requests.get(url, headers=FBREF_HEADERS, timeout=20)
                r.raise_for_status()
                tables = pd.read_html(StringIO(r.text), attrs={"id": table_id})
                if not tables:
                    return None
                df = tables[0]
                # Flatten MultiIndex columns
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [
                        b if a == b or "Unnamed" in str(a) else f"{a} {b}"
                        for a, b in df.columns
                    ]
                # Drop header repeat rows
                squad_col = next((c for c in df.columns if "Squad" in str(c)), None)
                if squad_col:
                    df = df[df[squad_col].notna() & (df[squad_col] != "Squad")].copy()
                    df["team"] = df[squad_col].apply(lambda x: NAME_MAP.get(str(x).strip(), str(x).strip()))
                time.sleep(2)   # polite delay between requests
                return df
            except Exception as e:
                logger.warning(f"FBref direct read failed [{table_id}]: {e}")
                return None

        try:
            std  = read_fbref_table("https://fbref.com/en/comps/9/Premier-League-Stats",
                                    "stats_squads_standard_for")
            if std is None or "team" not in std.columns:
                return None

            poss = read_fbref_table("https://fbref.com/en/comps/9/possession/Premier-League-Stats",
                                    "stats_squads_possession_for")

            def find_col(df, *keywords):
                for kw in keywords:
                    for c in df.columns:
                        if kw.lower() in str(c).lower():
                            return c
                return None

            xg_col  = find_col(std,  "xG")
            xga_col = find_col(std,  "xGA")
            gls_col = find_col(std,  "Gls", "Goals")

            if not xg_col or not xga_col:
                logger.warning(f"FBref direct: missing xG/xGA. Cols: {list(std.columns)}")
                return None

            merged = std[["team"]].copy()
            merged["xG"]  = pd.to_numeric(std[xg_col],  errors="coerce")
            merged["xGA"] = pd.to_numeric(std[xga_col], errors="coerce")
            merged["Gls"] = pd.to_numeric(std[gls_col], errors="coerce") if gls_col else merged["xG"]

            if poss is not None and "team" in poss.columns:
                poss_col = find_col(poss, "Poss")
                prgp_col = find_col(poss, "PrgP")
                prgc_col = find_col(poss, "PrgC")
                keep = ["team"] + [c for c in [poss_col, prgp_col, prgc_col] if c]
                merged = merged.merge(poss[keep], on="team", how="left")
                if poss_col: merged.rename(columns={poss_col: "Poss"}, inplace=True)
                if prgp_col: merged.rename(columns={prgp_col: "PrgP"}, inplace=True)
                if prgc_col: merged.rename(columns={prgc_col: "PrgC"}, inplace=True)

            merged = merged.dropna(subset=["xG", "xGA"]).set_index("team")
            if len(merged) < 10 or "Arsenal" not in merged.index:
                logger.warning(f"FBref direct: only {len(merged)} teams, Arsenal present: {'Arsenal' in merged.index}")
                return None

            def prank(s, hi=True):
                r = s.rank(pct=True, method="average") * 99
                return (r if hi else 99 - r).round(1)

            result = {}
            for team in merged.index:
                result[team] = {
                    "goals":       float(prank(merged["Gls"])[team])         if "Gls"  in merged.columns else float(prank(merged["xG"])[team]),
                    "attacking":   float(prank(merged["xG"])[team]),
                    "defending":   float(prank(merged["xGA"], False)[team]),
                    "possession":  float(prank(merged["Poss"])[team])        if "Poss" in merged.columns else 50.0,
                    "counters":    float(prank(merged["PrgP"])[team])        if "PrgP" in merged.columns else 50.0,
                    "physicality": float(prank(merged["PrgC"])[team])        if "PrgC" in merged.columns else 50.0,
                    "pressing":    50.0,
                }

            logger.info(f"FBref direct: {len(result)} teams — Arsenal: {result.get('Arsenal')}")
            return result

        except Exception as e:
            logger.warning(f"FBref direct scrape failed: {e}")
            return None

    def fetch_all_team_stats(self) -> Dict[str, Dict]:
        """
        Priority:
          1. In-memory cache (6h TTL)
          2. Understat live scrape
          3. fbrefdata library (Big 5, filters to PL)
          4. FBref direct pd.read_html scrape
          5. Last successful fetch from disk
        No hardcoded data anywhere.
        """
        # 1. In-memory cache
        if (self._cache is not None and self._cache_time is not None and
                datetime.now() - self._cache_time < timedelta(hours=self.CACHE_TTL_HOURS)):
            logger.info("TeamStats: using in-memory cache")
            return self._cache

        def _set_cache(parsed, source):
            self._cache      = parsed
            self._cache_time = datetime.now()
            self._save_to_disk(parsed)
            logger.info(f"TeamStats [{source}] — Arsenal: {parsed.get('Arsenal')}")
            return self._cache

        # 2. Understat
        raw = self._fetch_understat()
        if raw:
            parsed = self._parse_understat(raw)
            if parsed and "Arsenal" in parsed:
                return _set_cache(parsed, "Understat")
            logger.warning("Understat: parsed data missing Arsenal")

        # 3. fbrefdata library
        try:
            import fbrefdata as fd, warnings as _w
            _w.filterwarnings("ignore")
            fb = fd.FBref("Big 5 European Leagues Combined", "2024-2025", no_store=False)
            std  = fb.read_team_season_stats("standard")
            poss = fb.read_team_season_stats("possession")

            def pl_only(df):
                if "league" in df.index.names:
                    return df[df.index.get_level_values("league").str.contains("Premier|England", case=False, na=False)]
                return df

            std, poss = pl_only(std), pl_only(poss)

            def gcol(df, *kws):
                flat = [" ".join(str(c) for c in col).strip() if isinstance(col, tuple) else str(col)
                        for col in df.columns]
                for kw in kws:
                    for i, f in enumerate(flat):
                        if kw.lower() in f.lower():
                            return df.columns[i]
                return None

            NM = {"Manchester Utd": "Manchester United", "Newcastle Utd": "Newcastle",
                  "Nott'ham Forest": "Nottingham Forest", "Leicester City": "Leicester",
                  "Ipswich Town": "Ipswich"}

            def tnames(df):
                for lvl in (df.index.names or []):
                    if "team" in str(lvl).lower():
                        return [NM.get(str(t), str(t)) for t in df.index.get_level_values(lvl)]
                return [NM.get(str(t), str(t)) for t in df.index]

            data = {}
            for i, name in enumerate(tnames(std)):
                row = std.iloc[i]
                data[name] = {
                    "xG":  float(pd.to_numeric(row[gcol(std,  "xG")],  errors="coerce") or 0) if gcol(std,  "xG")  else 0,
                    "xGA": float(pd.to_numeric(row[gcol(std,  "xGA")], errors="coerce") or 0) if gcol(std,  "xGA") else 0,
                    "Gls": float(pd.to_numeric(row[gcol(std,  "Gls", "Goals")], errors="coerce") or 0) if gcol(std, "Gls", "Goals") else 0,
                }
            for i, name in enumerate(tnames(poss)):
                row = poss.iloc[i]
                if name not in data: data[name] = {}
                for src_k, dst_k in [("Poss","Poss"),("PrgP","PrgP"),("PrgC","PrgC")]:
                    col = gcol(poss, src_k)
                    if col: data[name][dst_k] = float(pd.to_numeric(row[col], errors="coerce") or 0)

            df = pd.DataFrame(data).T.dropna(subset=["xG","xGA"])
            if len(df) >= 10 and "Arsenal" in df.index:
                def pr(s, hi=True): r = s.rank(pct=True)*99; return (r if hi else 99-r).round(1)
                parsed = {t: {
                    "goals":       float(pr(df["Gls"])[t]) if "Gls" in df else float(pr(df["xG"])[t]),
                    "attacking":   float(pr(df["xG"])[t]),
                    "defending":   float(pr(df["xGA"], False)[t]),
                    "possession":  float(pr(df["Poss"])[t]) if "Poss" in df else 50.0,
                    "counters":    float(pr(df["PrgP"])[t]) if "PrgP" in df else 50.0,
                    "physicality": float(pr(df["PrgC"])[t]) if "PrgC" in df else 50.0,
                    "pressing":    50.0,
                } for t in df.index}
                return _set_cache(parsed, "fbrefdata")
        except Exception as e:
            logger.warning(f"TeamStats: fbrefdata failed: {e}")

        # 4. FBref direct pd.read_html scrape
        direct = self._fetch_fbref_direct()
        if direct and "Arsenal" in direct:
            return _set_cache(direct, "FBref direct")

        # 5. Last successful fetch from disk
        disk = self._load_from_disk()
        if disk:
            self._cache      = disk
            self._cache_time = datetime.now()
            logger.info("TeamStats: using last persisted fetch from disk")
            return self._cache

        logger.error("TeamStats: all 4 sources failed — no data available")
        return {}

    def get_team_percentiles(self, team_name: str) -> Optional[Dict[str, float]]:
        data = self.fetch_all_team_stats()
        if not data:
            return None
        if team_name in data:
            return {k: float(v) for k, v in data[team_name].items()}
        matches = [t for t in data if team_name.lower() in t.lower()
                   or t.lower() in team_name.lower()]
        if matches:
            logger.info(f"TeamStats fuzzy: '{team_name}' → '{matches[0]}'")
            return {k: float(v) for k, v in data[matches[0]].items()}
        logger.warning(f"TeamStats: '{team_name}' not found in {list(data.keys())}")
        return None

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
            # Log API errors returned in the response body
            if data.get("errors"):
                logger.error(f"API-Football errors [{endpoint} {params}]: {data['errors']}")
            remaining = r.headers.get("x-ratelimit-requests-remaining", "?")
            logger.debug(f"API-Football [{endpoint}] status={r.status_code} remaining={remaining}")
            self._cache[cache_key] = data
            return data
        except Exception as e:
            logger.error(f"API-Football request failed [{endpoint} {params}]: {e}")
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

    def get_league_teams(self, league_id: int, top_n: int = None,
                         season: int = STANDINGS_SEASON) -> List[Dict]:
        """
        Fetches teams via standings (free-tier compatible).
        Flattens ALL standings groups so every team is captured.
        top_n=None → all teams. top_n=N → first N by rank.
        """
        data = self._get("standings", {"league": league_id, "season": season})
        if not data:
            logger.error(f"get_league_teams: no data returned for league={league_id} season={season}")
            return []
        if not data.get("response"):
            logger.error(f"get_league_teams: empty response for league={league_id} season={season} — errors={data.get('errors')}")
            return []
        try:
            standings_groups = data["response"][0]["league"]["standings"]
        except (IndexError, KeyError) as e:
            logger.error(f"get_league_teams: unexpected structure — {e}")
            return []

        logger.info(f"get_league_teams: league={league_id} season={season} groups={len(standings_groups)}")

        # Flatten all groups and deduplicate by team id
        seen_ids = set()
        all_rows = []
        for group in standings_groups:
            for row in group:
                team_id = row.get("team", {}).get("id")
                if team_id and team_id not in seen_ids:
                    seen_ids.add(team_id)
                    all_rows.append(row)

        logger.info(f"get_league_teams: {len(all_rows)} unique teams found")

        all_rows.sort(key=lambda r: r.get("rank", 99))
        rows = all_rows[:top_n] if top_n else all_rows
        teams = []
        for row in rows:
            t = row.get("team", {})
            tid = t.get("id")
            if not tid or tid == ARSENAL_TEAM_ID:
                continue
            name = t.get("name", "")
            teams.append({
                "id":     tid,
                "name":   name,
                "colour": EPL_COLOURS.get(name, "#4A90D9"),
            })
        return teams

    def get_arsenal_squad(self, season: int = CURRENT_SEASON) -> List[Dict]:
        """
        Fetches Arsenal's current squad from API-Football.
        Returns [{id, name, pos, age}] sorted by position group.
        """
        data = self._get("players/squads", {"team": ARSENAL_TEAM_ID})
        if not data or not data.get("response"):
            return []
        pos_order = {"Goalkeeper": 0, "Defender": 1, "Midfielder": 2, "Attacker": 3}
        try:
            players = data["response"][0]["players"]
            result = []
            for p in players:
                api_pos = p.get("position", "Midfielder")
                pos_code = {
                    "Goalkeeper": "GK",
                    "Defender":   "CB",   # refined later if needed
                    "Midfielder": "MF",
                    "Attacker":   "WG",
                }.get(api_pos, "MF")
                result.append({
                    "id":   p["id"],
                    "name": p["name"],
                    "pos":  pos_code,
                    "api_pos": api_pos,
                })
            result.sort(key=lambda x: pos_order.get(x["api_pos"], 99))
            return result
        except (IndexError, KeyError):
            return []

    def get_squad(self, team_id: int) -> List[Dict]:
        """Returns [{id, name, position}] for a team's full squad — live."""
        data = self._get("players/squads", {"team": team_id})
        if not data or not data.get("response"):
            return []
        try:
            players = data["response"][0]["players"]
            pos_order = {"Goalkeeper": 0, "Defender": 1, "Midfielder": 2, "Attacker": 3}
            result = sorted(
                [{"id": p["id"], "name": p["name"],
                  "position": p.get("position", "Midfielder")} for p in players],
                key=lambda x: (pos_order.get(x["position"], 99), x["name"])
            )
            return result
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
# LIVE DATA CACHE
# Fetches teams and Arsenal squad from API at startup. Falls back to
# hardcoded data if API key is missing or calls fail.
# ─────────────────────────────────────────────────────────────────────────────

# League IDs
EPL_LEAGUE_ID = 39

LEAGUE_NAMES = {
    39: "Premier League",
}

# Fallback hardcoded EPL rival teams — names match API-Football exactly
_FALLBACK_RIVAL_TEAMS = {
    "Aston Villa":      {"id": 66,  "league": 39, "colour": "#670E36"},
    "Bournemouth":      {"id": 35,  "league": 39, "colour": "#DA291C"},
    "Brentford":        {"id": 55,  "league": 39, "colour": "#E30613"},
    "Brighton":         {"id": 51,  "league": 39, "colour": "#0057B8"},
    "Chelsea":          {"id": 49,  "league": 39, "colour": "#034694"},
    "Crystal Palace":   {"id": 52,  "league": 39, "colour": "#1B458F"},
    "Everton":          {"id": 45,  "league": 39, "colour": "#003399"},
    "Fulham":           {"id": 36,  "league": 39, "colour": "#CC0000"},
    "Ipswich":          {"id": 57,  "league": 39, "colour": "#3A64A3"},
    "Leicester":        {"id": 46,  "league": 39, "colour": "#003090"},
    "Liverpool":        {"id": 40,  "league": 39, "colour": "#C8102E"},
    "Manchester City":  {"id": 50,  "league": 39, "colour": "#6CABDD"},
    "Manchester United":{"id": 33,  "league": 39, "colour": "#DA291C"},
    "Newcastle":        {"id": 34,  "league": 39, "colour": "#241F20"},
    "Nottingham Forest":{"id": 65,  "league": 39, "colour": "#DD0000"},
    "Southampton":      {"id": 41,  "league": 39, "colour": "#D71920"},
    "Tottenham":        {"id": 47,  "league": 39, "colour": "#132257"},
    "West Ham":         {"id": 48,  "league": 39, "colour": "#7A263A"},
    "Wolves":           {"id": 39,  "league": 39, "colour": "#FDB913"},
}

# Fallback Arsenal squad (used if API fetch fails)
_FALLBACK_ARSENAL_SQUAD = [
    {"id": 2932,   "name": "David Raya",           "pos": "GK"},
    {"id": 47249,  "name": "William Saliba",        "pos": "CB"},
    {"id": 9711,   "name": "Gabriel Magalhães",     "pos": "CB"},
    {"id": 19220,  "name": "Ben White",             "pos": "CB"},
    {"id": 284460, "name": "Riccardo Calafiori",    "pos": "CB"},
    {"id": 19185,  "name": "Oleksandr Zinchenko",   "pos": "CB"},
    {"id": 19189,  "name": "Declan Rice",           "pos": "MF"},
    {"id": 19239,  "name": "Martin Ødegaard",       "pos": "MF"},
    {"id": 284524, "name": "Mikel Merino",          "pos": "MF"},
    {"id": 19268,  "name": "Bukayo Saka",           "pos": "WG"},
    {"id": 303117, "name": "Gabriel Martinelli",    "pos": "WG"},
    {"id": 521,    "name": "Kai Havertz",           "pos": "WG"},
]


class LiveDataCache:
    """
    Fetches and caches live team + squad data from API-Football.
    Populated once at agent startup. Thread-safe reads after init.
    """

    def __init__(self, api_client: "APIFootballClient"):
        self.api = api_client
        # {team_name: {id, league, colour}}
        self.rival_teams: Dict[str, Dict] = {}
        # [{id, name, pos, api_pos}]
        self.arsenal_squad: List[Dict] = []
        # {team_id: [{id, name, position}]}  — populated on-demand per /squad call
        self._squad_cache: Dict[int, List] = {}

    def initialise(self):
        """Fetches all EPL teams from standings + Arsenal squad at startup."""
        logger.info("🔄 Fetching live EPL team data from API-Football...")

        # Standings locked to 2024 — free tier does not allow 2025
        epl_teams = self.api.get_league_teams(39, top_n=None, season=STANDINGS_SEASON)
        if epl_teams:
            for t in epl_teams:
                self.rival_teams[t["name"]] = {
                    "id":     t["id"],
                    "league": 39,
                    "colour": EPL_COLOURS.get(t["name"], "#4A90D9"),
                }
            logger.info(f"✅ Premier League: {len(epl_teams)} teams loaded")
        else:
            logger.warning("⚠️ EPL fetch failed — using fallback team list")
            self.rival_teams = _FALLBACK_RIVAL_TEAMS.copy()

        # Arsenal squad — use current season (squads endpoint allows 2025)
        squad = self.api.get_arsenal_squad(season=CURRENT_SEASON)
        if not squad:
            squad = self.api.get_arsenal_squad(season=STANDINGS_SEASON)
        if squad:
            self.arsenal_squad = squad
            logger.info(f"✅ Arsenal squad: {len(squad)} players loaded")
        else:
            logger.warning("⚠️ Arsenal squad fetch failed — using fallback")
            self.arsenal_squad = _FALLBACK_ARSENAL_SQUAD.copy()

    def get_squad(self, team_id: int) -> List[Dict]:
        """Returns live squad for any team, with per-team caching."""
        if team_id not in self._squad_cache:
            self._squad_cache[team_id] = self.api.get_squad(team_id)
        return self._squad_cache[team_id]

    def teams_by_league(self, league_id: int) -> Dict[str, Dict]:
        return {k: v for k, v in self.rival_teams.items()
                if v.get("league") == league_id}

    def get_team_info(self, team_name: str) -> Optional[Dict]:
        return self.rival_teams.get(team_name)
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
        """Maps API-Football team stats to radar keys. Returns values scaled 0-100."""
        if not team_stats:
            return {}

        f  = team_stats.get("fixtures", {})
        g  = team_stats.get("goals", {})
        p  = team_stats.get("passes", {})
        cs = team_stats.get("clean_sheet", {})

        played     = f.get("played", {}).get("total") or 1
        wins       = f.get("wins", {}).get("total") or 0
        goals_for  = g.get("for",     {}).get("total", {}).get("total") or 0
        goals_ag   = g.get("against", {}).get("total", {}).get("total") or 0
        clean_sh   = cs.get("total") or 0
        pass_acc   = float(p.get("accuracy") or 60)

        gf_per90   = goals_for  / played
        ga_per90   = goals_ag   / played
        win_rate   = wins / played          # 0.0 – 1.0
        cs_rate    = clean_sh / played      # 0.0 – 1.0

        # Scale each to a 0-100 range using realistic PL bounds:
        #   goals/game: 0.5 (worst) → 3.0 (best) → mapped to 0-100
        #   defending:  low GA is better — invert: 0.5 GA = 100, 3.0 GA = 0
        #   possession: pass accuracy 50%=0, 90%=100
        #   pressing:   win rate 0=0, 1.0=100
        #   physicality: clean sheet rate 0=0, 0.6=100
        #   attacking = goals (same scale, separate axis)
        #   counters  = win rate, slightly adjusted
        def scale(val, lo, hi):
            """Linear scale val from [lo,hi] to [0,100], clamped."""
            return min(max(round((val - lo) / (hi - lo) * 100, 1), 0), 99)

        return {
            "goals":       scale(gf_per90,          0.5, 3.0),
            "attacking":   scale(gf_per90,          0.5, 3.0),
            "defending":   scale(3.0 - ga_per90,    0.0, 2.5),   # inverted: less GA = better
            "possession":  scale(pass_acc,          55,  90),
            "pressing":    scale(win_rate * 100,    20,  80),
            "physicality": scale(cs_rate * 100,     5,   60),
            "counters":    scale(win_rate * 100,    15,  75),
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
            # Team metrics are pre-scaled to 0-100 in extract_team_radar_values
            # so they use max=100 here (pass-through)
            "goals": 100, "attacking": 100, "defending": 100,
            "possession": 100, "pressing": 100, "physicality": 100, "counters": 100,
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
# RADAR CHART RENDERER  (DataMB style — stat table + radar)
# ─────────────────────────────────────────────────────────────────────────────

class RadarRenderer:
    """
    Generates a DataMB-style image: percentile table on top, radar below.
    White background, Arsenal red polygon, rival purple/blue polygon.
    """

    BG          = "#FFFFFF"
    ARSENAL_COL = "#EF0107"
    RIVAL_COL   = "#7B6BDE"
    GRID        = "#E8EAF0"
    SPOKE       = "#DDE0EA"
    TEXT_MED    = "#666680"
    TEXT_LIGHT  = "#AAAABC"
    AFC_LABEL   = "#3D5AF1"
    RIVAL_LABEL = "#E8356D"
    WATERMARK   = "#CCCCDD"

    def render(
        self,
        labels:       List[str],
        values_a:     List[float],
        label_a:      str,
        values_b:     List[float] = None,
        label_b:      str = None,
        title:        str = "",
        subtitle:     str = "",
        season:       str = "2025/26",
        rival_colour: str = None,
    ) -> bytes:

        rival_col = rival_colour or self.RIVAL_COL
        n      = len(labels)
        # Start at top, go clockwise
        angles = np.linspace(0, 2*np.pi, n, endpoint=False) + np.pi/2
        ac     = np.append(angles, angles[0])
        va_c   = np.append(np.array(values_a), values_a[0]) / 100.0
        vb_c   = (np.append(np.array(values_b), values_b[0]) / 100.0
                  if values_b is not None else None)

        fig = plt.figure(figsize=(8.5, 10.5), facecolor=self.BG)

        # ── STAT TABLE (top 26% of figure) ───────────────────────────────────
        ax_t = fig.add_axes([0.03, 0.74, 0.94, 0.24], facecolor=self.BG)
        ax_t.set_xlim(0, 1)
        ax_t.set_ylim(0, 1)
        ax_t.axis("off")

        # Column x positions — label col + one per metric
        cx = [0.0] + [0.175 + i * 0.115 for i in range(len(labels))]

        # Header background
        ax_t.add_patch(plt.Rectangle((0, 0.78), 1, 0.22,
            facecolor="#F7F8FC", edgecolor="none", zorder=0))
        ax_t.axhline(0.78, color="#E0E2EE", linewidth=0.8)

        # Header labels
        ax_t.text(cx[0], 0.89, "Percentiles",
            ha="left", va="center", fontsize=8, color=self.TEXT_LIGHT,
            style="italic")
        for i, lbl in enumerate(labels):
            if i + 1 < len(cx):
                ax_t.text(cx[i+1], 0.89, lbl,
                    ha="center", va="center", fontsize=8, color=self.TEXT_LIGHT)

        # Arsenal row
        ax_t.text(cx[0], 0.60, label_a,
            ha="left", va="center", fontsize=10, color=self.AFC_LABEL,
            fontweight="bold")
        ax_t.text(cx[0], 0.46, f"Premier League, {season}",
            ha="left", va="center", fontsize=7, color=self.TEXT_LIGHT)
        for i, v in enumerate(values_a):
            if i + 1 < len(cx):
                ax_t.text(cx[i+1], 0.53, f"{round(v, 1)}",
                    ha="center", va="center", fontsize=9.5,
                    color=self.AFC_LABEL, fontweight="bold")

        # Row divider
        ax_t.axhline(0.34, color="#E8EAF0", linewidth=0.6)

        # Rival row (if comparison)
        if values_b is not None and label_b:
            ax_t.text(cx[0], 0.24, label_b,
                ha="left", va="center", fontsize=10, color=self.RIVAL_LABEL,
                fontweight="bold")
            ax_t.text(cx[0], 0.10, f"Premier League, {season}",
                ha="left", va="center", fontsize=7, color=self.TEXT_LIGHT)
            for i, v in enumerate(values_b):
                if i + 1 < len(cx):
                    ax_t.text(cx[i+1], 0.17, f"{round(v, 1)}",
                        ha="center", va="center", fontsize=9.5,
                        color=self.RIVAL_LABEL, fontweight="bold")

        # Table border
        for spine in ["top", "bottom", "left", "right"]:
            ax_t.spines[spine].set_visible(True)
            ax_t.spines[spine].set_color("#E0E2EE")
            ax_t.spines[spine].set_linewidth(0.8)

        # ── RADAR (bottom 70% of figure) ─────────────────────────────────────
        ax = fig.add_axes([0.08, 0.03, 0.84, 0.70], polar=True,
                          facecolor=self.BG)
        ring_th = np.linspace(0, 2*np.pi, 360)

        # Subtle ring fills
        for rv, alpha in [(0.2,0.07),(0.4,0.05),(0.6,0.04),(0.8,0.03)]:
            ax.fill_between(ring_th, max(rv-0.2, 0), rv,
                color="#EEEEFF", alpha=alpha, zorder=0)

        # Ring outlines
        for rv in [0.2, 0.4, 0.6, 0.8, 1.0]:
            ax.plot(ring_th, [rv]*360, color=self.GRID, linewidth=0.7, zorder=1)

        # Spokes
        for angle in angles:
            ax.plot([angle, angle], [0, 1.0], color=self.SPOKE,
                    linewidth=0.7, zorder=1)

        # Rival behind Arsenal
        if vb_c is not None:
            ax.fill(ac, vb_c, color=rival_col, alpha=0.14, zorder=2)
            ax.plot(ac, vb_c, color=rival_col, linewidth=2.2, zorder=3)
            ax.scatter(angles, np.array(values_b)/100.0,
                color=rival_col, s=45, zorder=4,
                edgecolors="white", linewidths=1.2)

        # Arsenal on top
        ax.fill(ac, va_c, color=self.ARSENAL_COL, alpha=0.16, zorder=2)
        ax.plot(ac, va_c, color=self.ARSENAL_COL, linewidth=2.2, zorder=3)
        ax.scatter(angles, np.array(values_a)/100.0,
            color=self.ARSENAL_COL, s=45, zorder=5,
            edgecolors="white", linewidths=1.2)

        ax.set_xticks([]); ax.set_yticks([])
        ax.set_ylim(0, 1.18)
        ax.spines["polar"].set_visible(False)

        # Outer border ring
        ax.plot(ring_th, [1.0]*360, color="#C8CCDE", linewidth=1.4, zorder=5)

        # Axis labels
        LABEL_R = 1.10
        for angle, label in zip(angles, labels):
            deg = np.degrees(angle) % 360
            if   deg < 10 or deg > 350: ha, va_a = "center", "bottom"
            elif 10  <= deg < 80:        ha, va_a = "left",   "center"
            elif 80  <= deg < 100:       ha, va_a = "center", "bottom"
            elif 100 <= deg < 170:       ha, va_a = "left",   "center"
            elif 170 <= deg < 190:       ha, va_a = "center", "top"
            elif 190 <= deg < 260:       ha, va_a = "right",  "center"
            elif 260 <= deg < 280:       ha, va_a = "center", "top"
            else:                         ha, va_a = "right",  "center"
            ax.text(angle, LABEL_R, label,
                ha=ha, va=va_a, fontsize=9.5, color=self.TEXT_MED,
                fontweight="500", clip_on=False)

        # Watermark
        fig.text(0.5, 0.005,
            f"DataMB  ·  Premier League {season}  ·  Arsenal FC Agent",
            ha="center", va="bottom", fontsize=7.5, color=self.WATERMARK)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=160,
                    facecolor=self.BG, bbox_inches="tight", pad_inches=0.15)
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
    Orchestrator. Uses LiveDataCache for always-current team and player data.
    Called by the Flask web UI and the background scheduler.
    """

    def __init__(self, twitter_api=None, twitter_client=None):
        self.api_client     = APIFootballClient(API_FOOTBALL_KEY)
        self.cache          = LiveDataCache(self.api_client)
        self.extractor      = StatsExtractor()
        self.renderer       = RadarRenderer()
        self.narrative      = ArsenalNarrativeGenerator()
        self.scraper = TeamStatsScraper()   # Understat live + static fallback          # ← FBref team stats
        self.twitter_api    = twitter_api
        self.twitter_client = twitter_client

        # Populate live data (teams + Arsenal squad) at startup
        self.cache.initialise()

    # ── Convenience properties for web UI ────────────────────────────────
    @property
    def rival_teams(self) -> Dict:
        return self.cache.rival_teams

    @property
    def arsenal_squad(self) -> List[Dict]:
        return self.cache.arsenal_squad

    # ── Player vs Player ──────────────────────────────────────────────────

    def build_player_comparison(
        self,
        arsenal_player_id: int,     # player ID from live squad
        arsenal_player_name: str,
        arsenal_pos: str,           # pos code: GK/CB/MF/WG/ST
        rival_name: str,            # name to search
        rival_team_id: int = None,
        rival_league_id: int = None,
        tone: str = "hype",
        custom_note: str = "",
    ) -> Dict:
        metrics_def   = PLAYER_RADAR_METRICS.get(arsenal_pos, PLAYER_RADAR_METRICS["MF"])
        metric_labels = [m[0] for m in metrics_def]
        metric_keys   = [m[1] for m in metrics_def]

        # Arsenal player stats
        afc_data = self.api_client.get_player_stats(arsenal_player_id)
        if not afc_data:
            return {"error": f"Could not fetch stats for {arsenal_player_name}"}

        afc_raw = self.extractor.extract_player_radar_values(afc_data, arsenal_pos)
        afc_pct = self.extractor.percentile_normalise(afc_raw)

        if not afc_pct:
            return {"error": f"No stat data returned for {arsenal_player_name} — they may not have enough minutes this season."}

        vals_a = [afc_pct[k] for k in metric_keys if k in afc_pct]
        if len(vals_a) != len(metric_keys):
            missing = [k for k in metric_keys if k not in afc_pct]
            return {"error": f"Incomplete stats for {arsenal_player_name}. Missing: {missing}"}

        # Rival player stats
        vals_b     = None
        rival_data = None
        if rival_name:
            rival_data = self.api_client.search_player(
                rival_name, rival_team_id, rival_league_id
            )
            if rival_data:
                rival_raw = self.extractor.extract_player_radar_values(rival_data, arsenal_pos)
                rival_pct = self.extractor.percentile_normalise(rival_raw)
                if rival_pct and all(k in rival_pct for k in metric_keys):
                    vals_b = [rival_pct[k] for k in metric_keys]
                else:
                    logger.warning(f"Incomplete stats for rival {rival_name} — plotting Arsenal only")
                    rival_data = None

        rival_display = rival_data["player"]["name"] if rival_data else None
        title    = f"{arsenal_player_name}  {'vs  ' + rival_display if rival_display else ''}"
        subtitle = f"{arsenal_pos}  ·  Premier League 2025/26  ·  Percentile Rankings"

        img_bytes = self.renderer.render(
            labels=metric_labels, values_a=vals_a,
            label_a=arsenal_player_name,
            values_b=vals_b, label_b=rival_display,
            title=title, subtitle=subtitle,
        )

        metrics_for_narrative = [
            (metric_labels[i], vals_a[i], vals_b[i] if vals_b else 0)
            for i in range(len(metric_labels))
        ]

        text = self.narrative.generate_player_narrative(
            arsenal_player=arsenal_player_name,
            rival_player=rival_display or "",
            metrics=metrics_for_narrative,
            tone=tone, custom_note=custom_note,
        )

        return {
            "image_bytes":  img_bytes, "narrative": text,
            "labels":       metric_labels, "values_a": vals_a,
            "values_b":     vals_b, "arsenal_name": arsenal_player_name,
            "rival_name":   rival_display, "tone": tone, "mode": "player",
        }

    # ── Team vs Team ──────────────────────────────────────────────────────

    def build_team_comparison(
        self,
        rival_team_key: str,
        tone: str = "hype",
        custom_note: str = "",
    ) -> Dict:
        rival_info = self.cache.get_team_info(rival_team_key)
        if not rival_info:
            return {"error": f"Unknown rival team: {rival_team_key}"}

        # ── Fetch percentiles from FBref ──────────────────────────────────
        afc_pct   = self.scraper.get_team_percentiles("Arsenal")
        rival_pct = self.scraper.get_team_percentiles(rival_team_key)

        if not afc_pct:
            return {"error": "Could not fetch Arsenal stats from Understat or static data. Try again shortly."}
        if not rival_pct:
            return {"error": f"Could not fetch {rival_team_key} stats from FBref."}

        labels = [m[0] for m in TEAM_RADAR_METRICS]
        keys   = [m[1] for m in TEAM_RADAR_METRICS]

        if not all(k in afc_pct for k in keys):
            missing = [k for k in keys if k not in afc_pct]
            return {"error": f"Missing Arsenal FBref metrics: {missing}"}
        if not all(k in rival_pct for k in keys):
            missing = [k for k in keys if k not in rival_pct]
            return {"error": f"Missing {rival_team_key} FBref metrics: {missing}"}

        vals_a = [round(afc_pct[k],   1) for k in keys]
        vals_b = [round(rival_pct[k], 1) for k in keys]

        title    = f"Arsenal FC  vs  {rival_team_key}"
        subtitle = f"Team Radar  ·  Premier League  ·  2025/26"

        img_bytes = self.renderer.render(
            labels=labels, values_a=vals_a, label_a="Arsenal FC",
            values_b=vals_b, label_b=rival_team_key,
            title=title, subtitle=subtitle,
            rival_colour=rival_info.get("colour", RIVAL_COLOUR),
        )

        metrics_for_narrative = [
            (labels[i], vals_a[i], vals_b[i]) for i in range(len(labels))
        ]

        text = self.narrative.generate_team_narrative(
            rival_team=rival_team_key,
            metrics=metrics_for_narrative,
            tone=tone, custom_note=custom_note,
        )

        return {
            "image_bytes": img_bytes, "narrative": text,
            "labels": labels, "values_a": vals_a, "values_b": vals_b,
            "arsenal_name": "Arsenal FC", "rival_name": rival_team_key,
            "tone": tone, "mode": "team",
        }

    # ── Post to X ─────────────────────────────────────────────────────────

    def post_to_x(self, narrative: str, image_bytes: bytes) -> Dict:
        if not self.twitter_api or not self.twitter_client:
            return {"success": False, "error": "Twitter clients not configured"}
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name
            media    = self.twitter_api.media_upload(filename=tmp_path)
            os.unlink(tmp_path)
            response = self.twitter_client.create_tweet(
                text=narrative, media_ids=[media.media_id_string]
            )
            tweet_id = response.data["id"]
            logger.info(f"⚽ Posted: https://twitter.com/user/status/{tweet_id}")
            return {"success": True, "tweet_id": tweet_id}
        except Exception as e:
            logger.error(f"Post to X failed: {e}")
            return {"success": False, "error": str(e)}
