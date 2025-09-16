"""
Enhanced news_poster.py
Incorporates threading, verified user targeting, and growth acceleration features.
"""

import os
import random
import requests
import feedparser
import tweepy
import time
import hashlib
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
# CONFIGURATION (Enhanced)
# =========================

# Load from environment variables (.env file in production)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")

# Log files
LOG_FILE = "bot_log.txt"
POSTED_LOG = "posted_links.txt"
CONTENT_HASH_LOG = "posted_content_hashes.txt"
THREAD_PERFORMANCE_LOG = "thread_performance.txt"

# Image folder
IMAGE_FOLDER = "images"

# Enhanced rate limiting configuration
DAILY_POST_LIMIT = 15  # Increased for threads
POST_INTERVAL_MINUTES = 90  # Reduced for more frequent posting
THREAD_COOLDOWN_HOURS = 4  # Minimum time between threads
last_post_time = None
last_thread_time = None
FRESHNESS_WINDOW = timedelta(hours=72)

# Enhanced posting times - targeting premium demographics with strategic distribution
PREMIUM_POSTING_TIMES = [
    "13:30",  # 9:30 AM ET / 2:30 PM GMT - Morning business hours
    "16:30",  # 12:30 PM ET / 5:30 PM GMT - Lunch break
    "18:30",  # 2:30 PM ET / 7:30 PM GMT - Afternoon peak
    "20:30",  # 4:30 PM ET / 9:30 PM GMT - Evening engagement
    "22:30",  # 6:30 PM ET / 11:30 PM GMT - Night owls
    "14:00",  # 10:00 AM ET / 3:00 PM GMT - Mid-morning business
    "19:30",  # 3:30 PM ET / 8:30 PM GMT - After-work engagement
    "21:00"   # 5:00 PM ET / 10:00 PM GMT - Evening prime time
]

# Global engagement times for sports/entertainment content
GLOBAL_POSTING_TIMES = [
    "02:00",  # Asia/Australia morning
    "06:48",  # Europe morning
    "09:12",  # Europe business hours
    "11:36",  # Pre-lunch global
    "23:36",  # Late night Americas
    "01:24"   # Asia evening
]

# Categories that benefit from global timing
GLOBAL_CATEGORIES = ["EPL", "F1", "MotoGP", "Cycling"]

# Categories that should focus on business hours
BUSINESS_CATEGORIES = ["Crypto", "Tesla", "Space Exploration"]

# RSS feeds mapped to categories (same as original)
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
        "https://www.investopedia.com/trading-news-4689736",
        "https://cointelegraph.com/rss",
        "https://www.investopedia.com/markets-news-4427704",
        "https://www.investopedia.com/political-news-4689737",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://www.investopedia.com/company-news-4427705",
        "https://crypto.news/feed/"
    ],
    "Cycling": [
        "http://feeds2.feedburner.com/cyclingnews/news",
        "https://cycling.today/feed",
        "https://velo.outsideonline.com/feed/",
        "https://road.cc/rss"
    ],
    "Space Exploration": [
        "https://spacenews.com/feed",
        "https://phys.org/rss-feed/space-news/",
        "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "https://www.space.com/feeds/all"
    ],
    "Tesla": [
        "https://insideevs.com/rss/articles/all",
        "https://bloomberg.com/green",
        "https://electrek.co/feed/",
        "https://bloomberg.com/pursuits/autos",
        "https://www.tesla.com/blog/feed",
        "https://www.tesla.com/blog.rss"
    ]
}

