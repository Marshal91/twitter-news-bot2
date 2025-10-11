"""
Self-Learning Twitter Bot with Performance Analytics
Features:
- Tracks engagement metrics for posted content
- Learns what works and adapts content strategy
- Optimizes posting times, styles, and categories
- Fixes port binding issue for deployment
"""

import os
import sys
import signal
import random
import requests
import feedparser
import tweepy
import time
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import pytz
from openai import OpenAI
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from dataclasses import dataclass, asdict, field
import atexit
from collections import defaultdict

# Load environment
if os.path.exists('.env'):
    load_dotenv()

# =========================
# CONSTANTS
# =========================

POST_INTERVAL_MINUTES = 90
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 5

# Analytics
ANALYTICS_CHECK_INTERVAL_HOURS = 6
MIN_POSTS_FOR_LEARNING = 5  # Reduced for faster learning
ENGAGEMENT_RATE_WEIGHT = 0.4
LIKE_WEIGHT = 0.3
RETWEET_WEIGHT = 0.2
REPLY_WEIGHT = 0.1

PREMIUM_POSTING_TIMES = ["08:00", "12:00", "14:00", "16:00", "18:00", "22:00"]
GLOBAL_POSTING_TIMES = ["02:00", "04:00", "06:00", "10:00", "20:00", "00:00"]
MAIN_POSTING_TIMES = PREMIUM_POSTING_TIMES + GLOBAL_POSTING_TIMES

RSS_FEEDS = {
    "EPL": ["http://feeds.arsenal.com/arsenal-news", "https://www.premierleague.com/news"],
    "F1": ["https://www.formula1.com/en/latest/all.xml"],
    "Crypto": ["https://cointelegraph.com/rss", "https://www.coindesk.com/arc/outboundfeeds/rss/"],
    "Tesla": ["https://insideevs.com/rss/articles/all", "https://electrek.co/feed/"]
}

# =========================
# LOGGING
# =========================

