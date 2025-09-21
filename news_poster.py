"""
Complete Enhanced Twitter Bot with Ultra-Conservative Reply System
API Limits: 100 reads/month (3/day), 500 writes/month (12 posts + 3 replies/day)
"""

import os
import random
import requests
import feedparser
import tweepy
import time
import hashlib
import json
from datetime import datetime, timedelta
import pytz
from newspaper import Article, Config
from openai import OpenAI
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import logging
from logging.handlers import RotatingFileHandler
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Try to load .env file if it exists, otherwise use environment variables
try:
    if os.path.exists('.env'):
        load_dotenv()
        print("INFO: .env file loaded successfully")
    else:
        print("INFO: No .env file found, using system environment variables")
except Exception as e:
    print(f"INFO: Could not load .env file: {e}")

# =========================
# API QUOTA MANAGEMENT
# =========================

class APIQuotaManager:
    def __init__(self):
        self.quota_file = "api_quota.json"
        self.load_quota()
    
    def load_quota(self):
        """Load current month's quota usage"""
        try:
            if os.path.exists(self.quota_file):
                with open(self.quota_file, 'r') as f:
                    data = json.load(f)
                
                # Check if we're in a new month
                current_month = datetime.now(pytz.UTC).strftime("%Y-%m")
                if data.get("month") != current_month:
                    # Reset for new month
                    self.quota = {
                        "month": current_month,
                        "reads_used": 0,
                        "writes_used": 0,
                        "last_reset": datetime.now(pytz.UTC).isoformat()
                    }
                    self.save_quota()
                else:
                    self.quota = data
            else:
                # Initialize quota file
                self.quota = {
                    "month": datetime.now(pytz.UTC).strftime("%Y-%m"),
                    "reads_used": 0,
                    "writes_used": 0,
                    "last_reset": datetime.now(pytz.UTC).isoformat()
                }
                self.save_quota()
        except Exception as e:
            logging.error(f"Error loading quota: {e}")
            self.quota = {
                "month": datetime.now(pytz.UTC).strftime("%Y-%m"),
                "reads_used": 0,
                "writes_used": 0,
                "last_reset": datetime.now(pytz.UTC).isoformat()
            }
    
    def save_quota(self):
        """Save quota to file"""
        try:
            with open(self.quota_file, 'w') as f:
                json.dump(self.quota, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving quota: {e}")
    
    def can_read(self, count=1):
        """Check if we can make read requests (100/month = ~3/day)"""
        return (self.quota["reads_used"] + count) <= 100
    
    def can_write(self, count=1):
        """Check if we can make write requests (500/month)"""
        return (self.quota["writes_used"] + count) <= 500
    
    def use_read(self, count=1):
        """Record read API usage"""
        if self.can_read(count):
            self.quota["reads_used"] += count
            self.save_quota()
            return True
        return False
    
    def use_write(self, count=1):
        """Record write API usage"""
        if self.can_write(count):
            self.quota["writes_used"] += count
            self.save_quota()
            return True
        return False
    
    def get_quota_status(self):
        """Get current quota status"""
        return {
            "reads_remaining": 100 - self.quota["reads_used"],
            "writes_remaining": 500 - self.quota["writes_used"],
            "reads_used": self.quota["reads_used"],
            "writes_used": self.quota["writes_used"],
            "month": self.quota["month"]
        }

# =========================
# CONFIGURATION (Enhanced)
# =========================

# Load from environment variables (.env file in production)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")

# Initialize API Quota Manager
quota_manager = APIQuotaManager()

# Log files
LOG_FILE = "bot_log.txt"
POSTED_LOG = "posted_links.txt"
CONTENT_HASH_LOG = "posted_content_hashes.txt"

# Enhanced rate limiting configuration
DAILY_POST_LIMIT = 15  # Main content posts per day
POST_INTERVAL_MINUTES = 90 # 1 hour 30 mins between posts
last_post_time = None
FRESHNESS_WINDOW = timedelta(hours=72)

# Ultra-conservative reply limits
DAILY_REPLY_LIMIT = 3  # Only 3 replies per day to save writes
DAILY_READ_LIMIT = 3   # Only 3 reads per day for reply research

# Premium posting times - targeting business professionals and decision-makers
PREMIUM_POSTING_TIMES = [
    "08:00",  # Morning business hours
    "12:00",  # Lunch break business crowd
    "14:00",  # Afternoon peak
    "16:00",  # Evening engagement
    "18:00",  # Prime evening time
    "22:00",  # Late night Americas
   
]

# Global engagement times for sports/entertainment content
GLOBAL_POSTING_TIMES = [
    "02:00",  # Asia/Australia morning
    "04:00",  # Early Morning Nairobi
    "06:00",  # Europe morning
    "10:00",  # Pre-lunch global
    "20:00",  # Night professionals
    "00:00",  # Late night Americas
]

# All main posting times combined
MAIN_POSTING_TIMES = PREMIUM_POSTING_TIMES + GLOBAL_POSTING_TIMES

# Reply campaign times (only 3 times per day)
REPLY_CAMPAIGN_TIMES = [
    "10:55",  # Mid-morning
    "16:30",  # Mid-afternoon  
    "22:30",  # Late evening
]

# Categories that benefit from global timing
GLOBAL_CATEGORIES = ["EPL", "F1", "MotoGP", "Cycling"]

# Categories that should focus on business hours
BUSINESS_CATEGORIES = ["Crypto", "Tesla", "Space Exploration"]

# RSS feeds mapped to categories
RSS_FEEDS = {
    "EPL": [
        "http://feeds.arsenal.com/arsenal-news",
        "https://www.premierleague.com/news",
        "https://www.skysports.com/rss/12",
        "http://feeds.bbci.co.uk/sport/football/premier-league/rss.xml",
        "https://www.theguardian.com/football/premierleague/rss",
        "https://arseblog.com/feed/"
    ],
    "F1": [
        "https://www.formula1.com/en/latest/all.xml",
        "https://www.autosport.com/rss/f1/news/",
        "https://www.motorsport.com/rss/f1/news/"
    ],
    "MotoGP": [
        "https://www.motogp.com/en/news/rss",
        "https://www.autosport.com/rss/motogp/news/",
        "https://www.crash.net/rss/motogp"
    ],
    "Crypto": [
        "https://cointelegraph.com/rss",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://crypto.news/feed/"
    ],
    "Cycling": [
        "http://feeds2.feedburner.com/cyclingnews/news",
        "https://cycling.today/feed",
        "https://velo.outsideonline.com/feed/"
    ],
    "Space Exploration": [
        "https://spacenews.com/feed",
        "https://phys.org/rss-feed/space-news/",
        "https://www.space.com/feeds/all"
    ],
    "Tesla": [
        "https://insideevs.com/rss/articles/all",
        "https://electrek.co/feed/"
    ]
}

# Premium user targeting content strategies
PREMIUM_CONTENT_STRATEGIES = {
    "EPL": {
        "focus": "Business strategy, player valuations, commercial insights",
        "tone": "Professional analysis with strategic implications",
        "cta": "What's your take on the business side?"
    },
    "F1": {
        "focus": "Technology innovation, team strategies, commercial partnerships",
        "tone": "Technical expertise with business applications",
        "cta": "How does this impact the sport's commercial future?"
    },
    "Crypto": {
        "focus": "Regulatory compliance, institutional adoption, market structure",
        "tone": "Institutional-grade analysis and implications",
        "cta": "What are the regulatory implications here?"
    },
    "Tesla": {
        "focus": "Innovation leadership, market disruption, investment thesis",
        "tone": "Strategic business analysis and market positioning",
        "cta": "How does this reshape the EV landscape?"
    },
    "Space Exploration": {
        "focus": "Commercial space economy, technology transfer, investment opportunities",
        "tone": "Strategic business and technology analysis",
        "cta": "What are the commercial implications?"
    },
    "Cycling": {
        "focus": "Sports business, technology innovation, market trends",
        "tone": "Industry analysis and business perspective",
        "cta": "How does this change the sport's business model?"
    },
    "MotoGP": {
        "focus": "Technology transfer, commercial partnerships, market impact",
        "tone": "Technical and business analysis",
        "cta": "What's the broader industry impact?"
    }
}
TRENDING_HASHTAGS = {
    "EPL": {
        "primary": ["#PremierLeague", "#EPL", "#Football"],
        "secondary": ["#Arsenal", "#ManCity", "#Liverpool", "#Chelsea"],
        "trending": ["#MatchDay", "#FootballTwitter"]
    },
    "F1": {
        "primary": ["#F1", "#Formula1"],
        "secondary": ["#Verstappen", "#Hamilton", "#Ferrari"],
        "trending": ["#F1News", "#Racing"]
    },
    "Crypto": {
        "primary": ["#Bitcoin", "#Cryptocurrency"],
        "secondary": ["#Ethereum", "#DeFi", "#BTC"],
        "trending": ["#CryptoNews", "#Blockchain"]
    },
    "Tesla": {
        "primary": ["#Tesla", "#ElectricCars"],
        "secondary": ["#ElonMusk", "#EV"],
        "trending": ["#CleanEnergy", "#Innovation"]
    },
    "Space Exploration": {
        "primary": ["#Space", "#SpaceX"],
        "secondary": ["#NASA", "#Mars"],
        "trending": ["#SpaceExploration"]
    },
    "Cycling": {
        "primary": ["#Cycling", "#ProCycling"],
        "secondary": ["#TourDeFrance", "#BikeRacing"],
        "trending": ["#CyclingLife"]
    },
    "MotoGP": {
        "primary": ["#MotoGP", "#MotorcycleRacing"],
        "secondary": ["#GrandPrix", "#Racing"],
        "trending": ["#MotoGPNews"]
    }
}

# GPT Client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Twitter Client
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

# =========================
# LOGGING (Enhanced)
# =========================

if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[
        RotatingFileHandler('logs/bot_activity.log', maxBytes=10*1024*1024, backupCount=5),
        RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3),
        logging.StreamHandler()
    ]
)

