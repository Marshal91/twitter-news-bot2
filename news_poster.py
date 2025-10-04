"""
Enhanced Twitter Bot - Nairobi Cycling Safety Awareness
Premium X Account - Extended content support
Replaces reply mechanism with cycling safety advocacy
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
from io import BytesIO

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
# CONFIGURATION
# =========================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")  # Optional - get from unsplash.com/developers

quota_manager = APIQuotaManager()

# Log files
LOG_FILE = "bot_log.txt"
POSTED_LOG = "posted_links.txt"
CONTENT_HASH_LOG = "posted_content_hashes.txt"
CYCLING_POSTS_LOG = "cycling_posts.json"

# Rate limiting configuration
DAILY_POST_LIMIT = 15
POST_INTERVAL_MINUTES = 90
last_post_time = None
FRESHNESS_WINDOW = timedelta(hours=72)

# Cycling safety post configuration
DAILY_CYCLING_POSTS = 2  # Morning and evening posts
CYCLING_POST_TIMES = [
    "09:15",  # Morning commute tips
    "18:30",  # Evening reflection/safety
]

# Premium posting times for other content
PREMIUM_POSTING_TIMES = [
    "08:00", "12:00", "18:00", "22:00"
]

GLOBAL_POSTING_TIMES = [
    "02:00", "04:00", "06:00", "10:00", "20:00", "00:00", "14:00", "16:00"
]

MAIN_POSTING_TIMES = PREMIUM_POSTING_TIMES + GLOBAL_POSTING_TIMES

# RSS feeds for other content categories
RSS_FEEDS = {
    "EPL": [
        "http://feeds.arsenal.com/arsenal-news",
        "https://www.premierleague.com/news",
    ],
    "F1": [
        "https://www.formula1.com/en/latest/all.xml",
        "https://www.autosport.com/rss/f1/news/",
    ],
    "MotoGP": [
        "https://www.motogp.com/en/news/rss",
    ],
    "Crypto": [
        "https://cointelegraph.com/rss",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
    ],
    "Cycling": [
        "http://feeds2.feedburner.com/cyclingnews/news",
    ],
    "Space Exploration": [
        "https://spacenews.com/feed",
    ],
    "Tesla": [
        "https://insideevs.com/rss/articles/all",
    ]
}

PREMIUM_CONTENT_STRATEGIES = {
    "EPL": {
        "focus": "Business strategy, player valuations, commercial insights",
        "tone": "Professional analysis with strategic implications",
        "cta_templates": [
            "How does this reshape the Premier League's economic landscape?",
            "What's the ROI on this move for club stakeholders?",
        ]
    },
    "F1": {
        "focus": "Technology innovation, team strategies",
        "tone": "Technical expertise with business applications",
        "cta_templates": [
            "Which team benefits most from this technical development?",
            "How will this innovation transfer to consumer automotive?",
        ]
    },
    "Crypto": {
        "focus": "Regulatory compliance, institutional adoption",
        "tone": "Institutional-grade analysis",
        "cta_templates": [
            "What's the regulatory precedent this sets?",
            "How will institutional portfolios adjust to this?",
        ]
    }
}

TRENDING_HASHTAGS = {
    "EPL": {
        "primary": ["#PremierLeague", "#EPL", "#Football"],
        "secondary": ["#Arsenal", "#ManCity", "#Liverpool"],
        "trending": ["#MatchDay", "#FootballTwitter"]
    },
    "F1": {
        "primary": ["#F1", "#Formula1"],
        "secondary": ["#Verstappen", "#Hamilton"],
        "trending": ["#F1News", "#Racing"]
    },
    "Crypto": {
        "primary": ["#Bitcoin", "#Cryptocurrency"],
        "secondary": ["#Ethereum", "#DeFi"],
        "trending": ["#CryptoNews", "#Blockchain"]
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
# NAIROBI CYCLING SAFETY CONTENT SYSTEM
# =========================

class NairobiCyclingContent:
    def __init__(self):
        self.posts_log_file = CYCLING_POSTS_LOG
        self.load_posts_log()
        
        # Nairobi roads for image context
        self.nairobi_roads = [
            "Waiyaki Way",
            "Thika Road",
            "Ngong Road",
            "Mombasa Road",
            "Uhuru Highway",
            "Langata Road",
            "Kiambu Road",
            "Outer Ring Road",
            "Southern Bypass",
            "Eastern Bypass",
            "Limuru Road",
            "James Gichuru Road"
        ]
        
        # Stock photo search keywords for Unsplash/Pexels
        self.morning_photo_keywords = [
            "nairobi road morning traffic",
            "nairobi street cyclist",
            "kenya road traffic",
            "nairobi highway morning",
            "african city cycling",
            "nairobi urban transport"
        ]
        
        self.evening_photo_keywords = [
            "nairobi city lights evening",
            "nairobi road night",
            "kenya urban night",
            "nairobi street dusk",
            "african city night traffic",
            "nairobi evening commute"
        ]
        
        # Morning content themes (practical tips)
        self.morning_themes = [
            {
                "topic": "Helmet Safety",
                "prompt": """Write a Premium X post (2-3 short paragraphs) about helmet safety for cyclists in Nairobi.
                