# Enhanced hashtag pools for growth acceleration
TRENDING_HASHTAGS = {
    "EPL": {
        "primary": ["#PremierLeague", "#EPL", "#Football", "#COYG"],
        "secondary": ["#ManCity", "#Liverpool", "#Chelsea", "#Arsenal", "#ManUtd", "#Spurs"],
        "trending": ["#MatchDay", "#PL", "#FootballTwitter", "#Soccer"]
    },
    "F1": {
        "primary": ["#F1", "#Formula1", "#GrandPrix"],
        "secondary": ["#Verstappen", "#Hamilton", "#Norris", "#Leclerc"],
        "trending": ["#F1News", "#Motorsport", "#Racing", "#F1Tech"]
    },
    "MotoGP": {
        "primary": ["#MotoGP", "#MotorcycleRacing"],
        "secondary": ["#Bagnaia", "#Marquez", "#Quartararo", "#VR46"],
        "trending": ["#GrandPrix", "#MotoGPNews", "#Racing"]
    },
    "Crypto": {
        "primary": ["#Cryptocurrency", "#Bitcoin", "#Blockchain"],
        "secondary": ["#Ethereum", "#DeFi", "#Web3", "#BTC"],
        "trending": ["#CryptoNews", "#Investing", "#FinTech", "#Digital"]
    },
    "Cycling": {
        "primary": ["#Cycling", "#TourDeFrance", "#ProCycling"],
        "secondary": ["#Vingegaard", "#Pogacar", "#CyclistLife"],
        "trending": ["#RoadCycling", "#BikeRacing", "#Cycling2025"]
    },
    "Space Exploration": {
        "primary": ["#Space", "#NASA", "#SpaceX"],
        "secondary": ["#Mars", "#MoonMission", "#Astronomy"],
        "trending": ["#SpaceExploration", "#Starlink", "#SpaceTech"]
    },
    "Tesla": {
        "primary": ["#Tesla", "#ElonMusk", "#ElectricCars"],
        "secondary": ["#ModelY", "#Cybertruck", "#TeslaNews"],
        "trending": ["#EV", "#SustainableTransport", "#CleanEnergy"]
    }
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
    }
}

# Thread trigger keywords - when to create threads vs single tweets
THREAD_WORTHY_KEYWORDS = [
    "breaking", "major", "significant", "analysis", "report", "study", 
    "investigation", "exclusive", "controversial", "shocking", "unprecedented"
]

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
# THREAD CREATION SYSTEM
# =========================

def should_create_thread(title, content=""):
    """Determine if content warrants a thread based on keywords and complexity"""
    text_to_analyze = (title + " " + content).lower()
    
    # Check for thread-worthy keywords
    keyword_score = sum(1 for keyword in THREAD_WORTHY_KEYWORDS if keyword in text_to_analyze)
    
    # Check content length and complexity
    complexity_score = 0
    if len(text_to_analyze) > 200:
        complexity_score += 1
    if ":" in title and len(title.split(":")) > 1:
        complexity_score += 1
    if any(word in text_to_analyze for word in ["because", "however", "therefore", "analysis"]):
        complexity_score += 1
    
    total_score = keyword_score + complexity_score
    
    # 30% chance for threads on high-score content
    if total_score >= 3:
        return random.random() < 0.3
    elif total_score >= 2:
        return random.random() < 0.15
    
    return False

def can_post_thread():
    """Check if enough time has passed since last thread"""
    global last_thread_time
    if last_thread_time is None:
        return True
    time_since_last = datetime.now(pytz.UTC) - last_thread_time
    return time_since_last.total_seconds() >= (THREAD_COOLDOWN_HOURS * 3600)

def create_thread_content(title, category, article_content="", trend_term=None):
    """Generate multi-part thread content for higher engagement"""
    
    # Get premium strategy if applicable
    premium_strategy = PREMIUM_CONTENT_STRATEGIES.get(category, {})
    focus_area = premium_strategy.get("focus", "key insights and implications")
    cta = premium_strategy.get("cta", "What's your take on this?")
    
    context = f"""
    Title: {title}
    Category: {category}
    Content: {article_content[:300] if article_content else ""}
    Focus on: {focus_area}
    """
    
    thread_prompts = [
        f"""Create a compelling Twitter thread opener about: {title}
        
        Requirements:
        - Hook that creates curiosity gap
        - Under 250 characters
        - End with 🧵 or "Thread:"
        - Make people want to read more
        - Focus on: {focus_area}
        
        Write only the tweet text:""",
        
        f"""Create Part 2 of the thread about: {title}
        
        Requirements:
        - Start with "2/"
        - Provide the main insight or surprising angle
        - Under 250 characters
        - Focus on: {focus_area}
        - Bridge to the conclusion
        
        Write only the tweet text:""",
        
        f"""Create Part 3 (final) of the thread about: {title}
        
        Requirements:
        - Start with "3/"
        - Provide conclusion and implications
        - End with engaging question: {cta}
        - Under 250 characters
        - Encourage replies and engagement
        
        Write only the tweet text:"""
    ]
    
    thread_parts = []
    for i, prompt in enumerate(thread_prompts):
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You create viral Twitter threads that drive engagement from business professionals and decision-makers."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.8
            )
            thread_parts.append(response.choices[0].message.content.strip())
            time.sleep(1)  # Avoid rate limits on OpenAI
        except Exception as e:
            write_log(f"Thread part {i+1} generation failed: {e}")
            return None
    
    return thread_parts

