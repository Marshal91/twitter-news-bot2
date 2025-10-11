"""
Production-Ready Twitter Bot with All Improvements Applied
- Proper error handling and security
- Class-based state management
- Caching and performance optimizations
- Graceful shutdown
- Monitoring and alerting ready
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
from typing import Dict, List, Optional, Tuple
import pytz
from newspaper import Article, Config
from openai import OpenAI
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import logging
from logging.handlers import RotatingFileHandler
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from functools import lru_cache
from dataclasses import dataclass, asdict
import atexit

# Load environment variables
if os.path.exists('.env'):
    load_dotenv()

# =========================
# CONSTANTS
# =========================

# Rate limiting
DAILY_POST_LIMIT = 15
POST_INTERVAL_MINUTES = 90
FRESHNESS_WINDOW = timedelta(hours=72)
DAILY_REPLY_LIMIT = 3

# Probabilities
PRIORITY_CATEGORY_CHANCE = 0.7
TRENDING_HASHTAG_CHANCE = 0.3

# Cache TTL
RSS_CACHE_TTL_MINUTES = 30
URL_CACHE_TTL_HOURS = 24

# Retry configuration
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 5

# Posting times
PREMIUM_POSTING_TIMES = [
    "08:00", "12:00", "14:00", "16:00", "18:00", "22:00"
]

GLOBAL_POSTING_TIMES = [
    "02:00", "04:00", "06:00", "10:00", "20:00", "00:00"
]

MAIN_POSTING_TIMES = PREMIUM_POSTING_TIMES + GLOBAL_POSTING_TIMES

# Categories
GLOBAL_CATEGORIES = ["EPL", "F1", "MotoGP", "Cycling"]
BUSINESS_CATEGORIES = ["Crypto", "Tesla", "Space Exploration"]

# RSS feeds
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

CATEGORY_EMOJIS = {
    "EPL": {
        "breaking": "⚽", "news": "⚽", "analysis": "📊", "stats": "📊",
        "transfer": "🔄", "signing": "🔄", "match": "🏆", "goal": "⚡"
    },
    "F1": {
        "breaking": "🏎️", "news": "🏎️", "analysis": "📈", "tech": "🔧",
        "race": "🏁", "fastest": "⚡"
    },
    "Crypto": {
        "breaking": "🚨", "analysis": "📊", "trend": "📈", "bitcoin": "₿"
    },
    "Tesla": {
        "breaking": "⚡", "innovation": "🚀", "data": "📊", "battery": "🔋"
    },
    "Space Exploration": {
        "breaking": "🚀", "discovery": "🔭", "mission": "🛰️", "success": "✨"
    },
    "Cycling": {
        "breaking": "🚴", "race": "🏆", "tech": "⚙️", "sprint": "⚡"
    },
    "MotoGP": {
        "breaking": "🏍️", "race": "🏁", "tech": "⚙️", "champion": "🏆"
    }
}

# =========================
# LOGGING SETUP
# =========================

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

# =========================
# CUSTOM EXCEPTIONS
# =========================

class BotException(Exception):
    """Base exception for bot errors"""
    pass

class QuotaExceededException(BotException):
    """Raised when API quota is exceeded"""
    pass

class AuthenticationException(BotException):
    """Raised when authentication fails"""
    pass

class ContentGenerationException(BotException):
    """Raised when content generation fails"""
    pass

# =========================
# DATA CLASSES
# =========================

@dataclass
class Article:
    title: str
    url: str
    published: Optional[datetime] = None
    content_hash: Optional[str] = None
    
    def __post_init__(self):
        if self.content_hash is None:
            self.content_hash = hashlib.md5(
                f"{self.title}{self.url}".encode()
            ).hexdigest()

@dataclass
class QuotaStatus:
    reads_remaining: int
    writes_remaining: int
    reads_used: int
    writes_used: int
    month: str

# =========================
# API QUOTA MANAGER
# =========================

class APIQuotaManager:
    """Manages Twitter API quota tracking"""
    
    def __init__(self, quota_file: str = "api_quota.json"):
        self.quota_file = quota_file
        self.lock = threading.Lock()
        self.load_quota()
    
    def load_quota(self) -> None:
        """Load current month's quota usage"""
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
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading quota: {e}")
                self._reset_quota()
    
    def _reset_quota(self) -> None:
        """Reset quota for new month"""
        self.quota = {
            "month": datetime.now(pytz.UTC).strftime("%Y-%m"),
            "reads_used": 0,
            "writes_used": 0,
            "last_reset": datetime.now(pytz.UTC).isoformat()
        }
        self.save_quota()
    
    def save_quota(self) -> None:
        """Save quota to file"""
        with self.lock:
            try:
                with open(self.quota_file, 'w') as f:
                    json.dump(self.quota, f, indent=2)
            except IOError as e:
                logger.error(f"Error saving quota: {e}")
    
    def can_read(self, count: int = 1) -> bool:
        """Check if we can make read requests"""
        with self.lock:
            return (self.quota["reads_used"] + count) <= 100
    
    def can_write(self, count: int = 1) -> bool:
        """Check if we can make write requests"""
        with self.lock:
            return (self.quota["writes_used"] + count) <= 500
    
    def use_read(self, count: int = 1) -> bool:
        """Record read API usage"""
        with self.lock:
            if self.can_read(count):
                self.quota["reads_used"] += count
                self.save_quota()
                return True
            raise QuotaExceededException(f"Read quota exceeded: {self.quota['reads_used']}/100")
    
    def use_write(self, count: int = 1) -> bool:
        """Record write API usage"""
        with self.lock:
            if self.can_write(count):
                self.quota["writes_used"] += count
                self.save_quota()
                return True
            raise QuotaExceededException(f"Write quota exceeded: {self.quota['writes_used']}/500")
    
    def get_quota_status(self) -> QuotaStatus:
        """Get current quota status"""
        with self.lock:
            return QuotaStatus(
                reads_remaining=100 - self.quota["reads_used"],
                writes_remaining=500 - self.quota["writes_used"],
                reads_used=self.quota["reads_used"],
                writes_used=self.quota["writes_used"],
                month=self.quota["month"]
            )