Context: Nairobi roads are chaotic - matatus, bodas, unpredictable traffic.
Tone: Authentic Kenyan. Personal. Conversational but informative.
Message: Helmets are survival, not fashion.

End with hashtags: #CyclingKenya #RoadSafety #NairobiCyclists

Write the full post:"""
            },
            {
                "topic": "Visibility Gear",
                "prompt": """Write a Premium X post (2-3 short paragraphs) about wearing reflective gear while cycling in Nairobi.
                
Context: Drivers don't expect cyclists, especially at night.
Tone: Real talk. Smart. A bit witty.
Message: Being visible saves lives on Nairobi roads.

End with hashtags: #CyclingSafety #NairobiNights #BikeLifeKE

Write the full post:"""
            },
            {
                "topic": "Pre-Ride Check",
                "prompt": """Write a Premium X post (2-3 short paragraphs) about doing a quick bike check before riding in Nairobi.
                
Context: Potholes, rough roads, sudden stops are common.
Tone: Practical. Kenyan. Caring.
Message: 2 minutes checking brakes/tires beats hours in hospital.

End with hashtags: #BikeMainten ance #CyclingKenya #SafetyFirst

Write the full post:"""
            },
            {
                "topic": "Route Planning",
                "prompt": """Write a Premium X post (2-3 short paragraphs) about planning safe cycling routes in Nairobi.
                
Context: Some roads are death traps for cyclists.
Tone: Street-smart. Local knowledge.
Message: Know your roads before you ride them.

End with hashtags: #NairobiCycling #RouteWisdom #CyclingKenya

Write the full post:"""
            },
            {
                "topic": "Weather Awareness",
                "prompt": """Write a Premium X post (2-3 short paragraphs) about cycling in Nairobi's unpredictable weather.
                
Context: Sudden rains make roads slippery and visibility poor.
Tone: Observational. Humorous but serious.
Message: Respect the weather or it'll humble you.

End with hashtags: #NairobiWeather #CyclingSafety #BikeLifeKE

Write the full post:"""
            }
        ]
        
        # Evening content themes (reflections, real talk)
        self.evening_themes = [
            {
                "topic": "Night Riding Reality",
                "prompt": """Write a Premium X post (2-3 short paragraphs) reflecting on riding home after dark in Nairobi.
                
Context: City lights blur with headlights, you're invisible to drivers.
Tone: Reflective. Honest. Urban poetry.
Message: Light up or risk being a statistic.

End with hashtags: #NairobiNights #CyclingSafety #BikeLifeKE

Write the full post:"""
            },
            {
                "topic": "Close Call Stories",
                "prompt": """Write a Premium X post (2-3 short paragraphs) about a near-miss experience cycling in Nairobi (general, not personal).
                
Context: Matatu swerves, boda cuts across, pedestrian doesn't look.
Tone: Storytelling. Authentic. Lesson learned.
Message: Every close call teaches you something about survival.

End with hashtags: #CyclingStories #NairobiRoads #StaySafe