def post_thread_with_recovery(thread_parts, category, article_url=None):
    """Enhanced thread posting with failure recovery and analytics"""
    global last_thread_time
    
    if not thread_parts or len(thread_parts) < 2:
        write_log("Invalid thread parts provided")
        return False
    
    posted_tweets = []
    thread_id = None
    
    try:
        # Post first tweet with optimized hashtags
        first_tweet_text = optimize_hashtags_for_reach(thread_parts[0], category)
        if article_url:
            short_url = shorten_url_with_fallback(article_url)
            first_tweet_text += f"\n\n{short_url}"
        
        first_tweet = twitter_client.create_tweet(text=first_tweet_text)
        thread_id = first_tweet.data['id']
        posted_tweets.append(first_tweet.data)
        write_log(f"Posted thread starter: {thread_id}")
        
        # Post replies with exponential backoff
        for i, part in enumerate(thread_parts[1:], 1):
            wait_time = min(3 * (1.5 ** i), 15)  # Progressive delay, cap at 15s
            time.sleep(wait_time)
            
            optimized_part = optimize_hashtags_for_reach(part, category)
            
            reply = twitter_client.create_tweet(
                text=optimized_part,
                in_reply_to_tweet_id=posted_tweets[-1]['id']
            )
            posted_tweets.append(reply.data)
            write_log(f"Posted thread part {i+1}")
        
        # Log thread performance for analytics
        log_thread_performance(thread_id, category, len(thread_parts))
        last_thread_time = datetime.now(pytz.UTC)
        
        write_log(f"Thread posted successfully: {len(posted_tweets)} parts")
        return True
        
    except Exception as e:
        write_log(f"Thread posting failed at part {len(posted_tweets)+1}: {e}")
        
        # If we have partial thread, log for manual review
        if posted_tweets:
            write_log(f"Partial thread posted - first tweet ID: {thread_id}")
            
        return len(posted_tweets) > 0

def log_thread_performance(thread_id, category, parts_count):
    """Log thread performance for analytics"""
    with open(THREAD_PERFORMANCE_LOG, "a") as f:
        timestamp = datetime.now(pytz.UTC).isoformat()
        f.write(f"{timestamp},{thread_id},{category},{parts_count}\n")

# =========================
# PREMIUM USER TARGETING
# =========================

def generate_premium_targeted_content(title, category, article_url, article_content=""):
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

Content Context: {article_content[:200] if article_content else ""}

Requirements:
- Appeal to professionals and decision-makers
- Focus on strategic implications and business insights
- Include data-driven analysis angles
- End with thought-provoking question
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

def is_premium_posting_time():
    """Check if current time is optimal for premium demographics"""
    current_time = datetime.now(pytz.UTC).strftime("%H:%M")
    return current_time in PREMIUM_POSTING_TIMES

# =========================
# GROWTH ACCELERATION FEATURES
# =========================

def get_trending_hashtags(category):
    """Get optimized hashtags for better reach"""
    hashtag_data = TRENDING_HASHTAGS.get(category)
    if not hashtag_data:
        return []
    
    # Always include 1 primary hashtag
    selected = random.sample(hashtag_data["primary"], 1)
    
    # Add 1-2 secondary based on current context
    secondary_count = random.randint(1, 2)
    if len(hashtag_data["secondary"]) >= secondary_count:
        selected.extend(random.sample(hashtag_data["secondary"], secondary_count))
    
    # 30% chance to add trending hashtag
    if random.random() < 0.3 and hashtag_data["trending"]:
        selected.append(random.choice(hashtag_data["trending"]))
    
    return selected[:3]  # Maximum 3 hashtags

