"""
news_poster.py
Automates fetching news for EPL, F1, Cycling, Finance, Politics.
Generates witty GPT-powered hooks & posts to Twitter twice a day.
Enhanced version with better rate limiting, trend integration, URL validation, and content-aware posting.
"""

import os
import random
import requests
import feedparser
import tweepy
import schedule
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
# CONFIGURATION
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

# Image folder
IMAGE_FOLDER = "images"

# Rate limiting configuration
DAILY_POST_LIMIT = 6
POST_INTERVAL_MINUTES = 60
last_post_time = None
FRESHNESS_WINDOW = timedelta(hours=24)

# RSS feeds mapped to categories - Updated with working feeds
RSS_FEEDS = {
    "Arsenal": [
        "http://feeds.bbci.co.uk/sport/football/teams/arsenal/rss.xml",
        "https://www.theguardian.com/football/arsenal/rss",
        "https://arseblog.com/feed/"
    ],
    "EPL": [
        "http://feeds.bbci.co.uk/sport/football/premier-league/rss.xml",
        "https://www.theguardian.com/football/premierleague/rss",
        "https://www.skysports.com/rss/12"
    ],
    "F1": [
        "https://www.autosport.com/rss/f1/news/",
        "http://feeds.bbci.co.uk/sport/formula1/rss.xml",
        "https://www.motorsport.com/rss/f1/news/"
    ],
    "MotoGP": [
        "https://www.autosport.com/rss/motogp/news/",
        "https://www.crash.net/rss/motogp",
        "https://www.the-race.com/rss/motogp/"
    ],
    "World Finance": [
        "https://www.reuters.com/arc/outboundfeeds/business/?outputType=xml",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.bloomberg.com/markets/news.rss"
    ],
    "Crypto": [
        "https://cointelegraph.com/rss",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://coinjournal.net/rss/",
        "https://crypto.news/feed/"
    ],
    "Cycling": [
        "https://www.cyclingnews.com/rss/",
        "https://www.bikeradar.com/feed/",
        "https://velo.outsideonline.com/feed/",
        "https://road.cc/rss"
    ],
    "Space Exploration": [
        "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "https://www.space.com/feeds/all",
        "https://spacenews.com/feed/"
    ],
    "Tesla": [
        "https://electrek.co/feed/",
        "https://insideevs.com/rss/news/",
        "https://www.notateslaapp.com/feed"
    ]
}

# Hashtag pools
CATEGORY_HASHTAGS = {
    "Arsenal": ["#Arsenal", "#COYG", "#PremierLeague", "#Saka", "#Odegaard", "#Saliba", "#Arteta", "#Gunners", "#AFC"],
    "EPL": ["#PremierLeague", "#EPL", "#Football", "#ManCity", "#Liverpool", "#Chelsea", "#Arsenal", "#ManUtd", "#Spurs"],
    "F1": ["#F1", "#Formula1", "#Motorsport", "#Verstappen", "#Hamilton", "#Norris", "#Leclerc", "#McLaren", "#Ferrari", "#RedBull"],
    "MotoGP": ["#MotoGP", "#MotorcycleRacing", "#Bagnaia", "#Marquez", "#Quartararo", "#VR46", "#GrandPrix"],
    "World Finance": ["#Finance", "#GlobalEconomy", "#Markets", "#Stocks", "#Investing", "#WallStreet", "#Bloomberg", "#Crypto"],
    "Crypto": ["#Cryptocurrency", "#Bitcoin", "#Ethereum", "#Blockchain", "#CryptoNews", "#DeFi", "#Web3", "#BTC"],
    "Cycling": ["#Cycling", "#TourDeFrance", "#ProCycling", "#Vingegaard", "#Pogacar", "#CyclistLife", "#RoadCycling"],
    "Space Exploration": ["#Space", "#NASA", "#SpaceX", "#Mars", "#MoonMission", "#Astronomy", "#Starlink", "#SpaceExploration"],
    "Tesla": ["#Tesla", "#ElonMusk", "#ElectricCars", "#ModelY", "#Cybertruck", "#TeslaNews", "#EV", "#SustainableTransport"]
}