Write the full post:"""
            },
            {
                "topic": "Respecting the Road",
                "prompt": """Write a Premium X post (2-3 short paragraphs) about mutual respect between cyclists and drivers in Nairobi.
                
Context: We all just want to get home safely.
Tone: Thoughtful. Community-minded. Urban wisdom.
Message: The road belongs to all of us.

End with hashtags: #RoadRespect #NairobiTraffic #CyclingKenya

Write the full post:"""
            },
            {
                "topic": "Why We Ride",
                "prompt": """Write a Premium X post (2-3 short paragraphs) about why people choose to cycle in Nairobi despite the risks.
                
Context: Freedom, fitness, beating traffic, environmental choice.
Tone: Passionate. Inspiring. Real.
Message: The risk is worth the reward when you ride smart.

End with hashtags: #WhyWeRide #CyclingKenya #NairobiLife

Write the full post:"""
            },
            {
                "topic": "Community Solidarity",
                "prompt": """Write a Premium X post (2-3 short paragraphs) about the cycling community in Nairobi supporting each other.
                
Context: We wave, we warn, we watch out for each other.
Tone: Warm. Community-focused. Ubuntu spirit.
Message: Alone we're vulnerable, together we're stronger.

End with hashtags: #CyclingCommunity #NairobiCyclists #TogetherStronger