def optimize_hashtags_for_reach(tweet_text, category):
    """Add optimized hashtags for maximum reach without looking spammy"""
    hashtags = get_trending_hashtags(category)
    
    if not hashtags:
        return tweet_text
    
    # Calculate available space
    available_space = 280 - len(tweet_text) - 5  # 5 char buffer
    
    # Build hashtag string
    hashtag_text = " " + " ".join(hashtags)
    
    if len(hashtag_text) <= available_space:
        return tweet_text + hashtag_text
    else:
        # Add what fits, prioritizing primary hashtags
        for i in range(len(hashtags), 0, -1):
            test_tags = " " + " ".join(hashtags[:i])
            if len(test_tags) <= available_space:
                return tweet_text + test_tags
    
    return tweet_text

def create_poll_tweet(category, topic, article_url=None):
    """Generate engaging poll tweets for higher engagement"""
    
    poll_prompts = {
        "F1": f"Which aspect of {topic} will have the biggest impact on F1's future?",
        "EPL": f"What's the most important factor in {topic} for Premier League success?",
        "Crypto": f"Which element of {topic} poses the greatest opportunity for crypto adoption?",
        "Tesla": f"How will {topic} reshape Tesla's competitive position?",
        "Space Exploration": f"What's the most significant implication of {topic} for space exploration?"
    }
    
    base_prompt = poll_prompts.get(category, f"What's your take on the latest developments in {topic}?")
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Create engaging poll questions that spark professional debate and encourage detailed replies from industry experts."},
                {"role": "user", "content": f"""Create a poll question about {topic} in {category}. 
                
                Requirements:
                - Appeal to business professionals and decision-makers
                - Include strategic or analytical angle
                - End with 'Vote and share your analysis!'
                - Under 200 characters to leave room for poll options
                - Focus on implications and strategic thinking
                
                Write only the poll question:"""}
            ],
            max_tokens=80,
            temperature=0.7
        )
        poll_text = response.choices[0].message.content.strip()
        
        # Add URL if provided
        if article_url:
            short_url = shorten_url_with_fallback(article_url)
            poll_text += f"\n\n{short_url}"
        
        return optimize_hashtags_for_reach(poll_text, category)
    except Exception as e:
        write_log(f"Poll generation failed: {e}")
        return optimize_hashtags_for_reach(base_prompt, category)

# =========================
# ENHANCED CONTENT STRATEGY
# =========================

def choose_content_format(title, category, article_content="", article_url=None):
    """Decide whether to post thread, poll, or single tweet based on content and timing"""
    
    # Check if threads are allowed
    thread_eligible = can_post_thread() and should_create_thread(title, article_content)
    
    # Check if it's premium time (more likely to do threads for professionals)
    if is_premium_posting_time():
        thread_eligible = thread_eligible or (random.random() < 0.25)  # 25% chance during premium hours
    
    # 10% chance for polls on any content
    poll_chance = random.random() < 0.1
    
    if thread_eligible and not poll_chance:
        write_log(f"Creating thread for: {title[:50]}...")
        thread_parts = create_thread_content(title, category, article_content)
        if thread_parts:
            return "thread", thread_parts
    
    elif poll_chance and article_url:
        write_log(f"Creating poll for: {title[:50]}...")
        poll_content = create_poll_tweet(category, title, article_url)
        return "poll", poll_content
    
    # Default to enhanced single tweet
    if is_premium_posting_time():
        write_log(f"Creating premium-targeted content for: {title[:50]}...")
        content = generate_premium_targeted_content(title, category, article_url, article_content)
    else:
        write_log(f"Creating regular viral content for: {title[:50]}...")
        content = generate_content_aware_post(title, category, article_url)
    
    return "single", content

# =========================
# UTILITY FUNCTIONS (From Original + Enhancements)
# =========================