def write_log(message, level="info"):
    """Enhanced logging to both console and persistent file"""
    if level == "error":
        logging.error(message)
    else:
        logging.info(message)

# =========================
# REPLY SYSTEM COMPONENTS
# =========================

class TweetRetriever:
    def __init__(self):
        self.replied_tweets_file = "replied_tweets.txt"
        
    def load_replied_tweets(self):
        """Load list of already replied tweet IDs"""
        if os.path.exists(self.replied_tweets_file):
            with open(self.replied_tweets_file, 'r') as f:
                return set(line.strip() for line in f.readlines())
        return set()
    
    def save_replied_tweet(self, tweet_id):
        """Save tweet ID to avoid duplicate replies"""
        with open(self.replied_tweets_file, 'a') as f:
            f.write(f"{tweet_id}\n")
    
    def get_mentions(self, max_results=3):
        """Get recent mentions (ultra-conservative)"""
        if not quota_manager.can_read(1):
            write_log("Read quota exhausted - cannot get mentions")
            return []
        
        try:
            me = twitter_client.get_me()
            response = twitter_client.get_users_mentions(
                id=me.data.id,
                max_results=max_results,
                tweet_fields=['author_id', 'created_at', 'public_metrics']
            )
            
            quota_manager.use_read(1)
            write_log(f"Retrieved {len(response.data) if response.data else 0} mentions")
            
            return response.data if response.data else []
            
        except Exception as e:
            write_log(f"Error getting mentions: {e}")
            return []
    
    def search_relevant_tweets(self, keywords, max_results=3):
        """Search for tweets (ultra-conservative)"""
        if not quota_manager.can_read(1):
            write_log("Read quota exhausted - cannot search tweets")
            return []
        
        try:
            query = " OR ".join([f'"{keyword}"' for keyword in keywords[:2]])  # Max 2 keywords
            query += " -is:retweet -is:reply lang:en"
            
            response = twitter_client.search_recent_tweets(
                query=query,
                max_results=max_results,
                tweet_fields=['author_id', 'created_at', 'public_metrics']
            )
            
            quota_manager.use_read(1)
            write_log(f"Retrieved {len(response.data) if response.data else 0} tweets for keywords")
            
            return response.data if response.data else []
            
        except Exception as e:
            write_log(f"Error searching tweets: {e}")
            return []

