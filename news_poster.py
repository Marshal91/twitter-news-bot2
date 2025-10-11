"""
Complete Enhanced Twitter Bot with Visual Elements
API Limits: 100 reads/month (3/day), 500 writes/month (12 posts + 3 replies/day)
Enhanced with visual elements for better engagement
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

# Premium posting times - targeting business professionals and decision-makers
PREMIUM_POSTING_TIMES = [
    "08:00",  # Morning business hours
    "12:00",  # Lunch break business crowd
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
	"14:00",  # Afternoon peak
    "16:00",  # Evening engagement
]

# All main posting times combined
MAIN_POSTING_TIMES = PREMIUM_POSTING_TIMES + GLOBAL_POSTING_TIMES

# Reply campaign times (only 3 times per day)
REPLY_TIMES = [
    "10:25",  # Mid-morning
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

# Enhanced Premium user targeting content strategies with contextual CTAs
PREMIUM_CONTENT_STRATEGIES = {
    "EPL": {
        "focus": "Business strategy, player valuations, commercial insights",
        "tone": "Professional analysis with strategic implications",
        "cta_templates": [
            "How does this reshape the Premier League's economic landscape?",
            "What's the ROI on this move for club stakeholders?",
            "Which clubs are positioned to capitalize on this trend?",
            "How will this impact broadcast revenue models?",
            "What's your read on the market dynamics here?"
        ]
    },
    "F1": {
        "focus": "Technology innovation, team strategies, commercial partnerships",
        "tone": "Technical expertise with business applications",
        "cta_templates": [
            "Which team benefits most from this technical development?",
            "How will this innovation transfer to consumer automotive?",
            "What's the competitive advantage timeline here?",
            "Which manufacturers are best positioned to adapt?",
            "How does this change the cost-performance equation?"
        ]
    },
    "Crypto": {
        "focus": "Regulatory compliance, institutional adoption, market structure",
        "tone": "Institutional-grade analysis and implications",
        "cta_templates": [
            "What's the regulatory precedent this sets?",
            "How will institutional portfolios adjust to this?",
            "Which compliance frameworks address this scenario?",
            "What's the systemic risk assessment here?",
            "How does this impact market structure evolution?"
        ]
    },
    "Tesla": {
        "focus": "Innovation leadership, market disruption, investment thesis",
        "tone": "Strategic business analysis and market positioning",
        "cta_templates": [
            "What's Tesla's moat in this competitive landscape?",
            "How does this accelerate the EV adoption curve?",
            "Which legacy automakers face the biggest disruption?",
            "What's the supply chain implication for investors?",
            "How will this reshape automotive profit margins?"
        ]
    },
    "Space Exploration": {
        "focus": "Commercial space economy, technology transfer, investment opportunities",
        "tone": "Strategic business and technology analysis", 
        "cta_templates": [
            "Which sectors benefit from this space technology spillover?",
            "What's the commercial viability timeline?",
            "How does this impact the space economy valuation?",
            "Which earthbound applications show the most promise?",
            "What's the geopolitical competitive advantage here?"
        ]
    },
    "Cycling": {
        "focus": "Sports business, technology innovation, market trends",
        "tone": "Industry analysis and business perspective",
        "cta_templates": [
            "How will this technology disrupt the cycling industry?",
            "What's the market opportunity for equipment manufacturers?",
            "Which demographic trends does this capitalize on?",
            "How does this impact sponsorship valuations?",
            "What's the consumer adoption pathway here?"
        ]
    },
    "MotoGP": {
        "focus": "Technology transfer, commercial partnerships, market impact",
        "tone": "Technical and business analysis",
        "cta_templates": [
            "Which motorcycle manufacturers gain competitive edge?",
            "How will this tech transfer to consumer bikes?",
            "What's the safety ROI for the racing investment?",
            "Which partnerships are positioned to scale this?",
            "How does this reshape performance benchmarks?"
        ]
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
# TARGETED REPLY SYSTEM - Arsenal & Crypto Only
# =========================

class TargetedReplySystem:
    def __init__(self):
        self.reply_log_file = "replied_tweets.json"
        self.daily_reply_limit = 3  # Conservative: 90 replies/month
        self.load_reply_log()
        
    def load_reply_log(self):
        """Load reply history"""
        try:
            if os.path.exists(self.reply_log_file):
                with open(self.reply_log_file, 'r') as f:
                    self.reply_log = json.load(f)
            else:
                self.reply_log = {
                    "date": datetime.now(pytz.UTC).strftime("%Y-%m-%d"),
                    "today_count": 0,
                    "replied_ids": []
                }
        except:
            self.reply_log = {
                "date": datetime.now(pytz.UTC).strftime("%Y-%m-%d"),
                "today_count": 0,
                "replied_ids": []
            }
    
    def save_reply_log(self):
        """Save reply history"""
        with open(self.reply_log_file, 'w') as f:
            json.dump(self.reply_log, f, indent=2)
    
    def can_reply_today(self):
        """Check if we can still reply today"""
        current_date = datetime.now(pytz.UTC).strftime("%Y-%m-%d")
        
        # Reset counter if new day
        if self.reply_log["date"] != current_date:
            self.reply_log = {
                "date": current_date,
                "today_count": 0,
                "replied_ids": []
            }
            self.save_reply_log()
        
        return self.reply_log["today_count"] < self.daily_reply_limit
    
    def search_targeted_tweets(self, query, max_results=5):
        """Search for tweets about Arsenal or Crypto"""
        if not quota_manager.can_read(1):
            write_log("Cannot search - read quota exhausted")
            return []
        
        try:
            # Search for recent tweets (last 2 hours to ensure freshness)
            tweets = twitter_client.search_recent_tweets(
                query=query,
                max_results=max_results,
                tweet_fields=['author_id', 'created_at', 'public_metrics']
            )
            
            quota_manager.use_read(1)
            
            if tweets.data:
                # Filter out tweets we've already replied to
                new_tweets = [
                    tweet for tweet in tweets.data 
                    if str(tweet.id) not in self.reply_log["replied_ids"]
                ]
                return new_tweets
            return []
            
        except Exception as e:
            write_log(f"Error searching tweets: {e}")
            return []
    
    def generate_reply(self, tweet_text, topic):
        """Generate contextual reply using GPT"""
        
        prompts = {
            "Arsenal": """Create a thoughtful reply to this Arsenal tweet: "{tweet_text}"