def validate_env_vars():
    """Validate required environment variables."""
    required_vars = ["OPENAI_API_KEY", "TWITTER_API_KEY", "TWITTER_API_SECRET", "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        write_log(f"Missing environment variables: {', '.join(missing)}", level="error")
        raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

def validate_url(url, timeout=8):
    """Validate that a URL is accessible and returns valid content."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.google.com/'
        }
        response = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            return True
        elif response.status_code in [301, 302, 307, 308]:
            write_log(f"URL redirected but accessible: {url}")
            return True
        elif response.status_code == 405:
            try:
                response = requests.get(url, headers=headers, timeout=timeout)
                return response.status_code == 200
            except:
                return False
        else:
            write_log(f"URL validation failed - Status {response.status_code}: {url}")
            return False
    except Exception as e:
        write_log(f"URL validation failed: {url} - {e}")
        return False

def has_been_posted(url):
    """Check if a URL has already been posted."""
    if not os.path.exists(POSTED_LOG):
        return False
    with open(POSTED_LOG, "r") as f:
        return url.strip() in f.read()

def get_content_hash(title):
    """Generate hash for content similarity checking."""
    normalized = title.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()

def has_similar_content_posted(title):
    """Check if similar content has been posted recently."""
    if not os.path.exists(CONTENT_HASH_LOG):
        return False
    content_hash = get_content_hash(title)
    with open(CONTENT_HASH_LOG, "r") as f:
        return content_hash in f.read()

def log_content_hash(title):
    """Record content hash to prevent similar posts."""
    content_hash = get_content_hash(title)
    with open(CONTENT_HASH_LOG, "a") as f:
        f.write(f"{content_hash}\n")

def log_posted(url):
    """Record posted URL."""
    with open(POSTED_LOG, "a") as f:
        f.write(url.strip() + "\n")

def validate_tweet_length(text):
    """Ensure tweet doesn't exceed Twitter's character limit."""
    if len(text) > 280:
        return text[:277] + "..."
    return text

def can_post_now():
    """Check if enough time has passed since last post."""
    global last_post_time
    if last_post_time is None:
        return True
    time_since_last = datetime.now(pytz.UTC) - last_post_time
    return time_since_last.total_seconds() >= (POST_INTERVAL_MINUTES * 60)

def shorten_url_with_fallback(long_url):
    """Try multiple URL shortening services with fallback"""
    try:
        api_url = f"http://tinyurl.com/api-create.php?url={long_url}"
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200 and response.text.strip().startswith('http'):
            short_url = response.text.strip()
            write_log(f"URL shortened: {long_url[:50]}... -> {short_url}")
            return short_url
    except Exception as e:
        write_log(f"TinyURL shortening failed: {e}")
    
    try:
        api_url = f"https://is.gd/create.php?format=simple&url={long_url}"
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200 and response.text.strip().startswith('http'):
            short_url = response.text.strip()
            write_log(f"URL shortened with is.gd: {long_url[:50]}... -> {short_url}")
            return short_url
    except Exception as e:
        write_log(f"is.gd shortening failed: {e}")
    
    write_log("All URL shortening services failed, using original URL")
    return long_url

# =========================
# NEWS FETCHING (From Original)
# =========================

def fetch_rss(feed_url):
    """Fetch news from an RSS feed with better error handling."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(feed_url, headers=headers, timeout=15)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        if feed.bozo:
            write_log(f"Feed parsing issues for {feed_url} - continuing anyway")
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

def is_fresh(article):
    """Check if article is within freshness window."""
    pub_date = article.get('published_parsed')
    if not pub_date:
        return True
    try:
        dt = datetime(*pub_date[:6], tzinfo=pytz.UTC)
        return datetime.now(pytz.UTC) - dt <= FRESHNESS_WINDOW
    except:
        return True

def get_articles_for_category(category):
    """Get articles for a category with fallback handling."""
    feeds = RSS_FEEDS.get(category, [])
    articles = []
    valid_feeds_found = False
    
    for feed in feeds:
        write_log(f"Processing RSS feed for {category}: {feed}")
        feed_articles = fetch_rss(feed)
        if feed_articles:
            valid_feeds_found = True
            articles.extend(feed_articles)
        
    if not articles and not valid_feeds_found:
        write_log(f"No articles found for {category} after checking all feeds")
            
    write_log(f"Total articles fetched for {category}: {len(articles)}")
    return articles

# =========================
# CONTENT EXTRACTION & GENERATION
# =========================

def extract_article_content(url):
    """Fetch and extract main content from article URL."""
    try:
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
        config.request_timeout = 15
        
        article = Article(url, config=config)
        article.download()
        article.parse()
        
        if article.text and len(article.text.strip()) > 50:
            return article.text[:500]
        return None
    except Exception as e:
        write_log(f"Newspaper3k failed for {url}: {e}")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://www.google.com/'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try meta description first
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                return meta_desc['content'][:500]
            
            # Try to find article content
            paragraphs = soup.find_all('p')
            for p in paragraphs:
                text = p.get_text().strip()
                if len(text) > 50:
                    return text[:500]
            return None
        except Exception as e:
            write_log(f"Could not extract content from {url}: {e}")
            return None

def generate_content_aware_post(title, category, article_url, trend_term=None):
    """Generate viral-worthy posts that drive engagement (fallback method)."""
    try:
        article_content = extract_article_content(article_url)
        content_context = f"Title: {title}\n"
        if article_content:
            content_context += f"Content: {article_content}\n"
        content_context += f"Category: {category}\n"
        if trend_term:
            content_context += f"Trending topic: {trend_term}\n"
        
        prompt = f"""Create a highly engaging Twitter post that drives retweets, likes, and comments (under 200 characters):

{content_context}

Make it viral by using these techniques:
- Ask thought-provoking questions that demand answers
- Use contrarian takes or challenge conventional wisdom  
- Include bold predictions or hot takes
- Create "Wait, what?" moments that make people double-take
- Use psychological triggers: curiosity gaps, social proof, controversy
- End with questions that spark debate in replies

Write ONLY the tweet text, no quotes or explanations:"""

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a viral content creator who understands social media psychology and creates posts that people can't help but engage with."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=120,
            temperature=0.8
        )
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        write_log(f"GPT generation failed: {e}")
        return f"Breaking: {title[:100]}... What's your take on this?"