if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[
        RotatingFileHandler('logs/bot.log', maxBytes=10*1024*1024, backupCount=3),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# =========================
# EXCEPTIONS
# =========================

class BotException(Exception):
    pass

class QuotaExceededException(BotException):
    pass

# =========================
# DATA CLASSES
# =========================

@dataclass
class TweetMetrics:
    tweet_id: str
    text: str
    category: str
    posted_at: datetime
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    impressions: int = 0
    engagement_rate: float = 0.0
    has_emoji: bool = False
    has_question: bool = False
    word_count: int = 0
    posting_time: Optional[str] = None
    
    def calculate_engagement_rate(self):
        if self.impressions > 0:
            total = self.likes + self.retweets + self.replies
            self.engagement_rate = (total / self.impressions) * 100
        return self.engagement_rate

@dataclass
class LearningInsights:
    best_categories: List[Tuple[str, float]] = field(default_factory=list)
    best_times: List[str] = field(default_factory=list)
    category_recommendations: Dict[str, Dict] = field(default_factory=dict)
    last_updated: Optional[datetime] = None
    total_analyzed: int = 0

# =========================
# QUOTA MANAGER
# =========================

class APIQuotaManager:
    def __init__(self, quota_file: str = "api_quota.json"):
        self.quota_file = quota_file
        self.lock = threading.Lock()
        self.load_quota()
    
    def load_quota(self):
        with self.lock:
            try:
                if os.path.exists(self.quota_file):
                    with open(self.quota_file, 'r') as f:
                        data = json.load(f)
                    current_month = datetime.now(pytz.UTC).strftime("%Y-%m")
                    if data.get("month") != current_month:
                        self._reset_quota()
                    else:
                        self.quota = data
                else:
                    self._reset_quota()
            except:
                self._reset_quota()
    
    def _reset_quota(self):
        self.quota = {
            "month": datetime.now(pytz.UTC).strftime("%Y-%m"),
            "reads_used": 0,
            "writes_used": 0
        }
        self.save_quota()
    
    def save_quota(self):
        with self.lock:
            try:
                with open(self.quota_file, 'w') as f:
                    json.dump(self.quota, f, indent=2)
            except Exception as e:
                logger.error(f"Error saving quota: {e}")
    
    def can_read(self, count=1):
        with self.lock:
            return (self.quota["reads_used"] + count) <= 100
    
    def can_write(self, count=1):
        with self.lock:
            return (self.quota["writes_used"] + count) <= 500
    
    def use_read(self, count=1):
        with self.lock:
            if not self.can_read(count):
                raise QuotaExceededException("Read quota exceeded")
            self.quota["reads_used"] += count
            self.save_quota()
    
    def use_write(self, count=1):
        with self.lock:
            if not self.can_write(count):
                raise QuotaExceededException("Write quota exceeded")
            self.quota["writes_used"] += count
            self.save_quota()

# =========================
# ANALYTICS MANAGER
# =========================

class AnalyticsManager:
    def __init__(self):
        self.metrics_file = "tweet_metrics.json"
        self.insights_file = "learning_insights.json"
        self.metrics: List[TweetMetrics] = []
        self.insights: Optional[LearningInsights] = None
        self.lock = threading.Lock()
        self.load_data()
    
    def load_data(self):
        # Load metrics
        if os.path.exists(self.metrics_file):
            try:
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                    self.metrics = [
                        TweetMetrics(**{**m, 'posted_at': datetime.fromisoformat(m['posted_at'])})
                        for m in data
                    ]
                logger.info(f"Loaded {len(self.metrics)} tweet metrics")
            except:
                self.metrics = []
        
        # Load insights
        if os.path.exists(self.insights_file):
            try:
                with open(self.insights_file, 'r') as f:
                    data = json.load(f)
                    if data.get('last_updated'):
                        data['last_updated'] = datetime.fromisoformat(data['last_updated'])
                    self.insights = LearningInsights(**data)
                logger.info("Loaded learning insights")
            except:
                self.insights = LearningInsights()
        else:
            self.insights = LearningInsights()
    
    def save_data(self):
        with self.lock:
            # Save metrics
            try:
                data = [
                    {**asdict(m), 'posted_at': m.posted_at.isoformat()}
                    for m in self.metrics
                ]
                with open(self.metrics_file, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Error saving metrics: {e}")
            
            # Save insights
            try:
                data = asdict(self.insights)
                if self.insights.last_updated:
                    data['last_updated'] = self.insights.last_updated.isoformat()
                with open(self.insights_file, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Error saving insights: {e}")
    
    def record_tweet(self, tweet_id: str, text: str, category: str, attributes: Dict):
        with self.lock:
            metric = TweetMetrics(
                tweet_id=tweet_id,
                text=text,
                category=category,
                posted_at=datetime.now(pytz.UTC),
                **attributes
            )
            self.metrics.append(metric)
            self.save_data()
            logger.info(f"📊 Recorded tweet {tweet_id} for learning")
    
    def update_metrics(self, tweet_id: str, likes: int, retweets: int, replies: int, impressions: int):
        with self.lock:
            for m in self.metrics:
                if m.tweet_id == tweet_id:
                    m.likes = likes
                    m.retweets = retweets
                    m.replies = replies
                    m.impressions = impressions
                    m.calculate_engagement_rate()
                    self.save_data()
                    logger.info(f"✓ Updated metrics for {tweet_id}: {m.engagement_rate:.2f}% engagement")
                    return
    
    def analyze_performance(self):
        if len(self.metrics) < MIN_POSTS_FOR_LEARNING:
            logger.info(f"Need {MIN_POSTS_FOR_LEARNING - len(self.metrics)} more posts before learning")
            return
        
        logger.info("🧠 ANALYZING PERFORMANCE & LEARNING...")
        
        # Analyze by category
        category_performance = defaultdict(list)
        for m in self.metrics:
            if m.impressions > 0:
                category_performance[m.category].append(m.engagement_rate)
        
        # Rank categories
        category_avg = {
            cat: sum(rates)/len(rates) if rates else 0
            for cat, rates in category_performance.items()
        }
        best_categories = sorted(category_avg.items(), key=lambda x: x[1], reverse=True)
        
        # Analyze posting times
        time_performance = defaultdict(list)
        for m in self.metrics:
            if m.posting_time and m.impressions > 0:
                time_performance[m.posting_time].append(m.engagement_rate)
        
        time_avg = {
            time: sum(rates)/len(rates) if rates else 0
            for time, rates in time_performance.items()
        }
        best_times = sorted(time_avg.keys(), key=lambda t: time_avg[t], reverse=True)[:5]
        
        # Analyze content attributes per category
        recommendations = {}
        for category in RSS_FEEDS.keys():
            cat_metrics = [m for m in self.metrics if m.category == category and m.impressions > 0]
            if not cat_metrics:
                continue
            
            with_emoji = [m for m in cat_metrics if m.has_emoji]
            without_emoji = [m for m in cat_metrics if not m.has_emoji]
            emoji_helps = False
            if with_emoji and without_emoji:
                emoji_helps = (sum(m.engagement_rate for m in with_emoji)/len(with_emoji) >
                             sum(m.engagement_rate for m in without_emoji)/len(without_emoji))
            
            with_question = [m for m in cat_metrics if m.has_question]
            without_question = [m for m in cat_metrics if not m.has_question]
            question_helps = False
            if with_question and without_question:
                question_helps = (sum(m.engagement_rate for m in with_question)/len(with_question) >
                                sum(m.engagement_rate for m in without_question)/len(without_question))
            
            recommendations[category] = {
                'use_emoji': emoji_helps,
                'use_questions': question_helps,
                'avg_engagement': sum(m.engagement_rate for m in cat_metrics) / len(cat_metrics)
            }
        
        # Update insights
        self.insights = LearningInsights(
            best_categories=best_categories,
            best_times=best_times,
            category_recommendations=recommendations,
            last_updated=datetime.now(pytz.UTC),
            total_analyzed=len([m for m in self.metrics if m.impressions > 0])
        )
        self.save_data()
        
        # Log insights
        logger.info("📈 LEARNING INSIGHTS:")
        logger.info(f"   Best Categories: {best_categories[:3]}")
        logger.info(f"   Best Times: {best_times}")
        for cat, rec in recommendations.items():
            logger.info(f"   {cat}: Emoji={rec['use_emoji']}, Questions={rec['use_questions']}, "
                       f"Avg Engagement={rec['avg_engagement']:.2f}%")
    
    def get_recommendation(self, category: str) -> Dict:
        if not self.insights or category not in self.insights.category_recommendations:
            return {}
        return self.insights.category_recommendations[category]
    
    def should_post_category(self, category: str) -> bool:
        if not self.insights or not self.insights.best_categories:
            return True
        
        # Get category rank
        ranks = {cat: i for i, (cat, _) in enumerate(self.insights.best_categories)}
        if category not in ranks:
            return True
        
        rank = ranks[category]
        total = len(self.insights.best_categories)
        
        # Bottom 30% - reduce frequency
        if rank > total * 0.7:
            return random.random() < 0.4
        # Top 30% - increase frequency
        if rank < total * 0.3:
            return random.random() < 0.9
        return random.random() < 0.7

# =========================
# METRICS COLLECTOR
# =========================

class MetricsCollector:
    def __init__(self, twitter_client, analytics_manager, quota_manager):
        self.twitter_client = twitter_client
        self.analytics = analytics_manager
        self.quota = quota_manager
        self.last_collection = None
    
    def collect_metrics(self):
        if not self.quota.can_read(1):
            logger.warning("Cannot collect metrics - quota exhausted")
            return
        
        logger.info("📊 Collecting performance metrics...")
        
        # Get recent tweets (last 7 days, not yet updated)
        cutoff = datetime.now(pytz.UTC) - timedelta(days=7)
        to_update = [m for m in self.analytics.metrics 
                    if m.posted_at > cutoff and m.impressions == 0]
        
        if not to_update:
            logger.info("No tweets need updating")
            return
        
        # Collect in batches
        for i in range(0, min(len(to_update), 10), 10):
            batch = to_update[i:i+10]
            tweet_ids = [m.tweet_id for m in batch]
            
            try:
                tweets = self.twitter_client.get_tweets(
                    ids=tweet_ids,
                    tweet_fields=['public_metrics'],
                    user_auth=True
                )
                
                self.quota.use_read(1)
                
                if tweets.data:
                    for tweet in tweets.data:
                        metrics = tweet.public_metrics
                        self.analytics.update_metrics(
                            str(tweet.id),
                            metrics.get('like_count', 0),
                            metrics.get('retweet_count', 0),
                            metrics.get('reply_count', 0),
                            metrics.get('impression_count', 0)
                        )
                
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
        
        self.last_collection = datetime.now(pytz.UTC)
        
        # Trigger learning
        self.analytics.analyze_performance()
    
    def should_collect_now(self):
        if self.last_collection is None:
            return True
        elapsed = datetime.now(pytz.UTC) - self.last_collection
        return elapsed.total_seconds() >= (ANALYTICS_CHECK_INTERVAL_HOURS * 3600)

# =========================
# ADAPTIVE CONTENT GENERATOR
# =========================

class ContentGenerator:
    def __init__(self, api_key: str, analytics: AnalyticsManager):
        self.client = OpenAI(api_key=api_key)
        self.analytics = analytics
    
    def generate_content(self, title: str, category: str) -> Tuple[str, Dict]:
        # Get learned recommendations
        rec = self.analytics.get_recommendation(category)
        use_question = rec.get('use_questions', True)
        
        prompt = f"""Create an engaging Twitter post about: {title}

Category: {category}
{"End with a thought-provoking question." if use_question else "Make a bold statement."}

Requirements:
- Under 180 characters (for URL/hashtags)
- Drive engagement
- Be specific and insightful

Write ONLY the tweet:"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Create viral Twitter content."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=80,
                temperature=0.8
            )
            text = response.choices[0].message.content.strip()
            
            # Extract attributes for learning
            attributes = {
                'has_emoji': any(c in text for c in "⚽📊🔄🏆⚡🏎️🚨₿🚀🔋🏍️"),
                'has_question': '?' in text,
                'word_count': len(text.split()),
                'posting_time': datetime.now(pytz.UTC).strftime("%H:%M")
            }
            
            return text, attributes
            
        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            return f"Breaking: {title[:100]}...", {}

# =========================
# TWITTER BOT
# =========================

class TwitterBot:
    def __init__(self, openai_key, twitter_key, twitter_secret, token, token_secret):
        self.quota = APIQuotaManager()
        self.analytics = AnalyticsManager()
        
        # Twitter setup
        auth = tweepy.OAuth1UserHandler(twitter_key, twitter_secret, token, token_secret)
        self.api = tweepy.API(auth)
        self.client = tweepy.Client(
            consumer_key=twitter_key,
            consumer_secret=twitter_secret,
            access_token=token,
            access_token_secret=token_secret
        )
        
        self.content_gen = ContentGenerator(openai_key, self.analytics)
        self.metrics_collector = MetricsCollector(self.client, self.analytics, self.quota)
        
        self.last_post = None
        self.shutdown = False
        
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)
        atexit.register(self._cleanup)
    
    def _shutdown(self, signum, frame):
        logger.info(f"Shutdown signal {signum} received")
        self.shutdown = True
    
    def _cleanup(self):
        logger.info("Saving state...")
        self.quota.save_quota()
        self.analytics.save_data()
    
    def verify_auth(self):
        try:
            me = self.api.verify_credentials()
            logger.info(f"✓ Authenticated as @{me.screen_name}")
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False
    
    def can_post_now(self):
        if self.last_post is None:
            return True
        elapsed = datetime.now(pytz.UTC) - self.last_post
        return elapsed.total_seconds() >= (POST_INTERVAL_MINUTES * 60)
    
    def fetch_articles(self, category: str):
        feeds = RSS_FEEDS.get(category, [])
        for feed_url in feeds[:2]:
            try:
                response = requests.get(feed_url, timeout=10)
                feed = feedparser.parse(response.content)
                return [{'title': e.title, 'url': e.link} for e in feed.entries[:3]]
            except:
                continue
        return []
    
    def post_content(self, category: str):
        if not self.can_post_now() or not self.quota.can_write(1):
            return False
        
        articles = self.fetch_articles(category)
        
        for article in articles:
            try:
                # Generate content
                text, attributes = self.content_gen.generate_content(article['title'], category)
                
                # Build tweet
                full_tweet = f"{text}\n\n{article['url']}"
                if len(full_tweet) > 280:
                    full_tweet = full_tweet[:277] + "..."
                
                # Post
                response = self.client.create_tweet(text=full_tweet)
                self.quota.use_write(1)
                
                # Record for learning
                self.analytics.record_tweet(
                    str(response.data['id']),
                    text,
                    category,
                    attributes
                )
                
                self.last_post = datetime.now(pytz.UTC)
                logger.info(f"✓ Posted {category}: {text[:50]}...")
                return True
                
            except Exception as e:
                logger.error(f"Post failed: {e}")
                continue
        
        return False
    
    def run(self):
        logger.info("🚀 Bot starting with self-learning enabled!")
        logger.info(f"📊 {len(self.analytics.metrics)} historical tweets to learn from")
        
        last_minute = None
        
        while not self.shutdown:
            try:
                current_minute = datetime.now(pytz.UTC).strftime("%H:%M")
                
                if current_minute != last_minute:
                    # Check for posting time
                    if current_minute in MAIN_POSTING_TIMES:
                        # Use learning to select category
                        categories = list(RSS_FEEDS.keys())
                        selected_categories = [c for c in categories if self.analytics.should_post_category(c)]
                        
                        if selected_categories:
                            category = random.choice(selected_categories)
                            logger.info(f"⏰ Posting time - Selected: {category}")
                            self.post_content(category)
                    
                    # Check for metrics collection
                    if self.metrics_collector.should_collect_now():
                        self.metrics_collector.collect_metrics()
                    
                    last_minute = current_minute
                
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(60)

# =========================
# HEALTH SERVER
# =========================

class HealthHandler(BaseHTTPRequestHandler):
    bot_state = None
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        
        status = "Twitter Bot: RUNNING\n\n"
        if self.bot_state:
            status += f"Metrics Tracked: {len(self.bot_state['analytics'].metrics)}\n"
            if self.bot_state['analytics'].insights:
                insights = self.bot_state['analytics'].insights
                status += f"Posts Analyzed: {insights.total_analyzed}\n"
                status += f"Best Categories: {insights.best_categories[:3]}\n"
        
        self.wfile.write(status.encode())
    
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
    
    def log_message(self, format, *args):
        pass

def start_health_server(bot, port):
    HealthHandler.bot_state = {'analytics': bot.analytics}
    port = int(os.environ.get('PORT', 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        logger.info(f"✓ Health server bound to 0.0.0.0:{port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"CRITICAL: Health server failed on port {port}: {e}")
        raise

# =========================
# MAIN
# =========================

def main():
    logger.info("=== SELF-LEARNING TWITTER BOT STARTING ===")
    
    # Validate environment
    required = ["OPENAI_API_KEY", "TWITTER_API_KEY", "TWITTER_API_SECRET", 
                "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        logger.error(f"Missing: {missing}")
        sys.exit(1)
    
    # Initialize bot
    bot = TwitterBot(
        openai_key=os.getenv("OPENAI_API_KEY"),
        twitter_key=os.getenv("TWITTER_API_KEY"),
        twitter_secret=os.getenv("TWITTER_API_SECRET"),
        token=os.getenv("TWITTER_ACCESS_TOKEN"),
        token_secret=os.getenv("TWITTER_ACCESS_SECRET")
    )
    
    if not bot.verify_auth():
        sys.exit(1)
    
    logger.info("✓ Self-learning system active")
    logger.info("✓ Will track: engagement, likes, retweets, replies")
    logger.info("✓ Adapts: content style, timing, category selection")
    
    # Start health server FIRST (critical for deployment)
    port = int(os.environ.get('PORT', 10000))
    health_thread = threading.Thread(target=start_health_server, args=(bot, port), daemon=True)
    health_thread.start()
    time.sleep(2)  # Ensure port is bound
    
    # Start bot
    bot.run()

if __name__ == "__main__":
    main()