# Mapping trends to categories (disabled for now)
TREND_KEYWORDS = {
    "Arsenal": ["Arsenal", "Gunners", "Arteta", "Saka", "Odegaard", "Saliba", "Nwaneri", "Premier League"],
    "EPL": ["Premier League", "EPL", "Man City", "Liverpool", "Chelsea", "Arsenal", "Tottenham", "Football"],
    "F1": ["Formula 1", "F1", "Verstappen", "Norris", "Hamilton", "Leclerc", "McLaren", "Ferrari"],
    "MotoGP": ["MotoGP", "Bagnaia", "Marquez", "Quartararo", "Grand Prix", "Motorcycle Racing", "VR46"],
    "World Finance": ["Finance", "Markets", "Economy", "Stocks", "Investing", "Wall Street", "Crypto", "Global Economy"],
    "Crypto": ["Cryptocurrency", "Bitcoin", "Ethereum", "Blockchain", "DeFi", "Web3", "NFTs", "BTC"],
    "Cycling": ["Cycling", "Tour de France", "Pogacar", "Vingegaard", "Vuelta", "Giro", "Road cycling"],
    "Space Exploration": ["Space", "NASA", "SpaceX", "Mars", "Moon Mission", "Starlink", "Astronomy"],
    "Tesla": ["Tesla", "Elon Musk", "Cybertruck", "Model Y", "Electric Vehicles", "EV", "Autonomous Driving"]
}

# Freshness + fallback
FALLBACK_KEYWORDS = {
    "Arsenal": ["Arsenal FC", "Gunners", "Premier League"],
    "EPL": ["Premier League", "Football", "EPL"],
    "F1": ["Formula 1", "Grand Prix", "Motorsport"],
    "MotoGP": ["MotoGP", "Grand Prix", "Motorcycle Racing"],
    "World Finance": ["Finance", "Markets", "Economy"],
    "Crypto": ["Cryptocurrency", "Bitcoin", "Blockchain"],
    "Cycling": ["Cycling", "Tour de France", "Road Cycling"],
    "Space Exploration": ["Space", "NASA", "SpaceX"],
    "Tesla": ["Tesla", "Electric Vehicles", "Elon Musk"]
}

EVERGREEN_HOOKS = {
    "Arsenal": [
        "Arsenal fans know hope is the deadliest weapon. #COYG",
        "Every Arsenal season is a Shakespeare play: tragedy, comedy, miracle.",
        "Supporting Arsenal should come with free therapy sessions."
    ],
    "EPL": [
        "Premier League: Where dreams are made and hearts are broken.",
        "EPL weekends hit different. Who's your team?",
        "Football's home is the Premier League. #EPL"
    ],
    "F1": [
        "In F1, speed is everything—except when strategy is slower than dial-up.",
        "Formula 1: where even the safety car has a fanbase.",
        "Drivers chase glory, teams chase sponsors, fans chase sleep schedules."
    ],
    "MotoGP": [
        "MotoGP: Two wheels, one wild ride!",
        "Speed, skill, and spills—MotoGP has it all.",
        "Who's your pick for the next Grand Prix?"
    ],
    "World Finance": [
        "Markets move, money talks. What's the next big trend?",
        "Global finance: Where numbers tell epic stories.",
        "From Wall Street to Main Street, the economy never sleeps."
    ],
    "Crypto": [
        "Crypto: HODL or trade, what's your vibe?",
        "Bitcoin, Ethereum, or DeFi—pick your crypto adventure!",
        "Blockchain's changing the game, one block at a time."
    ],
    "Cycling": [
        "Cycling: Two wheels, endless thrills.",
        "From Tour de France to local trails, pedal hard!",
        "Who's ready to chase the peloton?"
    ],
    "Space Exploration": [
        "To the stars and beyond! #SpaceExploration",
        "NASA, SpaceX, or ESA—who's winning the space race?",
        "The universe is calling, and we're listening."
    ],
    "Tesla": [
        "Tesla: Driving the future, one EV at a time.",
        "Cybertruck or Model Y—pick your Tesla vibe!",
        "Elon's vision keeps Tesla charging ahead."
    ]
}

# Image categories for better matching
IMAGE_CATEGORIES = {
    "Arsenal": ["arsenal", "football", "soccer", "gunners"],
    "EPL": ["football", "soccer", "premier", "epl"],
    "F1": ["f1", "racing", "formula", "motorsport"],
    "MotoGP": ["motogp", "motorcycle", "racing", "grand prix"],
    "World Finance": ["finance", "money", "business", "stocks"],
    "Crypto": ["crypto", "bitcoin", "blockchain", "ethereum"],
    "Cycling": ["cycling", "bike", "tour", "bicycle"],
    "Space Exploration": ["space", "nasa", "spacex", "astronomy"],
    "Tesla": ["tesla", "electric car", "cybertruck", "elon musk"]
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
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)