# =========================
# ENHANCED POSTING SYSTEM
# =========================

def post_enhanced_content(content_type, content_data, category, article_url=None):
    """Post content based on type (single, thread, poll)"""
    global last_post_time
    
    if not can_post_now():
        write_log("Rate limited - cannot post now")
        return False
    
    try:
        if content_type == "thread":
            success = post_thread_with_recovery(content_data, category, article_url)
        elif content_type == "poll":
            # Note: Twitter API v2 polls require different handling
            # For now, post as regular tweet with poll-like content
            tweet_text = validate_tweet_length(content_data)
            twitter_client.create_tweet(text=tweet_text)
            success = True
            write_log(f"Posted poll-style content")
        else:  # single tweet
            tweet_text = content_data
            if article_url:
                short_url = shorten_url_with_fallback(article_url)
                tweet_text = f"{tweet_text}\n\n{short_url}"
            
            tweet_text = optimize_hashtags_for_reach(tweet_text, category)
            tweet_text = validate_tweet_length(tweet_text)
            
            twitter_client.create_tweet(text=tweet_text)
            success = True
            write_log(f"Posted enhanced single tweet")
        
        if success:
            last_post_time = datetime.now(pytz.UTC)
            return True
            
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "rate limit" in error_msg.lower():
            write_log(f"Rate limit hit. Will try again on next scheduled run.")
        elif "duplicate" in error_msg.lower():
            write_log("Duplicate tweet detected. Skipping...")
        else:
            write_log(f"Error posting content: {e}")
        return False
    
    return False

# =========================
# ENHANCED MAIN LOGIC
# =========================

def post_dynamic_update_enhanced(category, trend_term=None):
    """Enhanced posting with threading, premium targeting, and growth features"""
    
    # Check rate limiting first
    if not can_post_now():
        write_log(f"Rate limited - will retry {category} on next scheduled run")
        return False
        
    articles = get_articles_for_category(category)
    fresh_articles = [a for a in articles if is_fresh(a)]
    target_articles = fresh_articles if fresh_articles else articles
    
    valid_articles_processed = 0
    
    for article in target_articles:
        # Skip already posted or similar content
        if has_been_posted(article["url"]) or has_similar_content_posted(article["title"]):
            continue
            
        # Validate URL before processing
        if not validate_url(article["url"]):
            write_log(f"Skipping article with broken URL: {article['title'][:60]}...")
            continue
        
        valid_articles_processed += 1
        
        # Check if we can post BEFORE generating content
        if not can_post_now():
            write_log(f"Rate limited - will retry {category} on next scheduled run")
            return False
        
        # Extract article content for better context
        article_content = extract_article_content(article["url"])
        
        # Choose content format based on content and timing
        content_type, content_data = choose_content_format(
            article["title"], 
            category, 
            article_content or "", 
            article["url"]
        )
        
        # Post the content
        if post_enhanced_content(content_type, content_data, category, article["url"]):
            log_posted(article["url"])
            log_content_hash(article["title"])
            write_log(f"Posted {content_type} content for {category}: {article['title'][:50]}...")
            return True
        else:
            write_log(f"Failed to post {content_type} for {category} - stopping further attempts")
            return False
    
    if valid_articles_processed == 0:
        write_log(f"No valid articles found for {category}")
    
    # Fallback to evergreen content if no articles worked
    if can_post_now():
        write_log(f"No new articles for {category}, posting fallback content...")
        fallback_content = generate_fallback_content(category)
        return post_enhanced_content("single", fallback_content, category)
    else:
        write_log(f"Rate limited - skipping fallback content for {category}")
        return False

