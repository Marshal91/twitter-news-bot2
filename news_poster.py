"""
═══════════════════════════════════════════════════════════════════════════════
    COMPLETE CRYPTO + ARSENAL TWITTER BOT
    10 Crypto News + 4 Quotes + 1 Arsenal FC = 15 Posts Per Day
═══════════════════════════════════════════════════════════════════════════════

FEATURES:
✅ 10 Crypto News Posts (from RSS feeds)
✅ 4 Inspirational Quote Posts (Contrarian, Question, Educational, Bold)
✅ 1 Arsenal FC Post (from official Arsenal feeds)
✅ All Previous Enhancements (Database, A/B Testing, etc.)

POST BREAKDOWN:
- Crypto: News, analysis, and market updates
- Quotes: Inspirational content for engagement
- Arsenal: Match updates, news, and club content

VERSION: 2.2 - Arsenal FC Integration
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
DAILY_NEWS_LIMIT = 10        # Crypto news
DAILY_QUOTE_LIMIT = 4        # Inspirational quotes
DAILY_ARSENAL_LIMIT = 1      # Arsenal FC content
DAILY_TOTAL_LIMIT = 15       # Total posts per day
POST_INTERVAL_MINUTES = 90

# Tracking
last_post_time = None
daily_news_posts = 0
daily_quote_posts = 0
daily_arsenal_posts = 0
last_reset_date = datetime.now(pytz.UTC).date()

# Posting Schedule with Post Types
# Format: (time, post_type)
POSTING_SCHEDULE = [
    ("03:00", "news"),      # 1. Crypto News
    ("05:00", "quote"),     # 2. Quote
    ("07:00", "news"),      # 3. Crypto News
    ("09:00", "arsenal"),   # 4. Arsenal FC ⚽
    ("11:00", "quote"),     # 5. Quote
    ("13:00", "news"),      # 6. Crypto News
    ("15:00", "news"),      # 7. Crypto News
    ("17:00", "quote"),     # 8. Quote
    ("19:00", "news"),      # 9. Crypto News
    ("20:00", "news"),      # 10. Crypto News
    ("21:00", "news"),      # 11. Crypto News
    ("22:00", "quote"),     # 12. Quote
    ("23:00", "news"),      # 13. Crypto News
    ("01:00", "news"),      # 14. Crypto News
    ("02:00", "news")       # 15. Crypto News
]

# Content Types
CRYPTO_CONTENT_TYPES = [
    "educational", "market_analysis", "contrarian",
    "question", "hot_take", "breakdown"
]

ARSENAL_CONTENT_TYPES = [
    "match_update", "team_news", "fan_reaction", "analysis"
]

# Quote Categories
QUOTE_CATEGORIES = ["contrarian", "question", "educational", "bold"]

# RSS Feeds
CRYPTO_RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://crypto.news/feed/",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/.rss/full/"
]

# Arsenal FC RSS Feeds
ARSENAL_RSS_FEEDS = [
    "https://www.arsenal.com/rss.xml",                          # Official Arsenal
    "https://www.skysports.com/rss/12040",                      # Sky Sports Arsenal
    "https://www.espn.com/espn/rss/soccer/team/_/id/359",      # ESPN Arsenal
    "https://theathletic.com/team/arsenal/feed/",               # The Athletic (if accessible)
]

# Duplicate Detection
SIMILARITY_THRESHOLD = 0.75

# ═══════════════════════════════════════════════════════════════════════════
# INSPIRATIONAL QUOTES DATABASE
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
# DATABASE MANAGER (Enhanced with Arsenal Tracking)
# ═══════════════════════════════════════════════════════════════════════════

class DatabaseManager:
    """Manages all database operations"""
    
    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
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
        """Initialize all database tables"""
        with self.get_connection() as conn:
            c = conn.cursor()
            
            # Posts table (includes all post types)
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
            
            # Content hashes table
            c.execute('''
                CREATE TABLE IF NOT EXISTS content_hashes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_hash TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    tweet_id TEXT,
                    FOREIGN KEY (tweet_id) REFERENCES posts(tweet_id)
                )
            ''')
            
            # A/B Testing table
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
            
            # Hashtag performance table
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
            
            # Quote performance table
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
            
            # RSS sources table (for both crypto and Arsenal)
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
            
            # Create indexes
            c.execute('CREATE INDEX IF NOT EXISTS idx_posts_posted_at ON posts(posted_at)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_posts_content_type ON posts(content_type)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_posts_post_type ON posts(post_type)')
            
            logger.info("✅ Database initialized")
    
    def log_post(self, tweet_id, post_type, url, content_hash, tweet_text, 
                 content_type, hashtags, quote_category=None):
        """Log a new post"""
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
        """Check if URL has been posted"""
        if not url:
            return False
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM posts WHERE url = ?', (url,))
            return c.fetchone()[0] > 0
    
    def is_similar_content(self, content_hash, days=7):
        """Check if similar content was posted recently"""
        with self.get_connection() as conn:
            c = conn.cursor()
            cutoff = datetime.now(pytz.UTC) - timedelta(days=days)
            c.execute('''
                SELECT COUNT(*) FROM content_hashes 
                WHERE content_hash = ? AND created_at > ?
            ''', (content_hash, cutoff))
            return c.fetchone()[0] > 0
    
    def log_content_hash(self, content_hash, tweet_id=None):
        """Log content hash"""
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
        """Get recent posts, optionally filtered by type"""
        with self.get_connection() as conn:
            c = conn.cursor()
            
            if post_type:
                c.execute('''
                    SELECT tweet_id, tweet_text, content_type, post_type, posted_at,
                           likes, retweets, replies, engagement_rate
                    FROM posts
                    WHERE post_type = ?
                    ORDER BY posted_at DESC
                    LIMIT ?
                ''', (post_type, limit))
            else:
                c.execute('''
                    SELECT tweet_id, tweet_text, content_type, post_type, posted_at,
                           likes, retweets, replies, engagement_rate
                    FROM posts
                    ORDER BY posted_at DESC
                    LIMIT ?
                ''', (limit,))
            
            results = []
            for row in c.fetchall():
                results.append({
                    'tweet_id': row[0],
                    'tweet_text': row[1],
                    'content_type': row[2],
                    'post_type': row[3],
                    'posted_at': row[4],
                    'likes': row[5],
                    'retweets': row[6],
                    'replies': row[7],
                    'engagement_rate': row[8]
                })
            return results
    
    def get_content_type_performance(self, days=30):
        """Get performance by content type"""
        with self.get_connection() as conn:
            c = conn.cursor()
            cutoff = datetime.now(pytz.UTC) - timedelta(days=days)
            
            c.execute('''
                SELECT 
                    content_type,
                    post_type,
                    COUNT(*) as post_count,
                    AVG(likes) as avg_likes,
                    AVG(retweets) as avg_retweets,
                    AVG(engagement_rate) as avg_engagement_rate
                FROM posts
                WHERE posted_at > ? AND engagement_rate > 0
                GROUP BY content_type, post_type
                ORDER BY avg_engagement_rate DESC
            ''', (cutoff,))
            
            results = []
            for row in c.fetchall():
                results.append({
                    'content_type': row[0],
                    'post_type': row[1],
                    'post_count': row[2],
                    'avg_likes': round(row[3], 2),
                    'avg_retweets': round(row[4], 2),
                    'avg_engagement_rate': round(row[5], 2)
                })
            return results
    
    def log_ab_test(self, experiment_name, variant, tweet_id, is_control=False):
        """Log A/B test variant"""
        with self.get_connection() as conn:
            c = conn.cursor()
            now = datetime.now(pytz.UTC)
            
            c.execute('''
                INSERT INTO ab_tests (experiment_name, variant, tweet_id, posted_at, is_control)
                VALUES (?, ?, ?, ?, ?)
            ''', (experiment_name, variant, tweet_id, now, is_control))
    
    def update_hashtag_performance(self, hashtags, engagement):
        """Update hashtag performance"""
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
        """Get top performing hashtags"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT hashtag, uses_count, avg_engagement, performance_score
                FROM hashtag_performance
                WHERE uses_count >= 2
                ORDER BY performance_score DESC
                LIMIT ?
            ''', (limit,))
            
            results = []
            for row in c.fetchall():
                results.append({
                    'hashtag': row[0],
                    'uses_count': row[1],
                    'avg_engagement': round(row[2], 2),
                    'performance_score': round(row[3], 2)
                })
            return results
    
    def update_rss_source(self, url, feed_name, feed_type, success=True):
        """Update RSS source statistics"""
        with self.get_connection() as conn:
            c = conn.cursor()
            now = datetime.now(pytz.UTC)
            
            c.execute('SELECT success_count, failure_count FROM rss_sources WHERE url = ?', (url,))
            result = c.fetchone()
            
            if result:
                success_count = result[0] + (1 if success else 0)
                failure_count = result[1] + (0 if success else 1)
                total = success_count + failure_count
                success_rate = success_count / total if total > 0 else 1.0
                
                c.execute('''
                    UPDATE rss_sources 
                    SET last_fetched = ?, success_count = ?, failure_count = ?, success_rate = ?
                    WHERE url = ?
                ''', (now, success_count, failure_count, success_rate, url))
            else:
                c.execute('''
                    INSERT INTO rss_sources (url, feed_name, feed_type, last_fetched, 
                                           success_count, failure_count, success_rate)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (url, feed_name, feed_type, now, 
                     1 if success else 0, 
                     0 if success else 1, 
                     1.0 if success else 0.0))
    
    def get_daily_post_count(self, date=None, post_type=None):
        """Get number of posts for a date, optionally filtered by type"""
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
        """Track quote performance"""
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
        """Get top performing quotes for a category"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT quote_text, avg_engagement, uses_count
                FROM quote_performance
                WHERE quote_category = ? AND uses_count >= 1
                ORDER BY performance_score DESC
                LIMIT ?
            ''', (category, limit))
            
            results = []
            for row in c.fetchall():
                results.append({
                    'quote_text': row[0],
                    'avg_engagement': round(row[1], 2),
                    'uses_count': row[2]
                })
            return results

# ═══════════════════════════════════════════════════════════════════════════
# QUOTE SELECTOR
# ═══════════════════════════════════════════════════════════════════════════

class QuoteSelector:
    """Manages quote selection with rotation and performance tracking"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.last_categories = []
        self.max_history = 4
    
    def select_category(self):
        """Select quote category with smart rotation"""
        available = [cat for cat in QUOTE_CATEGORIES if cat not in self.last_categories[-2:]]
        
        if not available:
            available = QUOTE_CATEGORIES
        
        selected = random.choice(available)
        
        self.last_categories.append(selected)
        if len(self.last_categories) > self.max_history:
            self.last_categories.pop(0)
        
        return selected
    
    def select_quote(self, category):
        """Select a specific quote from category"""
        quotes = INSPIRATIONAL_QUOTES.get(category, [])
        
        if not quotes:
            return None
        
        top_quotes = self.db.get_top_quotes_by_category(category, limit=3)
        
        if top_quotes and random.random() < 0.7:
            return random.choice([q['quote_text'] for q in top_quotes])
        else:
            return random.choice(quotes)
    
    def format_quote_tweet(self, quote_text, category):
        """Format quote into tweet with appropriate styling"""
        
        category_emojis = {
            'contrarian': '🎯',
            'question': '💭',
            'educational': '📚',
            'bold': '🔥'
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
        """Get appropriate hashtags for quote category"""
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
# ARSENAL CONTENT GENERATOR (NEW)
# ═══════════════════════════════════════════════════════════════════════════

class ArsenalContentGenerator:
    """Generates engaging Arsenal FC content"""
    
    def __init__(self):
        self.arsenal_emojis = ["⚽", "🔴", "⚪", "🏆", "👑", "🔵"]
        self.arsenal_hashtags = [
            "#Arsenal", "#AFC", "#Gunners", "#COYG", 
            "#ArsenalFC", "#WeAreTheArsenal", "#PremierLeague"
        ]
    
    def generate_arsenal_tweet(self, title, url, content_type="team_news"):
        """Generate Arsenal tweet content"""
        
        # Shorten title if too long
        if len(title) > 150:
            title = title[:147] + "..."
        
        # Content type specific formatting
        if content_type == "match_update":
            templates = [
                f"⚽ {title}",
                f"🔴 Match Update: {title}",
                f"👑 {title}"
            ]
        elif content_type == "team_news":
            templates = [
                f"🔴⚪ {title}",
                f"Arsenal News: {title}",
                f"⚽ {title}"
            ]
        elif content_type == "analysis":
            templates = [
                f"📊 {title}",
                f"⚽ Analysis: {title}",
                f"🔴 {title}"
            ]
        else:  # fan_reaction or general
            templates = [
                f"⚽ {title}",
                f"🔴⚪ {title}",
                f"Gunners: {title}"
            ]
        
        base_content = random.choice(templates)
        
        # Select hashtags (2-3 for Arsenal content)
        selected_hashtags = random.sample(self.arsenal_hashtags, k=min(2, len(self.arsenal_hashtags)))
        
        return base_content, selected_hashtags

# ═══════════════════════════════════════════════════════════════════════════
# REST OF COMPONENTS (Duplicate Detector, URL Manager, etc.)
# Same as before...
# ═══════════════════════════════════════════════════════════════════════════

class DuplicateDetector:
    """Advanced duplicate detection using fuzzy matching"""
    
    def __init__(self, db_manager, similarity_threshold=SIMILARITY_THRESHOLD):
        self.db = db_manager
        self.similarity_threshold = similarity_threshold
    
    def get_exact_hash(self, text):
        normalized = self._normalize_text(text)
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def _normalize_text(self, text):
        text = text.lower()
        text = re.sub(r'http\S+|www.\S+', '', text)
        text = re.sub(r'#\w+', '', text)
        text = re.sub(r'@\w+', '', text)
        text = ' '.join(text.split())
        return text.strip()
    
    def _tokenize(self, text):
        normalized = self._normalize_text(text)
        cleaned = re.sub(r'[^\w\s]', '', normalized)
        words = cleaned.split()
        return [w for w in words if len(w) > 2]
    
    def levenshtein_similarity(self, text1, text2):
        text1_norm = self._normalize_text(text1)
        text2_norm = self._normalize_text(text2)
        return SequenceMatcher(None, text1_norm, text2_norm).ratio()
    
    def jaccard_similarity(self, text1, text2):
        words1 = set(self._tokenize(text1))
        words2 = set(self._tokenize(text2))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def cosine_similarity(self, text1, text2):
        words1 = self._tokenize(text1)
        words2 = self._tokenize(text2)
        
        counter1 = Counter(words1)
        counter2 = Counter(words2)
        
        all_words = set(counter1.keys()).union(set(counter2.keys()))
        
        if not all_words:
            return 0.0
        
        vec1 = [counter1.get(word, 0) for word in all_words]
        vec2 = [counter2.get(word, 0) for word in all_words]
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def combined_similarity(self, text1, text2):
        lev = self.levenshtein_similarity(text1, text2)
        jac = self.jaccard_similarity(text1, text2)
        cos = self.cosine_similarity(text1, text2)
        return (lev * 0.3) + (jac * 0.35) + (cos * 0.35)
    
    def is_duplicate(self, text, days=7, post_type=None):
        """Check for duplicates, optionally filtering by post type"""
        exact_hash = self.get_exact_hash(text)
        if self.db.is_similar_content(exact_hash, days):
            return True, {'method': 'exact', 'similarity': 1.0}
        
        recent_posts = self.db.get_recent_posts(limit=50, post_type=post_type)
        cutoff = datetime.now(pytz.UTC) - timedelta(days=days)
        
        for post in recent_posts:
            try:
                posted_at = datetime.fromisoformat(post['posted_at'].replace('Z', '+00:00'))
            except:
                continue
                
            if posted_at < cutoff:
                continue
            
            similarity = self.combined_similarity(text, post.get('tweet_text', ''))
            
            if similarity >= self.similarity_threshold:
                return True, {
                    'method': 'fuzzy',
                    'similarity': round(similarity, 3),
                    'tweet_id': post['tweet_id']
                }
        
        return False, None

class URLManager:
    """Manages URL shortening"""
    
    def __init__(self, bitly_token=None, preferred_service='native'):
        self.bitly_token = bitly_token
        self.preferred_service = preferred_service
    
    def is_valid_url(self, url):
        if not url or not url.startswith(('http://', 'https://')):
            return False
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    def sanitize_url(self, url):
        return url.strip()
    
    def shorten_url(self, long_url):
        if not self.is_valid_url(long_url):
            return long_url
        
        if self.preferred_service == 'native':
            return long_url
        
        if self.bitly_token:
            try:
                response = requests.post(
                    'https://api-ssl.bitly.com/v4/shorten',
                    headers={
                        'Authorization': f'Bearer {self.bitly_token}',
                        'Content-Type': 'application/json'
                    },
                    json={'long_url': long_url},
                    timeout=5
                )
                if response.status_code == 200:
                    return response.json().get('link', long_url)
            except:
                pass
        
        try:
            response = requests.get(
                'https://is.gd/create.php',
                params={'format': 'simple', 'url': long_url},
                timeout=5
            )
            if response.status_code == 200 and response.text.startswith('http'):
                return response.text.strip()
        except:
            pass
        
        return long_url

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
    """Monitor RSS feed health"""
    
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
        
        # Validate crypto feeds
        for feed_url in crypto_feeds:
            is_valid, details = self.validate_feed(feed_url, "crypto")
            
            if is_valid:
                valid_count += 1
                self.feed_health[feed_url] = FeedHealth(
                    url=feed_url,
                    name=details['feed_name'],
                    status=FeedStatus.HEALTHY,
                    success_rate=1.0,
                    consecutive_failures=0,
                    last_check=datetime.now(pytz.UTC),
                    error_message=None
                )
                logger.info(f"✅ Crypto: {details['feed_name']}: {details['entry_count']} entries")
            else:
                self.feed_health[feed_url] = FeedHealth(
                    url=feed_url,
                    name='Unknown',
                    status=FeedStatus.UNHEALTHY,
                    success_rate=0.0,
                    consecutive_failures=1,
                    last_check=datetime.now(pytz.UTC),
                    error_message=details
                )
                logger.warning(f"❌ Crypto: {feed_url}: {details}")
        
        # Validate Arsenal feeds
        for feed_url in arsenal_feeds:
            is_valid, details = self.validate_feed(feed_url, "arsenal")
            
            if is_valid:
                valid_count += 1
                self.feed_health[feed_url] = FeedHealth(
                    url=feed_url,
                    name=details['feed_name'],
                    status=FeedStatus.HEALTHY,
                    success_rate=1.0,
                    consecutive_failures=0,
                    last_check=datetime.now(pytz.UTC),
                    error_message=None
                )
                logger.info(f"⚽ Arsenal: {details['feed_name']}: {details['entry_count']} entries")
            else:
                self.feed_health[feed_url] = FeedHealth(
                    url=feed_url,
                    name='Unknown',
                    status=FeedStatus.UNHEALTHY,
                    success_rate=0.0,
                    consecutive_failures=1,
                    last_check=datetime.now(pytz.UTC),
                    error_message=details
                )
                logger.warning(f"❌ Arsenal: {feed_url}: {details}")
        
        total_feeds = len(crypto_feeds) + len(arsenal_feeds)
        logger.info(f"Validation complete: {valid_count}/{total_feeds} healthy")
        return valid_count
    
    def should_use_feed(self, feed_url):
        if feed_url not in self.feed_health:
            return True
        health = self.feed_health[feed_url]
        return health.status != FeedStatus.DEAD
    
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
            
            # Update database
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
            
            # Update database
            self.db.update_rss_source(feed_url, health.name, feed_type, success=False)
    
    def get_healthy_feeds(self, feed_type=None):
        """Get healthy feeds, optionally filtered by type"""
        healthy = [url for url, health in self.feed_health.items() 
                   if health.status in [FeedStatus.HEALTHY, FeedStatus.DEGRADED]]
        
        if not feed_type:
            return healthy
        
        # Filter by feed type if specified
        filtered = []
        for url in healthy:
            # Check database for feed type
            # For simplicity, we'll return all healthy feeds if type not in URL
            if feed_type == "arsenal" and ("arsenal" in url.lower() or "skysports" in url.lower()):
                filtered.append(url)
            elif feed_type == "crypto" and feed_type != "arsenal":
                if not ("arsenal" in url.lower() or "skysports" in url.lower()):
                    filtered.append(url)
        
        return filtered if filtered else healthy

class HashtagOptimizer:
    """Intelligent hashtag selection"""
    
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

class ABTestingFramework:
    """Simple A/B testing"""
    
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
        plan = {}
        for exp_name in self.experiments.keys():
            plan[exp_name] = self.select_variant(exp_name)
        return plan
    
    def apply_variants(self, content, test_plan):
        modified = content
        
        if 'emoji_placement' in test_plan:
            modified = self.apply_emoji_variant(modified, test_plan['emoji_placement'])
        
        return modified, test_plan

# ═══════════════════════════════════════════════════════════════════════════
# CONTENT GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_crypto_content(title, content_type):
    """Generate content using GPT"""
    templates = {
        "question": lambda t: f"What's your take on: {t[:120]}?",
        "hot_take": lambda t: f"Hot take: {t[:150]}",
        "contrarian": lambda t: f"Everyone's wrong about {t[:80]}. Here's why:",
        "educational": lambda t: f"Understanding {t[:100]}:",
        "market_analysis": lambda t: f"Why {t[:120]} matters:",
        "breakdown": lambda t: f"Breaking down {t[:100]}:"
    }
    
    try:
        prompt = f"Based on: {title}\n\nCreate a {content_type} crypto tweet. Under 180 chars."
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Create {content_type} crypto content."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=70,
            temperature=0.8
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"GPT failed: {e}, using template")
        template = templates.get(content_type, templates["educational"])
        return template(title)