def write_log(message, level="info"):
    """Append timestamped logs to bot_log.txt"""
    if level == "error":
        logging.error(message)
    else:
        logging.info(message)

# =========================
# UTILITY FUNCTIONS
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
        elif response.status_code == 403:
            write_log(f"URL blocked (403 Forbidden): {url}", level="error")
            return False
        else:
            write_log(f"URL validation failed - Status {response.status_code}: {url}")
            return False
    except requests.exceptions.ConnectionError:
        write_log(f"URL validation failed - Connection error: {url}")
        return False
    except requests.exceptions.Timeout:
        write_log(f"URL validation failed - Timeout: {url}")
        return False
    except requests.exceptions.TooManyRedirects:
        write_log(f"URL validation failed - Too many redirects: {url}")
        return False
    except Exception as e:
        write_log(f"URL validation failed - Unknown error: {url} ({e})")
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

def create_images_directory():
    """Create images directory if it doesn't exist."""
    if not os.path.exists(IMAGE_FOLDER):
        os.makedirs(IMAGE_FOLDER)
        write_log(f"Created images directory: {IMAGE_FOLDER}")

# =========================
# NEWS FETCHING
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
        if category in FALLBACK_KEYWORDS:
            write_log(f"Trying fallback keywords for {category}...")
            # Try alternative approach if no articles found
            
    write_log(f"Total articles fetched for {category}: {len(articles)}")
    return articles

# =========================
# CONTENT-AWARE POST GENERATION
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
    """Generate relevant post based on actual article content using GPT."""
    try:
        article_content = extract_article_content(article_url)
        content_context = f"Title: {title}\n"
        if article_content:
            content_context += f"Content: {article_content}\n"
        content_context += f"Category: {category}\n"
        if trend_term:
            content_context += f"Trending topic: {trend_term}\n"
        
        prompt = f"""Based on this news article, create an engaging Twitter post (under 200 characters to leave room for URL and hashtags):

{content_context}

Requirements:
- Be specific about the actual content/news
- Make it engaging and conversational
- Don't use generic templates
- Focus on the key newsworthy element
- Use appropriate tone for {category}
- Include relevant emojis if appropriate

Write ONLY the tweet text, no quotes or explanations:"""

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a witty social media manager creating engaging, specific tweets about current events."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.7
        )
        gpt_text = response.choices[0].message.content.strip()
        
        if trend_term and len(gpt_text) < 180:
            gpt_text = f"Trending {trend_term}: {gpt_text}"
        
        # Add relevant hashtags
        tags = CATEGORY_HASHTAGS.get(category, [])
        if tags:
            remaining_space = 240 - len(gpt_text)
            selected_tags = []
            for tag in tags[:3]:
                if tag.replace("#", "").lower() in gpt_text.lower() or tag.replace("#", "").lower() in title.lower():
                    if len(" " + tag) <= remaining_space and len(selected_tags) < 2:
                        selected_tags.append(tag)
                        remaining_space -= len(" " + tag)
            if selected_tags:
                gpt_text += " " + " ".join(selected_tags)
        
        return validate_tweet_length(gpt_text)
    
    except Exception as e:
        write_log(f"GPT generation failed: {e}")
        # Fallback to simpler GPT model
        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a witty social media manager creating engaging, specific tweets about current events."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.7
            )
            gpt_text = response.choices[0].message.content.strip()
            return validate_tweet_length(gpt_text)
        except Exception as e2:
            write_log(f"Fallback GPT generation failed: {e2}")
            return generate_fallback_post(title, category, trend_term)

def generate_fallback_post(title, category, trend_term=None):
    """Simple fallback when GPT fails - still better than generic templates."""
    if ":" in title:
        main_part = title.split(":")[0].strip()
    else:
        main_part = title[:80]
    
    category_prefixes = {
        "Arsenal": ["Arsenal news:", "Gunners update:", "Arsenal:"],
        "EPL": ["Premier League:", "EPL update:"],
        "F1": ["F1 news:", "Formula 1:"],
        "MotoGP": ["MotoGP news:", "Grand Prix update:"],
        "World Finance": ["Markets:", "Finance:"],
        "Crypto": ["Crypto news:", "Blockchain update:"],
        "Cycling": ["Cycling news:", "Pro cycling:"],
        "Space Exploration": ["Space news:", "NASA update:"],
        "Tesla": ["Tesla news:", "EV update:"]
    }
    
    prefix = random.choice(category_prefixes.get(category, ["News:"]))
    tweet_text = f"{prefix} {main_part}"
    
    if trend_term:
        tweet_text = f"Trending {trend_term} - {tweet_text}"
    
    tags = CATEGORY_HASHTAGS.get(category, [])
    if tags and len(tweet_text) < 200:
        tweet_text += " " + tags[0]
    
    return validate_tweet_length(tweet_text)