class ReplyGenerator:
    def __init__(self):
        self.reply_strategies = {
            "EPL": {
                "keywords": ["premier league", "arsenal", "football", "epl"],
                "tone": "knowledgeable football fan"
            },
            "F1": {
                "keywords": ["formula1", "f1", "racing"],
                "tone": "racing enthusiast"
            },
            "Crypto": {
                "keywords": ["bitcoin", "crypto", "blockchain"],
                "tone": "crypto analyst"
            },
            "Tesla": {
                "keywords": ["tesla", "electric car", "ev"],
                "tone": "tech enthusiast"
            },
            "Space": {
                "keywords": ["spacex", "nasa", "space"],
                "tone": "space tech fan"
            }
        }
    
    def categorize_tweet(self, tweet_text):
        """Determine the category of a tweet"""
        tweet_lower = tweet_text.lower()
        
        for category, data in self.reply_strategies.items():
            if any(keyword in tweet_lower for keyword in data["keywords"]):
                return category
        
        return "General"
    
    def should_reply_to_tweet(self, tweet):
        """Ultra-selective reply criteria"""
        if not tweet.public_metrics:
            return False
            
        likes = tweet.public_metrics.get('like_count', 0)
        retweets = tweet.public_metrics.get('retweet_count', 0)
        
        # Very selective engagement threshold
        if likes + retweets < 5 or likes + retweets > 500:
            return False
        
        # Only recent tweets
        if tweet.created_at:
            tweet_age = datetime.now(pytz.UTC) - tweet.created_at.replace(tzinfo=pytz.UTC)
            if tweet_age > timedelta(hours=12):
                return False
        
        return True
    
    def generate_reply(self, tweet_text, category):
        """Generate a thoughtful reply"""
        strategy = self.reply_strategies.get(category, {"tone": "helpful"})
        
        prompt = f"""Reply to: "{tweet_text}"

Create a {strategy.get('tone')} reply that:
- Adds genuine value to the conversation
- Shows knowledge without being pushy
- Asks a thoughtful question OR provides insight
- Is under 240 characters
- Feels natural and conversational

Write ONLY the reply text:"""
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Create engaging, valuable Twitter replies."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=80,
                temperature=0.7
            )
            
            reply = response.choices[0].message.content.strip()
            if reply.startswith('"') and reply.endswith('"'):
                reply = reply[1:-1]
            
            return reply
            
        except Exception as e:
            write_log(f"Error generating reply: {e}")
            return None

