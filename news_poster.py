"""
Crypto-Exclusive Self-Learning Twitter Bot with High-Engagement Strategies
API Limits: 100 reads/month (3/day), 500 writes/month (15 posts/day)
Enhanced with crypto-specific engagement tactics
"""

import os
import random
import requests
import feedparser
import tweepy
import time
import json
from datetime import datetime, timedelta
import pytz
from newspaper import Article, Config
from openai import OpenAI
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Load environment variables
try:
    if os.path.exists('.env'):
        load_dotenv()
        print("INFO: .env file loaded successfully")
    else:
        print("INFO: No .env file found, using system environment variables")
except Exception as e:
    print(f"INFO: Could not load .env file: {e}")

# =========================
# PERSISTENT STORAGE CONFIGURATION
# =========================

STORAGE_PATH = os.getenv("PERSISTENT_STORAGE_PATH", ".")

try:
    os.makedirs(STORAGE_PATH, exist_ok=True)
    print(f"INFO: Using persistent storage path: {STORAGE_PATH}")
except Exception as e:
    print(f"WARNING: Could not create storage directory: {e}")
    STORAGE_PATH = "."

# =========================
# API QUOTA MANAGEMENT
# =========================

class APIQuotaManager:
    def __init__(self):
        self.quota_file = os.path.join(STORAGE_PATH, "api_quota.json")
        self.load_quota()
    
    def load_quota(self):
        """Load current month's quota usage"""
        try:
            if os.path.exists(self.quota_file):
                with open(self.quota_file, 'r') as f:
                    data = json.load(f)
                
                current_month = datetime.now(pytz.UTC).strftime("%Y-%m")
                if data.get("month") != current_month:
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
        """Check if we can make read requests"""
        return (self.quota["reads_used"] + count) <= 100
    
    def can_write(self, count=1):
        """Check if we can make write requests"""
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
# CONFIGURATION
# =========================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")

quota_manager = APIQuotaManager()
learning_system = PerformanceLearningSystem()

LOG_FILE = "bot_log.txt"
POSTED_LOG = os.path.join(STORAGE_PATH, "posted_links.txt")

DAILY_POST_LIMIT = 15
POST_INTERVAL_MINUTES = 90
last_post_time = None

# CRYPTO-OPTIMIZED POSTING TIMES (US + Asian markets)
POSTING_TIMES = [
    "01:00",  # Asian morning
    "06:00",  # Asian afternoon
    "09:00",  # US pre-market
    "13:00",  # US lunch
    "14:00",  # US afternoon
    "17:00",  # US evening
    "21:00",  # US night / Asian early morning
    "23:00"   # US late night / Asian morning
]

# CRYPTO CONTENT TYPES (based on engagement strategy)
CRYPTO_CONTENT_TYPES = [
    "educational",      # "Here's how X works"
    "market_analysis",  # "Why BTC is doing X"
    "contrarian",       # "Everyone's wrong about..."
    "question",         # "Which do you prefer: X or Y?"
    "hot_take",         # Bold controversial opinions
    "breakdown"         # "5 things about..."
]

# CRYPTO RSS FEEDS
RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://crypto.news/feed/",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/.rss/full/"
]

# CRYPTO HASHTAGS
CRYPTO_HASHTAGS = {
    "primary": ["#Crypto", "#Bitcoin", "#Ethereum", "#BTC", "#ETH"],
    "trending": ["#CryptoNews", "#Blockchain", "#DeFi", "#Web3", "#Altcoins"],
    "specific": ["#Solana", "#Cardano", "#Polygon", "#BNB", "#XRP"]
}

# =========================
# CRYPTO ENGAGEMENT STRATEGIES
# =========================

