"""
═══════════════════════════════════════════════════════════════════════════════
    COMPLETE CRYPTO + ARSENAL TWITTER BOT
    10 Crypto News + 4 Quotes + 3 Arsenal FC = 17 Posts Per Day

    ARSENAL UPGRADES v3.0:
    ✅ Multiple reliable Arsenal RSS feeds (BBC, Sky, The Athletic, etc.)
    ✅ Positivity bias AI layer - counters negative pundit narratives
    ✅ Sentiment detection - flips negative framing to fan-positive framing
    ✅ 3 Arsenal posts per day (up from 1)
    ✅ Counter-narrative post types: fan_pride, stat_defense, counter_narrative
    ✅ Pundit/media negativity detection and rebuttal engine
    ✅ Latest news prioritisation (24-hour recency filter)
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import random
import requests
import feedparser
import tweepy
import time
import json
import hashlib
import sqlite3
import re
from datetime import datetime, timedelta
import pytz
from openai import OpenAI
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from contextlib import contextmanager
from typing import List, Dict, Tuple, Optional
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum
from difflib import SequenceMatcher
from urllib.parse import urlparse, quote

# ═══════════════════════════════════════════════════════════════════════════
# ENVIRONMENT & CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

load_dotenv()

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")
BITLY_TOKEN = os.getenv("BITLY_TOKEN")

# Database
DATABASE_PATH = "crypto_bot_data.db"

# Posting Limits
DAILY_NEWS_LIMIT = 10        # Crypto news posts
DAILY_QUOTE_LIMIT = 4        # Inspirational quote posts
DAILY_ARSENAL_LIMIT = 3      # Arsenal FC posts (increased from 1)
DAILY_TOTAL_LIMIT = 17       # Total posts per day
POST_INTERVAL_MINUTES = 60   # Minimum gap between posts

# Tracking
last_post_time = None
daily_news_posts = 0
daily_quote_posts = 0
daily_arsenal_posts = 0
last_reset_date = datetime.now(pytz.UTC).date()

# -----------------------------------------------------------------------
# POSTING SCHEDULE
# Format: (time_UTC, post_type)
# 10 crypto news + 4 quotes + 3 Arsenal = 17 posts
# -----------------------------------------------------------------------
POSTING_SCHEDULE = [
    ("01:30", "arsenal"),   #  2. Arsenal (morning latest news)
    ("02:31", "news"),      #  3. Crypto News
    ("03:45", "quote"),     #  4. Inspirational Quote
    ("05:00", "news"),      #  5. Crypto News
    ("08:00", "arsenal"),   #  7. Arsenal (morning edition)
    ("09:15", "news"),      #  8. Crypto News
    ("10:30", "quote"),     #  9. Inspirational Quote
    ("11:45", "news"),      # 10. Crypto News
    ("13:30", "arsenal"),   # 12. Arsenal (afternoon edition)
    ("19:00", "quote"),     # 16. Inspirational Quote
   ]

# Content Types
CRYPTO_CONTENT_TYPES = [
    "educational", "market_analysis", "contrarian",
    "question", "hot_take", "breakdown"
]

# Arsenal post types including new counter-narrative types
ARSENAL_CONTENT_TYPES = [
    "fan_pride",           # Celebrate Arsenal achievements & positives
    "counter_narrative",   # Directly rebut negative pundit/media takes
    "stat_defense",        # Use stats to defend Arsenal against criticism
    "match_hype",          # Build excitement around upcoming matches
    "team_news",           # Latest squad/transfer news with positive spin
    "analysis"             # Tactical/performance analysis, positive framing
]

# Quote Categories
QUOTE_CATEGORIES = ["contrarian", "question", "educational", "bold"]

# -----------------------------------------------------------------------
# ARSENAL RSS FEEDS - Multiple reliable sources for latest news
# -----------------------------------------------------------------------
ARSENAL_RSS_FEEDS = [
    "https://www.arsenal.com/rss.xml",                              # Official Arsenal
    "https://feeds.bbci.co.uk/sport/football/teams/arsenal/rss.xml",  # BBC Sport Arsenal
    "https://www.skysports.com/rss/11095",                          # Sky Sports Arsenal
    "https://www.90min.com/arsenal/rss",                            # 90min Arsenal
    "https://arseblog.com/feed/",                                   # Arseblog (fan-positive)
    "https://www.justarsenal.com/feed",                             # Just Arsenal (fan blog)
    "https://www.arsenalnews.net/feed/",                            # Arsenal News
    "https://www.goal.com/feeds/en/news?club=arsenal",              # Goal.com Arsenal
]

# Crypto RSS Feeds (unchanged)
CRYPTO_RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://crypto.news/feed/",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/.rss/full/"
]

# Duplicate Detection
SIMILARITY_THRESHOLD = 0.75

# -----------------------------------------------------------------------
# ARSENAL SENTIMENT CONFIG
# -----------------------------------------------------------------------

# Keywords that signal negative media/pundit narratives to counter
NEGATIVE_ARSENAL_KEYWORDS = [
    "crisis", "slump", "struggle", "flop", "concern", "worry", "doubt",
    "question", "pressure", "sack", "fire", "failed", "failure", "weak",
    "disappointing", "disaster", "collapse", "problems", "issues", "injury blow",
    "setback", "unconvincing", "fortunate", "lucky win", "poor", "below par",
    "overrated", "inconsistent", "must improve", "warning", "alarm",
    "concern", "missing", "absent", "suspend", "ban"
]

# Keywords that signal positive/fan-worthy stories to amplify
POSITIVE_ARSENAL_KEYWORDS = [
    "win", "victory", "goal", "scored", "assist", "clean sheet", "top",
    "leader", "champion", "title", "unbeaten", "record", "impressive",
    "brilliant", "excellent", "masterclass", "dominated", "controlled",
    "signing", "return", "fit", "available", "contract", "extend",
    "development", "academy", "young", "talent"
]

# Common negative pundit/media narratives and their counter-angles
NARRATIVE_COUNTERS = {
    "bottler": "Arsenal have the BEST Premier League record over the last 2 years. The data doesn't lie.",
    "lucky": "Luck? Arsenal create more chances per game than almost anyone in the league. That's not luck.",
    "inconsistent": "Top 4 finishes, FA Cup glory, title races. Arsenal's trajectory is one direction: UP.",
    "not title material": "They said that last year too. And the year before. Arsenal keep proving them wrong.",
    "too young": "Youth + quality + a world-class manager = Arsenal's formula. It's working.",
    "no leaders": "Odegaard. White. Saliba. Raya. Arsenal have leaders all over the pitch.",
    "defensive problems": "Arsenal's xGA stats are elite. The 'defensive problems' narrative is outdated.",
    "no striker": "Top 4 without a traditional 9. Imagine when they get one.",
    "mental weakness": "This Arsenal side bounces back every single time. That IS mentality.",
    "arteta out": "Arteta took Arsenal from mid-table chaos to title contenders. The project is real."
}

# ═══════════════════════════════════════════════════════════════════════════
# INSPIRATIONAL QUOTES DATABASE (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

INSPIRATIONAL_QUOTES = {
    "contrarian": [
        "When everyone is fearful, that's when fortunes are made. Be greedy when others are fearful.",
        "The crowd is usually wrong at the extremes. Think independently.",
        "Real wealth is built by going against the noise, not following it.",
        "If you're not uncomfortable, you're probably not growing your portfolio fast enough.",
        "The next Bitcoin millionaire is someone buying today while others panic.",
        "Your future self will either thank you or regret your inaction. Choose wisely.",
        "Markets reward contrarians who have the courage to act when everyone else freezes.",
        "The best opportunities look risky to the crowd. That's why they're opportunities.",
        "Popular opinion is expensive. Independent thinking is profitable.",
        "Everyone talks about buying the dip. Few have the conviction to actually do it.",
        "The herd mentality makes you broke. Independent analysis makes you rich.",
        "When the news is worst, that's often when the opportunity is best.",
        "Comfort zones build average portfolios. Calculated risks build generational wealth.",
        "The majority is often wrong at market turning points. Are you following or leading?",
        "Successful investing means being lonely sometimes. Get comfortable with it.",
    ],
    "question": [
        "What's your crypto strategy for 2026? Drop it below 👇",
        "Bull market or bear market - which teaches you more? Let's discuss.",
        "If you could only hold one coin for 10 years, what would it be?",
        "DCA or lump sum investing? Which strategy works better for you?",
        "What's the biggest lesson crypto taught you? Share your wisdom 👇",
        "HODL or active trading? What's your game plan?",
        "Which matters more: technical analysis or fundamentals? Defend your choice.",
        "What percentage of your portfolio is in crypto? Too much? Too little?",
        "If you could go back to 2020, what would you tell yourself about crypto?",
        "What's more important: timing the market or time in the market?",
        "Layer 1 or Layer 2 solutions - where's the real opportunity?",
        "Staking or lending - which generates better passive income for you?",
        "What's the most underrated crypto skill nobody talks about?",
        "How do you manage FOMO when coins are pumping? Share your tactics.",
        "What's your exit strategy? Or are you never selling?",
        "Which crypto narrative will dominate 2026? DeFi, NFTs, AI, or something else?",
        "What's one crypto myth you wish people would stop believing?",
        "How much research do you do before buying a coin? Hours, days, weeks?",
        "What's your risk management strategy? How do you protect your portfolio?",
        "If crypto disappeared tomorrow, what's the most valuable skill you gained?",
    ],
    "educational": [
        "Don't invest in what you don't understand. Study first, invest second.",
        "The market rewards those who do their homework. DYOR isn't optional. 📚",
        "Risk management isn't sexy. But it's what separates winners from gamblers.",
        "Diversification isn't being scared. It's being smart.",
        "Price is what you pay. Value is what you get. Know the difference.",
        "The best investment you can make is in your own education. Start there.",
        "Understanding tokenomics > Following influencers. Always.",
        "A strategy without discipline is just a wish. Build both.",
        "Reading whitepapers > Reading tweets. One builds wealth, one builds noise.",
        "Compound interest is the eighth wonder of the world. Let it work for you. ⏰💰",
        "Your biggest edge isn't information. It's how you process it.",
        "Learning to lose small is more valuable than learning to win big.",
        "The blockchain doesn't care about your feelings. It rewards knowledge and patience.",
        "Understanding market cycles > Predicting market moves.",
        "Position sizing is the difference between surviving and thriving in crypto.",
        "Smart contracts are code. Code has bugs. Never invest more than you can afford to lose.",
        "On-chain analysis beats Twitter sentiment. Learn to read the blockchain.",
        "Security isn't paranoia. It's insurance for your financial future.",
        "The best traders keep journals. Track, analyze, improve. Repeat.",
        "Volatility isn't risk. Not understanding what you own is the real risk.",
    ],
    "bold": [
        "Fear keeps you broke. Knowledge makes you rich. Which one are you choosing?",
        "Your 2030 self is watching. Make them proud. 👀",
        "Stop waiting for perfect entry. Perfect execution beats perfect timing.",
        "Fortune favors the brave. But it rewards the prepared. Be both.",
        "The best traders aren't lucky. They're disciplined. Which one are you?",
        "Success leaves clues. Study the winners, not the gamblers.",
        "Don't chase pumps. Build positions. Patience pays better than FOMO.",
        "Every dip is a discount if you're playing the long game. 💎🙌",
        "Your biggest competition isn't other traders. It's your own emotions.",
        "The hardest trades are usually the right ones. Trust your strategy.",
        "Wealth isn't built in green candles. It's built in red ones. 📉➡️📈",
        "Markets crash. Conviction doesn't. Stay focused on fundamentals.",
        "The best time to invest was yesterday. The second best time is now.",
        "Don't wait for the bull run. Build during the bear market. 🐻➡️🐂",
        "Your portfolio in 5 years will thank you for the decisions you make today.",
        "Volatility is the price of admission. Patience is the price of profit.",
        "Think in decades, not days. That's how generational wealth is built.",
        "Small consistent gains beat big risky bets. Play the long game.",
        "Financial freedom isn't about getting rich quick. It's about getting rich for sure.",
        "The difference between where you are and where you want to be is action. Start now.",
    ]
}

# ═══════════════════════════════════════════════════════════════════════════
# LOGGING SETUP
# ═══════════════════════════════════════════════════════════════════════════

if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[
        RotatingFileHandler('logs/bot_activity.log', maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# INITIALIZE APIS
# ═══════════════════════════════════════════════════════════════════════════

openai_client = OpenAI(api_key=OPENAI_API_KEY)

auth = tweepy.OAuth1UserHandler(
    TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
)
twitter_api = tweepy.API(auth)
twitter_client = tweepy.Client(
    consumer_key=TWITTER_API_KEY,
    consumer_secret=TWITTER_API_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_SECRET
)

# ═══════════════════════════════════════════════════════════════════════════
# DATABASE MANAGER
# ═══════════════════════════════════════════════════════════════════════════

class DatabaseManager:
    """Manages all database operations"""

    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        self.init_database()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def init_database(self):
        with self.get_connection() as conn:
            c = conn.cursor()

            c.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tweet_id TEXT UNIQUE NOT NULL,
                    post_type TEXT NOT NULL,
                    url TEXT,
                    content_hash TEXT NOT NULL,
                    tweet_text TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    quote_category TEXT,
                    hashtags TEXT,
                    posted_at TIMESTAMP NOT NULL,
                    likes INTEGER DEFAULT 0,
                    retweets INTEGER DEFAULT 0,
                    replies INTEGER DEFAULT 0,
                    impressions INTEGER DEFAULT 0,
                    engagement_rate REAL DEFAULT 0.0,
                    last_updated TIMESTAMP
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS content_hashes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_hash TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    tweet_id TEXT,
                    FOREIGN KEY (tweet_id) REFERENCES posts(tweet_id)
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS ab_tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_name TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    tweet_id TEXT NOT NULL,
                    posted_at TIMESTAMP NOT NULL,
                    engagement_score REAL DEFAULT 0.0,
                    is_control BOOLEAN DEFAULT 0,
                    metadata TEXT,
                    FOREIGN KEY (tweet_id) REFERENCES posts(tweet_id)
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS hashtag_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hashtag TEXT NOT NULL,
                    uses_count INTEGER DEFAULT 0,
                    total_engagement INTEGER DEFAULT 0,
                    avg_engagement REAL DEFAULT 0.0,
                    last_used TIMESTAMP,
                    performance_score REAL DEFAULT 0.0
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS quote_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quote_category TEXT NOT NULL,
                    quote_text TEXT NOT NULL,
                    uses_count INTEGER DEFAULT 0,
                    total_engagement INTEGER DEFAULT 0,
                    avg_engagement REAL DEFAULT 0.0,
                    last_used TIMESTAMP,
                    performance_score REAL DEFAULT 0.0
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS rss_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    feed_name TEXT,
                    feed_type TEXT,
                    last_fetched TIMESTAMP,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    success_rate REAL DEFAULT 1.0,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')

            c.execute('CREATE INDEX IF NOT EXISTS idx_posts_posted_at ON posts(posted_at)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_posts_content_type ON posts(content_type)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_posts_post_type ON posts(post_type)')

            logger.info("✅ Database initialized")

    def log_post(self, tweet_id, post_type, url, content_hash, tweet_text,
                 content_type, hashtags, quote_category=None):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = datetime.now(pytz.UTC)
            hashtag_str = json.dumps(hashtags) if hashtags else None
            c.execute('''
                INSERT INTO posts (tweet_id, post_type, url, content_hash, tweet_text,
                                 content_type, quote_category, hashtags, posted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (tweet_id, post_type, url, content_hash, tweet_text,
                  content_type, quote_category, hashtag_str, now))

    def has_been_posted(self, url):
        if not url:
            return False
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM posts WHERE url = ?', (url,))
            return c.fetchone()[0] > 0

    def is_similar_content(self, content_hash, days=7):
        with self.get_connection() as conn:
            c = conn.cursor()
            cutoff = datetime.now(pytz.UTC) - timedelta(days=days)
            c.execute('''
                SELECT COUNT(*) FROM content_hashes
                WHERE content_hash = ? AND created_at > ?
            ''', (content_hash, cutoff))
            return c.fetchone()[0] > 0

    def log_content_hash(self, content_hash, tweet_id=None):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = datetime.now(pytz.UTC)
            try:
                c.execute('''
                    INSERT INTO content_hashes (content_hash, created_at, tweet_id)
                    VALUES (?, ?, ?)
                ''', (content_hash, now, tweet_id))
            except sqlite3.IntegrityError:
                pass

    def get_recent_posts(self, limit=50, post_type=None):
        with self.get_connection() as conn:
            c = conn.cursor()
            if post_type:
                c.execute('''
                    SELECT tweet_id, tweet_text, content_type, post_type, posted_at,
                           likes, retweets, replies, engagement_rate
                    FROM posts WHERE post_type = ?
                    ORDER BY posted_at DESC LIMIT ?
                ''', (post_type, limit))
            else:
                c.execute('''
                    SELECT tweet_id, tweet_text, content_type, post_type, posted_at,
                           likes, retweets, replies, engagement_rate
                    FROM posts ORDER BY posted_at DESC LIMIT ?
                ''', (limit,))
            results = []
            for row in c.fetchall():
                results.append({
                    'tweet_id': row[0], 'tweet_text': row[1],
                    'content_type': row[2], 'post_type': row[3],
                    'posted_at': row[4], 'likes': row[5],
                    'retweets': row[6], 'replies': row[7],
                    'engagement_rate': row[8]
                })
            return results

    def get_content_type_performance(self, days=30):
        with self.get_connection() as conn:
            c = conn.cursor()
            cutoff = datetime.now(pytz.UTC) - timedelta(days=days)
            c.execute('''
                SELECT content_type, post_type, COUNT(*) as post_count,
                       AVG(likes) as avg_likes, AVG(retweets) as avg_retweets,
                       AVG(engagement_rate) as avg_engagement_rate
                FROM posts WHERE posted_at > ? AND engagement_rate > 0
                GROUP BY content_type, post_type
                ORDER BY avg_engagement_rate DESC
            ''', (cutoff,))
            results = []
            for row in c.fetchall():
                results.append({
                    'content_type': row[0], 'post_type': row[1],
                    'post_count': row[2], 'avg_likes': round(row[3], 2),
                    'avg_retweets': round(row[4], 2),
                    'avg_engagement_rate': round(row[5], 2)
                })
            return results

    def log_ab_test(self, experiment_name, variant, tweet_id, is_control=False):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = datetime.now(pytz.UTC)
            c.execute('''
                INSERT INTO ab_tests (experiment_name, variant, tweet_id, posted_at, is_control)
                VALUES (?, ?, ?, ?, ?)
            ''', (experiment_name, variant, tweet_id, now, is_control))

    def update_hashtag_performance(self, hashtags, engagement):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = datetime.now(pytz.UTC)
            for hashtag in hashtags:
                c.execute('SELECT uses_count, total_engagement FROM hashtag_performance WHERE hashtag = ?', (hashtag,))
                result = c.fetchone()
                if result:
                    new_uses = result[0] + 1
                    new_total = result[1] + engagement
                    new_avg = new_total / new_uses
                    c.execute('''
                        UPDATE hashtag_performance
                        SET uses_count = ?, total_engagement = ?,
                            avg_engagement = ?, last_used = ?, performance_score = ?
                        WHERE hashtag = ?
                    ''', (new_uses, new_total, new_avg, now, new_avg, hashtag))
                else:
                    c.execute('''
                        INSERT INTO hashtag_performance
                        (hashtag, uses_count, total_engagement, avg_engagement, last_used, performance_score)
                        VALUES (?, 1, ?, ?, ?, ?)
                    ''', (hashtag, engagement, engagement, now, engagement))

    def get_top_hashtags(self, limit=10):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT hashtag, uses_count, avg_engagement, performance_score
                FROM hashtag_performance WHERE uses_count >= 2
                ORDER BY performance_score DESC LIMIT ?
            ''', (limit,))
            return [{'hashtag': r[0], 'uses_count': r[1],
                     'avg_engagement': round(r[2], 2),
                     'performance_score': round(r[3], 2)}
                    for r in c.fetchall()]

    def update_rss_source(self, url, feed_name, feed_type, success=True):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = datetime.now(pytz.UTC)
            c.execute('SELECT success_count, failure_count FROM rss_sources WHERE url = ?', (url,))
            result = c.fetchone()
            if result:
                sc = result[0] + (1 if success else 0)
                fc = result[1] + (0 if success else 1)
                total = sc + fc
                sr = sc / total if total > 0 else 1.0
                c.execute('''
                    UPDATE rss_sources
                    SET last_fetched = ?, success_count = ?, failure_count = ?, success_rate = ?
                    WHERE url = ?
                ''', (now, sc, fc, sr, url))
            else:
                c.execute('''
                    INSERT INTO rss_sources
                    (url, feed_name, feed_type, last_fetched, success_count, failure_count, success_rate)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (url, feed_name, feed_type, now,
                      1 if success else 0, 0 if success else 1,
                      1.0 if success else 0.0))

    def get_daily_post_count(self, date=None, post_type=None):
        if date is None:
            date = datetime.now(pytz.UTC).date()
        with self.get_connection() as conn:
            c = conn.cursor()
            if post_type:
                c.execute('SELECT COUNT(*) FROM posts WHERE DATE(posted_at) = ? AND post_type = ?',
                           (date, post_type))
            else:
                c.execute('SELECT COUNT(*) FROM posts WHERE DATE(posted_at) = ?', (date,))
            return c.fetchone()[0]

    def log_quote_performance(self, quote_category, quote_text, engagement):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = datetime.now(pytz.UTC)
            c.execute('''
                SELECT uses_count, total_engagement
                FROM quote_performance
                WHERE quote_category = ? AND quote_text = ?
            ''', (quote_category, quote_text))
            result = c.fetchone()
            if result:
                new_uses = result[0] + 1
                new_total = result[1] + engagement
                new_avg = new_total / new_uses
                c.execute('''
                    UPDATE quote_performance
                    SET uses_count = ?, total_engagement = ?,
                        avg_engagement = ?, last_used = ?, performance_score = ?
                    WHERE quote_category = ? AND quote_text = ?
                ''', (new_uses, new_total, new_avg, now, new_avg, quote_category, quote_text))
            else:
                c.execute('''
                    INSERT INTO quote_performance
                    (quote_category, quote_text, uses_count, total_engagement,
                     avg_engagement, last_used, performance_score)
                    VALUES (?, ?, 1, ?, ?, ?, ?)
                ''', (quote_category, quote_text, engagement, engagement, now, engagement))

    def get_top_quotes_by_category(self, category, limit=5):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT quote_text, avg_engagement, uses_count
                FROM quote_performance
                WHERE quote_category = ? AND uses_count >= 1
                ORDER BY performance_score DESC LIMIT ?
            ''', (category, limit))
            return [{'quote_text': r[0], 'avg_engagement': round(r[1], 2),
                     'uses_count': r[2]} for r in c.fetchall()]


# ═══════════════════════════════════════════════════════════════════════════
# QUOTE SELECTOR
# ═══════════════════════════════════════════════════════════════════════════

class QuoteSelector:
    def __init__(self, db_manager):
        self.db = db_manager
        self.last_categories = []
        self.max_history = 4

    def select_category(self):
        available = [cat for cat in QUOTE_CATEGORIES if cat not in self.last_categories[-2:]]
        if not available:
            available = QUOTE_CATEGORIES
        selected = random.choice(available)
        self.last_categories.append(selected)
        if len(self.last_categories) > self.max_history:
            self.last_categories.pop(0)
        return selected

    def select_quote(self, category):
        quotes = INSPIRATIONAL_QUOTES.get(category, [])
        if not quotes:
            return None
        top_quotes = self.db.get_top_quotes_by_category(category, limit=3)
        if top_quotes and random.random() < 0.7:
            return random.choice([q['quote_text'] for q in top_quotes])
        return random.choice(quotes)

    def format_quote_tweet(self, quote_text, category):
        category_emojis = {
            'contrarian': '🎯', 'question': '💭',
            'educational': '📚', 'bold': '🔥'
        }
        emoji = category_emojis.get(category, '💡')
        if category == 'question':
            formatted = f"{emoji} {quote_text}"
        else:
            formatted = f'{emoji} "{quote_text}"'
        hashtags = self._get_quote_hashtags(category)
        if len(formatted) + len(" ".join(hashtags)) + 2 <= 280:
            formatted += "\n\n" + " ".join(hashtags)
        else:
            formatted += "\n\n" + " ".join(hashtags[:1])
        return formatted, hashtags

    def _get_quote_hashtags(self, category):
        base_tags = ['#Crypto', '#Bitcoin']
        category_tags = {
            'contrarian': ['#Investing', '#Mindset'],
            'question': ['#CryptoTwitter', '#Discussion'],
            'educational': ['#CryptoEducation', '#Learning'],
            'bold': ['#Motivation', '#Wealth']
        }
        specific = category_tags.get(category, [])
        return [random.choice(base_tags)] + ([random.choice(specific)] if specific else [])


# ═══════════════════════════════════════════════════════════════════════════
# ARSENAL SENTIMENT ANALYSER (NEW)
# ═══════════════════════════════════════════════════════════════════════════

class ArsenalSentimentAnalyser:
    """
    Detects whether an article headline carries negative media/pundit framing
    and selects an appropriate counter-narrative or positive framing strategy.
    """

    def __init__(self):
        self.negative_keywords = [kw.lower() for kw in NEGATIVE_ARSENAL_KEYWORDS]
        self.positive_keywords = [kw.lower() for kw in POSITIVE_ARSENAL_KEYWORDS]

    def score_headline(self, title: str) -> Dict:
        """Returns sentiment scores and recommended content_type."""
        title_lower = title.lower()

        neg_hits = [kw for kw in self.negative_keywords if kw in title_lower]
        pos_hits = [kw for kw in self.positive_keywords if kw in title_lower]

        neg_score = len(neg_hits)
        pos_score = len(pos_hits)

        # Detect which negative narrative is being pushed (if any)
        matched_counter = None
        for narrative_key, counter_text in NARRATIVE_COUNTERS.items():
            if narrative_key in title_lower:
                matched_counter = counter_text
                break

        if neg_score > pos_score:
            sentiment = "negative"
            # For negative headlines: counter-narrative or stat defense
            recommended_type = random.choice(["counter_narrative", "stat_defense"])
        elif pos_score > 0:
            sentiment = "positive"
            recommended_type = random.choice(["fan_pride", "match_hype"])
        else:
            sentiment = "neutral"
            recommended_type = random.choice(["team_news", "analysis"])

        return {
            "sentiment": sentiment,
            "neg_score": neg_score,
            "pos_score": pos_score,
            "neg_keywords": neg_hits,
            "matched_counter": matched_counter,
            "recommended_type": recommended_type
        }

    def is_recent_enough(self, entry, hours: int = 24) -> bool:
        """Check if a feed entry was published within the last N hours."""
        try:
            # feedparser provides published_parsed as a time.struct_time
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                import calendar
                pub_timestamp = calendar.timegm(entry.published_parsed)
                pub_dt = datetime.utcfromtimestamp(pub_timestamp).replace(tzinfo=pytz.UTC)
                cutoff = datetime.now(pytz.UTC) - timedelta(hours=hours)
                return pub_dt >= cutoff
        except Exception:
            pass
        # If we can't parse date, include it (better to include than miss)
        return True


# ═══════════════════════════════════════════════════════════════════════════
# ARSENAL CONTENT GENERATOR (Upgraded v3.0)
# ═══════════════════════════════════════════════════════════════════════════

class ArsenalContentGenerator:
    """
    Generates positive, fan-centric Arsenal FC content.
    Counters negative media/pundit narratives with data, confidence, and fan pride.
    """

    def __init__(self):
        self.sentiment_analyser = ArsenalSentimentAnalyser()

        self.arsenal_hashtags = [
            "#Arsenal", "#AFC", "#Gunners", "#COYG",
            "#ArsenalFC", "#WeAreTheArsenal", "#PremierLeague",
            "#ArsenalTwitter", "#Arteta"
        ]

        # Positive framing prefixes by content type
        self.framing_prefixes = {
            "fan_pride": [
                "⚽ Proud to be a Gooner 🔴⚪",
                "🔴 This is what Arsenal is about:",
                "👑 Arsenal doing what Arsenal do:",
                "🏆 Gunners on the rise:",
                "⚽ The Arsenal project continues:",
            ],
            "counter_narrative": [
                "🔴 The media won't tell you this, but:",
                "📊 Facts over narratives:",
                "🎯 Let's set the record straight:",
                "🔴⚪ Pundits said what? Actually:",
                "💡 The real Arsenal story:",
            ],
            "stat_defense": [
                "📊 The data speaks for itself:",
                "📈 Numbers don't lie:",
                "🔢 Arsenal by the stats:",
                "📊 Forget the noise. Here are the facts:",
                "📈 Statistically speaking:",
            ],
            "match_hype": [
                "⚽ MATCHDAY INCOMING 🔴⚪",
                "🔴 Let's go Gunners!",
                "⚡ Arsenal ready to go:",
                "🏟️ The Emirates is going to be loud:",
                "💪 Arsenal FC:",
            ],
            "team_news": [
                "🔴⚪ Arsenal latest:",
                "📋 Gunners update:",
                "⚽ Arsenal news:",
                "🔴 From the Emirates:",
                "🗞️ Arsenal:",
            ],
            "analysis": [
                "📊 Breaking down Arsenal:",
                "🔍 Tactical insight:",
                "📈 Why Arsenal's approach works:",
                "🔴 Under the microscope:",
                "💡 Arsenal analysis:",
            ]
        }

    def detect_and_counter_narrative(self, title: str) -> Optional[str]:
        """
        If the headline pushes a known negative narrative,
        return a direct counter-statement to weave into the tweet.
        """
        title_lower = title.lower()
        for narrative_key, counter_text in NARRATIVE_COUNTERS.items():
            if narrative_key in title_lower:
                return counter_text
        return None

    def generate_arsenal_tweet_with_ai(self, title: str, url: str,
                                        content_type: str,
                                        sentiment_data: Dict) -> Tuple[str, List[str]]:
        """
        Use GPT to generate a positive, fan-focused Arsenal tweet.
        The prompt is engineered to counter negative framing and inject positivity.
        """

        # Build a prompt tailored to the content type
        counter_note = ""
        if sentiment_data.get("matched_counter"):
            counter_note = f"\nIMPORTANT COUNTER-POINT TO INCLUDE: {sentiment_data['matched_counter']}"

        if content_type == "counter_narrative":
            system_prompt = (
                "You are a passionate, optimistic Arsenal FC fan account on Twitter. "
                "Your job is to counter negative media narratives about Arsenal with "
                "facts, confidence, and fan pride. Write in a punchy, assertive tone. "
                "Never be pessimistic. Always end on a positive, believer note. "
                "Maximum 200 characters for the main tweet body (exclude hashtags/URL)."
            )
            user_prompt = (
                f"The media/pundits are pushing this negative story: '{title}'\n"
                f"Write a confident Arsenal fan counter-narrative tweet that flips this "
                f"to a positive angle. Use stats or facts where possible.{counter_note}\n"
                f"Do NOT include hashtags or URLs - just the tweet body."
            )
        elif content_type == "stat_defense":
            system_prompt = (
                "You are an Arsenal FC analytics account. You defend Arsenal using stats "
                "and data. Write confident, fact-based tweets that silence critics. "
                "Tone: analytical but passionate. Max 200 characters for the main body."
            )
            user_prompt = (
                f"Arsenal news/criticism: '{title}'\n"
                f"Write a stat-based defense of Arsenal, citing real Premier League "
                f"performance metrics (xG, possession, clean sheets, etc.) to counter "
                f"negativity. {counter_note}\n"
                f"Do NOT include hashtags or URLs - just the tweet body."
            )
        elif content_type == "fan_pride":
            system_prompt = (
                "You are a proud, passionate Arsenal FC supporter. You celebrate every "
                "Arsenal achievement and find the positive in every news story. "
                "Write enthusiastic, uplifting fan content. Max 200 characters."
            )
            user_prompt = (
                f"Arsenal story: '{title}'\n"
                f"Write an enthusiastic, positive fan reaction tweet celebrating Arsenal "
                f"and what makes this club special.{counter_note}\n"
                f"Do NOT include hashtags or URLs - just the tweet body."
            )
        elif content_type == "match_hype":
            system_prompt = (
                "You are a hype Arsenal FC account. Build excitement and confidence "
                "around Arsenal matches. Be bold and optimistic. Max 200 characters."
            )
            user_prompt = (
                f"Arsenal news: '{title}'\n"
                f"Write an energetic match hype or pre-match confidence tweet for Arsenal fans.\n"
                f"Do NOT include hashtags or URLs - just the tweet body."
            )
        else:  # team_news or analysis
            system_prompt = (
                "You are a balanced but fan-positive Arsenal FC news account. "
                "Report Arsenal news with enthusiasm and optimism. "
                "Always frame news in a positive light for Arsenal fans. Max 200 characters."
            )
            user_prompt = (
                f"Arsenal news headline: '{title}'\n"
                f"Write a positive, fan-friendly Arsenal tweet summarising this news.{counter_note}\n"
                f"Do NOT include hashtags or URLs - just the tweet body."
            )

        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=100,
                temperature=0.85
            )
            body = response.choices[0].message.content.strip()

            # Strip any accidental hashtags/URLs the model might add
            body = re.sub(r'#\w+', '', body).strip()
            body = re.sub(r'http\S+', '', body).strip()

        except Exception as e:
            logger.warning(f"GPT failed for Arsenal tweet: {e}, using prefix+title fallback")
            prefixes = self.framing_prefixes.get(content_type, self.framing_prefixes["team_news"])
            body = f"{random.choice(prefixes)} {title[:140]}"

        # Select framing prefix (prepend to AI body for strong branding)
        prefix = random.choice(self.framing_prefixes.get(content_type, self.framing_prefixes["team_news"]))

        # Only prepend prefix if it doesn't make content too long
        if len(prefix) + len(body) + 2 <= 220:
            full_body = f"{prefix}\n{body}"
        else:
            full_body = body

        # Select hashtags (3 for Arsenal content for reach)
        selected_hashtags = random.sample(
            self.arsenal_hashtags,
            k=min(3, len(self.arsenal_hashtags))
        )

        return full_body, selected_hashtags

    def generate_arsenal_tweet(self, title: str, url: str,
                                content_type: str = None,
                                entry=None) -> Tuple[str, List[str], str]:
        """
        Main entry point. Analyses sentiment, selects optimal content_type,
        generates positive tweet. Returns (body, hashtags, content_type_used).
        """
        sentiment_data = self.sentiment_analyser.score_headline(title)

        # Auto-select content type based on sentiment if not specified
        if content_type is None:
            content_type = sentiment_data["recommended_type"]

        logger.info(
            f"⚽ Arsenal: sentiment={sentiment_data['sentiment']} | "
            f"neg_kws={sentiment_data['neg_keywords']} | type={content_type}"
        )

        body, hashtags = self.generate_arsenal_tweet_with_ai(
            title, url, content_type, sentiment_data
        )

        return body, hashtags, content_type


# ═══════════════════════════════════════════════════════════════════════════
# DUPLICATE DETECTOR
# ═══════════════════════════════════════════════════════════════════════════

class DuplicateDetector:
    def __init__(self, db_manager, similarity_threshold=SIMILARITY_THRESHOLD):
        self.db = db_manager
        self.similarity_threshold = similarity_threshold

    def get_exact_hash(self, text):
        return hashlib.md5(self._normalize_text(text).encode()).hexdigest()

    def _normalize_text(self, text):
        text = text.lower()
        text = re.sub(r'http\S+|www.\S+', '', text)
        text = re.sub(r'#\w+', '', text)
        text = re.sub(r'@\w+', '', text)
        return ' '.join(text.split()).strip()

    def _tokenize(self, text):
        normalized = self._normalize_text(text)
        cleaned = re.sub(r'[^\w\s]', '', normalized)
        return [w for w in cleaned.split() if len(w) > 2]

    def levenshtein_similarity(self, t1, t2):
        return SequenceMatcher(None, self._normalize_text(t1), self._normalize_text(t2)).ratio()

    def jaccard_similarity(self, t1, t2):
        s1, s2 = set(self._tokenize(t1)), set(self._tokenize(t2))
        if not s1 or not s2:
            return 0.0
        return len(s1 & s2) / len(s1 | s2)

    def cosine_similarity(self, t1, t2):
        w1, w2 = self._tokenize(t1), self._tokenize(t2)
        c1, c2 = Counter(w1), Counter(w2)
        all_words = set(c1) | set(c2)
        if not all_words:
            return 0.0
        v1 = [c1.get(w, 0) for w in all_words]
        v2 = [c2.get(w, 0) for w in all_words]
        dot = sum(a * b for a, b in zip(v1, v2))
        m1 = sum(a * a for a in v1) ** 0.5
        m2 = sum(b * b for b in v2) ** 0.5
        return dot / (m1 * m2) if m1 and m2 else 0.0

    def combined_similarity(self, t1, t2):
        return (self.levenshtein_similarity(t1, t2) * 0.3 +
                self.jaccard_similarity(t1, t2) * 0.35 +
                self.cosine_similarity(t1, t2) * 0.35)

    def is_duplicate(self, text, days=7, post_type=None):
        exact_hash = self.get_exact_hash(text)
        if self.db.is_similar_content(exact_hash, days):
            return True, {'method': 'exact', 'similarity': 1.0}

        recent_posts = self.db.get_recent_posts(limit=50, post_type=post_type)
        cutoff = datetime.now(pytz.UTC) - timedelta(days=days)

        for post in recent_posts:
            try:
                posted_at = datetime.fromisoformat(post['posted_at'].replace('Z', '+00:00'))
            except Exception:
                continue
            if posted_at < cutoff:
                continue
            similarity = self.combined_similarity(text, post.get('tweet_text', ''))
            if similarity >= self.similarity_threshold:
                return True, {'method': 'fuzzy', 'similarity': round(similarity, 3),
                               'tweet_id': post['tweet_id']}

        return False, None


# ═══════════════════════════════════════════════════════════════════════════
# URL MANAGER
# ═══════════════════════════════════════════════════════════════════════════

class URLManager:
    def __init__(self, bitly_token=None, preferred_service='native'):
        self.bitly_token = bitly_token
        self.preferred_service = preferred_service

    def is_valid_url(self, url):
        if not url or not url.startswith(('http://', 'https://')):
            return False
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def shorten_url(self, long_url):
        if not self.is_valid_url(long_url):
            return long_url
        if self.preferred_service == 'native':
            return long_url
        if self.bitly_token:
            try:
                response = requests.post(
                    'https://api-ssl.bitly.com/v4/shorten',
                    headers={'Authorization': f'Bearer {self.bitly_token}',
                             'Content-Type': 'application/json'},
                    json={'long_url': long_url}, timeout=5
                )
                if response.status_code == 200:
                    return response.json().get('link', long_url)
            except Exception:
                pass
        try:
            response = requests.get(
                'https://is.gd/create.php',
                params={'format': 'simple', 'url': long_url}, timeout=5
            )
            if response.status_code == 200 and response.text.startswith('http'):
                return response.text.strip()
        except Exception:
            pass
        return long_url


# ═══════════════════════════════════════════════════════════════════════════
# RSS FEED MONITOR
# ═══════════════════════════════════════════════════════════════════════════

class FeedStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DEAD = "dead"

@dataclass
class FeedHealth:
    url: str
    name: str
    status: FeedStatus
    success_rate: float
    consecutive_failures: int
    last_check: datetime
    error_message: Optional[str]

class RSSFeedMonitor:
    def __init__(self, db_manager):
        self.db = db_manager
        self.feed_health = {}
        self.max_failures = 5

    def validate_feed(self, feed_url, feed_type="crypto"):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(feed_url, headers=headers, timeout=15)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            if not feed.entries:
                return False, "No entries"
            return True, {
                'feed_name': feed.feed.get('title', 'Unknown'),
                'entry_count': len(feed.entries),
                'feed_type': feed_type
            }
        except Exception as e:
            return False, str(e)

    def validate_all_feeds(self, crypto_feeds, arsenal_feeds):
        logger.info(f"Validating {len(crypto_feeds)} crypto + {len(arsenal_feeds)} Arsenal feeds...")
        valid_count = 0

        for feed_url in crypto_feeds:
            is_valid, details = self.validate_feed(feed_url, "crypto")
            self._record_health(feed_url, is_valid, details, "✅ Crypto", "❌ Crypto")
            if is_valid:
                valid_count += 1

        for feed_url in arsenal_feeds:
            is_valid, details = self.validate_feed(feed_url, "arsenal")
            self._record_health(feed_url, is_valid, details, "⚽ Arsenal", "❌ Arsenal")
            if is_valid:
                valid_count += 1

        total = len(crypto_feeds) + len(arsenal_feeds)
        logger.info(f"Validation: {valid_count}/{total} feeds healthy")
        return valid_count

    def _record_health(self, url, is_valid, details, ok_prefix, fail_prefix):
        if is_valid:
            self.feed_health[url] = FeedHealth(
                url=url, name=details['feed_name'],
                status=FeedStatus.HEALTHY, success_rate=1.0,
                consecutive_failures=0,
                last_check=datetime.now(pytz.UTC), error_message=None
            )
            logger.info(f"{ok_prefix}: {details['feed_name']}: {details['entry_count']} entries")
        else:
            self.feed_health[url] = FeedHealth(
                url=url, name='Unknown',
                status=FeedStatus.UNHEALTHY, success_rate=0.0,
                consecutive_failures=1,
                last_check=datetime.now(pytz.UTC), error_message=details
            )
            logger.warning(f"{fail_prefix}: {url}: {details}")

    def should_use_feed(self, feed_url):
        if feed_url not in self.feed_health:
            return True
        return self.feed_health[feed_url].status != FeedStatus.DEAD

    def update_feed_health(self, feed_url, feed_type, success, error=None):
        if feed_url not in self.feed_health:
            return
        health = self.feed_health[feed_url]
        health.last_check = datetime.now(pytz.UTC)
        if success:
            health.consecutive_failures = 0
            health.success_rate = min(1.0, health.success_rate + 0.1)
            health.status = FeedStatus.HEALTHY
            health.error_message = None
            self.db.update_rss_source(feed_url, health.name, feed_type, success=True)
        else:
            health.consecutive_failures += 1
            health.success_rate = max(0.0, health.success_rate - 0.1)
            health.error_message = error
            if health.consecutive_failures >= self.max_failures:
                health.status = FeedStatus.DEAD
            elif health.success_rate < 0.5:
                health.status = FeedStatus.UNHEALTHY
            elif health.success_rate < 0.7:
                health.status = FeedStatus.DEGRADED
            self.db.update_rss_source(feed_url, health.name, feed_type, success=False)


# ═══════════════════════════════════════════════════════════════════════════
# HASHTAG OPTIMIZER
# ═══════════════════════════════════════════════════════════════════════════

class HashtagOptimizer:
    def __init__(self, db_manager):
        self.db = db_manager
        self.hashtag_pools = {
            'primary': ['#Bitcoin', '#BTC', '#Crypto', '#Ethereum', '#ETH'],
            'trending': ['#CryptoNews', '#Blockchain', '#DeFi', '#Web3'],
            'coins': ['#Solana', '#Cardano', '#Polygon', '#BNB', '#XRP']
        }

    def select_hashtags(self, content, strategy='adaptive', content_type='educational'):
        top_hashtags = self.db.get_top_hashtags(limit=10)
        top_tags = [h['hashtag'] for h in top_hashtags] if top_hashtags else []
        if strategy == 'adaptive' and top_tags:
            selected = top_tags[:2]
        elif strategy == 'aggressive':
            selected = random.sample(self.hashtag_pools['primary'], 2)
            selected.append(random.choice(self.hashtag_pools['trending']))
        else:
            selected = [random.choice(self.hashtag_pools['primary'])]
            selected.append(random.choice(self.hashtag_pools['trending']))
        return selected[:2]

    def optimize_tweet_with_hashtags(self, tweet_text, hashtags, max_length=280):
        available_space = max_length - len(tweet_text) - 2
        hashtag_text = " " + " ".join(hashtags)
        if len(hashtag_text) <= available_space:
            return tweet_text + "\n\n" + " ".join(hashtags), hashtags
        for i in range(len(hashtags), 0, -1):
            subset = hashtags[:i]
            hashtag_text = " " + " ".join(subset)
            if len(hashtag_text) <= available_space:
                return tweet_text + "\n\n" + " ".join(subset), subset
        return tweet_text, []


# ═══════════════════════════════════════════════════════════════════════════
# A/B TESTING FRAMEWORK
# ═══════════════════════════════════════════════════════════════════════════

class ABTestingFramework:
    def __init__(self, db_manager):
        self.db = db_manager
        self.experiments = {
            'emoji_placement': ['start', 'end', 'none'],
            'hashtag_count': ['one', 'two'],
            'content_length': ['short', 'medium']
        }

    def select_variant(self, experiment_name):
        if experiment_name in self.experiments:
            return random.choice(self.experiments[experiment_name])
        return None

    def apply_emoji_variant(self, tweet, variant):
        crypto_emojis = ["₿", "📊", "📈", "💎", "🚀"]
        if variant == 'start':
            return f"{random.choice(crypto_emojis)} {tweet}"
        elif variant == 'end':
            return f"{tweet} {random.choice(crypto_emojis)}"
        return tweet

    def generate_test_plan(self, base_content):
        return {exp_name: self.select_variant(exp_name) for exp_name in self.experiments}

    def apply_variants(self, content, test_plan):
        modified = content
        if 'emoji_placement' in test_plan:
            modified = self.apply_emoji_variant(modified, test_plan['emoji_placement'])
        return modified, test_plan


# ═══════════════════════════════════════════════════════════════════════════
# CONTENT GENERATION (Crypto)
# ═══════════════════════════════════════════════════════════════════════════

def generate_crypto_content(title, content_type):
    templates = {
        "question": lambda t: f"What's your take on: {t[:120]}?",
        "hot_take": lambda t: f"Hot take: {t[:150]}",
        "contrarian": lambda t: f"Everyone's wrong about {t[:80]}. Here's why:",
        "educational": lambda t: f"Understanding {t[:100]}:",
        "market_analysis": lambda t: f"Why {t[:120]} matters:",
        "breakdown": lambda t: f"Breaking down {t[:100]}:"
    }
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Create {content_type} crypto content."},
                {"role": "user", "content": f"Based on: {title}\n\nCreate a {content_type} crypto tweet. Under 180 chars."}
            ],
            max_tokens=70, temperature=0.8
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"GPT failed: {e}, using template")
        return templates.get(content_type, templates["educational"])(title)


# ═══════════════════════════════════════════════════════════════════════════
# RSS FEED FETCHING
# ═══════════════════════════════════════════════════════════════════════════

def fetch_articles(feed_monitor, feed_urls, feed_type="crypto",
                   recency_hours=24, sentiment_analyser=None):
    """
    Fetch articles from healthy feeds.
    For Arsenal feeds: prioritise articles from last `recency_hours` hours.
    Returns list sorted by recency (newest first).
    """
    articles = []

    for feed_url in feed_urls:
        if not feed_monitor.should_use_feed(feed_url):
            logger.debug(f"Skipping unhealthy feed: {feed_url}")
            continue
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(feed_url, headers=headers, timeout=15)
            response.raise_for_status()
            feed = feedparser.parse(response.content)

            if feed.entries:
                feed_monitor.update_feed_health(feed_url, feed_type, success=True)

                for entry in feed.entries[:10]:  # check more entries for recency filter
                    # For Arsenal: apply recency filter
                    if feed_type == "arsenal" and sentiment_analyser:
                        is_recent = sentiment_analyser.is_recent_enough(entry, hours=recency_hours)
                    else:
                        is_recent = True

                    # Try to get published date for sorting
                    pub_time = None
                    try:
                        import calendar
                        if hasattr(entry, 'published_parsed') and entry.published_parsed:
                            pub_time = calendar.timegm(entry.published_parsed)
                    except Exception:
                        pass

                    articles.append({
                        'title': entry.get('title', ''),
                        'url': entry.get('link', ''),
                        'source_feed': feed_url,
                        'feed_type': feed_type,
                        'is_recent': is_recent,
                        'pub_time': pub_time,
                        'entry': entry
                    })
            else:
                feed_monitor.update_feed_health(feed_url, feed_type, success=False, error='No entries')

        except Exception as e:
            feed_monitor.update_feed_health(feed_url, feed_type, success=False, error=str(e))
            logger.warning(f"Error fetching {feed_url}: {e}")

    # Sort: recent articles first, then by pub_time descending
    if feed_type == "arsenal":
        recent = [a for a in articles if a['is_recent']]
        older = [a for a in articles if not a['is_recent']]
        recent.sort(key=lambda x: x['pub_time'] or 0, reverse=True)
        older.sort(key=lambda x: x['pub_time'] or 0, reverse=True)
        articles = recent + older
        logger.info(f"⚽ Arsenal: {len(recent)} recent + {len(older)} older articles")
    else:
        logger.info(f"📰 Crypto: {len(articles)} articles fetched")

    return articles


# ═══════════════════════════════════════════════════════════════════════════
# MAIN BOT CLASS
# ═══════════════════════════════════════════════════════════════════════════

class CompleteCryptoArsenalBot:
    """
    Complete bot: crypto news + inspirational quotes + Arsenal FC (positive vibes only).
    """

    def __init__(self):
        logger.info("="*60)
        logger.info("INITIALIZING CRYPTO + ARSENAL BOT v3.0")
        logger.info("="*60)

        self.db = DatabaseManager()
        self.duplicate_detector = DuplicateDetector(self.db)
        self.url_manager = URLManager(bitly_token=BITLY_TOKEN, preferred_service='native')
        self.feed_monitor = RSSFeedMonitor(self.db)
        self.hashtag_optimizer = HashtagOptimizer(self.db)
        self.ab_framework = ABTestingFramework(self.db)
        self.quote_selector = QuoteSelector(self.db)
        self.arsenal_generator = ArsenalContentGenerator()
        self.sentiment_analyser = ArsenalSentimentAnalyser()

        logger.info("\nValidating RSS feeds...")
        self.feed_monitor.validate_all_feeds(CRYPTO_RSS_FEEDS, ARSENAL_RSS_FEEDS)

        logger.info("\n✅ All systems initialized")
        logger.info(f"📰 Crypto news: {DAILY_NEWS_LIMIT}/day")
        logger.info(f"💬 Quotes: {DAILY_QUOTE_LIMIT}/day")
        logger.info(f"⚽ Arsenal: {DAILY_ARSENAL_LIMIT}/day (with positivity engine)")
        logger.info(f"📊 Total: {DAILY_TOTAL_LIMIT}/day")
        logger.info("="*60 + "\n")

    def should_post_content(self, content, url, post_type=None):
        if url and self.db.has_been_posted(url):
            logger.info("❌ URL already posted")
            return False
        is_dup, match_info = self.duplicate_detector.is_duplicate(content, days=7, post_type=post_type)
        if is_dup:
            logger.info(f"❌ Duplicate: {match_info['method']} ({match_info.get('similarity', 1.0):.2%})")
            return False
        return True

    def generate_news_tweet(self, article_title, article_url, content_type):
        base_content = generate_crypto_content(article_title, content_type)
        test_plan = self.ab_framework.generate_test_plan(base_content)
        modified_content, variants = self.ab_framework.apply_variants(base_content, test_plan)

        if not self.should_post_content(modified_content, article_url, "news"):
            return None

        final_url = self.url_manager.shorten_url(article_url)
        hashtags = self.hashtag_optimizer.select_hashtags(
            modified_content, strategy='adaptive', content_type=content_type)
        tweet_with_url = f"{modified_content}\n\n{final_url}"
        final_tweet, included_hashtags = self.hashtag_optimizer.optimize_tweet_with_hashtags(
            tweet_with_url, hashtags)

        return {
            'post_type': 'news', 'tweet_text': final_tweet,
            'content_hash': self.duplicate_detector.get_exact_hash(modified_content),
            'url': article_url, 'content_type': content_type,
            'hashtags': included_hashtags, 'test_plan': test_plan, 'quote_category': None
        }

    def generate_quote_tweet(self):
        category = self.quote_selector.select_category()
        quote_text = self.quote_selector.select_quote(category)
        if not quote_text:
            logger.warning("No quote available")
            return None
        if not self.should_post_content(quote_text, None, "quote"):
            quote_text = random.choice(INSPIRATIONAL_QUOTES[category])
            if not self.should_post_content(quote_text, None, "quote"):
                return None
        final_tweet, hashtags = self.quote_selector.format_quote_tweet(quote_text, category)
        return {
            'post_type': 'quote', 'tweet_text': final_tweet,
            'content_hash': self.duplicate_detector.get_exact_hash(quote_text),
            'url': None, 'content_type': 'inspirational',
            'hashtags': hashtags, 'test_plan': {}, 'quote_category': category
        }

    def generate_arsenal_tweet(self, article_title, article_url,
                                content_type=None, entry=None):
        """
        Generate an Arsenal tweet with positivity engine.
        Content type is auto-determined by sentiment if not specified.
        """
        body, hashtags, used_content_type = self.arsenal_generator.generate_arsenal_tweet(
            article_title, article_url, content_type, entry
        )

        if not self.should_post_content(body, article_url, "arsenal"):
            return None

        final_url = self.url_manager.shorten_url(article_url)
        tweet_with_url = f"{body}\n\n{final_url}"
        final_tweet, included_hashtags = self.hashtag_optimizer.optimize_tweet_with_hashtags(
            tweet_with_url, hashtags, max_length=280
        )

        return {
            'post_type': 'arsenal', 'tweet_text': final_tweet,
            'content_hash': self.duplicate_detector.get_exact_hash(body),
            'url': article_url, 'content_type': used_content_type,
            'hashtags': included_hashtags, 'test_plan': {}, 'quote_category': None
        }

    def post_tweet(self, tweet_data):
        global last_post_time, daily_news_posts, daily_quote_posts, daily_arsenal_posts

        try:
            response = twitter_client.create_tweet(text=tweet_data['tweet_text'])
            tweet_id = response.data['id']

            self.db.log_post(
                tweet_id=tweet_id, post_type=tweet_data['post_type'],
                url=tweet_data['url'], content_hash=tweet_data['content_hash'],
                tweet_text=tweet_data['tweet_text'], content_type=tweet_data['content_type'],
                hashtags=tweet_data['hashtags'], quote_category=tweet_data.get('quote_category')
            )
            self.db.log_content_hash(tweet_data['content_hash'], tweet_id)

            for exp_name, variant in tweet_data.get('test_plan', {}).items():
                self.db.log_ab_test(exp_name, variant, tweet_id)

            last_post_time = datetime.now(pytz.UTC)

            if tweet_data['post_type'] == 'news':
                daily_news_posts += 1
            elif tweet_data['post_type'] == 'quote':
                daily_quote_posts += 1
            elif tweet_data['post_type'] == 'arsenal':
                daily_arsenal_posts += 1

            post_emoji = {'news': '📰', 'quote': '💬', 'arsenal': '⚽'}.get(
                tweet_data['post_type'], '📝')

            logger.info("="*60)
            logger.info(f"✅ {post_emoji} {tweet_data['post_type'].upper()} POSTED!")
            logger.info(f"Tweet ID: {tweet_id}")
            logger.info(f"URL: https://twitter.com/user/status/{tweet_id}")
            logger.info(f"Content Type: {tweet_data['content_type']}")
            if tweet_data.get('quote_category'):
                logger.info(f"Quote Category: {tweet_data['quote_category']}")
            logger.info(f"Hashtags: {tweet_data['hashtags']}")
            logger.info(
                f"Daily: News {daily_news_posts}/{DAILY_NEWS_LIMIT} | "
                f"Quotes {daily_quote_posts}/{DAILY_QUOTE_LIMIT} | "
                f"Arsenal {daily_arsenal_posts}/{DAILY_ARSENAL_LIMIT}"
            )
            logger.info(f"Tweet preview:\n{tweet_data['tweet_text'][:200]}")
            logger.info("="*60)
            return True

        except Exception as e:
            logger.error(f"❌ Error posting tweet: {e}")
            return False

    def run_posting_cycle(self, post_type):
        global daily_news_posts, daily_quote_posts, daily_arsenal_posts

        if post_type == 'news' and daily_news_posts >= DAILY_NEWS_LIMIT:
            logger.info(f"News limit reached ({daily_news_posts}/{DAILY_NEWS_LIMIT})")
            return False
        if post_type == 'quote' and daily_quote_posts >= DAILY_QUOTE_LIMIT:
            logger.info(f"Quote limit reached ({daily_quote_posts}/{DAILY_QUOTE_LIMIT})")
            return False
        if post_type == 'arsenal' and daily_arsenal_posts >= DAILY_ARSENAL_LIMIT:
            logger.info(f"Arsenal limit reached ({daily_arsenal_posts}/{DAILY_ARSENAL_LIMIT})")
            return False
        if not can_post_now():
            return False

        if post_type == 'quote':
            logger.info("Generating quote post...")
            tweet_data = self.generate_quote_tweet()
            return self.post_tweet(tweet_data) if tweet_data else False

        elif post_type == 'arsenal':
            logger.info("⚽ Generating Arsenal post (positivity engine active)...")
            articles = fetch_articles(
                self.feed_monitor, ARSENAL_RSS_FEEDS, "arsenal",
                recency_hours=24, sentiment_analyser=self.sentiment_analyser
            )
            if not articles:
                logger.info("No Arsenal articles available")
                return False

            for article in articles:
                tweet_data = self.generate_arsenal_tweet(
                    article['title'], article['url'],
                    content_type=None,  # let sentiment engine decide
                    entry=article.get('entry')
                )
                if tweet_data:
                    return self.post_tweet(tweet_data)

            logger.info("No suitable Arsenal articles found")
            return False

        elif post_type == 'news':
            content_type = random.choice(CRYPTO_CONTENT_TYPES)
            logger.info(f"Generating crypto news post (type: {content_type})...")
            articles = fetch_articles(self.feed_monitor, CRYPTO_RSS_FEEDS, "crypto")
            if not articles:
                logger.info("No crypto articles available")
                return False

            for article in articles:
                tweet_data = self.generate_news_tweet(
                    article['title'], article['url'], content_type)
                if tweet_data:
                    return self.post_tweet(tweet_data)

            logger.info("No suitable crypto articles found")
            return False

        return False


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def reset_daily_counter():
    global daily_news_posts, daily_quote_posts, daily_arsenal_posts, last_reset_date
    current_date = datetime.now(pytz.UTC).date()
    if current_date > last_reset_date:
        daily_news_posts = 0
        daily_quote_posts = 0
        daily_arsenal_posts = 0
        last_reset_date = current_date
        logger.info("📅 Daily counters reset")

def can_post_now():
    global last_post_time
    if last_post_time is None:
        return True
    return (datetime.now(pytz.UTC) - last_post_time).total_seconds() >= (POST_INTERVAL_MINUTES * 60)

def get_current_post_type():
    current_time = datetime.now(pytz.UTC).strftime("%H:%M")
    for scheduled_time, post_type in POSTING_SCHEDULE:
        if scheduled_time == current_time:
            return post_type
    return None


# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULER
# ═══════════════════════════════════════════════════════════════════════════

def start_scheduler(bot):
    logger.info("="*60)
    logger.info("🚀 CRYPTO + ARSENAL BOT v3.0 - SCHEDULER STARTING")
    logger.info("="*60)
    logger.info(f"📰 Crypto News: {DAILY_NEWS_LIMIT}/day")
    logger.info(f"💬 Quotes: {DAILY_QUOTE_LIMIT}/day")
    logger.info(f"⚽ Arsenal FC: {DAILY_ARSENAL_LIMIT}/day (positivity engine ON)")
    logger.info(f"📊 Total: {DAILY_TOTAL_LIMIT}/day across {len(POSTING_SCHEDULE)} time slots")
    logger.info("="*60 + "\n")

    last_checked_minute = None
    last_heartbeat = datetime.now(pytz.UTC)

    while True:
        try:
            current_time = datetime.now(pytz.UTC)
            current_minute = current_time.strftime("%H:%M")

            if (current_time - last_heartbeat).total_seconds() >= 300:
                logger.info(
                    f"💓 Bot running | {current_minute} UTC | "
                    f"News: {daily_news_posts}/{DAILY_NEWS_LIMIT} | "
                    f"Quotes: {daily_quote_posts}/{DAILY_QUOTE_LIMIT} | "
                    f"Arsenal: {daily_arsenal_posts}/{DAILY_ARSENAL_LIMIT}"
                )
                last_heartbeat = current_time

            if current_minute != last_checked_minute:
                post_type = get_current_post_type()
                if post_type:
                    post_emoji = {'news': '📰', 'quote': '💬', 'arsenal': '⚽'}.get(post_type, '📝')
                    logger.info(f"\n⏰ Posting time: {current_minute} UTC ({post_emoji} {post_type})")
                    reset_daily_counter()
                    bot.run_posting_cycle(post_type)
                last_checked_minute = current_minute

            time.sleep(30)

        except KeyboardInterrupt:
            logger.info("\n👋 Shutting down...")
            logger.info(f"Final stats: News {daily_news_posts} | Quotes {daily_quote_posts} | Arsenal {daily_arsenal_posts}")
            break
        except Exception as e:
            logger.error(f"❌ Scheduler error: {e}")
            time.sleep(60)


# ═══════════════════════════════════════════════════════════════════════════
# HEALTH CHECK SERVER
# ═══════════════════════════════════════════════════════════════════════════

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        status = (
            f"Crypto+Arsenal Bot v3.0: RUNNING\n"
            f"Time: {datetime.now(pytz.UTC)}\n"
            f"News: {daily_news_posts}/{DAILY_NEWS_LIMIT}\n"
            f"Quotes: {daily_quote_posts}/{DAILY_QUOTE_LIMIT}\n"
            f"Arsenal: {daily_arsenal_posts}/{DAILY_ARSENAL_LIMIT}\n"
            f"Arsenal Positivity Engine: ACTIVE\n"
        )
        self.wfile.write(status.encode())

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

    def log_message(self, format, *args):
        pass

def start_health_server():
    port = int(os.environ.get('PORT', 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        logger.info(f"Health server on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Health server error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        logger.info("Testing Twitter authentication...")
        me = twitter_api.verify_credentials()
        logger.info(f"✅ Authenticated as @{me.screen_name}")

        bot = CompleteCryptoArsenalBot()

        health_thread = threading.Thread(target=start_health_server, daemon=True)
        health_thread.start()

        start_scheduler(bot)

    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
        exit(0)
    except Exception as e:
        logger.error(f"\n❌ CRITICAL ERROR: {e}")
        exit(1)