class ReplyOrchestrator:
    def __init__(self):
        self.retriever = TweetRetriever()
        self.generator = ReplyGenerator()
        self.daily_replies_file = "daily_replies.json"
        self.daily_reads_file = "daily_reads.json"
        
    def load_daily_count(self, file_name, limit_type):
        """Load today's count for replies or reads"""
        today = datetime.now(pytz.UTC).strftime("%Y-%m-%d")
        
        if os.path.exists(file_name):
            with open(file_name, 'r') as f:
                data = json.load(f)
                if data.get("date") == today:
                    return data.get("count", 0)
        
        self.save_daily_count(file_name, 0)
        return 0
    
    def save_daily_count(self, file_name, count):
        """Save today's count"""
        today = datetime.now(pytz.UTC).strftime("%Y-%m-%d")
        data = {"date": today, "count": count}
        
        with open(file_name, 'w') as f:
            json.dump(data, f)
    
    def can_reply_today(self):
        """Check daily limits"""
        daily_replies = self.load_daily_count(self.daily_replies_file, "replies")
        daily_reads = self.load_daily_count(self.daily_reads_file, "reads")
        
        return (daily_replies < DAILY_REPLY_LIMIT and 
                daily_reads < DAILY_READ_LIMIT and 
                quota_manager.can_write(1) and 
                quota_manager.can_read(1))
    
def execute_ultra_conservative_reply_campaign(self):
    """Ultra-conservative reply strategy - prioritize keywords over mentions"""
    if not self.can_reply_today():
        write_log("Daily limits reached (3 reads/3 replies) or quota exhausted")
        return
    
    replied_tweets = self.retriever.load_replied_tweets()
    daily_replies = self.load_daily_count(self.daily_replies_file, "replies")
    daily_reads = self.load_daily_count(self.daily_reads_file, "reads")
    
    # Strategy 1: Keyword searches (highest priority for growth)
    if daily_reads < DAILY_READ_LIMIT and daily_replies < DAILY_REPLY_LIMIT:
        # Rotate through categories - pick one per session
        categories = list(self.generator.reply_strategies.keys())
        selected_category = random.choice(categories)
        keywords = self.generator.reply_strategies[selected_category]["keywords"][:2]
        
        write_log(f"Searching for tweets with {selected_category} keywords: {keywords}")
        tweets = self.retriever.search_relevant_tweets(keywords, max_results=3)
        
        if tweets:  # Only count as read if we got results
            daily_reads += 1
            self.save_daily_count(self.daily_reads_file, daily_reads)
        
        for tweet in tweets:
            if (tweet.id not in replied_tweets and 
                daily_replies < DAILY_REPLY_LIMIT and
                self.generator.should_reply_to_tweet(tweet)):
                
                if self.reply_to_tweet(tweet):
                    daily_replies += 1
                    self.save_daily_count(self.daily_replies_file, daily_replies)
                    replied_tweets.add(tweet.id)
                    self.retriever.save_replied_tweet(tweet.id)
                    break  # Only one reply per campaign
    
    # Strategy 2: Check mentions as backup (if still have quota)
    if daily_reads < DAILY_READ_LIMIT and daily_replies < DAILY_REPLY_LIMIT:
        write_log("Checking mentions as backup strategy")
        mentions = self.retriever.get_mentions(max_results=2)
        
        if mentions:  # Only count as read if we got results
            daily_reads += 1
            self.save_daily_count(self.daily_reads_file, daily_reads)
        
        for tweet in mentions:
            if (tweet.id not in replied_tweets and 
                daily_replies < DAILY_REPLY_LIMIT and
                self.generator.should_reply_to_tweet(tweet)):
                
                if self.reply_to_tweet(tweet):
                    daily_replies += 1
                    self.save_daily_count(self.daily_replies_file, daily_replies)
                    replied_tweets.add(tweet.id)
                    self.retriever.save_replied_tweet(tweet.id)
                    break
    
    write_log(f"Reply campaign completed. Daily usage: {daily_replies}/3 replies, {daily_reads}/3 reads")
    
    def reply_to_tweet(self, tweet):
        """Reply to a specific tweet"""
        try:
            category = self.generator.categorize_tweet(tweet.text)
            reply_text = self.generator.generate_reply(tweet.text, category)
            
            if not reply_text or not quota_manager.can_write(1):
                return False
            
            response = twitter_client.create_tweet(
                text=reply_text,
                in_reply_to_tweet_id=tweet.id
            )
            
            quota_manager.use_write(1)
            write_log(f"Successfully replied to tweet {tweet.id}: {reply_text[:50]}...")
            return True
            
        except Exception as e:
            write_log(f"Error replying to tweet {tweet.id}: {e}")
            return False