def generate_fallback_content(category):
    """Generate fallback content when no fresh articles available"""
    evergreen_topics = {
        "EPL": "What makes a Premier League season truly memorable? The drama, the goals, or the unexpected twists?",
        "F1": "F1 technology continues to push boundaries. Which innovation will have the biggest impact on road cars?",
        "Crypto": "Institutional crypto adoption is accelerating. What's the most undervalued aspect investors are missing?",
        "Tesla": "Tesla's influence extends beyond cars. Which industry will they disrupt next?",
        "Space Exploration": "Private space companies are reshaping exploration. What's the most exciting possibility ahead?",
        "MotoGP": "MotoGP riders push physics to the limit. What separates champions from the rest of the field?",
        "Cycling": "Professional cycling combines strategy, endurance, and split-second decisions. What's the most underrated skill?"
    }
    
    base_content = evergreen_topics.get(category, f"What's the most exciting development you're following in {category}?")
    
    # Add premium angle if it's premium time
    if is_premium_posting_time():
        premium_angle = f"From a business perspective: {base_content}"
        return premium_angle
    
    return base_content

# =========================
# SCHEDULING SYSTEM
# =========================

def detect_category_from_trends():
    """Select category with enhanced logic for premium times"""
    categories = list(RSS_FEEDS.keys())
    
    # During premium posting times, prioritize business-relevant categories
    if is_premium_posting_time():
        priority_categories = ["Crypto", "Tesla", "F1", "Space Exploration"]
        available_priority = [cat for cat in priority_categories if cat in categories]
        if available_priority and random.random() < 0.7:  # 70% chance for priority
            category = random.choice(available_priority)
            write_log(f"Selected priority category for premium time: {category}")
            return category, None
    
    # Regular random selection
    category = random.choice(categories)
    write_log(f"Selected category: {category}")
    return category, None

def should_post_now():
    """Enhanced scheduling that considers premium times"""
    current_minute = datetime.now(pytz.UTC).strftime("%H:%M")
    
    all_scheduled_times = PREMIUM_POSTING_TIMES + REGULAR_POSTING_TIMES
    
    write_log(f"Checking time: {current_minute} against {len(all_scheduled_times)} scheduled times")
    result = current_minute in all_scheduled_times
    
    if result and current_minute in PREMIUM_POSTING_TIMES:
        write_log(f"Premium posting time detected: {current_minute}")
    
    return result

def run_enhanced_job():
    """Enhanced job runner with all new features"""
    try:
        if not can_post_now():
            write_log("Still rate limited from previous posts - skipping this run")
            return
            
        write_log("Starting enhanced dynamic job...")
        write_log(f"Premium time: {is_premium_posting_time()}")
        write_log(f"Thread available: {can_post_thread()}")
        
        category, trend_term = detect_category_from_trends()
        success = post_dynamic_update_enhanced(category, trend_term)
        
        if not success and can_post_now():
            write_log("Primary category failed, trying backup category...")
            backup_categories = [cat for cat in RSS_FEEDS.keys() if cat != category]
            random.shuffle(backup_categories)
            
            # Only try ONE backup to avoid rate limit spam
            for backup_category in backup_categories[:1]:
                if not can_post_now():
                    write_log("Rate limited - stopping backup attempts")
                    break
                if post_dynamic_update_enhanced(backup_category):
                    write_log(f"Backup category succeeded: {backup_category}")
                    break
        
        write_log("Enhanced dynamic job completed")
    except Exception as e:
        write_log(f"Error in run_enhanced_job: {e}")