Write the full post:"""
            }
        ]
    
    def load_posts_log(self):
        """Load cycling posts history"""
        try:
            if os.path.exists(self.posts_log_file):
                with open(self.posts_log_file, 'r') as f:
                    self.posts_log = json.load(f)
            else:
                self.posts_log = {
                    "date": datetime.now(pytz.UTC).strftime("%Y-%m-%d"),
                    "today_count": 0,
                    "themes_used": []
                }
        except:
            self.posts_log = {
                "date": datetime.now(pytz.UTC).strftime("%Y-%m-%d"),
                "today_count": 0,
                "themes_used": []
            }
    
    def save_posts_log(self):
        """Save posts history"""
        with open(self.posts_log_file, 'w') as f:
            json.dump(self.posts_log, f, indent=2)
    
    def can_post_today(self):
        """Check if we can still post cycling content today"""
        current_date = datetime.now(pytz.UTC).strftime("%Y-%m-%d")
        
        if self.posts_log["date"] != current_date:
            self.posts_log = {
                "date": current_date,
                "today_count": 0,
                "themes_used": []
            }
            self.save_posts_log()
        
        return self.posts_log["today_count"] < DAILY_CYCLING_POSTS
    
    def fetch_unsplash_photo(self, keywords, is_morning=True):
        """Fetch relevant photo from Unsplash API"""
        if not UNSPLASH_ACCESS_KEY:
            write_log("Unsplash API key not set - skipping image")
            return None
        
        try:
            search_term = random.choice(keywords)
            url = f"https://api.unsplash.com/search/photos"
            params = {
                "query": search_term,
                "per_page": 5,
                "orientation": "landscape"
            }
            headers = {
                "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("results"):
                # Pick random photo from results
                photo = random.choice(data["results"])
                photo_url = photo["urls"]["regular"]
                photographer = photo["user"]["name"]
                photo_link = photo["links"]["html"]
                
                write_log(f"Found Unsplash photo by {photographer}")
                
                # Download the image
                img_response = requests.get(photo_url, timeout=30)
                img_response.raise_for_status()
                
                return {
                    "data": BytesIO(img_response.content),
                    "photographer": photographer,
                    "link": photo_link
                }
            else:
                write_log(f"No Unsplash results for: {search_term}")
                return None
                
        except Exception as e:
            write_log(f"Error fetching Unsplash photo: {e}")
            return None
    
    def fetch_pexels_photo(self, keywords, is_morning=True):
        """Fetch relevant photo from Pexels API (fallback)"""
        pexels_key = os.getenv("PEXELS_API_KEY")
        if not pexels_key:
            return None
        
        try:
            search_term = random.choice(keywords)
            url = f"https://api.pexels.com/v1/search"
            params = {
                "query": search_term,
                "per_page": 5,
                "orientation": "landscape"
            }
            headers = {
                "Authorization": pexels_key
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("photos"):
                photo = random.choice(data["photos"])
                photo_url = photo["src"]["large"]
                photographer = photo["photographer"]
                
                write_log(f"Found Pexels photo by {photographer}")
                
                # Download the image
                img_response = requests.get(photo_url, timeout=30)
                img_response.raise_for_status()
                
                return {
                    "data": BytesIO(img_response.content),
                    "photographer": photographer,
                    "link": photo["url"]
                }
            else:
                write_log(f"No Pexels results for: {search_term}")
                return None
                
        except Exception as e:
            write_log(f"Error fetching Pexels photo: {e}")
            return None
    
    def get_stock_photo(self, is_morning=True):
        """Get stock photo from Unsplash or Pexels"""
        keywords = self.morning_photo_keywords if is_morning else self.evening_photo_keywords
        
        # Try Unsplash first
        photo = self.fetch_unsplash_photo(keywords, is_morning)
        
        # Fallback to Pexels if Unsplash fails
        if not photo:
            photo = self.fetch_pexels_photo(keywords, is_morning)
        
        return photo
    
    def upload_media_to_twitter(self, image_data):
        """Upload image to Twitter using v1.1 API and return media_id"""
        try:
            # Reset to beginning of BytesIO stream
            image_data.seek(0)
            
            # Upload using Tweepy's media_upload (v1.1 API)
            media = twitter_api.media_upload(filename="nairobi_cycling.jpg", file=image_data)
            
            write_log(f"Image uploaded to Twitter - media_id: {media.media_id}")
            return media.media_id
            
        except Exception as e:
            write_log(f"Error uploading media to Twitter: {e}")
            return None
    
    def generate_cycling_post(self, is_morning=True):
        """Generate cycling safety content"""
        themes = self.morning_themes if is_morning else self.evening_themes
        
        # Filter out recently used themes
        available_themes = [
            t for t in themes 
            if t["topic"] not in self.posts_log["themes_used"][-3:]
        ]
        
        if not available_themes:
            available_themes = themes
        
        theme = random.choice(available_themes)
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a Nairobi cyclist who shares authentic, practical safety advice. Your tone is conversational, Kenyan, and relatable. You write 2-3 paragraph posts that feel real, not corporate."
                    },
                    {
                        "role": "user",
                        "content": theme["prompt"]
                    }
                ],
                max_tokens=400,
                temperature=0.8
            )
            
            post_text = response.choices[0].message.content.strip()
            
            # Log theme usage
            self.posts_log["themes_used"].append(theme["topic"])
            self.posts_log["today_count"] += 1
            self.save_posts_log()
            
            return {
                "text": post_text,
                "theme": theme["topic"],
                "road": random.choice(self.nairobi_roads)
            }
            
        except Exception as e:
            write_log(f"Error generating cycling post: {e}")
            return None
    
    def post_cycling_content(self, is_morning=True):
        """Post cycling safety content with stock photo"""
        if not self.can_post_today():
            write_log("Daily cycling post limit reached")
            return False
        
        if not quota_manager.can_write(1):
            write_log("Cannot post - write quota exhausted")
            return False
        
        content = self.generate_cycling_post(is_morning)
        if not content:
            return False
        
        try:
            # Fetch stock photo
            write_log(f"Fetching stock photo for {'morning' if is_morning else 'evening'} post...")
            photo_data = self.get_stock_photo(is_morning)
            
            media_ids = []
            if photo_data:
                # Upload image to Twitter
                media_id = self.upload_media_to_twitter(photo_data["data"])
                if media_id:
                    media_ids = [media_id]
                    write_log(f"Photo by {photo_data['photographer']} - {photo_data['link']}")
            else:
                write_log("No image available - posting text only")
            
            # Post the tweet with or without image
            response = twitter_client.create_tweet(
                text=content["text"],
                media_ids=media_ids if media_ids else None
            )
            quota_manager.use_write(1)
            
            post_type = "Morning" if is_morning else "Evening"
            write_log(f"{post_type} cycling post published - Theme: {content['theme']}")
            write_log(f"Featured road: {content['road']}")
            
            return True
            
        except Exception as e:
            write_log(f"Error posting cycling content: {e}")
            return False

# Initialize cycling content system
cycling_content = NairobiCyclingContent()

# =========================
# VISUAL ELEMENTS ENHANCEMENT
# =========================

def add_visual_elements_to_tweet(tweet_text, category):
    """Add visual elements to increase engagement"""
    category_emojis = {
        "EPL": {"breaking": "⚽", "analysis": "📊", "transfer": "🔄"},
        "F1": {"breaking": "🏎️", "analysis": "📈", "race": "🏁"},
        "Crypto": {"breaking": "🚨", "analysis": "📊", "trend": "📈"},
    }
    
    emojis = category_emojis.get(category, {})
    if not emojis or (tweet_text and tweet_text[0] in "⚽📊🔄🏎️📈🏁🚨"):
        return tweet_text
    
    tweet_lower = tweet_text.lower()
    for keyword, emoji in emojis.items():
        if keyword in tweet_lower:
            return f"{emoji} {tweet_text}"
    
    return tweet_text

# =========================
# MAIN CONTENT POSTING
# =========================

def validate_env_vars():
    """Validate required environment variables"""
    required_vars = ["OPENAI_API_KEY", "TWITTER_API_KEY", "TWITTER_API_SECRET", 
                     "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"]
    missing = [var for var in required_vars if not os.getenv(var)]
    
    # Check for optional stock photo APIs
    if not os.getenv("UNSPLASH_ACCESS_KEY") and not os.getenv("PEXELS_API_KEY"):
        write_log("WARNING: No stock photo API keys found (UNSPLASH_ACCESS_KEY or PEXELS_API_KEY)")
        write_log("Cycling posts will be text-only without images")
    
    if missing:
        raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

def get_trending_hashtags(category):
    """Get optimized hashtags"""
    hashtag_data = TRENDING_HASHTAGS.get(category)
    if not hashtag_data:
        return []
    
    selected = random.sample(hashtag_data["primary"], 1)
    if len(hashtag_data["secondary"]) >= 1:
        selected.extend(random.sample(hashtag_data["secondary"], 1))
    
    return selected[:3]

def fetch_rss(feed_url):
    """Fetch news from RSS feed"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(feed_url, headers=headers, timeout=15)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        
        return [{"title": e.title, "url": e.link} for e in feed.entries[:3]]
    except Exception as e:
        write_log(f"Error fetching RSS: {e}")
        return []