# =========================
# MAIN CONTENT POSTING (From Original)
# =========================

def validate_env_vars():
    """Validate required environment variables."""
    required_vars = ["OPENAI_API_KEY", "TWITTER_API_KEY", "TWITTER_API_SECRET", "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        write_log(f"Missing environment variables: {', '.join(missing)}", level="error")
        raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

def get_trending_hashtags(category):
    """Get optimized hashtags for better reach"""
    hashtag_data = TRENDING_HASHTAGS.get(category)
    if not hashtag_data:
        return []
    
    selected = random.sample(hashtag_data["primary"], 1)
    
    if len(hashtag_data["secondary"]) >= 1:
        selected.extend(random.sample(hashtag_data["secondary"], 1))
    
    if random.random() < 0.3 and hashtag_data["trending"]:
        selected.append(random.choice(hashtag_data["trending"]))
    
    return selected[:3]

def optimize_hashtags_for_reach(tweet_text, category):
    """Add optimized hashtags"""
    hashtags = get_trending_hashtags(category)
    
    if not hashtags:
        return tweet_text
    
    available_space = 280 - len(tweet_text) - 5
    hashtag_text = " " + " ".join(hashtags)
    
    if len(hashtag_text) <= available_space:
        return tweet_text + hashtag_text
    
    return tweet_text

def fetch_rss(feed_url):
    """Fetch news from an RSS feed"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(feed_url, headers=headers, timeout=15)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        
        articles = []
        for entry in feed.entries[:3]:  # Reduced to 3
            article = {
                "title": entry.title,
                "url": entry.link,
                "published_parsed": getattr(entry, 'published_parsed', None)
            }
            articles.append(article)
        return articles
    except Exception as e:
        write_log(f"Error fetching RSS from {feed_url}: {e}")
        return []

def get_articles_for_category(category):
    """Get articles for a category"""
    feeds = RSS_FEEDS.get(category, [])
    articles = []
    
    for feed in feeds[:2]:  # Only check first 2 feeds to save time
        feed_articles = fetch_rss(feed)
        if feed_articles:
            articles.extend(feed_articles)
            break  # Stop after first successful feed
    
    write_log(f"Total articles fetched for {category}: {len(articles)}")
    return articles

def is_premium_posting_time():
    """Check if current time is optimal for premium demographics"""
    current_time = datetime.now(pytz.UTC).strftime("%H:%M")
    return current_time in PREMIUM_POSTING_TIMES

def is_global_posting_time():
    """Check if current time is optimal for global audiences"""
    current_time = datetime.now(pytz.UTC).strftime("%H:%M")
    return current_time in GLOBAL_POSTING_TIMES

def should_use_premium_strategy(category):
    """Determine if category should use premium targeting"""
    return category in BUSINESS_CATEGORIES or is_premium_posting_time()

def should_use_global_strategy(category):
    """Determine if category should use global timing strategy"""
    return category in GLOBAL_CATEGORIES or is_global_posting_time()

def generate_premium_targeted_content(title, category, article_url):
    """Generate content specifically appealing to Premium subscribers and professionals"""
    
    strategy = PREMIUM_CONTENT_STRATEGIES.get(category)
    if not strategy:
        # Fallback to regular content generation
        return generate_content_aware_post(title, category, article_url)
    
    # Enhanced prompt for premium demographics
    prompt = f"""Create a Twitter post about: {title}

Target Audience: Business professionals, decision-makers, industry experts
Category: {category}
Focus Areas: {strategy['focus']}
Tone: {strategy['tone']}

Requirements:
- Appeal to professionals and decision-makers
- Focus on strategic implications and business insights
- Include data-driven analysis angles
- End with thought-provoking question: {strategy['cta']}
- Under 200 characters (leave room for URL and hashtags)
- Avoid buzzwords, focus on substance

Examples for {category}:
- "Market implications suggest..."
- "Strategic analysis reveals..."
- "Industry data shows..."
- "This reshapes how we think about..."

Write ONLY the tweet text:"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"You create content for business professionals and industry experts. Focus on strategic insights, market implications, and data-driven analysis that appeals to decision-makers in {category}."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=120,
            temperature=0.7  # Slightly lower for more professional tone
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        write_log(f"Premium content generation failed: {e}")
        # Fallback to regular content generation
        return generate_content_aware_post(title, category, article_url)

def detect_category_with_timing_strategy():
    """Select category with enhanced logic for premium/global times"""
    categories = list(RSS_FEEDS.keys())
    
    # During premium posting times, prioritize business-relevant categories
    if is_premium_posting_time():
        priority_categories = BUSINESS_CATEGORIES
        available_priority = [cat for cat in priority_categories if cat in categories]
        if available_priority and random.random() < 0.7:  # 70% chance for priority
            category = random.choice(available_priority)
            write_log(f"Selected business category for premium time: {category}")
            return category
    
    # During global posting times, prioritize global categories
    if is_global_posting_time():
        priority_categories = GLOBAL_CATEGORIES
        available_priority = [cat for cat in priority_categories if cat in categories]
        if available_priority and random.random() < 0.7:  # 70% chance for priority
            category = random.choice(available_priority)
            write_log(f"Selected global category for global time: {category}")
            return category
    
    # Regular random selection
    category = random.choice(categories)
    write_log(f"Selected category: {category}")
    return category

def generate_content_aware_post(title, category, article_url):
    """Generate viral-worthy posts"""
    try:
        prompt = f"""Create an engaging Twitter post about: {title}

Category: {category}
Requirements:
- Under 200 characters (leave room for URL and hashtags)
- Ask thought-provoking questions
- Create curiosity or controversy
- Drive engagement and replies

Write ONLY the tweet text:"""

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Create viral Twitter content that drives engagement."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.8
        )
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        write_log(f"GPT generation failed: {e}")
        return f"Breaking: {title[:100]}... What's your take?"

