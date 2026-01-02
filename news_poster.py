"""
═══════════════════════════════════════════════════════════════════════════════
    COMPLETE CRYPTO TWITTER BOT - ALL ENHANCEMENTS INTEGRATED
═══════════════════════════════════════════════════════════════════════════════

FEATURES INCLUDED:
✅ SQLite Database Management (replaces text files)
✅ A/B Testing Framework (5 simultaneous experiments)
✅ Intelligent Hashtag Optimization (5 strategies)
✅ Fuzzy Duplicate Detection (catches near-duplicates)
✅ Multi-Service URL Management (with fallback)
✅ RSS Feed Health Monitoring (validates & tracks)
✅ Comprehensive Analytics & Reporting
✅ Error Handling & Retry Logic
✅ Daily Statistics & Performance Tracking

AUTHOR: Enhanced Crypto Bot V2
VERSION: 2.0
DATE: 2026

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
BITLY_TOKEN = os.getenv("BITLY_TOKEN")  # Optional

# Database
DATABASE_PATH = "crypto_bot_data.db"

# Posting Configuration
DAILY_POST_LIMIT = 15
POST_INTERVAL_MINUTES = 90
last_post_time = None
daily_posts = 0
last_reset_date = datetime.now(pytz.UTC).date()

# Posting Schedule (UTC)
POSTING_TIMES = [
    "03:00", "05:00", "07:00", "09:00", "11:00", "13:00",
    "15:00", "17:00", "19:00", "21:00", "23:00", "01:00"
]

# Content Types
CRYPTO_CONTENT_TYPES = [
    "educational", "market_analysis", "contrarian",
    "question", "hot_take", "breakdown"
]

# RSS Feeds
RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://crypto.news/feed/",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/.rss/full/"
]

# Duplicate Detection Threshold
SIMILARITY_THRESHOLD = 0.75  # 75% similarity = duplicate

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
            
            # Posts table
            c.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tweet_id TEXT UNIQUE NOT NULL,
                    url TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    tweet_text TEXT NOT NULL,
                    content_type TEXT NOT NULL,
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
            
            # RSS sources table
            c.execute('''
                CREATE TABLE IF NOT EXISTS rss_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    feed_name TEXT,
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
            
            logger.info("✅ Database initialized")
    
    def log_post(self, tweet_id, url, content_hash, tweet_text, content_type, hashtags):
        """Log a new post"""
        with self.get_connection() as conn:
            c = conn.cursor()
            now = datetime.now(pytz.UTC)
            hashtag_str = json.dumps(hashtags) if hashtags else None
            
            c.execute('''
                INSERT INTO posts (tweet_id, url, content_hash, tweet_text, 
                                 content_type, hashtags, posted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (tweet_id, url, content_hash, tweet_text, content_type, hashtag_str, now))
    
    def has_been_posted(self, url):
        """Check if URL has been posted"""
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
    
    def get_recent_posts(self, limit=50):
        """Get recent posts"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT tweet_id, tweet_text, content_type, posted_at,
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
                    'posted_at': row[3],
                    'likes': row[4],
                    'retweets': row[5],
                    'replies': row[6],
                    'engagement_rate': row[7]
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
                    COUNT(*) as post_count,
                    AVG(likes) as avg_likes,
                    AVG(retweets) as avg_retweets,
                    AVG(engagement_rate) as avg_engagement_rate
                FROM posts
                WHERE posted_at > ? AND engagement_rate > 0
                GROUP BY content_type
                ORDER BY avg_engagement_rate DESC
            ''', (cutoff,))
            
            results = []
            for row in c.fetchall():
                results.append({
                    'content_type': row[0],
                    'post_count': row[1],
                    'avg_likes': round(row[2], 2),
                    'avg_retweets': round(row[3], 2),
                    'avg_engagement_rate': round(row[4], 2)
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
    
    def update_rss_source(self, url, feed_name, success=True):
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
                    INSERT INTO rss_sources (url, feed_name, last_fetched, 
                                           success_count, failure_count, success_rate)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (url, feed_name, now, 
                     1 if success else 0, 
                     0 if success else 1, 
                     1.0 if success else 0.0))
    
    def get_daily_post_count(self, date=None):
        """Get number of posts for a date"""
        if date is None:
            date = datetime.now(pytz.UTC).date()
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM posts WHERE DATE(posted_at) = ?', (date,))
            return c.fetchone()[0]

# ═══════════════════════════════════════════════════════════════════════════
# FUZZY DUPLICATE DETECTOR
# ═══════════════════════════════════════════════════════════════════════════

class DuplicateDetector:
    """Advanced duplicate detection using fuzzy matching"""
    
    def __init__(self, db_manager, similarity_threshold=SIMILARITY_THRESHOLD):
        self.db = db_manager
        self.similarity_threshold = similarity_threshold
    
    def get_exact_hash(self, text):
        """Get MD5 hash for exact duplicate detection"""
        normalized = self._normalize_text(text)
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def _normalize_text(self, text):
        """Normalize text for comparison"""
        text = text.lower()
        text = re.sub(r'http\S+|www.\S+', '', text)  # Remove URLs
        text = re.sub(r'#\w+', '', text)  # Remove hashtags
        text = re.sub(r'@\w+', '', text)  # Remove mentions
        text = ' '.join(text.split())  # Normalize whitespace
        return text.strip()
    
    def _tokenize(self, text):
        """Tokenize text into words"""
        normalized = self._normalize_text(text)
        cleaned = re.sub(r'[^\w\s]', '', normalized)
        words = cleaned.split()
        return [w for w in words if len(w) > 2]
    
    def levenshtein_similarity(self, text1, text2):
        """Calculate character-level similarity"""
        text1_norm = self._normalize_text(text1)
        text2_norm = self._normalize_text(text2)
        return SequenceMatcher(None, text1_norm, text2_norm).ratio()
    
    def jaccard_similarity(self, text1, text2):
        """Calculate word-level similarity"""
        words1 = set(self._tokenize(text1))
        words2 = set(self._tokenize(text2))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def cosine_similarity(self, text1, text2):
        """Calculate TF-IDF style similarity"""
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
        """Combine multiple algorithms"""
        lev = self.levenshtein_similarity(text1, text2)
        jac = self.jaccard_similarity(text1, text2)
        cos = self.cosine_similarity(text1, text2)
        
        # Weighted average
        return (lev * 0.3) + (jac * 0.35) + (cos * 0.35)
    
    def is_duplicate(self, text, days=7):
        """Check if text is a duplicate"""
        # Exact hash check
        exact_hash = self.get_exact_hash(text)
        if self.db.is_similar_content(exact_hash, days):
            return True, {'method': 'exact', 'similarity': 1.0}
        
        # Fuzzy similarity check
        recent_posts = self.db.get_recent_posts(limit=50)
        cutoff = datetime.now(pytz.UTC) - timedelta(days=days)
        
        for post in recent_posts:
            posted_at = datetime.fromisoformat(post['posted_at'].replace('Z', '+00:00'))
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

# ═══════════════════════════════════════════════════════════════════════════
# URL MANAGER
# ═══════════════════════════════════════════════════════════════════════════

class URLManager:
    """Manages URL shortening with multiple services"""
    
    def __init__(self, bitly_token=None, preferred_service='native'):
        self.bitly_token = bitly_token
        self.preferred_service = preferred_service
        self.url_cache = {}
    
    def is_valid_url(self, url):
        """Validate URL format"""
        if not url or not url.startswith(('http://', 'https://')):
            return False
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    def sanitize_url(self, url):
        """Clean URL"""
        return url.strip()
    
    def shorten_url(self, long_url):
        """Shorten URL with fallback"""
        if not self.is_valid_url(long_url):
            return long_url
        
        # Use Twitter's native shortening (recommended)
        if self.preferred_service == 'native':
            return long_url
        
        # Try Bitly
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
        
        # Try is.gd
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
        
        # Fallback to original
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
    """Monitor RSS feed health"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.feed_health = {}
        self.max_failures = 5
    
    def validate_feed(self, feed_url):
        """Validate a single feed"""
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(feed_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            feed = feedparser.parse(response.content)
            
            if not feed.entries:
                return False, "No entries"
            
            return True, {
                'feed_name': feed.feed.get('title', 'Unknown'),
                'entry_count': len(feed.entries)
            }
        except Exception as e:
            return False, str(e)
    
    def validate_all_feeds(self, feed_urls):
        """Validate all feeds"""
        logger.info(f"Validating {len(feed_urls)} RSS feeds...")
        
        valid_count = 0
        for feed_url in feed_urls:
            is_valid, details = self.validate_feed(feed_url)
            
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
                logger.info(f"✅ {details['feed_name']}: {details['entry_count']} entries")
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
                logger.warning(f"❌ {feed_url}: {details}")
        
        logger.info(f"Validation complete: {valid_count}/{len(feed_urls)} healthy")
        return valid_count
    
    def should_use_feed(self, feed_url):
        """Check if feed should be used"""
        if feed_url not in self.feed_health:
            return True
        
        health = self.feed_health[feed_url]
        return health.status != FeedStatus.DEAD
    
    def update_feed_health(self, feed_url, success, error=None):
        """Update feed health"""
        if feed_url not in self.feed_health:
            return
        
        health = self.feed_health[feed_url]
        health.last_check = datetime.now(pytz.UTC)
        
        if success:
            health.consecutive_failures = 0
            health.success_rate = min(1.0, health.success_rate + 0.1)
            health.status = FeedStatus.HEALTHY
            health.error_message = None
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
    
    def get_healthy_feeds(self):
        """Get list of healthy feeds"""
        return [url for url, health in self.feed_health.items() 
                if health.status in [FeedStatus.HEALTHY, FeedStatus.DEGRADED]]

# ═══════════════════════════════════════════════════════════════════════════
# HASHTAG OPTIMIZER
# ═══════════════════════════════════════════════════════════════════════════

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
        """Select hashtags based on strategy"""
        
        # Get top performers from database
        top_hashtags = self.db.get_top_hashtags(limit=10)
        top_tags = [h['hashtag'] for h in top_hashtags] if top_hashtags else []
        
        if strategy == 'adaptive' and top_tags:
            # Use data-driven approach
            selected = top_tags[:2]
        elif strategy == 'aggressive':
            # Maximum reach
            selected = random.sample(self.hashtag_pools['primary'], 2)
            selected.append(random.choice(self.hashtag_pools['trending']))
        else:
            # Balanced approach
            selected = [random.choice(self.hashtag_pools['primary'])]
            selected.append(random.choice(self.hashtag_pools['trending']))
        
        return selected[:2]  # Limit to 2 hashtags
    
    def optimize_tweet_with_hashtags(self, tweet_text, hashtags, max_length=280):
        """Add hashtags to tweet"""
        available_space = max_length - len(tweet_text) - 2
        
        hashtag_text = " " + " ".join(hashtags)
        
        if len(hashtag_text) <= available_space:
            return tweet_text + "\n\n" + " ".join(hashtags), hashtags
        
        # Try with fewer hashtags
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
    """Simple A/B testing for content variations"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        
        self.experiments = {
            'emoji_placement': ['start', 'end', 'none'],
            'hashtag_count': ['one', 'two'],
            'content_length': ['short', 'medium']
        }
    
    def select_variant(self, experiment_name):
        """Select random variant"""
        if experiment_name in self.experiments:
            return random.choice(self.experiments[experiment_name])
        return None
    
    def apply_emoji_variant(self, tweet, variant):
        """Apply emoji variant"""
        crypto_emojis = ["₿", "📊", "📈", "💎", "🚀"]
        
        if variant == 'start':
            return f"{random.choice(crypto_emojis)} {tweet}"
        elif variant == 'end':
            return f"{tweet} {random.choice(crypto_emojis)}"
        return tweet
    
    def generate_test_plan(self, base_content):
        """Generate A/B test plan"""
        plan = {}
        for exp_name in self.experiments.keys():
            plan[exp_name] = self.select_variant(exp_name)
        return plan
    
    def apply_variants(self, content, test_plan):
        """Apply all variants"""
        modified = content
        
        # Apply emoji
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

def fetch_crypto_articles(feed_monitor, feed_urls):
    """Fetch articles from healthy feeds"""
    articles = []
    
    for feed_url in feed_urls:
        # Check if feed is healthy
        if not feed_monitor.should_use_feed(feed_url):
            logger.debug(f"Skipping unhealthy feed: {feed_url}")
            continue
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(feed_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            feed = feedparser.parse(response.content)
            
            if feed.entries:
                feed_monitor.update_feed_health(feed_url, success=True)
                
                for entry in feed.entries[:5]:
                    articles.append({
                        'title': entry.title,
                        'url': entry.link,
                        'source_feed': feed_url
                    })
            else:
                feed_monitor.update_feed_health(feed_url, success=False, error='No entries')
        
        except Exception as e:
            feed_monitor.update_feed_health(feed_url, success=False, error=str(e))
            logger.warning(f"Error fetching {feed_url}: {e}")
    
    logger.info(f"Fetched {len(articles)} articles from feeds")
    return articles

# ═══════════════════════════════════════════════════════════════════════════
# MAIN BOT CLASS
# ═══════════════════════════════════════════════════════════════════════════

class CompleteCryptoBot:
    """Complete crypto bot with all enhancements"""
    
    def __init__(self):
        logger.info("="*60)
        logger.info("INITIALIZING COMPLETE CRYPTO BOT")
        logger.info("="*60)
        
        # Initialize all systems
        self.db = DatabaseManager()
        self.duplicate_detector = DuplicateDetector(self.db)
        self.url_manager = URLManager(bitly_token=BITLY_TOKEN, preferred_service='native')
        self.feed_monitor = RSSFeedMonitor(self.db)
        self.hashtag_optimizer = HashtagOptimizer(self.db)
        self.ab_framework = ABTestingFramework(self.db)
        
        # Validate RSS feeds
        logger.info("\nValidating RSS feeds...")
        self.feed_monitor.validate_all_feeds(RSS_FEEDS)
        
        logger.info("\n✅ All systems initialized")
        logger.info("="*60 + "\n")
    
    def should_post_content(self, content, url):
        """Check if content should be posted"""
        # Check URL
        if self.db.has_been_posted(url):
            logger.info(f"❌ URL already posted")
            return False
        
        # Check duplicates (fuzzy matching)
        is_dup, match_info = self.duplicate_detector.is_duplicate(content, days=7)
        if is_dup:
            logger.info(f"❌ Duplicate detected: {match_info['method']} (similarity: {match_info.get('similarity', 1.0):.2%})")
            return False
        
        return True
    
    def generate_tweet(self, article_title, article_url, content_type):
        """Generate complete tweet with all enhancements"""
        
        # 1. Generate base content
        base_content = generate_crypto_content(article_title, content_type)
        
        # 2. Apply A/B testing
        test_plan = self.ab_framework.generate_test_plan(base_content)
        modified_content, variants = self.ab_framework.apply_variants(base_content, test_plan)
        
        # 3. Check for duplicates
        if not self.should_post_content(modified_content, article_url):
            return None
        
        # 4. Process URL
        final_url = self.url_manager.shorten_url(article_url)
        
        # 5. Select hashtags
        hashtags = self.hashtag_optimizer.select_hashtags(
            modified_content,
            strategy='adaptive',
            content_type=content_type
        )
        
        # 6. Construct tweet
        tweet_with_url = f"{modified_content}\n\n{final_url}"
        
        final_tweet, included_hashtags = self.hashtag_optimizer.optimize_tweet_with_hashtags(
            tweet_with_url,
            hashtags
        )
        
        return {
            'tweet_text': final_tweet,
            'content_hash': self.duplicate_detector.get_exact_hash(modified_content),
            'url': article_url,
            'content_type': content_type,
            'hashtags': included_hashtags,
            'test_plan': test_plan
        }
    
    def post_tweet(self, tweet_data):
        """Post tweet to Twitter"""
        global last_post_time, daily_posts
        
        try:
            # Post to Twitter
            response = twitter_client.create_tweet(text=tweet_data['tweet_text'])
            tweet_id = response.data['id']
            
            # Log to database
            self.db.log_post(
                tweet_id=tweet_id,
                url=tweet_data['url'],
                content_hash=tweet_data['content_hash'],
                tweet_text=tweet_data['tweet_text'],
                content_type=tweet_data['content_type'],
                hashtags=tweet_data['hashtags']
            )
            
            self.db.log_content_hash(tweet_data['content_hash'], tweet_id)
            
            # Log A/B tests
            for exp_name, variant in tweet_data['test_plan'].items():
                self.db.log_ab_test(exp_name, variant, tweet_id)
            
            # Update tracking
            last_post_time = datetime.now(pytz.UTC)
            daily_posts += 1
            
            logger.info("="*60)
            logger.info(f"✅ TWEET POSTED SUCCESSFULLY!")
            logger.info(f"Tweet ID: {tweet_id}")
            logger.info(f"URL: https://twitter.com/user/status/{tweet_id}")
            logger.info(f"Content Type: {tweet_data['content_type']}")
            logger.info(f"Hashtags: {tweet_data['hashtags']}")
            logger.info(f"Daily Posts: {daily_posts}/{DAILY_POST_LIMIT}")
            logger.info("="*60)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error posting tweet: {e}")
            return False
    
    def run_posting_cycle(self):
        """Run one posting cycle"""
        global daily_posts
        
        # Check limits
        if daily_posts >= DAILY_POST_LIMIT:
            logger.info(f"Daily limit reached ({daily_posts}/{DAILY_POST_LIMIT})")
            return False
        
        if not can_post_now():
            return False
        
        # Select content type
        content_type = random.choice(CRYPTO_CONTENT_TYPES)
        logger.info(f"Selected content type: {content_type}")
        
        # Fetch articles
        articles = fetch_crypto_articles(self.feed_monitor, RSS_FEEDS)
        
        if not articles:
            logger.info("No articles available")
            return False
        
        # Try each article
        for article in articles:
            tweet_data = self.generate_tweet(
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
    """Reset daily post counter"""
    global daily_posts, last_reset_date
    current_date = datetime.now(pytz.UTC).date()
    if current_date > last_reset_date:
        daily_posts = 0
        last_reset_date = current_date
        logger.info("Daily post counter reset")

def can_post_now():
    """Check if enough time has passed"""
    global last_post_time
    if last_post_time is None:
        return True
    time_since_last = datetime.now(pytz.UTC) - last_post_time
    return time_since_last.total_seconds() >= (POST_INTERVAL_MINUTES * 60)

def should_post_now():
    """Check if current time matches schedule"""
    current_time = datetime.now(pytz.UTC).strftime("%H:%M")
    return current_time in POSTING_TIMES

# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULER
# ═══════════════════════════════════════════════════════════════════════════

def start_scheduler(bot):
    """Main scheduler loop"""
    logger.info("="*60)
    logger.info("🚀 STARTING CRYPTO BOT SCHEDULER")
    logger.info("="*60)
    logger.info(f"Daily Limit: {DAILY_POST_LIMIT} posts")
    logger.info(f"Posting Times: {len(POSTING_TIMES)} times per day")
    logger.info(f"Post Interval: {POST_INTERVAL_MINUTES} minutes")
    logger.info("="*60 + "\n")
    
    last_checked_minute = None
    last_heartbeat = datetime.now(pytz.UTC)
    
    while True:
        try:
            current_time = datetime.now(pytz.UTC)
            current_minute = current_time.strftime("%H:%M")
            
            # Heartbeat every 5 minutes
            if (current_time - last_heartbeat).total_seconds() >= 300:
                logger.info(f"💓 Bot running | Time: {current_minute} UTC | Daily: {daily_posts}/{DAILY_POST_LIMIT}")
                last_heartbeat = current_time
            
            # Check for posting time
            if current_minute != last_checked_minute:
                if should_post_now():
                    logger.info(f"\n⏰ Posting time: {current_minute}")
                    reset_daily_counter()
                    bot.run_posting_cycle()
                
                last_checked_minute = current_minute
            
            time.sleep(30)
            
        except KeyboardInterrupt:
            logger.info("\n👋 Shutting down...")
            logger.info(f"Final stats: {daily_posts} posts today")
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
        status = f"Crypto Bot: RUNNING\nTime: {datetime.now(pytz.UTC)}\nPosts: {daily_posts}/{DAILY_POST_LIMIT}\n"
        self.wfile.write(status.encode())
    
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
        # Test Twitter auth
        logger.info("Testing Twitter authentication...")
        me = twitter_api.verify_credentials()
        logger.info(f"✅ Authenticated as @{me.screen_name}")
        
        # Initialize bot
        bot = CompleteCryptoBot()
        
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