def get_articles_for_category(category):
    """Get articles for category"""
    feeds = RSS_FEEDS.get(category, [])
    for feed in feeds[:2]:
        articles = fetch_rss(feed)
        if articles:
            return articles
    return []

def generate_content_aware_post(title, category):
    """Generate engaging posts"""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Create viral Twitter content."},
                {"role": "user", "content": f"Create Twitter post about: {title}\nCategory: {category}\nUnder 200 chars:"}
            ],
            max_tokens=100,
            temperature=0.8
        )
        return response.choices[0].message.content.strip()
    except:
        return f"Breaking: {title[:100]}..."

def has_been_posted(url):
    """Check if URL posted"""
    if not os.path.exists(POSTED_LOG):
        return False
    with open(POSTED_LOG, "r") as f:
        return url in f.read()

def log_posted(url):
    """Record posted URL"""
    with open(POSTED_LOG, "a") as f:
        f.write(url + "\n")

def can_post_now():
    """Check rate limit"""
    global last_post_time
    if last_post_time is None:
        return True
    time_since = datetime.now(pytz.UTC) - last_post_time
    return time_since.total_seconds() >= (POST_INTERVAL_MINUTES * 60)

def post_main_content(category):
    """Post main content"""
    global last_post_time
    
    if not can_post_now() or not quota_manager.can_write(1):
        return False
    
    articles = get_articles_for_category(category)
    
    for article in articles:
        if has_been_posted(article["url"]):
            continue
        
        tweet_text = generate_content_aware_post(article["title"], category)
        tweet_text = add_visual_elements_to_tweet(tweet_text, category)
        
        hashtags = " ".join(get_trending_hashtags(category))
        full_tweet = f"{tweet_text}\n\n{article['url']}\n\n{hashtags}"
        
        if len(full_tweet) > 280:
            full_tweet = full_tweet[:277] + "..."
        
        try:
            twitter_client.create_tweet(text=full_tweet)
            quota_manager.use_write(1)
            log_posted(article["url"])
            last_post_time = datetime.now(pytz.UTC)
            
            write_log(f"Posted {category}: {article['title'][:50]}...")
            return True
        except Exception as e:
            write_log(f"Error posting: {e}")
            return False
    
    return False