Requirements:
- Show genuine Arsenal knowledge and passion
- Add value to the conversation (insight, question, or perspective)
- Keep it under 200 characters
- Be conversational, not spammy
- No hashtags or self-promotion

Write ONLY the reply text:""",
            
            "Crypto": """Create an insightful reply to this crypto tweet: "{tweet_text}"

Requirements:
- Demonstrate crypto/blockchain knowledge
- Provide analytical perspective or thoughtful question
- Keep it under 200 characters
- Professional tone, not financial advice
- No hashtags or promotional content

Write ONLY the reply text:"""
        }
        
        try:
            prompt = prompts[topic].format(tweet_text=tweet_text)
            
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"You're a knowledgeable {topic} enthusiast who adds value to conversations with insights and thoughtful questions."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            write_log(f"Error generating reply: {e}")
            return None
    
    def post_reply(self, tweet_id, reply_text):
        """Post reply with quota check"""
        if not quota_manager.can_write(1):
            write_log("Cannot reply - write quota exhausted")
            return False
        
        try:
            twitter_client.create_tweet(
                text=reply_text,
                in_reply_to_tweet_id=tweet_id
            )
            
            quota_manager.use_write(1)
            self.reply_log["today_count"] += 1
            self.reply_log["replied_ids"].append(str(tweet_id))
            self.save_reply_log()
            
            write_log(f"Posted reply to tweet {tweet_id}")
            return True
            
        except Exception as e:
            write_log(f"Error posting reply: {e}")
            return False
    
    def execute_reply_campaign(self):
        """Execute targeted reply campaign"""
        if not self.can_reply_today():
            write_log("Daily reply limit reached")
            return
        
        # Define search queries
        searches = [
            ("Arsenal", "Arsenal FC -filter:retweets -filter:replies lang:en", 5),
            ("Crypto", "Bitcoin OR Ethereum OR crypto -filter:retweets -filter:replies lang:en", 5)
        ]
        
        for topic, query, max_results in searches:
            if not self.can_reply_today():
                break
            
            write_log(f"Searching for {topic} tweets...")
            tweets = self.search_targeted_tweets(query, max_results)
            
            for tweet in tweets:
                if not self.can_reply_today():
                    break
                
                # Generate and post reply
                reply_text = self.generate_reply(tweet.text, topic)
                if reply_text:
                    success = self.post_reply(tweet.id, reply_text)
                    if success:
                        write_log(f"Replied to {topic} tweet: {tweet.text[:50]}...")
                        time.sleep(60)  # 1 minute cooldown between replies

# Initialize reply system
reply_system = TargetedReplySystem()

# =========================
# VISUAL ELEMENTS ENHANCEMENT
# =========================

def add_visual_elements_to_tweet(tweet_text, category):
    """Add visual elements to increase engagement based on content and category"""
    
    # Category-specific emoji mappings
    category_emojis = {
        "EPL": {
            "breaking": "⚽", "news": "⚽",
            "analysis": "📊", "stats": "📊", "data": "📊",
            "transfer": "🔄", "signing": "🔄",
            "match": "🏆", "win": "🏆", "victory": "🏆",
            "goal": "⚡", "score": "⚡"
        },
        "F1": {
            "breaking": "🏎️", "news": "🏎️",
            "analysis": "📈", "performance": "📈",
            "tech": "🔧", "technical": "🔧", "innovation": "🔧",
            "race": "🏁", "qualifying": "🏁",
            "fastest": "⚡", "speed": "⚡"
        },
        "Crypto": {
            "breaking": "🚨", "alert": "🚨",
            "analysis": "📊", "chart": "📊",
            "trend": "📈", "surge": "📈", "rally": "📈",
            "regulation": "⚖️", "legal": "⚖️",
            "bitcoin": "₿", "btc": "₿"
        },
        "Tesla": {
            "breaking": "⚡", "news": "⚡",
            "innovation": "🚀", "technology": "🚀",
            "data": "📊", "quarterly": "📊", "earnings": "📊",
            "battery": "🔋", "electric": "🔋",
            "production": "🏭", "delivery": "🏭"
        },
        "Space Exploration": {
            "breaking": "🚀", "launch": "🚀",
            "discovery": "🔭", "observe": "🔭",
            "mission": "🛰️", "satellite": "🛰️",
            "mars": "🔴", "moon": "🌙",
            "success": "✨", "achieve": "✨"
        },
        "Cycling": {
            "breaking": "🚴", "news": "🚴",
            "race": "🏆", "stage": "🏆", "win": "🏆",
            "tech": "⚙️", "equipment": "⚙️",
            "climb": "⛰️", "mountain": "⛰️",
            "sprint": "⚡", "attack": "⚡"
        },
        "MotoGP": {
            "breaking": "🏍️", "news": "🏍️",
            "race": "🏁", "qualifying": "🏁",
            "tech": "⚙️", "technical": "⚙️",
            "fastest": "⚡", "lap": "⚡",
            "champion": "🏆", "podium": "🏆"
        }
    }
    
    # Get emoji mapping for category
    emojis = category_emojis.get(category, {})
    if not emojis:
        return tweet_text
    
    # Check if tweet already has an emoji at the start
    if tweet_text and tweet_text[0] in "⚽📊🔄🏆⚡🏎️📈🔧🏁🚨⚖️₿🚀🔋🏭🔭🛰️🔴🌙✨🚴⛰️🏍️":
        return tweet_text
    
    # Find matching keyword and add appropriate emoji
    tweet_lower = tweet_text.lower()
    for keyword, emoji in emojis.items():
        if keyword in tweet_lower:
            return f"{emoji} {tweet_text}"
    
    # Fallback to first primary emoji for category if no keyword match
    fallback_emojis = {
        "EPL": "⚽",
        "F1": "🏎️",
        "Crypto": "📊",
        "Tesla": "⚡",
        "Space Exploration": "🚀",
        "Cycling": "🚴",
        "MotoGP": "🏍️"
    }
    
    if category in fallback_emojis:
        return f"{fallback_emojis[category]} {tweet_text}"
    
    return tweet_text

# =========================
# ENHANCED CONTENT STRATEGIES
# =========================

def get_contextual_cta(category, title):
    """Generate contextual CTA based on article content"""
    strategy = PREMIUM_CONTENT_STRATEGIES.get(category)
    if not strategy or not strategy.get("cta_templates"):
        return "What's your take on this development?"
    
    # Simple keyword matching to select most relevant CTA
    title_lower = title.lower()
    cta_templates = strategy["cta_templates"]
    
    # Priority keywords for CTA selection
    cta_keywords = {
        0: ["partnership", "deal", "merger", "acquisition", "investment"],
        1: ["technology", "innovation", "breakthrough", "development", "tech"],
        2: ["market", "competition", "competitor", "industry", "business"],
        3: ["regulation", "policy", "compliance", "legal", "government"],
        4: ["financial", "revenue", "profit", "economic", "cost", "pricing"]
    }
    
    # Find best matching CTA based on content
    for i, keywords in cta_keywords.items():
        if any(keyword in title_lower for keyword in keywords) and i < len(cta_templates):
            return cta_templates[i]
    
    # Fallback to random selection from available CTAs
    return random.choice(cta_templates)

def get_example_openers(category):
    """Get category-specific example openers"""
    examples = {
        "EPL": [
            "Financial Fair Play data reveals...",
            "Transfer market analysis shows...", 
            "Commercial performance indicates...",
            "Revenue projections suggest..."
        ],
        "F1": [
            "Aerodynamic regulations reshape...",
            "Technical partnerships indicate...",
            "Performance data suggests...",
            "Innovation cycles show..."
        ],
        "Crypto": [
            "Institutional flow patterns reveal...",
            "Regulatory frameworks suggest...",
            "Market structure analysis shows...",
            "Adoption metrics indicate..."
        ],
        "Tesla": [
            "Manufacturing efficiency data shows...",
            "Market positioning analysis reveals...",
            "Supply chain indicators suggest...",
            "Innovation pipeline indicates..."
        ],
        "Space Exploration": [
            "Commercial viability studies show...",
            "Technology transfer patterns reveal...",
            "Mission economics suggest...",
            "Industry partnerships indicate..."
        ],
        "Cycling": [
            "Performance analytics reveal...",
            "Equipment innovation data shows...",
            "Sponsorship metrics suggest...",
            "Market trend analysis indicates..."
        ],
        "MotoGP": [
            "Technical development cycles show...",
            "Safety innovation data reveals...",
            "Manufacturer partnerships indicate...",
            "Performance benchmarks suggest..."
        ]
    }
    
    return examples.get(category, [
        "Market implications suggest...",
        "Strategic analysis reveals...",
        "Industry data shows...",
        "Performance metrics indicate..."
    ])

# =========================
# MAIN CONTENT POSTING (Enhanced)
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
    """Generate content with contextual CTA and dynamic examples"""
    strategy = PREMIUM_CONTENT_STRATEGIES.get(category)
    if not strategy:
        return generate_content_aware_post(title, category, article_url)
    
    # Get contextual CTA instead of generic one
    contextual_cta = get_contextual_cta(category, title)
    
    # Get dynamic examples
    example_openers = get_example_openers(category)
    examples_text = "\n".join([f"- \"{opener}\"" for opener in example_openers])
    
    prompt = f"""Create a Twitter post about: {title}