CRYPTO_ENGAGEMENT_TEMPLATES = {
    "question": [
        "Which would you choose: {option1} or {option2}?",
        "Quick poll: {option1} vs {option2}?",
        "Honest question: {option1} or {option2}?",
        "You can only pick one: {option1} or {option2}. Which is it?",
        "{question} Drop your answer below 👇"
    ],
    
    "hot_take": [
        "Unpopular opinion: {statement}",
        "Hot take: {statement}",
        "Controversial but true: {statement}",
        "Nobody wants to hear this but {statement}",
        "Real talk: {statement}"
    ],
    
    "contrarian": [
        "Everyone's wrong about {topic}. Here's why:",
        "The truth about {topic} that nobody talks about:",
        "Why {mainstream_belief} is actually backwards:",
        "Unpopular opinion: {topic} is completely misunderstood",
        "Let's be honest about {topic}:"
    ],
    
    "educational": [
        "Here's how {concept} actually works:",
        "Understanding {concept} in simple terms:",
        "{concept} explained (no BS):",
        "Quick breakdown: {concept}",
        "What you need to know about {concept}:"
    ],
    
    "market_analysis": [
        "Why {coin} is {movement} today:",
        "What's really driving {coin}'s {movement}:",
        "The real reason behind {coin}'s {movement}:",
        "{coin} {movement} - here's what's happening:",
        "Breaking down {coin}'s {movement}:"
    ],
    
    "breakdown": [
        "5 things about {topic} you need to know:",
        "3 reasons why {topic} matters:",
        "The top {number} signs of {topic}:",
        "{number} facts about {topic} that will surprise you:",
        "Here are {number} things everyone gets wrong about {topic}:"
    ]
}

CRYPTO_QUESTION_TEMPLATES = [
    "Bitcoin or Ethereum for the next 5 years?",
    "DeFi or CeFi - which is the future?",
    "Would you rather: 10 BTC in 2010 or $10M cash today?",
    "Bull market or bear market - which teaches you more?",
    "Holding or trading - which makes you more money?",
    "Layer 1 or Layer 2 - where's the real opportunity?",
    "Staking or lending - which is better for passive income?",
    "Privacy coins: necessary innovation or regulatory nightmare?"
]

CRYPTO_HOT_TAKES = [
    "Most crypto 'investors' are just gamblers with better vocabulary",
    "The next bull run will look nothing like the last one",
    "NFTs solved a real problem, people just hate the art",
    "Regulation will make crypto bigger, not smaller",
    "99% of altcoins will go to zero",
    "The real crypto wealth is made in bear markets",
    "Technical analysis in crypto is modern astrology"
]

CRYPTO_EMOJIS = ["₿", "💎", "🚀", "📊", "📈", "📉", "⚡", "🔥", "💰", "🎯"]

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

# =========================
# LOGGING
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
# CRYPTO CONTENT GENERATION
# =========================

def generate_crypto_question(title):
    """Generate engaging question-based content"""
    template = random.choice(CRYPTO_ENGAGEMENT_TEMPLATES["question"])
    
    # Use GPT to extract key concepts for comparison
    prompt = f"""Based on this crypto news: "{title}"

Create a simple, engaging question that makes people want to reply.
Format: "X or Y?" where X and Y are two clear choices.
Keep it under 150 characters.

Write ONLY the question:"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You create engaging crypto questions that drive replies. Be concise and force a choice."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=60,
            temperature=0.8
        )
        return response.choices[0].message.content.strip()
    except:
        return random.choice(CRYPTO_QUESTION_TEMPLATES)

def generate_crypto_hot_take(title):
    """Generate bold, controversial takes"""
    prompt = f"""Based on this crypto news: "{title}"

Create a bold, controversial take that sparks debate.
Start with: "Unpopular opinion:", "Hot take:", or "Real talk:"
Be provocative but not offensive.
Under 200 characters.

Write ONLY the tweet:"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You create controversial but insightful crypto takes that drive engagement through debate."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=80,
            temperature=0.9
        )
        return response.choices[0].message.content.strip()
    except:
        return f"Hot take: {random.choice(CRYPTO_HOT_TAKES)}"

def generate_contrarian_take(title):
    """Generate contrarian analysis"""
    template = random.choice(CRYPTO_ENGAGEMENT_TEMPLATES["contrarian"])
    
    prompt = f"""Based on this crypto news: "{title}"

Create a contrarian take that challenges mainstream thinking.
Be thought-provoking and data-driven if possible.
Under 200 characters.

Write ONLY the tweet:"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You create contrarian crypto analysis that challenges mainstream narratives."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=80,
            temperature=0.8
        )
        return response.choices[0].message.content.strip()
    except:
        return f"Everyone's wrong about {title[:50]}... here's why:"

def generate_educational_breakdown(title):
    """Generate educational content"""
    prompt = f"""Based on this crypto news: "{title}"