# ═══════════════════════════════════════════════════════════════════════════
# RSS FEED FETCHING
# ═══════════════════════════════════════════════════════════════════════════

def fetch_articles(feed_monitor, feed_urls, feed_type="crypto"):
    """Fetch articles from healthy feeds"""
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
                
                for entry in feed.entries[:5]:
                    articles.append({
                        'title': entry.title,
                        'url': entry.link,
                        'source_feed': feed_url,
                        'feed_type': feed_type
                    })
            else:
                feed_monitor.update_feed_health(feed_url, feed_type, success=False, error='No entries')
        
        except Exception as e:
            feed_monitor.update_feed_health(feed_url, feed_type, success=False, error=str(e))
            logger.warning(f"Error fetching {feed_url}: {e}")
    
    logger.info(f"Fetched {len(articles)} {feed_type} articles from feeds")
    return articles

# ═══════════════════════════════════════════════════════════════════════════
# MAIN BOT CLASS (Enhanced with Arsenal)
# ═══════════════════════════════════════════════════════════════════════════

class CompleteCryptoArsenalBot:
    """Complete bot with crypto news + quotes + Arsenal FC"""
    
    def __init__(self):
        logger.info("="*60)
        logger.info("INITIALIZING CRYPTO + ARSENAL BOT")
        logger.info("="*60)
        
        # Initialize all systems
        self.db = DatabaseManager()
        self.duplicate_detector = DuplicateDetector(self.db)
        self.url_manager = URLManager(bitly_token=BITLY_TOKEN, preferred_service='native')
        self.feed_monitor = RSSFeedMonitor(self.db)
        self.hashtag_optimizer = HashtagOptimizer(self.db)
        self.ab_framework = ABTestingFramework(self.db)
        self.quote_selector = QuoteSelector(self.db)
        self.arsenal_generator = ArsenalContentGenerator()  # NEW
        
        # Validate all RSS feeds
        logger.info("\nValidating RSS feeds...")
        self.feed_monitor.validate_all_feeds(CRYPTO_RSS_FEEDS, ARSENAL_RSS_FEEDS)
        
        logger.info("\n✅ All systems initialized")
        logger.info(f"📰 Crypto news: {DAILY_NEWS_LIMIT}/day")
        logger.info(f"💬 Quotes: {DAILY_QUOTE_LIMIT}/day")
        logger.info(f"⚽ Arsenal: {DAILY_ARSENAL_LIMIT}/day")
        logger.info(f"📊 Total: {DAILY_TOTAL_LIMIT}/day")
        logger.info("="*60 + "\n")
    
    def should_post_content(self, content, url, post_type=None):
        """Check if content should be posted"""
        if url and self.db.has_been_posted(url):
            logger.info(f"❌ URL already posted")
            return False
        
        is_dup, match_info = self.duplicate_detector.is_duplicate(content, days=7, post_type=post_type)
        if is_dup:
            logger.info(f"❌ Duplicate detected: {match_info['method']} (similarity: {match_info.get('similarity', 1.0):.2%})")
            return False
        
        return True
    
    def generate_news_tweet(self, article_title, article_url, content_type):
        """Generate crypto news tweet"""
        
        base_content = generate_crypto_content(article_title, content_type)
        
        test_plan = self.ab_framework.generate_test_plan(base_content)
        modified_content, variants = self.ab_framework.apply_variants(base_content, test_plan)
        
        if not self.should_post_content(modified_content, article_url, "news"):
            return None
        
        final_url = self.url_manager.shorten_url(article_url)
        
        hashtags = self.hashtag_optimizer.select_hashtags(
            modified_content,
            strategy='adaptive',
            content_type=content_type
        )
        
        tweet_with_url = f"{modified_content}\n\n{final_url}"
        
        final_tweet, included_hashtags = self.hashtag_optimizer.optimize_tweet_with_hashtags(
            tweet_with_url,
            hashtags
        )
        
        return {
            'post_type': 'news',
            'tweet_text': final_tweet,
            'content_hash': self.duplicate_detector.get_exact_hash(modified_content),
            'url': article_url,
            'content_type': content_type,
            'hashtags': included_hashtags,
            'test_plan': test_plan,
            'quote_category': None
        }
    
    def generate_quote_tweet(self):
        """Generate inspirational quote tweet"""
        
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
            'post_type': 'quote',
            'tweet_text': final_tweet,
            'content_hash': self.duplicate_detector.get_exact_hash(quote_text),
            'url': None,
            'content_type': 'inspirational',
            'hashtags': hashtags,
            'test_plan': {},
            'quote_category': category
        }
    
    def generate_arsenal_tweet(self, article_title, article_url, content_type="team_news"):
        """Generate Arsenal FC tweet (NEW)"""
        
        # Generate Arsenal content
        base_content, hashtags = self.arsenal_generator.generate_arsenal_tweet(
            article_title, article_url, content_type
        )
        
        # Check for duplicates (within Arsenal posts)
        if not self.should_post_content(base_content, article_url, "arsenal"):
            return None
        
        # Shorten URL
        final_url = self.url_manager.shorten_url(article_url)
        
        # Construct tweet
        tweet_with_url = f"{base_content}\n\n{final_url}"
        
        # Optimize with hashtags
        final_tweet, included_hashtags = self.hashtag_optimizer.optimize_tweet_with_hashtags(
            tweet_with_url,
            hashtags,
            max_length=280
        )
        
        return {
            'post_type': 'arsenal',
            'tweet_text': final_tweet,
            'content_hash': self.duplicate_detector.get_exact_hash(base_content),
            'url': article_url,
            'content_type': content_type,
            'hashtags': included_hashtags,
            'test_plan': {},
            'quote_category': None
        }
    
    def post_tweet(self, tweet_data):
        """Post tweet to Twitter"""
        global last_post_time, daily_news_posts, daily_quote_posts, daily_arsenal_posts
        
        try:
            response = twitter_client.create_tweet(text=tweet_data['tweet_text'])
            tweet_id = response.data['id']
            
            # Log to database
            self.db.log_post(
                tweet_id=tweet_id,
                post_type=tweet_data['post_type'],
                url=tweet_data['url'],
                content_hash=tweet_data['content_hash'],
                tweet_text=tweet_data['tweet_text'],
                content_type=tweet_data['content_type'],
                hashtags=tweet_data['hashtags'],
                quote_category=tweet_data.get('quote_category')
            )
            
            self.db.log_content_hash(tweet_data['content_hash'], tweet_id)
            
            # Log A/B tests
            for exp_name, variant in tweet_data.get('test_plan', {}).items():
                self.db.log_ab_test(exp_name, variant, tweet_id)
            
            # Update counters
            last_post_time = datetime.now(pytz.UTC)
            
            if tweet_data['post_type'] == 'news':
                daily_news_posts += 1
            elif tweet_data['post_type'] == 'quote':
                daily_quote_posts += 1
            elif tweet_data['post_type'] == 'arsenal':
                daily_arsenal_posts += 1
            
            # Log output
            post_emoji = {
                'news': '📰',
                'quote': '💬',
                'arsenal': '⚽'
            }.get(tweet_data['post_type'], '📝')
            
            logger.info("="*60)
            logger.info(f"✅ {post_emoji} {tweet_data['post_type'].upper()} POSTED!")
            logger.info(f"Tweet ID: {tweet_id}")
            logger.info(f"URL: https://twitter.com/user/status/{tweet_id}")
            logger.info(f"Content Type: {tweet_data['content_type']}")
            if tweet_data.get('quote_category'):
                logger.info(f"Quote Category: {tweet_data['quote_category']}")
            logger.info(f"Hashtags: {tweet_data['hashtags']}")
            logger.info(f"Daily: News {daily_news_posts}/{DAILY_NEWS_LIMIT} | Quotes {daily_quote_posts}/{DAILY_QUOTE_LIMIT} | Arsenal {daily_arsenal_posts}/{DAILY_ARSENAL_LIMIT}")
            logger.info("="*60)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error posting tweet: {e}")
            return False
    
    def run_posting_cycle(self, post_type):
        """Run one posting cycle"""
        global daily_news_posts, daily_quote_posts, daily_arsenal_posts
        
        # Check limits
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
        
        # Generate appropriate content
        if post_type == 'quote':
            logger.info(f"Generating quote post...")
            tweet_data = self.generate_quote_tweet()
            
            if tweet_data:
                return self.post_tweet(tweet_data)
            else:
                logger.info("Failed to generate quote")
                return False
        
        elif post_type == 'arsenal':
            logger.info(f"⚽ Generating Arsenal post...")
            
            # Fetch Arsenal articles
            articles = fetch_articles(self.feed_monitor, ARSENAL_RSS_FEEDS, "arsenal")
            
            if not articles:
                logger.info("No Arsenal articles available")
                return False
            
            # Try each article
            for article in articles:
                content_type = random.choice(ARSENAL_CONTENT_TYPES)
                tweet_data = self.generate_arsenal_tweet(
                    article['title'],
                    article['url'],
                    content_type
                )
                
                if tweet_data:
                    return self.post_tweet(tweet_data)
            
            logger.info("No suitable Arsenal articles found")
            return False
        
        elif post_type == 'news':
            content_type = random.choice(CRYPTO_CONTENT_TYPES)
            logger.info(f"Selected content type: {content_type}")
            
            articles = fetch_articles(self.feed_monitor, CRYPTO_RSS_FEEDS, "crypto")
            
            if not articles:
                logger.info("No crypto articles available")
                return False
            
            for article in articles:
                tweet_data = self.generate_news_tweet(
                    article['title'],
                    article['url'],
                    content_type
                )
                
                if tweet_data:
                    return self.post_tweet(tweet_data)
            
            logger.info("No suitable articles found")
        
        return False

# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def reset_daily_counter():
    """Reset daily post counters"""
    global daily_news_posts, daily_quote_posts, daily_arsenal_posts, last_reset_date
    current_date = datetime.now(pytz.UTC).date()
    if current_date > last_reset_date:
        daily_news_posts = 0
        daily_quote_posts = 0
        daily_arsenal_posts = 0
        last_reset_date = current_date
        logger.info("Daily counters reset")

def can_post_now():
    """Check if enough time has passed"""
    global last_post_time
    if last_post_time is None:
        return True
    time_since_last = datetime.now(pytz.UTC) - last_post_time
    return time_since_last.total_seconds() >= (POST_INTERVAL_MINUTES * 60)

def get_current_post_type():
    """Get what type of post should be made now"""
    current_time = datetime.now(pytz.UTC).strftime("%H:%M")
    
    for scheduled_time, post_type in POSTING_SCHEDULE:
        if scheduled_time == current_time:
            return post_type
    
    return None

# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULER
# ═══════════════════════════════════════════════════════════════════════════

def start_scheduler(bot):
    """Main scheduler loop"""
    logger.info("="*60)
    logger.info("🚀 STARTING CRYPTO + ARSENAL BOT SCHEDULER")
    logger.info("="*60)
    logger.info(f"📰 Crypto News: {DAILY_NEWS_LIMIT}/day")
    logger.info(f"💬 Quotes: {DAILY_QUOTE_LIMIT}/day")
    logger.info(f"⚽ Arsenal FC: {DAILY_ARSENAL_LIMIT}/day")
    logger.info(f"📊 Total: {DAILY_TOTAL_LIMIT}/day")
    logger.info(f"⏰ Posting Times: {len(POSTING_SCHEDULE)}")
    logger.info(f"⏱️  Post Interval: {POST_INTERVAL_MINUTES} minutes")
    logger.info("="*60 + "\n")
    
    last_checked_minute = None
    last_heartbeat = datetime.now(pytz.UTC)
    
    while True:
        try:
            current_time = datetime.now(pytz.UTC)
            current_minute = current_time.strftime("%H:%M")
            
            # Heartbeat
            if (current_time - last_heartbeat).total_seconds() >= 300:
                logger.info(f"💓 Bot running | {current_minute} UTC | News: {daily_news_posts}/{DAILY_NEWS_LIMIT} | Quotes: {daily_quote_posts}/{DAILY_QUOTE_LIMIT} | Arsenal: {daily_arsenal_posts}/{DAILY_ARSENAL_LIMIT}")
                last_heartbeat = current_time
            
            # Check for posting time
            if current_minute != last_checked_minute:
                post_type = get_current_post_type()
                
                if post_type:
                    post_emoji = {'news': '📰', 'quote': '💬', 'arsenal': '⚽'}.get(post_type, '📝')
                    logger.info(f"\n⏰ Posting time: {current_minute} ({post_emoji} {post_type})")
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
# HEALTH CHECK SERVER (Fixed for UptimeRobot)
# ═══════════════════════════════════════════════════════════════════════════

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests from monitoring services"""
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Content-Length', '150')
        self.end_headers()
        status = f"Crypto+Arsenal Bot: RUNNING\nTime: {datetime.now(pytz.UTC)}\nNews: {daily_news_posts}/{DAILY_NEWS_LIMIT}\nQuotes: {daily_quote_posts}/{DAILY_QUOTE_LIMIT}\nArsenal: {daily_arsenal_posts}/{DAILY_ARSENAL_LIMIT}\n"
        self.wfile.write(status.encode())
    
    def do_HEAD(self):
        """Handle HEAD requests from monitoring services like UptimeRobot"""
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Content-Length', '150')
        self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress access logs"""
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
        # Test Twitter auth
        logger.info("Testing Twitter authentication...")
        me = twitter_api.verify_credentials()
        logger.info(f"✅ Authenticated as @{me.screen_name}")
        
        # Initialize bot
        bot = CompleteCryptoArsenalBot()
        
        # Start health server
        health_thread = threading.Thread(target=start_health_server, daemon=True)
        health_thread.start()
        
        # Start scheduler
        start_scheduler(bot)
        
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
        exit(0)
    except Exception as e:
        logger.error(f"\n❌ CRITICAL ERROR: {e}")
        exit(1)