def has_been_posted(url):
    """Check if URL already posted"""
    if not os.path.exists(POSTED_LOG):
        return False
    with open(POSTED_LOG, "r") as f:
        return url.strip() in f.read()

def log_posted(url):
    """Record posted URL"""
    with open(POSTED_LOG, "a") as f:
        f.write(url.strip() + "\n")

def can_post_now():
    """Check if enough time has passed since last post"""
    global last_post_time
    if last_post_time is None:
        return True
    time_since_last = datetime.now(pytz.UTC) - last_post_time
    return time_since_last.total_seconds() >= (POST_INTERVAL_MINUTES * 60)

def shorten_url_with_fallback(long_url):
    """URL shortening with fallback"""
    try:
        api_url = f"http://tinyurl.com/api-create.php?url={long_url}"
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200 and response.text.strip().startswith('http'):
            return response.text.strip()
    except:
        pass
    return long_url

def post_main_content(category):
    """Post main content using write quota with premium/global strategies"""
    global last_post_time
    
    if not can_post_now() or not quota_manager.can_write(1):
        write_log("Cannot post - rate limited or quota exhausted")
        return False
    
    articles = get_articles_for_category(category)
    
    for article in articles:
        if has_been_posted(article["url"]):
            continue
        
        # Choose content generation strategy based on timing and category
        if should_use_premium_strategy(category):
            write_log(f"Using premium strategy for {category} at {datetime.now(pytz.UTC).strftime('%H:%M')}")
            tweet_text = generate_premium_targeted_content(article["title"], category, article["url"])
        else:
            write_log(f"Using standard strategy for {category}")
            tweet_text = generate_content_aware_post(article["title"], category, article["url"])
        
        short_url = shorten_url_with_fallback(article["url"])
        full_tweet = f"{tweet_text}\n\n{short_url}"
        full_tweet = optimize_hashtags_for_reach(full_tweet, category)
        
        if len(full_tweet) > 280:
            full_tweet = full_tweet[:277] + "..."
        
        try:
            response = twitter_client.create_tweet(text=full_tweet)
            quota_manager.use_write(1)
            log_posted(article["url"])
            last_post_time = datetime.now(pytz.UTC)
            
            timing_type = "premium" if is_premium_posting_time() else "global" if is_global_posting_time() else "standard"
            write_log(f"Posted {timing_type} content for {category}: {article['title'][:50]}...")
            return True
            
        except Exception as e:
            write_log(f"Error posting main content: {e}")
            return False
    
    write_log(f"No new articles to post for {category}")
    return False