Create an educational tweet that breaks down a concept.
Start with "Here's how..." or "Understanding..."
Make it accessible and valuable.
Under 200 characters.

Write ONLY the tweet:"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You create educational crypto content that's easy to understand and valuable."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=80,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except:
        return f"Here's what {title[:60]} actually means:"

def generate_market_analysis(title):
    """Generate market analysis content"""
    prompt = f"""Based on this crypto news: "{title}"

Create a market analysis tweet explaining the "why" behind the move.
Focus on causes and implications.
Under 200 characters.

Write ONLY the tweet:"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You create insightful crypto market analysis that explains price movements and trends."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=80,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except:
        return f"Why this matters for crypto: {title[:80]}"

def generate_listicle_thread(title):
    """Generate list-based content"""
    numbers = ["3", "5", "7"]
    number = random.choice(numbers)
    
    prompt = f"""Based on this crypto news: "{title}"

Create a tweet announcing a {number}-point breakdown.
Format: "{number} things about [topic]:"
Make it compelling and promise value.
Under 180 characters.

Write ONLY the tweet:"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You create compelling list-based crypto content that drives saves and shares."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=70,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except:
        return f"{number} things you need to know about {title[:60]}"

def generate_crypto_content(title, content_type):
    """Main content generation router"""
    generators = {
        "question": generate_crypto_question,
        "hot_take": generate_crypto_hot_take,
        "contrarian": generate_contrarian_take,
        "educational": generate_educational_breakdown,
        "market_analysis": generate_market_analysis,
        "breakdown": generate_listicle_thread
    }
    
    generator = generators.get(content_type, generate_educational_breakdown)
    return generator(title)

def add_crypto_visual_elements(tweet_text):
    """Add crypto-specific emojis"""
    # Don't add if already has emoji
    if any(emoji in tweet_text for emoji in CRYPTO_EMOJIS):
        return tweet_text
    
    # Add context-appropriate emoji
    text_lower = tweet_text.lower()
    
    if any(word in text_lower for word in ["bitcoin", "btc"]):
        return f"₿ {tweet_text}"
    elif any(word in text_lower for word in ["up", "surge", "pump", "bull"]):
        return f"📈 {tweet_text}"
    elif any(word in text_lower for word in ["down", "dump", "bear", "crash"]):
        return f"📉 {tweet_text}"
    elif any(word in text_lower for word in ["analysis", "breakdown", "data"]):
        return f"📊 {tweet_text}"
    elif any(word in text_lower for word in ["hot", "fire", "controversial"]):
        return f"🔥 {tweet_text}"
    else:
        return f"{random.choice(CRYPTO_EMOJIS)} {tweet_text}"

def get_crypto_hashtags():
    """Get optimized crypto hashtags"""
    selected = random.sample(CRYPTO_HASHTAGS["primary"], 2)
    
    if random.random() < 0.4:
        selected.append(random.choice(CRYPTO_HASHTAGS["trending"]))
    
    if random.random() < 0.2:
        selected.append(random.choice(CRYPTO_HASHTAGS["specific"]))
    
    return selected[:3]

def optimize_hashtags(tweet_text):
    """Add hashtags if space allows"""
    hashtags = get_crypto_hashtags()
    available_space = 280 - len(tweet_text) - 5
    hashtag_text = " " + " ".join(hashtags)
    
    if len(hashtag_text) <= available_space:
        return tweet_text + hashtag_text
    
    return tweet_text

# =========================
# CONTENT FETCHING & POSTING
# =========================

