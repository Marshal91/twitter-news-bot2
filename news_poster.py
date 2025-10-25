"""
Crypto-Exclusive Bot with High-Engagement Strategies
Enhanced with crypto-specific engagement tactics
FIXED VERSION - All syntax errors resolved
"""

import os
import random
import requests
import feedparser
import tweepy
import time
import json
import hashlib
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
# CONFIGURATION
# =========================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")

# FILE PATHS
POSTED_LOG = "posted_urls.txt"
CONTENT_HASHES_FILE = "content_hashes.txt"
LOG_FILE = "bot_log.txt"

# POSTING CONFIGURATION
DAILY_POST_LIMIT = 15
POST_INTERVAL_MINUTES = 90
last_post_time = None
FRESHNESS_WINDOW = timedelta(hours=24)

# DAILY POST TRACKING
daily_posts = 0
last_reset_date = datetime.now(pytz.UTC).date()

# CONTENT VARIETY TRACKING
recent_content_types = []
MAX_RECENT_TYPES = 5

# CRYPTO-OPTIMIZED POSTING TIMES (US + Asian markets)
POSTING_TIMES = [
    "03:00", "05:00", "07:00", "09:00", "11:00", "13:00",
    "15:00", "17:00", "19:00", "21:00", "23:00", "01:00"
]