# =========================
# CONTENT TRACKER
# =========================

class ContentTracker:
    """Tracks posted content to prevent duplicates"""
    
    def __init__(self, url_file: str = "posted_links.txt", 
                 hash_file: str = "posted_content_hashes.txt"):
        self.url_file = url_file
        self.hash_file = hash_file
        self.posted_urls = set(self._load_urls())
        self.content_hashes = set(self._load_hashes())
        self.lock = threading.Lock()
    
    def _load_urls(self) -> List[str]:
        """Load posted URLs from file"""
        if not os.path.exists(self.url_file):
            return []
        try:
            with open(self.url_file, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        except IOError:
            return []
    
    def _load_hashes(self) -> List[str]:
        """Load content hashes from file"""
        if not os.path.exists(self.hash_file):
            return []
        try:
            with open(self.hash_file, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        except IOError:
            return []
    
    def is_duplicate(self, url: str, content: str) -> bool:
        """Check if content is duplicate"""
        with self.lock:
            if url in self.posted_urls:
                return True
            
            content_hash = hashlib.md5(content.encode()).hexdigest()
            if content_hash in self.content_hashes:
                return True
            
            return False
    
    def mark_posted(self, url: str, content: str) -> None:
        """Mark content as posted"""
        with self.lock:
            try:
                with open(self.url_file, 'a') as f:
                    f.write(f"{url}\n")
                self.posted_urls.add(url)
                
                content_hash = hashlib.md5(content.encode()).hexdigest()
                with open(self.hash_file, 'a') as f:
                    f.write(f"{content_hash}\n")
                self.content_hashes.add(content_hash)
            except IOError as e:
                logger.error(f"Error marking content as posted: {e}")

# =========================
# URL CACHE
# =========================

class URLCache:
    """Cache for shortened URLs"""
    
    def __init__(self, cache_file: str = "url_cache.json"):
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self.lock = threading.Lock()
    
    def _load_cache(self) -> Dict[str, Dict]:
        """Load cache from file"""
        if not os.path.exists(self.cache_file):
            return {}
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    
    def _save_cache(self) -> None:
        """Save cache to file"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except IOError as e:
            logger.error(f"Error saving URL cache: {e}")
    
    def get(self, url: str) -> Optional[str]:
        """Get shortened URL from cache"""
        with self.lock:
            if url in self.cache:
                cached = self.cache[url]
                cached_time = datetime.fromisoformat(cached['timestamp'])
                if datetime.now(pytz.UTC) - cached_time < timedelta(hours=URL_CACHE_TTL_HOURS):
                    return cached['short_url']
            return None
    
    def set(self, url: str, short_url: str) -> None:
        """Store shortened URL in cache"""
        with self.lock:
            self.cache[url] = {
                'short_url': short_url,
                'timestamp': datetime.now(pytz.UTC).isoformat()
            }
            self._save_cache()

# =========================
# CONTENT GENERATOR
# =========================

class ContentGenerator:
    """Generates tweet content using GPT"""
    
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
    
    def generate_premium_content(self, title: str, category: str, 
                                 article_url: str) -> str:
        """Generate premium targeted content"""
        strategy = PREMIUM_CONTENT_STRATEGIES.get(category)
        if not strategy:
            return self.generate_standard_content(title, category, article_url)
        
        contextual_cta = self._get_contextual_cta(category, title)
        example_openers = self._get_example_openers(category)
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
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": f"You create content for business professionals and industry experts. Focus on strategic insights, market implications, and data-driven analysis that appeals to decision-makers in {category}."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=120,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Premium content generation failed: {e}")
            raise ContentGenerationException(f"Failed to generate premium content: {e}")
    
    def generate_standard_content(self, title: str, category: str,
                                  article_url: str) -> str:
        """Generate standard engaging content"""
        prompt = f"""Create an engaging Twitter post about: {title}

Category: {category}
Requirements:
- Under 200 characters (leave room for URL and hashtags)
- Ask thought-provoking questions
- Create curiosity or controversy
- Drive engagement and replies

Write ONLY the tweet text:"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Create viral Twitter content that drives engagement."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.8
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Standard content generation failed: {e}")
            raise ContentGenerationException(f"Failed to generate content: {e}")
    
    def _get_contextual_cta(self, category: str, title: str) -> str:
        """Get contextual CTA based on article content"""
        strategy = PREMIUM_CONTENT_STRATEGIES.get(category)
        if not strategy or not strategy.get("cta_templates"):
            return "What's your take on this development?"
        
        title_lower = title.lower()
        cta_templates = strategy["cta_templates"]
        
        cta_keywords = {
            0: ["partnership", "deal", "merger", "acquisition", "investment"],
            1: ["technology", "innovation", "breakthrough", "development", "tech"],
            2: ["market", "competition", "competitor", "industry", "business"],
            3: ["regulation", "policy", "compliance", "legal", "government"],
            4: ["financial", "revenue", "profit", "economic", "cost", "pricing"]
        }
        
        for i, keywords in cta_keywords.items():
            if any(keyword in title_lower for keyword in keywords) and i < len(cta_templates):
                return cta_templates[i]
        
        return random.choice(cta_templates)
    
    def _get_example_openers(self, category: str) -> List[str]:
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
# CONTENT ENHANCER
# =========================

class ContentEnhancer:
    """Adds visual elements and hashtags to tweets"""
    
    @staticmethod
    def add_visual_elements(tweet_text: str, category: str) -> str:
        """Add emoji based on content and category"""
        if tweet_text and tweet_text[0] in "⚽📊🔄🏆⚡🏎️📈🔧🏁🚨⚖️₿🚀🔋🏭🔭🛰️🔴🌙✨🚴⛰️🏍️":
            return tweet_text
        
        emojis = CATEGORY_EMOJIS.get(category, {})
        if not emojis:
            return tweet_text
        
        tweet_lower = tweet_text.lower()
        for keyword, emoji in emojis.items():
            if keyword in tweet_lower:
                return f"{emoji} {tweet_text}"
        
        fallback_emojis = {
            "EPL": "⚽", "F1": "🏎️", "Crypto": "📊", "Tesla": "⚡",
            "Space Exploration": "🚀", "Cycling": "🚴", "MotoGP": "🏍️"
        }
        
        if category in fallback_emojis:
            return f"{fallback_emojis[category]} {tweet_text}"
        
        return tweet_text
    
    @staticmethod
    def add_hashtags(tweet_text: str, category: str) -> str:
        """Add optimized hashtags"""
        hashtag_data = TRENDING_HASHTAGS.get(category)
        if not hashtag_data:
            return tweet_text
        
        selected = random.sample(hashtag_data["primary"], 1)
        
        if len(hashtag_data["secondary"]) >= 1:
            selected.extend(random.sample(hashtag_data["secondary"], 1))
        
        if random.random() < TRENDING_HASHTAG_CHANCE and hashtag_data["trending"]:
            selected.append(random.choice(hashtag_data["trending"]))
        
        hashtags = selected[:3]
        available_space = 280 - len(tweet_text) - 5
        hashtag_text = " " + " ".join(hashtags)
        
        if len(hashtag_text) <= available_space:
            return tweet_text + hashtag_text
        
        return tweet_text

# =========================
# RSS FETCHER
# =========================

class RSSFetcher:
    """Fetches and caches RSS feeds"""
    
    def __init__(self):
        self._cache = {}
        self._cache_lock = threading.Lock()
    
    def _get_cache_key(self) -> str:
        """Generate cache key based on time"""
        return datetime.now(pytz.UTC).strftime("%Y-%m-%d-%H-%M")[:14]  # 30-min buckets
    
    def fetch_feed(self, feed_url: str) -> List[Article]:
        """Fetch articles from RSS feed with caching"""
        cache_key = f"{feed_url}:{self._get_cache_key()}"
        
        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(feed_url, headers=headers, timeout=15)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            
            articles = []
            for entry in feed.entries[:3]:
                article = Article(
                    title=entry.title,
                    url=entry.link,
                    published=datetime(*entry.published_parsed[:6], tzinfo=pytz.UTC) 
                    if hasattr(entry, 'published_parsed') and entry.published_parsed else None
                )
                articles.append(article)
            
            with self._cache_lock:
                self._cache[cache_key] = articles
            
            return articles
            
        except (requests.RequestException, Exception) as e:
            logger.error(f"Error fetching RSS from {feed_url}: {e}")
            return []
    
    def get_articles_for_category(self, category: str) -> List[Article]:
        """Get articles for a category with feed rotation"""
        feeds = RSS_FEEDS.get(category, [])
        if not feeds:
            return []
        
        # Shuffle feeds for variety
        feeds_copy = feeds.copy()
        random.shuffle(feeds_copy)
        
        all_articles = []
        for feed in feeds_copy[:2]:  # Try first 2 shuffled feeds
            articles = self.fetch_feed(feed)
            if articles:
                all_articles.extend(articles)
                break
        
        return all_articles

# =========================
# URL SHORTENER
# =========================

class URLShortener:
    """Shortens URLs with caching"""
    
    def __init__(self):
        self.cache = URLCache()
    
    def shorten(self, long_url: str) -> str:
        """Shorten URL with fallback and caching"""
        # Check cache first
        cached = self.cache.get(long_url)
        if cached:
            return cached
        
        try:
            api_url = f"http://tinyurl.com/api-create.php?url={long_url}"
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200 and response.text.strip().startswith('http'):
                short_url = response.text.strip()
                self.cache.set(long_url, short_url)
                return short_url
        except requests.RequestException as e:
            logger.warning(f"URL shortening failed: {e}")
        
        return long_url

# =========================
# TWITTER PUBLISHER
# =========================

class TwitterPublisher:
    """Handles Twitter API interactions"""
    
    def __init__(self, api_key: str, api_secret: str, 
                 access_token: str, access_secret: str,
                 quota_manager: APIQuotaManager):
        self.quota_manager = quota_manager
        
        # Setup authentication
        auth = tweepy.OAuth1UserHandler(
            api_key, api_secret, access_token, access_secret
        )
        self.api = tweepy.API(auth)
        self.client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret
        )
    
    def verify_credentials(self) -> bool:
        """Verify Twitter authentication"""
        try:
            me = self.api.verify_credentials()
            logger.info(f"Authentication successful! @{me.screen_name}")
            logger.info(f"Followers: {me.followers_count}")
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise AuthenticationException(f"Twitter authentication failed: {e}")
    
    def post_tweet(self, text: str, max_retries: int = MAX_RETRIES) -> bool:
        """Post tweet with retry logic"""
        if not self.quota_manager.can_write(1):
            raise QuotaExceededException("Write quota exhausted")
        
        retry_delay = INITIAL_RETRY_DELAY
        
        for attempt in range(max_retries):
            try:
                response = self.client.create_tweet(text=text)
                self.quota_manager.use_write(1)
                logger.info(f"Tweet posted successfully: {text[:50]}...")
                return True
                
            except Exception as e:
                error_msg = str(e).lower()
                
                # Don't retry on these errors
                if "403" in error_msg or "forbidden" in error_msg:
                    logger.error("403 Forbidden - check API permissions")
                    return False
                elif "duplicate" in error_msg:
                    logger.warning("Duplicate content detected")
                    return False
                
                # Retry on network errors
                if attempt < max_retries - 1:
                    logger.warning(f"Tweet failed (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"All {max_retries} retry attempts failed: {e}")
                    return False
        
        return False

# =========================
# BOT STATE MANAGER
# =========================

class BotState:
    """Manages bot state"""
    
    def __init__(self):
        self.last_post_time: Optional[datetime] = None
        self.quota_manager = APIQuotaManager()
        self.content_tracker = ContentTracker()
        self.url_cache = URLCache()
        self.rss_fetcher = RSSFetcher()
        self.url_shortener = URLShortener()
        self.shutdown_requested = False
        self.lock = threading.Lock()
    
    def can_post_now(self) -> bool:
        """Check if enough time has passed since last post"""
        with self.lock:
            if self.last_post_time is None:
                return True
            time_since_last = datetime.now(pytz.UTC) - self.last_post_time
            return time_since_last.total_seconds() >= (POST_INTERVAL_MINUTES * 60)
    
    def mark_post_time(self) -> None:
        """Update last post time"""
        with self.lock:
            self.last_post_time = datetime.now(pytz.UTC)
    
    def request_shutdown(self) -> None:
        """Request graceful shutdown"""
        with self.lock:
            self.shutdown_requested = True
            logger.info("Shutdown requested")
    
    def should_shutdown(self) -> bool:
        """Check if shutdown was requested"""
        with self.lock:
            return self.shutdown_requested

# =========================
# TIMING STRATEGY
# =========================

class TimingStrategy:
    """Determines optimal posting times"""
    
    @staticmethod
    def is_premium_posting_time() -> bool:
        """Check if current time is optimal for premium demographics"""
        current_time = datetime.now(pytz.UTC).strftime("%H:%M")
        return current_time in PREMIUM_POSTING_TIMES
    
    @staticmethod
    def is_global_posting_time() -> bool:
        """Check if current time is optimal for global audiences"""
        current_time = datetime.now(pytz.UTC).strftime("%H:%M")
        return current_time in GLOBAL_POSTING_TIMES
    
    @staticmethod
    def should_use_premium_strategy(category: str) -> bool:
        """Determine if category should use premium targeting"""
        return (category in BUSINESS_CATEGORIES or 
                TimingStrategy.is_premium_posting_time())
    
    @staticmethod
    def should_use_global_strategy(category: str) -> bool:
        """Determine if category should use global timing strategy"""
        return (category in GLOBAL_CATEGORIES or 
                TimingStrategy.is_global_posting_time())
    
    @staticmethod
    def select_category() -> str:
        """Select category with timing strategy"""
        categories = list(RSS_FEEDS.keys())
        
        # During premium posting times, prioritize business categories
        if TimingStrategy.is_premium_posting_time():
            priority_categories = BUSINESS_CATEGORIES
            available_priority = [cat for cat in priority_categories if cat in categories]
            if available_priority and random.random() < PRIORITY_CATEGORY_CHANCE:
                category = random.choice(available_priority)
                logger.info(f"Selected business category for premium time: {category}")
                return category
        
        # During global posting times, prioritize global categories
        if TimingStrategy.is_global_posting_time():
            priority_categories = GLOBAL_CATEGORIES
            available_priority = [cat for cat in priority_categories if cat in categories]
            if available_priority and random.random() < PRIORITY_CATEGORY_CHANCE:
                category = random.choice(available_priority)
                logger.info(f"Selected global category for global time: {category}")
                return category
        
        # Regular random selection
        category = random.choice(categories)
        logger.info(f"Selected category: {category}")
        return category

# =========================
# MAIN BOT
# =========================

class TwitterBot:
    """Main bot orchestrator"""
    
    def __init__(self, openai_api_key: str, twitter_api_key: str,
                 twitter_api_secret: str, twitter_access_token: str,
                 twitter_access_secret: str):
        self.state = BotState()
        self.content_generator = ContentGenerator(openai_api_key)
        self.content_enhancer = ContentEnhancer()
        self.publisher = TwitterPublisher(
            twitter_api_key, twitter_api_secret,
            twitter_access_token, twitter_access_secret,
            self.state.quota_manager
        )
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # Register cleanup
        atexit.register(self._cleanup)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.state.request_shutdown()
    
    def _cleanup(self):
        """Cleanup on exit"""
        logger.info("Bot shutting down, saving state...")
        self.state.quota_manager.save_quota()
    
    def prepare_tweet(self, article: Article, category: str) -> Tuple[str, str]:
        """Generate and format tweet content"""
        # Choose content generation strategy
        if TimingStrategy.should_use_premium_strategy(category):
            tweet_text = self.content_generator.generate_premium_content(
                article.title, category, article.url
            )
        else:
            tweet_text = self.content_generator.generate_standard_content(
                article.title, category, article.url
            )
        
        # Add visual elements
        tweet_text = self.content_enhancer.add_visual_elements(tweet_text, category)
        
        # Shorten URL
        short_url = self.state.url_shortener.shorten(article.url)
        
        # Combine text and URL
        full_tweet = f"{tweet_text}\n\n{short_url}"
        
        # Add hashtags
        full_tweet = self.content_enhancer.add_hashtags(full_tweet, category)
        
        # Ensure tweet fits length limit
        if len(full_tweet) > 280:
            full_tweet = full_tweet[:277] + "..."
        
        return full_tweet, tweet_text
    
    def post_content(self, category: str) -> bool:
        """Post main content"""
        if not self.state.can_post_now():
            logger.info("Rate limited - too soon since last post")
            return False
        
        if not self.state.quota_manager.can_write(1):
            logger.warning("Write quota exhausted")
            return False
        
        # Get articles
        articles = self.state.rss_fetcher.get_articles_for_category(category)
        
        for article in articles:
            # Check if already posted
            if self.state.content_tracker.is_duplicate(article.url, article.title):
                continue
            
            try:
                # Prepare tweet
                full_tweet, base_text = self.prepare_tweet(article, category)
                
                # Post tweet
                if self.publisher.post_tweet(full_tweet):
                    self.state.content_tracker.mark_posted(article.url, base_text)
                    self.state.mark_post_time()
                    
                    timing_type = ("premium" if TimingStrategy.is_premium_posting_time() 
                                 else "global" if TimingStrategy.is_global_posting_time() 
                                 else "standard")
                    logger.info(f"Posted {timing_type} content for {category}: {article.title[:50]}...")
                    return True
                
            except (ContentGenerationException, QuotaExceededException) as e:
                logger.error(f"Failed to post article: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error posting article: {e}")
                continue
        
        logger.info(f"No new articles to post for {category}")
        return False
    
    def run_content_job(self) -> None:
        """Run main content posting job"""
        try:
            logger.info("Starting content posting job...")
            
            # Select category strategically
            category = TimingStrategy.select_category()
            
            # Try to post
            success = self.post_content(category)
            
            # Try backup category if needed
            if not success and self.state.quota_manager.can_write(1):
                categories = list(RSS_FEEDS.keys())
                backup_categories = [cat for cat in categories if cat != category]
                if backup_categories:
                    backup_category = random.choice(backup_categories)
                    logger.info(f"Trying backup category: {backup_category}")
                    self.post_content(backup_category)
            
            logger.info("Content posting job completed")
            
        except Exception as e:
            logger.error(f"Error in content job: {e}", exc_info=True)
    
    def should_post_now(self) -> bool:
        """Check if it's time to post"""
        current_time = datetime.now(pytz.UTC).strftime("%H:%M")
        return current_time in MAIN_POSTING_TIMES
    
    def run_scheduler(self) -> None:
        """Run the main scheduler loop"""
        logger.info("Starting scheduler...")
        logger.info(f"Premium posting times: {PREMIUM_POSTING_TIMES}")
        logger.info(f"Global posting times: {GLOBAL_POSTING_TIMES}")
        
        quota_status = self.state.quota_manager.get_quota_status()
        logger.info(f"Monthly quota - Reads: {quota_status.reads_used}/100, "
                   f"Writes: {quota_status.writes_used}/500")
        
        last_checked_minute = None
        
        while not self.state.should_shutdown():
            try:
                current_minute = datetime.now(pytz.UTC).strftime("%H:%M")
                
                if current_minute != last_checked_minute:
                    if self.should_post_now():
                        timing_type = ("PREMIUM" if TimingStrategy.is_premium_posting_time()
                                     else "GLOBAL" if TimingStrategy.is_global_posting_time()
                                     else "STANDARD")
                        logger.info(f"{timing_type} content time: {current_minute}")
                        self.run_content_job()
                    
                    last_checked_minute = current_minute
                
                time.sleep(30)
                
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                time.sleep(60)
        
        logger.info("Scheduler stopped")

# =========================
# HEALTH CHECK SERVER
# =========================

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Health check endpoint handler"""
    
    bot_state: Optional[BotState] = None
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        
        if self.bot_state:
            quota_status = self.bot_state.quota_manager.get_quota_status()
            status = f"""Twitter Bot Status: RUNNING

Monthly Quota:
- Reads: {quota_status.reads_used}/100 ({quota_status.reads_remaining} remaining)
- Writes: {quota_status.writes_used}/500 ({quota_status.writes_remaining} remaining)
- Month: {quota_status.month}

Daily Allocation:
- Main Posts: 15/day (450/month)
- Emergency Buffer: 50/month

Features:
- Visual Elements: ACTIVE
- Contextual CTAs: ACTIVE
- Premium Targeting: ACTIVE
- Strategic Timing: ACTIVE
- Smart Caching: ACTIVE
- Content Deduplication: ACTIVE

Last Post: {self.bot_state.last_post_time or 'Never'}
Status: {'Shutting down' if self.bot_state.should_shutdown() else 'Running'}
"""
        else:
            status = "Twitter Bot Status: STARTING\n"
        
        self.wfile.write(status.encode())
    
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress request logging

def start_health_server(bot_state: BotState, port: int = 10000):
    """Start health check server"""
    HealthCheckHandler.bot_state = bot_state
    
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        logger.info(f"Health server starting on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Health server failed: {e}")

# =========================
# CONFIGURATION VALIDATOR
# =========================

class ConfigValidator:
    """Validates configuration and environment"""
    
    @staticmethod
    def validate_env_vars() -> None:
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
            error_msg = f"Missing required environment variables: {', '.join(missing)}"
            logger.error(error_msg)
            raise EnvironmentError(error_msg)
        
        logger.info("All required environment variables present")
    
    @staticmethod
    def validate_config() -> None:
        """Validate configuration"""
        # Check posting times
        if not MAIN_POSTING_TIMES:
            raise ValueError("No posting times configured")
        
        # Check categories
        if not RSS_FEEDS:
            raise ValueError("No RSS feeds configured")
        
        # Check rate limits
        if POST_INTERVAL_MINUTES < 1:
            raise ValueError("Post interval must be at least 1 minute")
        
        logger.info("Configuration validated successfully")

# =========================
# MAIN EXECUTION
# =========================

def main():
    """Main entry point"""
    logger.info("=== TWITTER BOT STARTING ===")
    
    try:
        # Validate configuration
        ConfigValidator.validate_env_vars()
        ConfigValidator.validate_config()
        
        # Get credentials from environment
        openai_api_key = os.getenv("OPENAI_API_KEY")
        twitter_api_key = os.getenv("TWITTER_API_KEY")
        twitter_api_secret = os.getenv("TWITTER_API_SECRET")
        twitter_access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        twitter_access_secret = os.getenv("TWITTER_ACCESS_SECRET")
        
        # Initialize bot
        bot = TwitterBot(
            openai_api_key=openai_api_key,
            twitter_api_key=twitter_api_key,
            twitter_api_secret=twitter_api_secret,
            twitter_access_token=twitter_access_token,
            twitter_access_secret=twitter_access_secret
        )
        
        # Verify authentication
        bot.publisher.verify_credentials()
        
        # Display startup info
        quota_status = bot.state.quota_manager.get_quota_status()
        logger.info("=== QUOTA STATUS ===")
        logger.info(f"Reads: {quota_status.reads_used}/100 ({quota_status.reads_remaining} remaining)")
        logger.info(f"Writes: {quota_status.writes_used}/500 ({quota_status.writes_remaining} remaining)")
        
        logger.info("=== FEATURES ===")
        logger.info("✓ Visual elements with smart emojis")
        logger.info("✓ Contextual CTAs and dynamic examples")
        logger.info("✓ Premium targeting with smart timing")
        logger.info("✓ RSS feed caching (30-min TTL)")
        logger.info("✓ URL shortening cache (24-hour TTL)")
        logger.info("✓ Content deduplication")
        logger.info("✓ Graceful shutdown handling")
        logger.info("✓ Retry logic with exponential backoff")
        
        # Start health server in background
        port = int(os.environ.get('PORT', 10000))
        health_thread = threading.Thread(
            target=start_health_server,
            args=(bot.state, port),
            daemon=True
        )
        health_thread.start()
        
        # Start the scheduler
        logger.info("Starting scheduler...")
        bot.run_scheduler()
        
    except (EnvironmentError, AuthenticationException) as e:
        logger.error(f"CRITICAL: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"CRITICAL ERROR: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("=== TWITTER BOT STOPPED ===")

if __name__ == "__main__":
    main()