def fetch_rss(feed_url):
    """Fetch news from RSS feed"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(feed_url, headers=headers, timeout=15)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        
        articles = []
        for entry in feed.entries[:5]:
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

def get_crypto_articles():
    """Get crypto articles from all feeds"""
    articles = []
    
    for feed in RSS_FEEDS:
        feed_articles = fetch_rss(feed)
        if feed_articles:
            articles.extend(feed_articles)
    
    write_log(f"Total crypto articles fetched: {len(articles)}")
    return articles

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

def shorten_url(long_url):
    """URL shortening with fallback"""
    try:
        api_url = f"http://tinyurl.com/api-create.php?url={long_url}"
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200 and response.text.strip().startswith('http'):
            return response.text.strip()
    except:
        pass
    return long_url

def post_crypto_content():
    """Main posting function with learning integration"""
    global last_post_time
    
    if not can_post_now() or not quota_manager.can_write(1):
        write_log("Cannot post - rate limited or quota exhausted")
        return False
    
    # Get recommended content type from learning
    content_type = learning_system.get_recommended_content_type()
    write_log(f"🎯 Selected content type: {content_type}")
    
    articles = get_crypto_articles()
    
    for article in articles:
        if has_been_posted(article["url"]):
            continue
        
        # Generate content based on type
        tweet_text = generate_crypto_content(article["title"], content_type)
        
        # Add visual elements
        tweet_text = add_crypto_visual_elements(tweet_text)
        
        # Add URL
        short_url = shorten_url(article["url"])
        full_tweet = f"{tweet_text}\n\n{short_url}"
        
        # Add hashtags
        full_tweet = optimize_hashtags(full_tweet)
        
        # Extract hashtags for tracking
        hashtags = [word for word in full_tweet.split() if word.startswith('#')]
        
        # Truncate if needed
        if len(full_tweet) > 280:
            full_tweet = full_tweet[:277] + "..."
        
        # Determine engagement style
        engagement_style = "standard"
        if "?" in tweet_text:
            engagement_style = "question"
        elif any(phrase in tweet_text.lower() for phrase in ["hot take", "unpopular", "controversial"]):
            engagement_style = "provocative"
        elif any(phrase in tweet_text.lower() for phrase in ["here's how", "understanding", "breakdown"]):
            engagement_style = "educational"
        
        # Post tweet
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                response = twitter_client.create_tweet(text=full_tweet)
                tweet_id = response.data['id']
                
                quota_manager.use_write(1)
                log_posted(article["url"])
                last_post_time = datetime.now(pytz.UTC)
                
                # Record for learning
                current_time = datetime.now(pytz.UTC).strftime("%H:%M")
                learning_system.record_tweet_posted(
                    tweet_id=tweet_id,
                    tweet_text=full_tweet,
                    content_type=content_type,
                    time_slot=current_time,
                    hashtags=hashtags,
                    engagement_style=engagement_style
                )
                
                write_log(f"✅ Posted {content_type} ({engagement_style}): {article['title'][:50]}...")
                return True
                
            except Exception as e:
                error_msg = str(e)
                
                if "403" in error_msg or "forbidden" in error_msg.lower():
                    write_log(f"403 Forbidden error - check API permissions")
                    return False
                elif "duplicate" in error_msg.lower():
                    write_log("Duplicate content detected")
                    return False
                elif attempt < max_retries - 1:
                    write_log(f"Network error on attempt {attempt + 1}/{max_retries}: {error_msg}")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    write_log(f"All {max_retries} retry attempts failed: {e}")
                    return False
    
    write_log(f"No new crypto articles to post")
    return False

# =========================
# SCHEDULER
# =========================

def should_post_now():
    """Check if it's an optimal posting time"""
    current_time = datetime.now(pytz.UTC).strftime("%H:%M")
    return current_time in POSTING_TIMES

def run_posting_job():
    """Main posting job with learning"""
    try:
        write_log("🚀 Starting crypto posting job...")
        
        # Run performance analysis if needed
        if learning_system.should_analyze_performance():
            write_log("🧠 Running performance analysis...")
            learning_system.analyze_performance()
        
        # Post content
        success = post_crypto_content()
        
        if not success and quota_manager.can_write(1):
            write_log("Retrying with different content type...")
            time.sleep(5)
            post_crypto_content()
        
        write_log("✅ Crypto posting job completed")
    except Exception as e:
        write_log(f"Error in posting job: {e}")