# =========================
# POST TO TWITTER
# =========================

def pick_relevant_image(category):
    """Pick image relevant to the category."""
    if not os.path.exists(IMAGE_FOLDER):
        create_images_directory()
        return None
        
    files = [f for f in os.listdir(IMAGE_FOLDER) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    if not files:
        write_log(f"No image files found in '{IMAGE_FOLDER}'")
        return None
    
    category_keywords = IMAGE_CATEGORIES.get(category, [])
    relevant_files = []
    
    for file in files:
        file_lower = file.lower()
        if any(keyword in file_lower for keyword in category_keywords):
            relevant_files.append(file)
    
    if not relevant_files:
        write_log(f"No images match keywords for category '{category}': {category_keywords}")
        chosen_files = files
    else:
        chosen_files = relevant_files
        
    chosen_image = os.path.join(IMAGE_FOLDER, random.choice(chosen_files))
    write_log(f"Selected image: {chosen_image}")
    return chosen_image

def post_tweet(text, category=None):
    """Post tweet with improved rate limiting and error handling."""
    global last_post_time
    
    # Check rate limiting first
    if not can_post_now():
        if last_post_time:
            wait_time = POST_INTERVAL_MINUTES * 60 - (datetime.now(pytz.UTC) - last_post_time).total_seconds()
            write_log(f"Rate limit: waiting {wait_time/60:.1f} minutes before posting")
        return False
    
    try:
        text = validate_tweet_length(text)
        image_path = pick_relevant_image(category) if category else None
        media_ids = []
        
        # Only use local repository images for evergreen content (when category is provided)
        if category:
            local_image_path = pick_relevant_image(category)
            if local_image_path and os.path.exists(local_image_path):
                try:
                    media = twitter_api.media_upload(local_image_path)
                    media_ids = [media.media_id]
                    write_log(f"Local image uploaded successfully: {local_image_path}")
                except Exception as img_error:
                    write_log(f"Failed to upload local image: {img_error}")
                    media_ids = []
        
        # Post the tweet
        twitter_client.create_tweet(text=text, media_ids=media_ids or None)
        if media_ids:
            write_log(f"Tweet posted successfully with local image")
        else:
            write_log(f"Tweet posted successfully - link preview will provide image")
        
        last_post_time = datetime.now(pytz.UTC)
        return True
        
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "rate limit" in error_msg.lower():
            write_log(f"Rate limit hit. Will try again on next scheduled run.")
            return False
        elif "duplicate" in error_msg.lower():
            write_log("Duplicate tweet detected. Skipping...")
            return False
        else:
            write_log(f"Error posting tweet: {e}")
            return False

# =========================
# TREND DETECTION (DISABLED)
# =========================

def detect_category_from_trends():
    """Select category randomly since Twitter API trends are not available."""
    category = random.choice(list(RSS_FEEDS.keys()))
    write_log(f"Selected random category: {category}")
    return category, None

# =========================
# NEWS + FALLBACK FLOW
# =========================

def fallback_tweet(category):
    """Generate fallback tweet when no news is available."""
    if category in EVERGREEN_HOOKS:
        tweet = random.choice(EVERGREEN_HOOKS[category])
        tags = CATEGORY_HASHTAGS.get(category, [])
        if tags:
            additional_tags = random.sample(tags, min(2, len(tags)))
            tweet += " " + " ".join(additional_tags)
        return validate_tweet_length(tweet)
    return validate_tweet_length(f"No fresh news today for {category}, but the passion never stops!")

def post_dynamic_update(category, trend_term=None):
    """Post update for category with content-aware generation and URL validation."""
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
        
        # CRITICAL FIX: Check if we can post BEFORE generating content
        if not can_post_now():
            write_log(f"Rate limited - will retry {category} on next scheduled run")
            return False
        
        # Generate content-aware post
        post_text = generate_content_aware_post(
            article["title"], 
            category, 
            article["url"], 
            trend_term
        )
        
        tweet_text = f"{post_text}\n\n{article['url']}"
        
        if post_tweet(tweet_text, category):
            log_posted(article["url"])
            log_content_hash(article["title"])
            write_log(f"Posted content-aware article from {category}")
            return True
        else:
            # If posting failed (likely due to rate limit), stop trying more articles
            write_log(f"Failed to post article from {category} - stopping further attempts")
            return False
    
    if valid_articles_processed == 0:
        write_log(f"No valid URLs found for {category} articles")
    
    # Only try evergreen content if we haven't hit rate limits
    if can_post_now():
        write_log(f"No new articles for {category}, posting evergreen content...")
        tweet = fallback_tweet(category)
        return post_tweet(tweet, category)
    else:
        write_log(f"Rate limited - skipping evergreen content for {category}")
        return False

# =========================
# MAIN LOGIC
# =========================

def run_dynamic_job():
    """Runs a dynamic posting job with trend integration."""
    try:
        # First check if we're still rate limited from previous attempts
        if not can_post_now():
            write_log("Still rate limited from previous posts - skipping this run")
            return
            
        write_log("Starting dynamic job...")
        category, trend_term = detect_category_from_trends()
        success = post_dynamic_update(category, trend_term)
        
        if not success and can_post_now():
            write_log("Primary category failed, trying random category...")
            backup_categories = [cat for cat in RSS_FEEDS.keys() if cat != category]
            random.shuffle(backup_categories)
            # Only try ONE backup category to avoid rate limit spam
            for backup_category in backup_categories[:1]:
                if not can_post_now():
                    write_log("Rate limited - stopping backup attempts")
                    break
                if post_dynamic_update(backup_category):
                    break
        
        write_log("Dynamic job completed")
    except Exception as e:
        write_log(f"Error in run_dynamic_job: {e}")

# =========================
# SCHEDULER
# =========================

def schedule_posts():
    """Schedule posts with better timing."""
    times = ["19:17", "20:40", "21:42", "22:46", "23:46", "00:47"]
    for t in times:
        schedule.every().day.at(t).do(run_dynamic_job)
        write_log(f"Dynamic job scheduled at {t}")

def start_scheduler():
    """Start the scheduler with initial setup."""
    schedule_posts()
    write_log("Scheduler started with dynamic trending jobs.")
    write_log(f"Rate limiting: {DAILY_POST_LIMIT} posts/day, {POST_INTERVAL_MINUTES}min intervals")
    
    while True:
        schedule.run_pending()
        time.sleep(60)

# =========================
# TESTING & MANUAL FUNCTIONS
# =========================

def check_rate_limits():
    """Check current Twitter API rate limits."""
    try:
        # Try the v2 client first
        try:
            # Using tweepy v2 client
            response = twitter_client.get_rate_limit_status()
            write_log("=== TWITTER API RATE LIMIT STATUS (v2) ===")
            write_log(f"Response: {response}")
        except:
            # Fallback to v1.1 API
            limits = twitter_api.get_application_rate_limit_status()
            
            write_log("=== TWITTER API RATE LIMIT STATUS ===")
            
            # Check different endpoints
            if 'statuses' in limits['resources']:
                if '/statuses/update' in limits['resources']['statuses']:
                    tweet_limits = limits['resources']['statuses']['/statuses/update']
                    write_log(f"Tweet posting limit: {tweet_limits['limit']}")
                    write_log(f"Remaining posts: {tweet_limits['remaining']}")
                    write_log(f"Reset time: {datetime.fromtimestamp(tweet_limits['reset'])}")
                else:
                    write_log("Tweet limits not found in response")
            
            # Check media limits if available
            if 'media' in limits['resources'] and '/media/upload' in limits['resources']['media']:
                media_limits = limits['resources']['media']['/media/upload']
                write_log(f"Media upload limit: {media_limits['limit']}")
                write_log(f"Remaining uploads: {media_limits['remaining']}")
            
            write_log("=====================================")
            
            return limits
            
    except Exception as e:
        write_log(f"Error checking rate limits with tweepy: {e}")
        
        # Manual check using requests
        try:
            write_log("Attempting manual rate limit check...")
            
            # Try to make a simple API call to test if we're rate limited
            headers = {
                'Authorization': f'Bearer {TWITTER_ACCESS_TOKEN}',
                'User-Agent': 'TwitterBot/1.0'
            }
            
            # Test endpoint that doesn't count against posting limits
            test_response = requests.get(
                'https://api.twitter.com/1.1/application/rate_limit_status.json',
                headers=headers,
                timeout=10
            )
            
            if test_response.status_code == 200:
                write_log("API connection successful - rate limits might be on posting only")
            elif test_response.status_code == 429:
                write_log("Rate limited on all API calls")
            else:
                write_log(f"API response code: {test_response.status_code}")
                
        except Exception as manual_error:
            write_log(f"Manual rate limit check also failed: {manual_error}")
            
        return None

def test_single_post(category=None):
    """Test function for single post."""
    if category is None:
        category, trend_term = detect_category_from_trends()
    else:
        trend_term = None
    write_log(f"Testing single post for category: {category}")
    
    # Check rate limits before testing
    limits = check_rate_limits()
    if limits and 'resources' in limits and 'statuses' in limits['resources']:
        if '/statuses/update' in limits['resources']['statuses']:
            remaining = limits['resources']['statuses']['/statuses/update']['remaining']
            if remaining == 0:
                reset_time = datetime.fromtimestamp(limits['resources']['statuses']['/statuses/update']['reset'])
                write_log(f"Cannot test - rate limit exhausted. Resets at: {reset_time}")
                return False
    
    return post_dynamic_update(category, trend_term)

def test_url_validation(url):
    """Test function to check URL validation."""
    print(f"Testing URL: {url}")
    is_valid = validate_url(url)
    print(f"Result: {'Valid' if is_valid else 'Invalid'}")
    return is_valid

def test_full_pipeline(category="Arsenal"):
    """Test the complete pipeline including URL validation."""
    write_log(f"Testing full pipeline for {category}...")
    articles = get_articles_for_category(category)
    if not articles:
        write_log("No articles found")
        return
    
    for article in articles[:3]:
        print(f"\nTesting: {article['title']}")
        print(f"URL: {article['url']}")
        if validate_url(article['url']):
            print("URL: VALID")
            content = extract_article_content(article['url'])
            print(f"Content extracted: {'Yes' if content else 'No'}")
        else:
            print("URL: INVALID - would skip this article")
        print("-" * 50)

def test_content_extraction(url):
    """Test function to see content extraction in action."""
    content = extract_article_content(url)
    print(f"Extracted content: {content}")
    return content

def test_simulation_mode():
    """Test the bot without actually posting to Twitter."""
    write_log("=== RUNNING IN SIMULATION MODE ===")
    write_log("Bot will generate content but not actually post to Twitter")
    
    # Override the post_tweet function temporarily
    global original_post_tweet
    original_post_tweet = post_tweet
    
    def simulate_post_tweet(text, category=None):
        write_log(f"SIMULATION: Would post to Twitter:")
        write_log(f"Category: {category}")
        write_log(f"Content: {text}")
        write_log("=" * 50)
        return True
    
    # Replace the function
    globals()['post_tweet'] = simulate_post_tweet
    
    # Run a test
    test_single_post("Arsenal")
    
    # Restore original function
    globals()['post_tweet'] = original_post_tweet
    write_log("=== SIMULATION MODE ENDED ===")

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
        write_log("Please check your Twitter API credentials in environment variables")
        return False

def check_env_file():
    """Check if environment variables exist and are valid."""
    required_vars = ["TWITTER_API_KEY", "TWITTER_API_SECRET", "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"]
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            write_log(f"ERROR: {var} not found in environment variables")
            return False
        elif len(value) < 10:
            write_log(f"WARNING: {var} seems too short: {len(value)} characters")
        else:
            write_log(f"OK: {var} found ({len(value)} characters)")
    
    return True

if __name__ == "__main__":
    write_log("=== TWITTER BOT STARTUP DIAGNOSTICS ===")
    
    # Check environment variables first
    if not check_env_file():
        write_log("Fix environment variable issues before running bot")
        exit(1)
    
    validate_env_vars()
    create_images_directory()
    
    # Test authentication
    write_log("Testing Twitter API authentication...")
    if not test_auth():
        write_log("CRITICAL: Authentication failed. Bot cannot run.")
        write_log("Steps to fix:")
        write_log("1. Go to developer.twitter.com")
        write_log("2. Check your app is active")
        write_log("3. Regenerate API keys if needed")
        write_log("4. Ensure app has Read/Write permissions")
        write_log("5. Update environment variables with correct keys")
        exit(1)
    
    # If auth works, check rate limits
    write_log("Authentication successful! Checking rate limits...")
    check_rate_limits()
    
    write_log("=== STARTING BOT SCHEDULER ===")
    # Uncomment ONE of these for testing:
    #test_single_post("F1")
    # test_simulation_mode()
    
    start_scheduler()