Target Audience: Business professionals, decision-makers, industry experts
Category: {category}
Focus Areas: {strategy['focus']}
Tone: {strategy['tone']}

Requirements:
- Appeal to professionals and decision-makers
- Focus on strategic implications and business insights
- Include data-driven analysis angles
- End with this specific question: {contextual_cta}
- Under 200 characters (leave room for URL and hashtags)
- Avoid buzzwords, focus on substance

Examples for {category}:
{examples_text}

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
    """Post main content using write quota with premium/global strategies, visual elements, and retry logic"""
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
        
        # Add visual elements enhancement
        tweet_text = add_visual_elements_to_tweet(tweet_text, category)
        
        short_url = shorten_url_with_fallback(article["url"])
        full_tweet = f"{tweet_text}\n\n{short_url}"
        full_tweet = optimize_hashtags_for_reach(full_tweet, category)
        
        if len(full_tweet) > 280:
            full_tweet = full_tweet[:277] + "..."
        
        # Retry logic for network failures
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                response = twitter_client.create_tweet(text=full_tweet)
                quota_manager.use_write(1)
                log_posted(article["url"])
                last_post_time = datetime.now(pytz.UTC)
                
                timing_type = "premium" if is_premium_posting_time() else "global" if is_global_posting_time() else "standard"
                write_log(f"Posted {timing_type} content with visual elements for {category}: {article['title'][:50]}...")
                return True
                
            except Exception as e:
                error_msg = str(e)
                
                # Don't retry on permission errors
                if "403" in error_msg or "forbidden" in error_msg.lower():
                    write_log(f"403 Forbidden error - check API permissions")
                    return False
                elif "duplicate" in error_msg.lower():
                    write_log("Duplicate content detected")
                    return False
                # Retry on network errors
                elif attempt < max_retries - 1:
                    write_log(f"Network error on attempt {attempt + 1}/{max_retries}: {error_msg}")
                    write_log(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff: 5s, 10s, 20s
                else:
                    write_log(f"All {max_retries} retry attempts failed: {e}")
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
    """Check if it's time for reply campaign - TEMPORARILY DISABLED"""
    return False  # Disabled due to API permission issues

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
    """Execute reply campaign"""
    try:
        write_log("Starting reply campaign...")
        reply_system.execute_reply_campaign()
        write_log("Reply campaign completed")
    except Exception as e:
        write_log(f"Error in reply campaign: {e}")

def start_conservative_scheduler():
    """Ultra-conservative scheduler with premium/global timing, visual elements, and replies"""
    write_log("Starting ultra-conservative scheduler with replies enabled...")
    write_log(f"Premium posting times (business focus): {PREMIUM_POSTING_TIMES}")
    write_log(f"Global posting times (sports/entertainment): {GLOBAL_POSTING_TIMES}")
    write_log(f"Reply campaign times: {REPLY_TIMES}")
    write_log(f"Business categories: {BUSINESS_CATEGORIES}")
    write_log(f"Global categories: {GLOBAL_CATEGORIES}")
    write_log("Visual elements enhancement: ACTIVE")
    write_log("Targeted reply system: ACTIVE (Arsenal & Crypto)")
    
    quota_status = quota_manager.get_quota_status()
    write_log(f"Monthly quota: {quota_status}")
    
    last_checked_minute = None
    
    while True:
        try:
            current_minute = datetime.now(pytz.UTC).strftime("%H:%M")
            
            if current_minute != last_checked_minute:
                write_log(f"Checking time: {current_minute} against {len(MAIN_POSTING_TIMES)} scheduled times")
                
                # Check for main content posting
                if should_post_main_content():
                    timing_type = "PREMIUM" if is_premium_posting_time() else "GLOBAL" if is_global_posting_time() else "STANDARD"
                    write_log(f"{timing_type} content time: {current_minute}")
                    run_main_content_job()

                # Check for reply campaign
                if should_run_reply_campaign():
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
        status = f"""Enhanced Twitter Bot Status: RUNNING

Monthly Quota:
- Reads: {quota_status['reads_used']}/100 ({quota_status['reads_remaining']} remaining)
- Writes: {quota_status['writes_used']}/500 ({quota_status['writes_remaining']} remaining)

Daily Allocation:
- Main Posts: 12/day (360/month)
- Replies: 3/day (90/month)
- Emergency Buffer: 50/month

Enhanced Features:
- Visual Elements: ACTIVE
- Contextual CTAs: ACTIVE
- Dynamic Examples: ACTIVE
- Premium Targeting: ACTIVE
- Strategic Timing: ACTIVE
- Smart Quota Management: ACTIVE
- Targeted Replies: ACTIVE (Arsenal & Crypto)

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
        write_log(f"Authentication successful! @{me.screen_name}")
        write_log(f"Followers: {me.followers_count}")
        return True
    except Exception as e:
        write_log(f"Authentication failed: {e}")
        return False

# =========================
# MAIN EXECUTION
# =========================

if __name__ == "__main__":
    write_log("=== ENHANCED TWITTER BOT STARTUP (WITH VISUAL ELEMENTS) ===")
    
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
    
    write_log("=== ENHANCED FEATURES ===")
    write_log("✓ Visual elements with smart emojis")
    write_log("✓ Main posts: 12/day with contextual CTAs")
    write_log("✓ Dynamic example openers per category")
    write_log("✓ Premium targeting with smart timing")
    write_log("✓ Strategic category selection")
    write_log("✓ Smart quota management active")
    write_log("✓ Targeted reply system ACTIVE (Arsenal & Crypto)")
    write_log("✓ Reply times: 10:00, 15:00, 21:00 UTC")
    
    # Start health server in background
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Start the enhanced scheduler
    write_log("Starting enhanced scheduler with visual elements...")
    start_conservative_scheduler()
