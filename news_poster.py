"""
Complete Self-Learning Twitter Bot with Performance Analytics
API Limits: 100 reads/month (3/day), 500 writes/month (12 posts + 3 replies/day)
Enhanced with machine learning capabilities that adapt based on performance
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



# Try to load .env file if it exists
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

# Persistent storage path (configurable for cloud deployments)
# For Render: Set PERSISTENT_STORAGE_PATH=/var/data in environment variables
# For local: Leave unset (defaults to current directory)
STORAGE_PATH = os.getenv("PERSISTENT_STORAGE_PATH", ".")

# Ensure storage directory exists
try:
    os.makedirs(STORAGE_PATH, exist_ok=True)
    print(f"INFO: Using persistent storage path: {STORAGE_PATH}")
except Exception as e:
    print(f"WARNING: Could not create storage directory: {e}")
    STORAGE_PATH = "."  # Fallback to current directory

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
# SELF-LEARNING PERFORMANCE ANALYTICS
# =========================

class PerformanceLearningSystem:
    """
    Analyzes tweet performance and adapts strategies based on what works.
    Uses read quota efficiently: 1 read per analysis session (daily).
    """
    
    def __init__(self):
        self.performance_db = os.path.join(STORAGE_PATH, "tweet_performance.json")
        self.learning_insights = os.path.join(STORAGE_PATH, "learning_insights.json")
        self.min_tweets_for_learning = 10
        self.load_performance_data()
        self.load_learning_insights()
    
    def load_performance_data(self):
        """Load historical tweet performance data"""
        try:
            if os.path.exists(self.performance_db):
                with open(self.performance_db, 'r') as f:
                    self.performance_data = json.load(f)
            else:
                self.performance_data = {
                    "tweets": [],
                    "last_analysis": None,
                    "total_analyzed": 0
                }
        except Exception as e:
            logging.error(f"Error loading performance data: {e}")
            self.performance_data = {
                "tweets": [],
                "last_analysis": None,
                "total_analyzed": 0
            }
    
    def load_learning_insights(self):
        """Load learned insights about what works"""
        try:
            if os.path.exists(self.learning_insights):
                with open(self.learning_insights, 'r') as f:
                    self.insights = json.load(f)
            else:
                self.insights = {
                    "category_performance": {},
                    "time_slot_performance": {},
                    "hashtag_effectiveness": {},
                    "content_style_scores": {},
                    "emoji_impact": {},
                    "cta_effectiveness": {},
                    "best_practices": [],
                    "avoid_patterns": []
                }
        except Exception as e:
            logging.error(f"Error loading insights: {e}")
            self.insights = {
                "category_performance": {},
                "time_slot_performance": {},
                "hashtag_effectiveness": {},
                "content_style_scores": {},
                "emoji_impact": {},
                "cta_effectiveness": {},
                "best_practices": [],
                "avoid_patterns": []
            }
    
    def save_performance_data(self):
        """Save performance data to file"""
        try:
            with open(self.performance_db, 'w') as f:
                json.dump(self.performance_data, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving performance data: {e}")
    
    def save_learning_insights(self):
        """Save learning insights to file"""
        try:
            with open(self.learning_insights, 'w') as f:
                json.dump(self.insights, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving insights: {e}")
    
    def record_tweet_posted(self, tweet_id, tweet_text, category, time_slot, hashtags, has_emoji, has_cta):
        """Record when a tweet is posted for later analysis"""
        tweet_record = {
            "id": str(tweet_id),
            "text": tweet_text,
            "category": category,
            "time_slot": time_slot,
            "hashtags": hashtags,
            "has_emoji": has_emoji,
            "has_cta": has_cta,
            "posted_at": datetime.now(pytz.UTC).isoformat(),
            "analyzed": False,
            "metrics": None
        }
        
        self.performance_data["tweets"].append(tweet_record)
        self.save_performance_data()
        write_log(f"📊 Recorded tweet {tweet_id} for learning analysis")
    
    def should_analyze_performance(self):
        """Check if it's time to analyze performance (once daily)"""
        if not self.performance_data["last_analysis"]:
            return len(self.performance_data["tweets"]) >= self.min_tweets_for_learning
        
        last_analysis = datetime.fromisoformat(self.performance_data["last_analysis"])
        time_since_analysis = datetime.now(pytz.UTC) - last_analysis
        
        unanalyzed = [t for t in self.performance_data["tweets"] if not t["analyzed"]]
        return time_since_analysis.total_seconds() >= 86400 and len(unanalyzed) > 0
    
    def fetch_tweet_metrics(self, tweet_ids):
        """Fetch engagement metrics for tweets using read quota"""
        if not quota_manager.can_read(1):
            write_log("Cannot fetch metrics - read quota exhausted")
            return {}
        
        try:
            tweets = twitter_client.get_tweets(
                ids=tweet_ids[:100],
                tweet_fields=['public_metrics', 'non_public_metrics', 'created_at']
            )
            
            quota_manager.use_read(1)
            
            metrics_dict = {}
            if tweets.data:
                for tweet in tweets.data:
                    metrics = tweet.public_metrics
                    engagement_score = (
                        metrics['like_count'] * 1.0 +
                        metrics['retweet_count'] * 2.0 +
                        metrics['reply_count'] * 3.0 +
                        metrics['quote_count'] * 2.5
                    )
                    
                    metrics_dict[str(tweet.id)] = {
                        "likes": metrics['like_count'],
                        "retweets": metrics['retweet_count'],
                        "replies": metrics['reply_count'],
                        "quotes": metrics['quote_count'],
                        "impressions": tweet.non_public_metrics.get('impression_count', 0) if hasattr(tweet, 'non_public_metrics') else 0,,
                        "engagement_score": engagement_score,
                        "engagement_rate": engagement_score / max(tweet.non_public_metrics.get('impression_count', 1) if hasattr(tweet, 'non_public_metrics') else 1, 1)
                    }
            
            return metrics_dict
            
        except Exception as e:
            write_log(f"Error fetching tweet metrics: {e}")
            return {}
    
    def analyze_performance(self):
        """Analyze tweet performance and update learning insights"""
        write_log("🧠 Starting performance analysis...")
        
        cutoff_time = datetime.now(pytz.UTC) - timedelta(hours=24)
        unanalyzed = [
            t for t in self.performance_data["tweets"]
            if not t["analyzed"] and datetime.fromisoformat(t["posted_at"]) < cutoff_time
        ]
        
        if not unanalyzed:
            write_log("No tweets ready for analysis")
            return
        
        tweet_ids = [t["id"] for t in unanalyzed]
        metrics = self.fetch_tweet_metrics(tweet_ids)
        
        if not metrics:
            write_log("Could not fetch metrics")
            return
        
        for tweet in unanalyzed:
            if tweet["id"] in metrics:
                tweet["metrics"] = metrics[tweet["id"]]
                tweet["analyzed"] = True
        
        self._analyze_category_performance()
        self._analyze_time_slot_performance()
        self._analyze_hashtag_effectiveness()
        self._analyze_emoji_impact()
        self._analyze_cta_effectiveness()
        self._identify_best_practices()
        
        self.performance_data["last_analysis"] = datetime.now(pytz.UTC).isoformat()
        self.performance_data["total_analyzed"] += len([t for t in unanalyzed if t["analyzed"]])
        
        self.save_performance_data()
        self.save_learning_insights()
        
        write_log(f"✅ Performance analysis complete. Analyzed {len(metrics)} tweets.")
        self._log_key_insights()
    
    def _analyze_category_performance(self):
        """Analyze which categories perform best"""
        category_stats = {}
        
        for tweet in self.performance_data["tweets"]:
            if tweet["analyzed"] and tweet["metrics"]:
                category = tweet["category"]
                if category not in category_stats:
                    category_stats[category] = {
                        "total_engagement": 0,
                        "count": 0,
                        "avg_engagement": 0
                    }
                
                category_stats[category]["total_engagement"] += tweet["metrics"]["engagement_score"]
                category_stats[category]["count"] += 1
        
        for category, stats in category_stats.items():
            stats["avg_engagement"] = stats["total_engagement"] / stats["count"]
        
        self.insights["category_performance"] = category_stats
    
    def _analyze_time_slot_performance(self):
        """Analyze which time slots perform best"""
        time_stats = {}
        
        for tweet in self.performance_data["tweets"]:
            if tweet["analyzed"] and tweet["metrics"]:
                time_slot = tweet["time_slot"]
                if time_slot not in time_stats:
                    time_stats[time_slot] = {
                        "total_engagement": 0,
                        "count": 0,
                        "avg_engagement": 0
                    }
                
                time_stats[time_slot]["total_engagement"] += tweet["metrics"]["engagement_score"]
                time_stats[time_slot]["count"] += 1
        
        for time_slot, stats in time_stats.items():
            stats["avg_engagement"] = stats["total_engagement"] / stats["count"]
        
        self.insights["time_slot_performance"] = time_stats
    
    def _analyze_hashtag_effectiveness(self):
        """Analyze hashtag performance"""
        hashtag_stats = {}
        
        for tweet in self.performance_data["tweets"]:
            if tweet["analyzed"] and tweet["metrics"]:
                for hashtag in tweet["hashtags"]:
                    if hashtag not in hashtag_stats:
                        hashtag_stats[hashtag] = {
                            "total_engagement": 0,
                            "count": 0,
                            "avg_engagement": 0
                        }
                    
                    hashtag_stats[hashtag]["total_engagement"] += tweet["metrics"]["engagement_score"]
                    hashtag_stats[hashtag]["count"] += 1
        
        for hashtag, stats in hashtag_stats.items():
            if stats["count"] >= 3:
                stats["avg_engagement"] = stats["total_engagement"] / stats["count"]
        
        self.insights["hashtag_effectiveness"] = hashtag_stats
    
    def _analyze_emoji_impact(self):
        """Analyze impact of emoji usage"""
        emoji_stats = {"with_emoji": [], "without_emoji": []}
        
        for tweet in self.performance_data["tweets"]:
            if tweet["analyzed"] and tweet["metrics"]:
                key = "with_emoji" if tweet["has_emoji"] else "without_emoji"
                emoji_stats[key].append(tweet["metrics"]["engagement_score"])
        
        if emoji_stats["with_emoji"] and emoji_stats["without_emoji"]:
            self.insights["emoji_impact"] = {
                "with_emoji_avg": sum(emoji_stats["with_emoji"]) / len(emoji_stats["with_emoji"]),
                "without_emoji_avg": sum(emoji_stats["without_emoji"]) / len(emoji_stats["without_emoji"]),
                "improvement_factor": (sum(emoji_stats["with_emoji"]) / len(emoji_stats["with_emoji"])) / 
                                    (sum(emoji_stats["without_emoji"]) / len(emoji_stats["without_emoji"]))
            }
    
    def _analyze_cta_effectiveness(self):
        """Analyze effectiveness of CTAs"""
        cta_stats = {"with_cta": [], "without_cta": []}
        
        for tweet in self.performance_data["tweets"]:
            if tweet["analyzed"] and tweet["metrics"]:
                key = "with_cta" if tweet["has_cta"] else "without_cta"
                cta_stats[key].append(tweet["metrics"]["engagement_score"])
        
        if cta_stats["with_cta"] and cta_stats["without_cta"]:
            self.insights["cta_effectiveness"] = {
                "with_cta_avg": sum(cta_stats["with_cta"]) / len(cta_stats["with_cta"]),
                "without_cta_avg": sum(cta_stats["without_cta"]) / len(cta_stats["without_cta"]),
                "improvement_factor": (sum(cta_stats["with_cta"]) / len(cta_stats["with_cta"])) / 
                                    (sum(cta_stats["without_cta"]) / len(cta_stats["without_cta"]))
            }
    
    def _identify_best_practices(self):
        """Identify best practices from top-performing tweets"""
        analyzed_tweets = [t for t in self.performance_data["tweets"] if t["analyzed"] and t["metrics"]]
        
        if len(analyzed_tweets) < 10:
            return
        
        sorted_tweets = sorted(analyzed_tweets, key=lambda x: x["metrics"]["engagement_score"], reverse=True)
        top_10_percent = sorted_tweets[:max(len(sorted_tweets) // 10, 5)]
        bottom_10_percent = sorted_tweets[-max(len(sorted_tweets) // 10, 5):]
        
        best_practices = []
        
        top_categories = {}
        for tweet in top_10_percent:
            category = tweet["category"]
            top_categories[category] = top_categories.get(category, 0) + 1
        
        if top_categories:
            best_category = max(top_categories, key=top_categories.get)
            best_practices.append(f"Category '{best_category}' performs best")
        
        top_time_slots = {}
        for tweet in top_10_percent:
            time_slot = tweet["time_slot"]
            top_time_slots[time_slot] = top_time_slots.get(time_slot, 0) + 1
        
        if top_time_slots:
            best_time = max(top_time_slots, key=top_time_slots.get)
            best_practices.append(f"Time slot '{best_time}' shows strong performance")
        
        emoji_in_top = sum(1 for t in top_10_percent if t["has_emoji"])
        if emoji_in_top / len(top_10_percent) > 0.7:
            best_practices.append("Emoji usage correlates with higher engagement")
        
        cta_in_top = sum(1 for t in top_10_percent if t["has_cta"])
        if cta_in_top / len(top_10_percent) > 0.7:
            best_practices.append("CTAs drive more engagement")
        
        self.insights["best_practices"] = best_practices
        
        avoid_patterns = []
        bottom_categories = {}
        for tweet in bottom_10_percent:
            category = tweet["category"]
            bottom_categories[category] = bottom_categories.get(category, 0) + 1
        
        if bottom_categories:
            worst_category = max(bottom_categories, key=bottom_categories.get)
            avoid_patterns.append(f"Category '{worst_category}' shows lower engagement")
        
        self.insights["avoid_patterns"] = avoid_patterns
    
    def _log_key_insights(self):
        """Log key learning insights"""
        write_log("=== 🎯 KEY LEARNING INSIGHTS ===")
        
        if self.insights["category_performance"]:
            sorted_cats = sorted(
                self.insights["category_performance"].items(),
                key=lambda x: x[1]["avg_engagement"],
                reverse=True
            )
            write_log(f"🏆 Top Category: {sorted_cats[0][0]} (avg: {sorted_cats[0][1]['avg_engagement']:.2f})")
        
        if self.insights["time_slot_performance"]:
            sorted_times = sorted(
                self.insights["time_slot_performance"].items(),
                key=lambda x: x[1]["avg_engagement"],
                reverse=True
            )
            write_log(f"⏰ Best Time Slot: {sorted_times[0][0]} (avg: {sorted_times[0][1]['avg_engagement']:.2f})")
        
        if self.insights.get("emoji_impact"):
            improvement = self.insights["emoji_impact"]["improvement_factor"]
            write_log(f"😀 Emoji Impact: {improvement:.2f}x engagement boost")
        
        if self.insights.get("cta_effectiveness"):
            improvement = self.insights["cta_effectiveness"]["improvement_factor"]
            write_log(f"❓ CTA Impact: {improvement:.2f}x engagement boost")
        
        for practice in self.insights["best_practices"]:
            write_log(f"✓ {practice}")
    
    def get_recommended_category(self, available_categories):
        """Get recommended category based on learning"""
        if not self.insights["category_performance"]:
            return random.choice(available_categories)
        
        category_scores = {}
        for category in available_categories:
            if category in self.insights["category_performance"]:
                stats = self.insights["category_performance"][category]
                category_scores[category] = stats["avg_engagement"]
            else:
                category_scores[category] = 0
        
        if random.random() < 0.8 and category_scores:
            return max(category_scores, key=category_scores.get)
        else:
            return random.choice(available_categories)
    
    def get_recommended_time_slot(self, current_time):
        """Check if current time is optimal based on learning"""
        if not self.insights["time_slot_performance"]:
            return True
        
        time_slot = current_time
        if time_slot in self.insights["time_slot_performance"]:
            stats = self.insights["time_slot_performance"][time_slot]
            avg_all = sum(s["avg_engagement"] for s in self.insights["time_slot_performance"].values()) / len(self.insights["time_slot_performance"])
            return stats["avg_engagement"] >= avg_all * 0.8
        
        return True
    
    def should_use_emoji(self):
        """Recommend emoji usage based on learning"""
        if not self.insights.get("emoji_impact"):
            return True
        return self.insights["emoji_impact"]["improvement_factor"] > 1.0
    
    def should_use_cta(self):
        """Recommend CTA usage based on learning"""
        if not self.insights.get("cta_effectiveness"):
            return True
        return self.insights["cta_effectiveness"]["improvement_factor"] > 1.0

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
CONTENT_HASH_LOG = os.path.join(STORAGE_PATH, "posted_content_hashes.txt")

DAILY_POST_LIMIT = 15
POST_INTERVAL_MINUTES = 90
last_post_time = None
FRESHNESS_WINDOW = timedelta(hours=72)

DAILY_REPLY_LIMIT = 3

PREMIUM_POSTING_TIMES = [
    "08:00", "12:00", "18:00", "22:00"
]

GLOBAL_POSTING_TIMES = [
    "02:00", "04:00", "06:00", "10:00", "20:00", "00:00", "14:00", "16:00"
]

MAIN_POSTING_TIMES = PREMIUM_POSTING_TIMES + GLOBAL_POSTING_TIMES

REPLY_TIMES = [
    "10:25", "16:30", "22:30"
]

GLOBAL_CATEGORIES = ["EPL", "F1", "MotoGP", "Cycling"]
BUSINESS_CATEGORIES = ["Crypto", "Tesla", "Space Exploration"]

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
# TARGETED REPLY SYSTEM
# =========================

class TargetedReplySystem:
    def __init__(self):
        self.reply_log_file = os.path.join(STORAGE_PATH, "replied_tweets.json")
        self.daily_reply_limit = 3
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
            tweets = twitter_client.search_recent_tweets(
                query=query,
                max_results=max_results,
                tweet_fields=['author_id', 'created_at', 'public_metrics']
            )
            
            quota_manager.use_read(1)
            
            if tweets.data:
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
                
                reply_text = self.generate_reply(tweet.text, topic)
                if reply_text:
                    success = self.post_reply(tweet.id, reply_text)
                    if success:
                        write_log(f"Replied to {topic} tweet: {tweet.text[:50]}...")
                        time.sleep(60)

reply_system = TargetedReplySystem()

# =========================
# VISUAL ELEMENTS ENHANCEMENT
# =========================

def add_visual_elements_to_tweet(tweet_text, category):
    """Add visual elements to increase engagement"""
    
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
    
    emojis = category_emojis.get(category, {})
    if not emojis:
        return tweet_text
    
    if tweet_text and tweet_text[0] in "⚽📊🔄🏆⚡🏎️📈🔧🏁🚨⚖️₿🚀🔋🏭🔭🛰️🔴🌙✨🚴⛰️🏍️":
        return tweet_text
    
    tweet_lower = tweet_text.lower()
    for keyword, emoji in emojis.items():
        if keyword in tweet_lower:
            return f"{emoji} {tweet_text}"
    
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
# CONTENT STRATEGIES
# =========================

def get_contextual_cta(category, title):
    """Generate contextual CTA based on article content"""
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
# MAIN CONTENT POSTING
# =========================

def validate_env_vars():
    """Validate required environment variables"""
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
        for entry in feed.entries[:3]:
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
    
    for feed in feeds[:2]:
        feed_articles = fetch_rss(feed)
        if feed_articles:
            articles.extend(feed_articles)
            break
    
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
    
    contextual_cta = get_contextual_cta(category, title)
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
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        write_log(f"Premium content generation failed: {e}")
        return generate_content_aware_post(title, category, article_url)

def detect_category_with_learning():
    """Enhanced category selection using learning insights"""
    categories = list(RSS_FEEDS.keys())
    
    recommended_category = learning_system.get_recommended_category(categories)
    
    if is_premium_posting_time():
        priority_categories = BUSINESS_CATEGORIES
        available_priority = [cat for cat in priority_categories if cat in categories]
        if available_priority and recommended_category in available_priority:
            write_log(f"🎯 Learning + Premium: Selected {recommended_category}")
            return recommended_category
        elif available_priority and random.random() < 0.5:
            category = random.choice(available_priority)
            write_log(f"Premium override: Selected {category}")
            return category
    
    if is_global_posting_time():
        priority_categories = GLOBAL_CATEGORIES
        available_priority = [cat for cat in priority_categories if cat in categories]
        if available_priority and recommended_category in available_priority:
            write_log(f"🎯 Learning + Global: Selected {recommended_category}")
            return recommended_category
        elif available_priority and random.random() < 0.5:
            category = random.choice(available_priority)
            write_log(f"Global override: Selected {category}")
            return category
    
    write_log(f"🎯 Learning recommendation: {recommended_category}")
    return recommended_category

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

def post_main_content_with_learning(category):
    """Enhanced posting with performance recording and learning"""
    global last_post_time
    
    if not can_post_now() or not quota_manager.can_write(1):
        write_log("Cannot post - rate limited or quota exhausted")
        return False
    
    current_time = datetime.now(pytz.UTC).strftime("%H:%M")
    if not learning_system.get_recommended_time_slot(current_time):
        write_log(f"🧠 Learning system: Time slot {current_time} shows below-average performance, skipping")
        return False
    
    articles = get_articles_for_category(category)
    
    for article in articles:
        if has_been_posted(article["url"]):
            continue
        
        use_premium = should_use_premium_strategy(category)
        if use_premium:
            tweet_text = generate_premium_targeted_content(article["title"], category, article["url"])
        else:
            tweet_text = generate_content_aware_post(article["title"], category, article["url"])
        
        has_emoji = learning_system.should_use_emoji()
        if has_emoji:
            tweet_text = add_visual_elements_to_tweet(tweet_text, category)
        
        has_cta = any(q in tweet_text for q in ["?", "What's", "How", "Which", "Who"])
        
        short_url = shorten_url_with_fallback(article["url"])
        full_tweet = f"{tweet_text}\n\n{short_url}"
        full_tweet = optimize_hashtags_for_reach(full_tweet, category)
        
        hashtags = [word for word in full_tweet.split() if word.startswith('#')]
        
        if len(full_tweet) > 280:
            full_tweet = full_tweet[:277] + "..."
        
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                response = twitter_client.create_tweet(text=full_tweet)
                tweet_id = response.data['id']
                
                quota_manager.use_write(1)
                log_posted(article["url"])
                last_post_time = datetime.now(pytz.UTC)
                
                learning_system.record_tweet_posted(
                    tweet_id=tweet_id,
                    tweet_text=full_tweet,
                    category=category,
                    time_slot=current_time,
                    hashtags=hashtags,
                    has_emoji=has_emoji,
                    has_cta=has_cta
                )
                
                timing_type = "premium" if is_premium_posting_time() else "global" if is_global_posting_time() else "standard"
                write_log(f"✅ Posted {timing_type} content (learning-optimized): {article['title'][:50]}...")
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
    return False  # Disabled due to API permission issues

def run_main_content_job_with_learning():
    """Enhanced main content job with learning"""
    try:
        write_log("🚀 Starting strategic main content job with learning...")
        
        if learning_system.should_analyze_performance():
            write_log("🧠 Running performance analysis...")
            learning_system.analyze_performance()
        
        category = detect_category_with_learning()
        
        success = post_main_content_with_learning(category)
        if not success:
            categories = list(RSS_FEEDS.keys())
            backup_categories = [cat for cat in categories if cat != category]
            if backup_categories and quota_manager.can_write(1):
                backup_category = learning_system.get_recommended_category(backup_categories)
                write_log(f"Trying learning-recommended backup: {backup_category}")
                post_main_content_with_learning(backup_category)
        
        write_log("✅ Strategic main content job with learning completed")
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

def start_learning_scheduler():
    """Scheduler with integrated learning system and continuous heartbeat"""
    write_log("🧠 Starting SELF-LEARNING scheduler...")
    write_log("="*60)
    write_log("Learning system: ACTIVE - Bot adapts based on performance data")
    write_log(f"Performance analysis: Daily (when {learning_system.min_tweets_for_learning}+ tweets posted)")
    write_log(f"Premium posting times: {PREMIUM_POSTING_TIMES}")
    write_log(f"Global posting times: {GLOBAL_POSTING_TIMES}")
    write_log(f"Business categories: {BUSINESS_CATEGORIES}")
    write_log(f"Global categories: {GLOBAL_CATEGORIES}")
    write_log("Visual elements: ACTIVE")
    write_log("Targeted replies: DISABLED (API limitations)")
    write_log("Continuous heartbeat: ACTIVE (30-second intervals)")
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
            
            # Heartbeat logging every 5 minutes to show bot is alive
            if (current_time - last_heartbeat).total_seconds() >= heartbeat_interval:
                quota_status = quota_manager.get_quota_status()
                write_log(f"💓 HEARTBEAT #{loop_count} - Bot running | Time: {current_minute} UTC | "
                         f"Writes: {quota_status['writes_used']}/500 | "
                         f"Reads: {quota_status['reads_used']}/100 | "
                         f"Analyzed: {learning_system.performance_data['total_analyzed']} tweets")
                last_heartbeat = current_time
            
            # Check for scheduled actions only when minute changes
            if current_minute != last_checked_minute:
                write_log(f"🕐 Time check: {current_minute} UTC (Loop #{loop_count})")
                
                if should_post_main_content():
                    timing_type = "PREMIUM" if is_premium_posting_time() else "GLOBAL" if is_global_posting_time() else "STANDARD"
                    write_log(f"⏰ {timing_type} content time: {current_minute}")
                    run_main_content_job_with_learning()

                if should_run_reply_campaign():
                    write_log(f"⏰ Reply campaign time: {current_minute}")
                    run_reply_job()
                
                last_checked_minute = current_minute
            
            # Sleep for 30 seconds to keep the process alive
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
        
        status = f"""Self-Learning Twitter Bot Status: RUNNING

=== MONTHLY QUOTA ===
Reads: {quota_status['reads_used']}/100 ({quota_status['reads_remaining']} remaining)
Writes: {quota_status['writes_used']}/500 ({quota_status['writes_remaining']} remaining)

=== DAILY ALLOCATION ===
Main Posts: 12/day (360/month)
Replies: 3/day (90/month)
Emergency Buffer: 50/month

=== LEARNING SYSTEM ===
Status: ACTIVE
Tweets Analyzed: {learning_status['total_analyzed']}
Last Analysis: {learning_status['last_analysis'] or 'Never'}
Pending Analysis: {len([t for t in learning_status['tweets'] if not t['analyzed']])} tweets

=== LEARNING INSIGHTS ==="""

        if learning_system.insights.get("category_performance"):
            sorted_cats = sorted(
                learning_system.insights["category_performance"].items(),
                key=lambda x: x[1]["avg_engagement"],
                reverse=True
            )
            status += f"\nTop Category: {sorted_cats[0][0]} (avg: {sorted_cats[0][1]['avg_engagement']:.2f})"
        
        if learning_system.insights.get("emoji_impact"):
            improvement = learning_system.insights["emoji_impact"]["improvement_factor"]
            status += f"\nEmoji Impact: {improvement:.2f}x boost"
        
        if learning_system.insights.get("cta_effectiveness"):
            improvement = learning_system.insights["cta_effectiveness"]["improvement_factor"]
            status += f"\nCTA Impact: {improvement:.2f}x boost"

        status += f"""

=== ENHANCED FEATURES ===
✓ Self-Learning Analytics
✓ Performance-Based Optimization
✓ Visual Elements with Smart Emojis
✓ Contextual CTAs
✓ Dynamic Example Openers
✓ Premium Targeting
✓ Strategic Timing
✓ Smart Quota Management

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

def test_learning_system():
    """Test learning system functionality"""
    write_log("Testing learning system...")
    
    # Check if data files exist
    if os.path.exists(learning_system.performance_db):
        write_log(f"✓ Performance DB found: {len(learning_system.performance_data['tweets'])} tweets recorded")
    else:
        write_log("○ Performance DB not found (will be created on first post)")
    
    if os.path.exists(learning_system.learning_insights):
        write_log(f"✓ Learning insights found")
    else:
        write_log("○ Learning insights not found (will be created after first analysis)")
    
    # Check if we have enough data for learning
    if learning_system.performance_data["total_analyzed"] >= learning_system.min_tweets_for_learning:
        write_log(f"✓ Sufficient data for learning: {learning_system.performance_data['total_analyzed']} tweets analyzed")
        learning_system._log_key_insights()
    else:
        write_log(f"○ Gathering initial data: {learning_system.performance_data['total_analyzed']}/{learning_system.min_tweets_for_learning} tweets analyzed")
    
    return True

# =========================
# MAIN EXECUTION
# =========================

if __name__ == "__main__":
    write_log("="*60)
    write_log("🧠 SELF-LEARNING TWITTER BOT STARTUP")
    write_log("="*60)
    
    # Validate environment
    try:
        validate_env_vars()
        write_log("✅ Environment variables validated")
    except Exception as e:
        write_log(f"❌ Environment validation failed: {e}")
        exit(1)
    
    # Test authentication
    if not test_auth():
        write_log("CRITICAL: Authentication failed. Bot cannot run.")
        exit(1)
    
    # Test learning system
    test_learning_system()
    
    # Display startup info
    quota_status = quota_manager.get_quota_status()
    write_log("")
    write_log("=== QUOTA STATUS ===")
    write_log(f"Monthly reads: {quota_status['reads_used']}/100 ({quota_status['reads_remaining']} remaining)")
    write_log(f"Monthly writes: {quota_status['writes_used']}/500 ({quota_status['writes_remaining']} remaining)")
    
    write_log("")
    write_log("=== SELF-LEARNING FEATURES ===")
    write_log("✓ Performance tracking for all tweets")
    write_log("✓ Daily analysis of tweet engagement")
    write_log("✓ Category performance learning")
    write_log("✓ Time slot optimization")
    write_log("✓ Hashtag effectiveness analysis")
    write_log("✓ Emoji and CTA impact measurement")
    write_log("✓ Adaptive content strategy")
    write_log("✓ Best practices identification")
    
    write_log("")
    write_log("=== POSTING STRATEGY ===")
    write_log("✓ Main posts: 12/day with learning optimization")
    write_log("✓ Visual elements with smart emojis")
    write_log("✓ Contextual CTAs based on content")
    write_log("✓ Premium targeting for business categories")
    write_log("✓ Global timing for sports/entertainment")
    write_log("✓ Strategic category selection based on performance")
    write_log("✓ Time slot filtering (skip underperforming times)")
    
    write_log("")
    write_log("=== LEARNING INSIGHTS ===")
    if learning_system.performance_data["total_analyzed"] > 0:
        write_log(f"📊 Total tweets analyzed: {learning_system.performance_data['total_analyzed']}")
        write_log(f"📅 Last analysis: {learning_system.performance_data['last_analysis']}")
        
        if learning_system.insights["best_practices"]:
            write_log("📈 Best practices identified:")
            for practice in learning_system.insights["best_practices"]:
                write_log(f"   • {practice}")
        
        if learning_system.insights["avoid_patterns"]:
            write_log("⚠️  Patterns to avoid:")
            for pattern in learning_system.insights["avoid_patterns"]:
                write_log(f"   • {pattern}")
    else:
        write_log("📊 Learning mode: Data collection phase")
        write_log(f"   Need {learning_system.min_tweets_for_learning} tweets before optimization begins")
    
    write_log("")
    write_log("=== QUOTA EFFICIENCY ===")
    write_log("• Read usage: 1 call/day for performance analysis (30/month)")
    write_log("• Write usage: 12 posts/day (360/month)")
    write_log("• Buffer: 70 reads + 140 writes reserved")
    
    # Start health server in background
    write_log("")
    write_log("Starting health check server...")
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Start the self-learning scheduler
    write_log("")
    write_log("="*60)
    write_log("🚀 STARTING SELF-LEARNING SCHEDULER")
    write_log("="*60)
    write_log("")
    
    try:
        start_learning_scheduler()
    except KeyboardInterrupt:
        write_log("")
        write_log("="*60)
        write_log("🛑 Bot stopped by user")
        write_log("="*60)
        
        # Save final learning insights
        learning_system.save_performance_data()
        learning_system.save_learning_insights()
        
        write_log("✅ Learning data saved successfully")
        write_log(f"📊 Total tweets recorded: {len(learning_system.performance_data['tweets'])}")
        write_log(f"📈 Total tweets analyzed: {learning_system.performance_data['total_analyzed']}")
    except Exception as e:
        write_log(f"❌ Critical error: {e}")
        
        # Save data before exit
        learning_system.save_performance_data()
        learning_system.save_learning_insights()
        
        exit(1)