def start_scheduler():
    """Main scheduler with continuous monitoring"""
    write_log("🚀 Starting CRYPTO-FOCUSED scheduler...")
    write_log("="*60)
    write_log("Niche: CRYPTO ONLY")
    write_log("Learning system: ACTIVE")
    write_log(f"Posting times (UTC): {POSTING_TIMES}")
    write_log(f"Content types: {CRYPTO_CONTENT_TYPES}")
    write_log("Engagement strategy: Questions, Hot Takes, Contrarian Views")
    write_log("="*60)
    
    quota_status = quota_manager.get_quota_status()
    write_log(f"Monthly quota: {quota_status}")
    
    if learning_system.performance_data["total_analyzed"] > 0:
        write_log(f"🎓 Learning status: {learning_system.performance_data['total_analyzed']} tweets analyzed")
        learning_system._log_key_insights()
    else:
        write_log("🎓 Learning status: Gathering initial data...")
    
    last_checked_minute = None
    last_heartbeat = datetime.now(pytz.UTC)
    heartbeat_interval = 300  # 5 minutes
    loop_count = 0
    
    while True:
        try:
            current_time = datetime.now(pytz.UTC)
            current_minute = current_time.strftime("%H:%M")
            loop_count += 1
            
            # Heartbeat
            if (current_time - last_heartbeat).total_seconds() >= heartbeat_interval:
                quota_status = quota_manager.get_quota_status()
                write_log(f"💓 HEARTBEAT #{loop_count} - Bot running | Time: {current_minute} UTC | "
                         f"Writes: {quota_status['writes_used']}/500 | "
                         f"Reads: {quota_status['reads_used']}/100 | "
                         f"Analyzed: {learning_system.performance_data['total_analyzed']} tweets")
                last_heartbeat = current_time
            
            # Check for posting time
            if current_minute != last_checked_minute:
                write_log(f"🕐 Time check: {current_minute} UTC (Loop #{loop_count})")
                
                if should_post_now():
                    write_log(f"⏰ Posting time: {current_minute}")
                    run_posting_job()
                
                last_checked_minute = current_minute
            
            time.sleep(30)
            
        except KeyboardInterrupt:
            write_log("⚠️  Keyboard interrupt detected - shutting down gracefully...")
            raise
        except Exception as e:
            write_log(f"❌ ERROR in scheduler loop: {e}", level="error")
            write_log("Continuing after 60 second cooldown...")
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
        learning_status = learning_system.performance_data
        
        status = f"""Crypto-Focused Twitter Bot: RUNNING

=== MONTHLY QUOTA ===
Reads: {quota_status['reads_used']}/100 ({quota_status['reads_remaining']} remaining)
Writes: {quota_status['writes_used']}/500 ({quota_status['writes_remaining']} remaining)

=== DAILY ALLOCATION ===
Posts: ~15/day (450/month)
Emergency Buffer: 50/month

=== LEARNING SYSTEM ===
Status: ACTIVE
Tweets Analyzed: {learning_status['total_analyzed']}
Last Analysis: {learning_status['last_analysis'] or 'Never'}
Pending Analysis: {len([t for t in learning_status['tweets'] if not t['analyzed']])} tweets

=== LEARNING INSIGHTS ==="""

        if learning_system.insights.get("content_type_performance"):
            sorted_types = sorted(
                learning_system.insights["content_type_performance"].items(),
                key=lambda x: x[1]["avg_engagement"],
                reverse=True
            )
            if sorted_types:
                status += f"\nTop Content Type: {sorted_types[0][0]} (avg: {sorted_types[0][1]['avg_engagement']:.2f})"
        
        if learning_system.insights.get("engagement_style_scores"):
            sorted_styles = sorted(
                learning_system.insights["engagement_style_scores"].items(),
                key=lambda x: x[1]["avg_engagement"],
                reverse=True
            )
            if sorted_styles:
                status += f"\nTop Engagement Style: {sorted_styles[0][0]} (avg: {sorted_styles[0][1]['avg_engagement']:.2f})"

        status += f"""

=== CRYPTO FEATURES ===
✓ Multi-format content (questions, hot takes, analysis)
✓ Engagement-optimized posting times (US + Asia)
✓ Self-learning content optimization
✓ Performance tracking & adaptation
✓ Smart hashtag optimization
✓ Crypto-specific emojis

=== CONTENT TYPES ===
• Questions (drive replies)
• Hot Takes (spark debate)
• Contrarian Views (challenge thinking)
• Educational (build authority)
• Market Analysis (timely insights)
• Breakdowns/Lists (saves & shares)

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

def test_auth():
    """Test Twitter API authentication"""
    try:
        me = twitter_api.verify_credentials()
        write_log(f"✅ Authentication successful! @{me.screen_name}")
        write_log(f"Followers: {me.followers_count}")
        return True
    except Exception as e:
        write_log(f"❌ Authentication failed: {e}")
        return False

def test_content_generation():
    """Test crypto content generation"""
    write_log("Testing content generation...")
    
    test_title = "Bitcoin surges past $50K as institutional adoption accelerates"
    
    for content_type in CRYPTO_CONTENT_TYPES:
        try:
            content = generate_crypto_content(test_title, content_type)
            write_log(f"✓ {content_type}: {content[:60]}...")
        except Exception as e:
            write_log(f"✗ {content_type}: {e}")
    
    return True

def validate_env_vars():
    """Validate required environment variables"""
    required_vars = [
        "OPENAI_API_KEY", 
        "TWITTER_API_KEY", 
        "TWITTER_API_SECRET", 
        "TWITTER_ACCESS_TOKEN", 
        "TWITTER_ACCESS_SECRET"
    ]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        write_log(f"Missing environment variables: {', '.join(missing)}", level="error")
        raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

# =========================
# MAIN EXECUTION
# =========================

if __name__ == "__main__":
    write_log("="*60)
    write_log("🚀 CRYPTO-FOCUSED TWITTER BOT STARTUP")
    write_log("="*60)
    
    try:
        validate_env_vars()
        write_log("✅ Environment variables validated")
    except Exception as e:
        write_log(f"❌ Environment validation failed: {e}")
        exit(1)
    
    if not test_auth():
        write_log("CRITICAL: Authentication failed. Bot cannot run.")
        exit(1)
    
    test_content_generation()
    
    quota_status = quota_manager.get_quota_status()
    write_log("")
    write_log("=== QUOTA STATUS ===")
    write_log(f"Monthly reads: {quota_status['reads_used']}/100 ({quota_status['reads_remaining']} remaining)")
    write_log(f"Monthly writes: {quota_status['writes_used']}/500 ({quota_status['writes_remaining']} remaining)")
    
    write_log("")
    write_log("=== CRYPTO SPECIALIZATION ===")
    write_log("✓ 100% crypto-focused content")
    write_log("✓ 6 high-engagement content formats")
    write_log("✓ Optimized for US + Asian crypto markets")
    write_log("✓ Questions drive replies")
    write_log("✓ Hot takes spark debate")
    write_log("✓ Educational builds authority")
    write_log("✓ Market analysis provides value")
    
    write_log("")
    write_log("=== ENGAGEMENT STRATEGY ===")
    write_log("📊 Content mix:")
    write_log("   • 30% Questions (replies)")
    write_log("   • 25% Hot Takes (debate)")
    write_log("   • 20% Educational (saves)")
    write_log("   • 15% Market Analysis (shares)")
    write_log("   • 10% Contrarian (controversy)")
    
    write_log("")
    write_log("=== POSTING TIMES (UTC) ===")
    for time_slot in POSTING_TIMES:
        write_log(f"   • {time_slot}")
    
    write_log("")
    write_log("Starting health check server...")
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    write_log("")
    write_log("="*60)
    write_log("🚀 STARTING CRYPTO SCHEDULER")
    write_log("="*60)
    write_log("")
    
    try:
        start_scheduler()
    except KeyboardInterrupt:
        write_log("")
        write_log("="*60)
        write_log("🛑 Bot stopped by user")
        write_log("="*60)
        
        learning_system.save_performance_data()
        learning_system.save_learning_insights()
        
        write_log("✅ Learning data saved successfully")
        write_log(f"📊 Total tweets recorded: {len(learning_system.performance_data['tweets'])}")
        write_log(f"📈 Total tweets analyzed: {learning_system.performance_data['total_analyzed']}")
    except Exception as e:
        write_log(f"❌ Critical error: {e}")
        
        learning_system.save_performance_data()
        learning_system.save_learning_insights()
        
        exit(1)