def start_enhanced_scheduler():
    """Enhanced scheduler with premium time awareness"""
    write_log("Starting enhanced scheduler...")
    write_log(f"Rate limiting: {DAILY_POST_LIMIT} posts/day, {POST_INTERVAL_MINUTES}min intervals")
    write_log(f"Thread cooldown: {THREAD_COOLDOWN_HOURS} hours")
    
    all_times = sorted(PREMIUM_POSTING_TIMES + REGULAR_POSTING_TIMES)
    write_log(f"Scheduled times: {all_times}")
    write_log(f"Premium times: {PREMIUM_POSTING_TIMES}")
    
    last_checked_minute = None
    
    while True:
        try:
            current_minute = datetime.now(pytz.UTC).strftime("%H:%M")
            
            # Only check once per minute
            if current_minute != last_checked_minute:
                if should_post_now():
                    write_log(f"Scheduled time reached: {current_minute}")
                    run_enhanced_job()
                last_checked_minute = current_minute
                
            time.sleep(30)  # Check every 30 seconds
            
        except Exception as e:
            write_log(f"ERROR in enhanced scheduler loop: {e}")
            time.sleep(60)

# =========================
# HEALTH SERVER (From Original)
# =========================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        
        # Enhanced health check with feature status
        status = f"""Enhanced Twitter Bot Status: RUNNING
        
Features Active:
- Threading: {can_post_thread()}
- Premium Targeting: {is_premium_posting_time()}
- Growth Acceleration: Enabled
- Rate Limiting: {can_post_now()}

Last Post: {last_post_time or 'Never'}
Last Thread: {last_thread_time or 'Never'}
        """
        self.wfile.write(status.encode())
    
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress server access logs

def start_health_server():
    """Start health check server for Render Web Service."""
    port = int(os.environ.get('PORT', 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        write_log(f"Enhanced health server starting on port {port}")
        server.serve_forever()
    except Exception as e:
        write_log(f"Health server failed to start: {e}")

# =========================
# TESTING FUNCTIONS
# =========================

def test_enhanced_features():
    """Test all new enhanced features"""
    write_log("=== TESTING ENHANCED FEATURES ===")
    
    # Test premium time detection
    write_log(f"Current time premium: {is_premium_posting_time()}")
    
    # Test hashtag optimization
    test_tweet = "This is a test tweet about Formula 1 racing"
    optimized = optimize_hashtags_for_reach(test_tweet, "F1")
    write_log(f"Hashtag optimization test: {optimized}")
    
    # Test thread detection
    test_title = "Breaking: Major investigation reveals significant changes in Formula 1 regulations"
    thread_worthy = should_create_thread(test_title)
    write_log(f"Thread detection test: {thread_worthy}")
    
    # Test content format selection
    content_type, content_data = choose_content_format(test_title, "F1")
    write_log(f"Content format selection: {content_type}")
    
    write_log("=== ENHANCED FEATURES TEST COMPLETE ===")

def test_single_enhanced_post(category=None):
    """Test enhanced posting system"""
    if category is None:
        category, trend_term = detect_category_from_trends()
    else:
        trend_term = None
    
    write_log(f"Testing enhanced post for category: {category}")
    write_log(f"Premium time: {is_premium_posting_time()}")
    write_log(f"Thread available: {can_post_thread()}")
    
    return post_dynamic_update_enhanced(category, trend_term)

def test_auth():
    """Test Twitter API authentication."""
    try:
        me = twitter_api.verify_credentials()
        write_log(f"Authentication successful! Logged in as: @{me.screen_name}")
        write_log(f"Account ID: {me.id}")
        write_log(f"Followers: {me.followers_count}")
        return True
    except Exception as e:
        write_log(f"Authentication failed: {e}")
        return False

# =========================
# MAIN EXECUTION
# =========================

if __name__ == "__main__":
    write_log("=== ENHANCED TWITTER BOT STARTUP ===")
    
    # Validate environment
    validate_env_vars()
    
    # Test authentication
    if not test_auth():
        write_log("CRITICAL: Authentication failed. Bot cannot run.")
        exit(1)
    
    write_log("=== ENHANCED FEATURES INITIALIZED ===")
    write_log("✓ Threading system active")
    write_log("✓ Premium user targeting enabled")
    write_log("✓ Growth acceleration features loaded")
    write_log("✓ Enhanced hashtag optimization ready")
    write_log("✓ Multi-format content generation active")
    
    # Start health server in background
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Uncomment for testing:
    # test_enhanced_features()
    # test_single_enhanced_post("F1")
    
    # Start the enhanced scheduler
    start_enhanced_scheduler()