# =========================
# SCHEDULER SYSTEM
# =========================

def should_post_main_content():
    """Check main content time"""
    return datetime.now(pytz.UTC).strftime("%H:%M") in MAIN_POSTING_TIMES

def should_post_cycling_content():
    """Check cycling content time"""
    return datetime.now(pytz.UTC).strftime("%H:%M") in CYCLING_POST_TIMES

def is_morning_cycling_time():
    """Check if morning cycling time"""
    return datetime.now(pytz.UTC).strftime("%H:%M") == CYCLING_POST_TIMES[0]

def run_main_content_job():
    """Run main content job"""
    try:
        category = random.choice(list(RSS_FEEDS.keys()))
        post_main_content(category)
    except Exception as e:
        write_log(f"Error in main job: {e}")

def run_cycling_content_job():
    """Run cycling safety content job"""
    try:
        is_morning = is_morning_cycling_time()
        cycling_content.post_cycling_content(is_morning)
    except Exception as e:
        write_log(f"Error in cycling job: {e}")

def start_scheduler():
    """Main scheduler with cycling content"""
    write_log("Starting scheduler with Nairobi Cycling Safety content...")
    write_log(f"Cycling post times: {CYCLING_POST_TIMES}")
    write_log(f"Main content times: {len(MAIN_POSTING_TIMES)} scheduled")
    
    last_checked_minute = None
    
    while True:
        try:
            current_minute = datetime.now(pytz.UTC).strftime("%H:%M")
            
            if current_minute != last_checked_minute:
                # Check for cycling content
                if should_post_cycling_content():
                    write_log(f"Cycling content time: {current_minute}")
                    run_cycling_content_job()
                
                # Check for main content
                if should_post_main_content():
                    write_log(f"Main content time: {current_minute}")
                    run_main_content_job()
                
                last_checked_minute = current_minute
            
            time.sleep(30)
            
        except Exception as e:
            write_log(f"Scheduler error: {e}")
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
        status = f"""Nairobi Cycling Safety Bot: RUNNING

Monthly Quota:
- Reads: {quota_status['reads_used']}/100
- Writes: {quota_status['writes_used']}/500

Content Strategy:
- Cycling Safety: 2 posts/day (morning & evening)
- Other Content: 12 posts/day
- Visual Elements: ACTIVE
- Premium X: Extended content support

Last Post: {last_post_time or 'Never'}
"""
        self.wfile.write(status.encode())
    
    def log_message(self, format, *args):
        pass

def start_health_server():
    """Start health server"""
    port = int(os.environ.get('PORT', 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        write_log(f"Health server on port {port}")
        server.serve_forever()
    except Exception as e:
        write_log(f"Health server error: {e}")

def test_auth():
    """Test Twitter auth"""
    try:
        me = twitter_api.verify_credentials()
        write_log(f"Auth successful! @{me.screen_name}")
        return True
    except Exception as e:
        write_log(f"Auth failed: {e}")
        return False

# =========================
# MAIN
# =========================

if __name__ == "__main__":
    write_log("=== NAIROBI CYCLING SAFETY BOT STARTUP ===")
    
    validate_env_vars()
    
    if not test_auth():
        exit(1)
    
    quota_status = quota_manager.get_quota_status()
    write_log(f"Quota: {quota_status['reads_used']}/100 reads, {quota_status['writes_used']}/500 writes")
    write_log("Cycling safety content: 2 posts/day (morning & evening)")
    write_log("Main content: 12 posts/day")
    write_log("Visual elements: ACTIVE")
    
    # Start health server in background
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Start scheduler
    start_scheduler()