# =========================
# SCHEDULER SYSTEM
# =========================

def should_post_main_content():
    """Check if it's time for main content"""
    current_time = datetime.now(pytz.UTC).strftime("%H:%M")
    return current_time in MAIN_POSTING_TIMES

def should_run_reply_campaign():
    """Check if it's time for reply campaign"""
    current_time = datetime.now(pytz.UTC).strftime("%H:%M")
    return current_time in REPLY_CAMPAIGN_TIMES

def run_main_content_job():
    """Run main content posting job with strategic timing"""
    try:
        write_log("Starting strategic main content job...")
        
        # Log current timing context
        current_time = datetime.now(pytz.UTC).strftime("%H:%M")
        is_premium = is_premium_posting_time()
        is_global = is_global_posting_time()
        
        write_log(f"Current time: {current_time} (Premium: {is_premium}, Global: {is_global})")
        
        # Use strategic category selection
        category = detect_category_with_timing_strategy()
        
        success = post_main_content(category)
        if not success:
            # Try one backup category with same strategic logic
            categories = list(RSS_FEEDS.keys())
            backup_categories = [cat for cat in categories if cat != category]
            if backup_categories and quota_manager.can_write(1):
                backup_category = random.choice(backup_categories)
                write_log(f"Trying backup category: {backup_category}")
                post_main_content(backup_category)
        
        write_log("Strategic main content job completed")
    except Exception as e:
        write_log(f"Error in main content job: {e}")

def run_reply_job():
    """Run reply campaign job"""
    try:
        write_log("Starting ultra-conservative reply campaign...")
        reply_orchestrator = ReplyOrchestrator()
        reply_orchestrator.execute_ultra_conservative_reply_campaign()
        write_log("Reply campaign completed")
    except Exception as e:
        write_log(f"Error in reply campaign: {e}")

def start_conservative_scheduler():
    """Ultra-conservative scheduler with premium/global timing strategies"""
    write_log("Starting ultra-conservative scheduler with strategic timing...")
    write_log(f"Premium posting times (business focus): {PREMIUM_POSTING_TIMES}")
    write_log(f"Global posting times (sports/entertainment): {GLOBAL_POSTING_TIMES}")
    write_log(f"Reply campaign times (3/day): {REPLY_CAMPAIGN_TIMES}")
    write_log(f"Business categories: {BUSINESS_CATEGORIES}")
    write_log(f"Global categories: {GLOBAL_CATEGORIES}")
    
    quota_status = quota_manager.get_quota_status()
    write_log(f"Monthly quota: {quota_status}")
    
    last_checked_minute = None
    
    while True:
        try:
            current_minute = datetime.now(pytz.UTC).strftime("%H:%M")
            
            if current_minute != last_checked_minute:
                write_log(f"Checking time: {current_minute} against {len(MAIN_POSTING_TIMES + REPLY_CAMPAIGN_TIMES)} scheduled times")
                
                # Check for main content posting
                if should_post_main_content():
                    timing_type = "PREMIUM" if is_premium_posting_time() else "GLOBAL" if is_global_posting_time() else "STANDARD"
                    write_log(f"{timing_type} content time: {current_minute}")
                    run_main_content_job()
                
                # Check for reply campaigns
                elif should_run_reply_campaign():
                    write_log(f"Reply campaign time: {current_minute}")
                    run_reply_job()
                
                last_checked_minute = current_minute
                
            time.sleep(30)
            
        except Exception as e:
            write_log(f"ERROR in scheduler loop: {e}")
            time.sleep(60)

# =========================
# HEALTH SERVER
# =========================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        
        quota_status = quota_manager.get_quota_status()
        status = f"""Ultra-Conservative Twitter Bot Status: RUNNING

Monthly Quota:
- Reads: {quota_status['reads_used']}/100 ({quota_status['reads_remaining']} remaining)
- Writes: {quota_status['writes_used']}/500 ({quota_status['writes_remaining']} remaining)

Daily Allocation:
- Main Posts: 12/day (360/month)
- Replies: 3/day (90/month)
- Emergency Buffer: 50/month

Features:
- Threading: DISABLED
- Conservative Reply System: ENABLED
- Smart Quota Management: ACTIVE

Last Post: {last_post_time or 'Never'}
        """
        self.wfile.write(status.encode())
    
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
    
    def log_message(self, format, *args):
        pass