# CRYPTO CONTENT TYPES
CRYPTO_CONTENT_TYPES = [
    "educational", "market_analysis", "contrarian",
    "question", "hot_take", "breakdown"
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

# ENGAGEMENT TEMPLATES
CRYPTO_ENGAGEMENT_TEMPLATES = {
    "question": [
        "Which would you choose: {option1} or {option2}?",
        "Quick poll: {option1} vs {option2}?",
        "Honest question: {option1} or {option2}?",
        "You can only pick one: {option1} or {option2}. Which is it?",
        "{question} Drop your answer below"
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
    "Most crypto investors are just gamblers with better vocabulary",
    "The next bull run will look nothing like the last one",
    "NFTs solved a real problem, people just hate the art",
    "Regulation will make crypto bigger, not smaller",
    "99% of altcoins will go to zero",
    "The real crypto wealth is made in bear markets",
    "Technical analysis in crypto is modern astrology"
]

CRYPTO_EMOJIS = ["₿", "💎", "🚀", "📊", "📈", "📉", "⚡", "🔥", "💰", "🎯"]

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize Twitter API
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
    if level == "error":
        logging.error(message)
    else:
        logging.info(message)

# =========================
# CONTENT TRACKING FUNCTIONS
# =========================

def get_content_hash(text):
    return hashlib.md5(text.lower().encode()).hexdigest()

def is_similar_content(tweet_text):
    content_hash = get_content_hash(tweet_text)
    if not os.path.exists(CONTENT_HASHES_FILE):
        return False
    try:
        with open(CONTENT_HASHES_FILE, 'r') as f:
            recent_hashes = f.read().splitlines()[-100:]
        return content_hash in recent_hashes
    except Exception as e:
        write_log(f"Error checking content similarity: {e}")
        return False

def log_content_hash(tweet_text):
    content_hash = get_content_hash(tweet_text)
    try:
        with open(CONTENT_HASHES_FILE, 'a') as f:
            f.write(f"{content_hash}\n")
    except Exception as e:
        write_log(f"Error logging content hash: {e}")

def reset_daily_counter():
    global daily_posts, last_reset_date
    current_date = datetime.now(pytz.UTC).date()
    if current_date > last_reset_date:
        daily_posts = 0
        last_reset_date = current_date
        write_log("Daily post counter reset to 0")

def get_varied_content_type():
    global recent_content_types
    available_types = [t for t in CRYPTO_CONTENT_TYPES 
                      if t not in recent_content_types[-2:]]
    if not available_types:
        available_types = CRYPTO_CONTENT_TYPES
    selected = random.choice(available_types)
    recent_content_types.append(selected)
    if len(recent_content_types) > MAX_RECENT_TYPES:
        recent_content_types.pop(0)
    return selected

# =========================
# CRYPTO CONTENT GENERATION
# =========================

def generate_crypto_question(title):
    prompt = f"Based on this crypto news: {title}\n\nCreate a simple, engaging question that makes people want to reply. Format: X or Y? Keep it under 150 characters.\n\nWrite ONLY the question:"
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
    except Exception as e:
        write_log(f"GPT question generation failed: {e}, using fallback")
        return random.choice(CRYPTO_QUESTION_TEMPLATES)

def generate_crypto_hot_take(title):
    prompt = f"Based on this crypto news: {title}\n\nCreate a bold, controversial take that sparks debate. Start with: Unpopular opinion, Hot take, or Real talk. Be provocative but not offensive. Under 200 characters.\n\nWrite ONLY the tweet:"
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
    except Exception as e:
        write_log(f"GPT hot take generation failed: {e}, using fallback")
        return f"Hot take: {random.choice(CRYPTO_HOT_TAKES)}"

def generate_contrarian_take(title):
    prompt = f"Based on this crypto news: {title}\n\nCreate a contrarian take that challenges mainstream thinking. Be thought-provoking and data-driven if possible. Under 200 characters.\n\nWrite ONLY the tweet:"
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
    except Exception as e:
        write_log(f"GPT contrarian generation failed: {e}, using fallback")
        return f"Everyone's wrong about {title[:50]}... here's why:"

def generate_educational_breakdown(title):
    prompt = f"Based on this crypto news: {title}\n\nCreate an educational tweet that breaks down a concept. Start with Here's how or Understanding. Make it accessible and valuable. Under 200 characters.\n\nWrite ONLY the tweet:"
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
    except Exception as e:
        write_log(f"GPT educational generation failed: {e}, using fallback")
        return f"Here's what {title[:60]} actually means:"

def generate_market_analysis(title):
    prompt = f"Based on this crypto news: {title}\n\nCreate a market analysis tweet explaining the why behind the move. Focus on causes and implications. Under 200 characters.\n\nWrite ONLY the tweet:"
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
    except Exception as e:
        write_log(f"GPT market analysis generation failed: {e}, using fallback")
        return f"Why this matters for crypto: {title[:80]}"

def generate_listicle_thread(title):
    numbers = ["3", "5", "7"]
    number = random.choice(numbers)
    prompt = f"Based on this crypto news: {title}\n\nCreate a tweet announcing a {number}-point breakdown. Format: {number} things about [topic]. Make it compelling and promise value. Under 180 characters.\n\nWrite ONLY the tweet:"
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
    except Exception as e:
        write_log(f"GPT listicle generation failed: {e}, using fallback")
        return f"{number} things you need to know about {title[:60]}"

def generate_crypto_content(title, content_type):
    generators = {
        "question": generate_crypto_question,
        "hot_take": generate_crypto_hot_take,
        "contrarian": generate_contrarian_take,
        "educational": generate_educational_breakdown,
        "market_analysis": generate_market_analysis,
        "breakdown": generate_listicle_thread
    }
    generator = generators.get(content_type, generate_educational_breakdown)
    try:
        return generator(title)
    except Exception as e:
        write_log(f"Content generation failed completely: {e}, using simple fallback")
        return f"Breaking: {title[:150]}"

def add_crypto_visual_elements(tweet_text):
    if any(emoji in tweet_text for emoji in CRYPTO_EMOJIS):
        return tweet_text
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
    selected = random.sample(CRYPTO_HASHTAGS["primary"], 2)
    if random.random() < 0.4:
        selected.append(random.choice(CRYPTO_HASHTAGS["trending"]))
    if random.random() < 0.2:
        selected.append(random.choice(CRYPTO_HASHTAGS["specific"]))
    return selected[:3]

def optimize_hashtags(tweet_text):
    hashtags = get_crypto_hashtags()
    available_space = 280 - len(tweet_text) - 5
    hashtag_text = " " + " ".join(hashtags)
    if len(hashtag_text) <= available_space:
        return tweet_text + hashtag_text
    return tweet_text

# =========================
# CONTENT FETCHING & POSTING
# =========================

def fetch_rss_with_retry(feed_url, max_retries=3):
    for attempt in range(max_retries):
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(feed_url, headers=headers, timeout=15)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            if feed.entries:
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
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                write_log(f"RSS fetch failed for {feed_url} (attempt {attempt+1}/{max_retries}), retrying in {wait_time}s: {e}")
                time.sleep(wait_time)
            else:
                write_log(f"RSS fetch failed after {max_retries} attempts for {feed_url}: {e}")
    return []

def get_crypto_articles():
    articles = []
    for feed in RSS_FEEDS:
        feed_articles = fetch_rss_with_retry(feed)
        if feed_articles:
            articles.extend(feed_articles)
    write_log(f"Total crypto articles fetched: {len(articles)}")
    return articles

def has_been_posted(url):
    if not os.path.exists(POSTED_LOG):
        return False
    try:
        with open(POSTED_LOG, "r") as f:
            return url.strip() in f.read()
    except Exception as e:
        write_log(f"Error checking posted log: {e}")
        return False

def log_posted(url):
    try:
        with open(POSTED_LOG, "a") as f:
            f.write(url.strip() + "\n")
    except Exception as e:
        write_log(f"Error logging posted URL: {e}")

def can_post_now():
    global last_post_time
    if last_post_time is None:
        return True
    time_since_last = datetime.now(pytz.UTC) - last_post_time
    return time_since_last.total_seconds() >= (POST_INTERVAL_MINUTES * 60)

def shorten_url(long_url):
    try:
        api_url = f"http://tinyurl.com/api-create.php?url={long_url}"
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200 and response.text.strip().startswith('http'):
            return response.text.strip()
    except Exception as e:
        write_log(f"URL shortening failed: {e}, using original URL")
    return long_url

def post_crypto_content():
    global last_post_time, daily_posts
    reset_daily_counter()
    if daily_posts >= DAILY_POST_LIMIT:
        write_log(f"Daily limit reached ({daily_posts}/{DAILY_POST_LIMIT} posts)")
        return False
    if not can_post_now():
        write_log("Cannot post - rate limited (90 min interval)")
        return False
    content_type = get_varied_content_type()
    write_log(f"Selected content type: {content_type}")
    articles = get_crypto_articles()
    if not articles:
        write_log("No articles fetched from RSS feeds")
        return False
    for article in articles:
        if has_been_posted(article["url"]):
            continue
        try:
            tweet_text = generate_crypto_content(article["title"], content_type)
        except Exception as e:
            write_log(f"Content generation error: {e}")
            continue
        if is_similar_content(tweet_text):
            write_log(f"Similar content detected, skipping")
            continue
        tweet_text = add_crypto_visual_elements(tweet_text)
        short_url = shorten_url(article["url"])
        full_tweet = f"{tweet_text}\n\n{short_url}"
        full_tweet = optimize_hashtags(full_tweet)
        hashtags = [word for word in full_tweet.split() if word.startswith('#')]
        if len(full_tweet) > 280:
            full_tweet = full_tweet[:277] + "..."
        engagement_style = "standard"
        if "?" in tweet_text:
            engagement_style = "question"
        elif any(phrase in tweet_text.lower() for phrase in ["hot take", "unpopular", "controversial"]):
            engagement_style = "provocative"
        elif any(phrase in tweet_text.lower() for phrase in ["here's how", "understanding", "breakdown"]):
            engagement_style = "educational"
        max_retries = 3
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                response = twitter_client.create_tweet(text=full_tweet)
                tweet_id = response.data['id']
                log_posted(article["url"])
                log_content_hash(tweet_text)
                last_post_time = datetime.now(pytz.UTC)
                daily_posts += 1
                write_log("="*60)
                write_log(f"TWEET POSTED SUCCESSFULLY!")
                write_log(f"Daily posts: {daily_posts}/{DAILY_POST_LIMIT}")
                write_log(f"Content type: {content_type}")
                write_log(f"Tweet: {tweet_text[:80]}...")
                write_log(f"Hashtags: {', '.join(hashtags) if hashtags else 'None'}")
                write_log(f"Engagement style: {engagement_style}")
                write_log(f"Tweet ID: {tweet_id}")
                write_log(f"URL: https://twitter.com/user/status/{tweet_id}")
                write_log("="*60)
                return True
            except Exception as e:
                error_msg = str(e)
                if "403" in error_msg or "forbidden" in error_msg.lower():
                    write_log(f"403 Forbidden error - check API permissions: {e}", level="error")
                    return False
                elif "duplicate" in error_msg.lower():
                    write_log(f"Duplicate content detected by Twitter: {e}")
                    break
                elif "429" in error_msg or "rate limit" in error_msg.lower():
                    write_log(f"Rate limit hit: {e}", level="error")
                    return False
                elif attempt < max_retries - 1:
                    write_log(f"Network error on attempt {attempt + 1}/{max_retries}: {error_msg}")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    write_log(f"All {max_retries} retry attempts failed: {e}", level="error")
                    break
    write_log(f"No new crypto articles to post (all already posted or failed)")
    return False

# =========================
# SCHEDULER
# =========================

def should_post_now():
    current_time = datetime.now(pytz.UTC).strftime("%H:%M")
    return current_time in POSTING_TIMES

def get_next_posting_time():
    current_time = datetime.now(pytz.UTC)
    current_str = current_time.strftime("%H:%M")
    for post_time in POSTING_TIMES:
        if post_time > current_str:
            return post_time
    return POSTING_TIMES[0]

def run_posting_job():
    try:
        write_log("Starting crypto posting job...")
        success = post_crypto_content()
        if success:
            write_log("Crypto posting job completed successfully")
        else:
            write_log("Crypto posting job completed with no posts")
    except Exception as e:
        write_log(f"Error in posting job: {e}", level="error")

def start_scheduler():
    write_log("Starting CRYPTO-FOCUSED scheduler...")
    write_log("="*60)
    write_log("Niche: CRYPTO ONLY")
    write_log(f"Posting times (UTC): {POSTING_TIMES}")
    write_log(f"Content types: {CRYPTO_CONTENT_TYPES}")
    write_log("Engagement strategy: Questions, Hot Takes, Contrarian Views")
    write_log(f"Daily limit: {DAILY_POST_LIMIT} posts")
    write_log(f"Post interval: {POST_INTERVAL_MINUTES} minutes")
    write_log("="*60)
    last_checked_minute = None
    last_heartbeat = datetime.now(pytz.UTC)
    heartbeat_interval = 300
    loop_count = 0
    while True:
        try:
            current_time = datetime.now(pytz.UTC)
            current_minute = current_time.strftime("%H:%M")
            loop_count += 1
            if (current_time - last_heartbeat).total_seconds() >= heartbeat_interval:
                next_post = get_next_posting_time()
                write_log(f"HEARTBEAT #{loop_count} - Bot running | Time: {current_minute} UTC | Next post: {next_post} | Daily: {daily_posts}/{DAILY_POST_LIMIT}")
                last_heartbeat = current_time
            if current_minute != last_checked_minute:
                write_log(f"Time check: {current_minute} UTC (Loop #{loop_count})")
                if should_post_now():
                    write_log(f"Posting time reached: {current_minute}")
                    run_posting_job()
                last_checked_minute = current_minute
            time.sleep(30)
        except KeyboardInterrupt:
            write_log("Keyboard interrupt detected - shutting down gracefully...")
            raise
        except Exception as e:
            write_log(f"ERROR in scheduler loop: {e}", level="error")
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
        status_text = f"Crypto-Focused Twitter Bot: RUNNING\n\nCurrent Time: {datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}\nLast Post: {last_post_time.strftime('%Y-%m-%d %H:%M:%S UTC') if last_post_time else 'Never'}\nDaily Posts: {daily_posts}/{DAILY_POST_LIMIT}\n\nPosting Times: {', '.join(POSTING_TIMES)}\n"
        self.wfile.write(status_text.encode())
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
        write_log(f"Health server started on port {port}")
        server.serve_forever()
    except Exception as e:
        write_log(f"Health server failed to start: {e}", level="error")

# =========================
# TESTING FUNCTIONS
# =========================

def test_auth():
    try:
        me = twitter_api.verify_credentials()
        write_log(f"Authentication successful! @{me.screen_name}")
        write_log(f"Followers: {me.followers_count}")
        return True
    except Exception as e:
        write_log(f"Authentication failed: {e}", level="error")
        return False

def test_content_generation():
    write_log("Testing content generation...")
    test_title = "Bitcoin surges past $50K as institutional adoption accelerates"
    for content_type in CRYPTO_CONTENT_TYPES:
        try:
            content = generate_crypto_content(test_title, content_type)
            write_log(f"{content_type}: {content[:60]}...")
        except Exception as e:
            write_log(f"{content_type}: {e}")
    return True

def validate_env_vars():
    required_vars = [
        "OPENAI_API_KEY", "TWITTER_API_KEY", "TWITTER_API_SECRET",
        "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"
    ]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        error_msg = f"Missing environment variables: {', '.join(missing)}"
        write_log(error_msg, level="error")
        raise EnvironmentError(error_msg)
    write_log("All required environment variables present")

# =========================
# MAIN EXECUTION
# =========================

if __name__ == "__main__":
    write_log("="*60)
    write_log("CRYPTO-FOCUSED TWITTER BOT STARTUP")
    write_log("="*60)
    try:
        validate_env_vars()
    except Exception as e:
        write_log(f"Environment validation failed: {e}", level="error")
        exit(1)
    if not test_auth():
        write_log("CRITICAL: Authentication failed. Bot cannot run.", level="error")
        exit(1)
    test_content_generation()
    write_log("")
    write_log("Starting health check server...")
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    write_log("")
    write_log("="*60)
    write_log("STARTING CRYPTO SCHEDULER")
    write_log("="*60)
    write_log("")
    try:
        start_scheduler()
    except KeyboardInterrupt:
        write_log("")
        write_log("="*60)
        write_log("Bot stopped by user")
        write_log(f"Final stats: {daily_posts} posts today")
        write_log("="*60)
        exit(0)
    except Exception as e:
        write_log(f"CRITICAL ERROR: {e}", level="error")
        exit(1)