def start_health_server():
    """Start health check server"""
    port = int(os.environ.get('PORT', 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        write_log(f"Health server starting on port {port}")
        server.serve_forever()
    except Exception as e:
        write_log(f"Health server failed to start: {e}")

# =========================
# TESTING FUNCTIONS
# =========================

def test_quota_system():
    """Test quota management system"""
    write_log("=== TESTING QUOTA SYSTEM ===")
    status = quota_manager.get_quota_status()
    write_log(f"Current quota: {status}")
    
    # Test read quota
    can_read = quota_manager.can_read(1)
    write_log(f"Can read (1): {can_read}")
    
    # Test write quota
    can_write = quota_manager.can_write(1)
    write_log(f"Can write (1): {can_write}")
    
    write_log("=== QUOTA TEST COMPLETE ===")

def test_reply_system():
    """Test reply system without using quota"""
    write_log("=== TESTING REPLY SYSTEM ===")
    
    orchestrator = ReplyOrchestrator()
    
    # Test daily limits
    daily_replies = orchestrator.load_daily_count(orchestrator.daily_replies_file, "replies")
    daily_reads = orchestrator.load_daily_count(orchestrator.daily_reads_file, "reads")
    
    write_log(f"Daily replies used: {daily_replies}/3")
    write_log(f"Daily reads used: {daily_reads}/3")
    write_log(f"Can reply today: {orchestrator.can_reply_today()}")
    
    write_log("=== REPLY SYSTEM TEST COMPLETE ===")

def test_main_content_system():
    """Test main content system"""
    write_log("=== TESTING MAIN CONTENT SYSTEM ===")
    
    # Test category selection
    categories = list(RSS_FEEDS.keys())
    selected = random.choice(categories)
    write_log(f"Selected category: {selected}")
    
    # Test article fetching
    articles = get_articles_for_category(selected)
    write_log(f"Fetched {len(articles)} articles")
    
    # Test hashtag optimization
    test_text = "This is a test tweet"
    optimized = optimize_hashtags_for_reach(test_text, selected)
    write_log(f"Hashtag optimization: {optimized}")
    
    write_log("=== MAIN CONTENT TEST COMPLETE ===")

def test_auth():
    """Test Twitter API authentication"""
    try:
        me = twitter_api.verify_credentials()
        write_log(f"Authentication successful! @{me.screen_name}")
        write_log(f"Followers: {me.followers_count}")
        return True
    except Exception as e:
        write_log(f"Authentication failed: {e}")
        return False

def run_single_test_post():
    """Test posting a single tweet (uses quota)"""
    write_log("=== TESTING SINGLE POST ===")
    
    if not quota_manager.can_write(1):
        write_log("Cannot test - write quota exhausted")
        return False
    
    categories = list(RSS_FEEDS.keys())
    category = random.choice(categories)
    
    result = post_main_content(category)
    write_log(f"Test post result: {result}")
    
    return result

def run_single_test_reply():
    """Test reply system (uses quota)"""
    write_log("=== TESTING SINGLE REPLY ===")
    
    if not quota_manager.can_read(1) or not quota_manager.can_write(1):
        write_log("Cannot test - quota exhausted")
        return False
    
    orchestrator = ReplyOrchestrator()
    orchestrator.execute_ultra_conservative_reply_campaign()
    
    return True

# =========================
# MAIN EXECUTION
# =========================

if __name__ == "__main__":
    write_log("=== ULTRA-CONSERVATIVE TWITTER BOT STARTUP ===")
    
    # Validate environment
    validate_env_vars()
    
    # Test authentication
    if not test_auth():
        write_log("CRITICAL: Authentication failed. Bot cannot run.")
        exit(1)
    
    # Display startup info
    quota_status = quota_manager.get_quota_status()
    write_log("=== QUOTA STATUS ===")
    write_log(f"Monthly reads: {quota_status['reads_used']}/100 ({quota_status['reads_remaining']} remaining)")
    write_log(f"Monthly writes: {quota_status['writes_used']}/500 ({quota_status['writes_remaining']} remaining)")
    
    write_log("=== ULTRA-CONSERVATIVE FEATURES ===")
    write_log("✓ Main posts: 12/day (360/month)")
    write_log("✓ Replies: 3/day (90/month)")
    write_log("✓ Reads: 3/day (90/month)")
    write_log("✓ Emergency buffer: 50 writes/month")
    write_log("✓ Smart quota management active")
    write_log("✗ Threading disabled")
    
    # Start health server in background
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Uncomment for testing (WARNING: Uses real quota):
    # test_quota_system()
    # test_reply_system()
    # test_main_content_system()
    # run_single_test_post()  # Uses 1 write quota
    # run_single_test_reply()  # Uses 1 read + 1 write quota
    
    # Start the ultra-conservative scheduler
    write_log("Starting ultra-conservative scheduler...")
    start_conservative_scheduler()








