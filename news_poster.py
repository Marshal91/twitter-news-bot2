"""
Complete Enhanced Twitter Bot with Day-Aware Football Matchday Targeting
API Limits: 100 reads/month (3/day), 500 writes/month (12 posts + 3 replies/day)

Football Schedule:
- Tue/Wed/Thu 16:00-01:00 UTC: Champions League/Europa League content
- Sat/Sun 14:00-00:00 UTC: Premier League/La Liga content
- All other times: Normal diverse content scheduling
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
from openai import OpenAI
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

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
        try:
            if os.path.exists(self.quota_file):
                with open(self.quota_file, 'r') as f:
                    data = json.load(f)
                current_month = datetime.now(pytz.UTC).strftime("%Y-%m")
                if data.get("month") != current_month:
                    self.quota = {"month": current_month, "reads_used": 0, "writes_used": 0, "last_reset": datetime.now(pytz.UTC).isoformat()}
                    self.save_quota()
                else:
                    self.quota = data
            else:
                self.quota = {"month": datetime.now(pytz.UTC).strftime("%Y-%m"), "reads_used": 0, "writes_used": 0, "last_reset": datetime.now(pytz.UTC).isoformat()}
                self.save_quota()
        except Exception as e:
            logging.error(f"Error loading quota: {e}")
            self.quota = {"month": datetime.now(pytz.UTC).strftime("%Y-%m"), "reads_used": 0, "writes_used": 0, "last_reset": datetime.now(pytz.UTC).isoformat()}
    
    def save_quota(self):
        try:
            with open(self.quota_file, 'w') as f:
                json.dump(self.quota, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving quota: {e}")
    
    def can_read(self, count=1):
        return (self.quota["reads_used"] + count) <= 100
    
    def can_write(self, count=1):
        return (self.quota["writes_used"] + count) <= 500
    
    def use_read(self, count=1):
        if self.can_read(count):
            self.quota["reads_used"] += count
            self.save_quota()
            return True
        return False
    
    def use_write(self, count=1):
        if self.can_write(count):
            self.quota["writes_used"] += count
            self.save_quota()
            return True
        return False
    
    def get_quota_status(self):
        return {"reads_remaining": 100 - self.quota["reads_used"], "writes_remaining": 500 - self.quota["writes_used"], "reads_used": self.quota["reads_used"], "writes_used": self.quota["writes_used"], "month": self.quota["month"]}

# =========================
# CONFIGURATION
# =========================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")

quota_manager = APIQuotaManager()

LOG_FILE = "bot_log.txt"
POSTED_LOG = "posted_links.txt"
POST_INTERVAL_MINUTES = 90
last_post_time = None

# Day names for logging
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Premium posting times - business hours
PREMIUM_POSTING_TIMES = ["08:00", "12:00", "14:00", "16:00", "18:00", "22:00"]

# Global engagement times - diverse content
GLOBAL_POSTING_TIMES = ["02:00", "04:00", "06:00", "10:00", "20:00", "00:00"]

# Football matchday windows
CHAMPIONS_LEAGUE_TIMES = ["16:00", "18:10", "19:10", "20:45", "22:20", "23:55", "01:30"]
WEEKEND_LEAGUE_TIMES = ["14:00", "15:35", "17:10", "18:50", "20:30", "22:05", "23:40", "01:30"]

# Combined posting times for normal scheduling
MAIN_POSTING_TIMES = PREMIUM_POSTING_TIMES + GLOBAL_POSTING_TIMES

REPLY_TIMES = ["10:25", "16:30", "22:30"]

# Category groups
GLOBAL_CATEGORIES = ["F1", "MotoGP", "Cycling"]
BUSINESS_CATEGORIES = ["Crypto", "Tesla", "Space Exploration"]
FOOTBALL_CATEGORIES = ["EPL", "Champions League", "Europa League", "La Liga"]

# RSS feeds
RSS_FEEDS = {
    "EPL": [
        "https://footyaccumulators.com/feed/",
		"http://feeds.arsenal.com/arsenal-news",
        "https://www.premierleague.com/news",
        "https://www.skysports.com/rss/12",
        "http://feeds.bbci.co.uk/sport/football/premier-league/rss.xml",
        "https://www.theguardian.com/football/premierleague/rss",
        "https://arseblog.com/feed/"
    ],
    "Champions League": [
        "https://www.skysports.com/rss/11095",
        "http://feeds.bbci.co.uk/sport/football/champions-league/rss.xml",
        "https://www.theguardian.com/football/championsleague/rss"
    ],
    "Europa League": [
        "https://www.uefa.com/uefaeuropaleague/news/rss.xml",
        "https://www.skysports.com/rss/11750",
        "http://feeds.bbci.co.uk/sport/football/europa-league/rss.xml",
        "https://www.theguardian.com/football/uefa-europa-league/rss"
    ],
    "La Liga": [
		"https://footyaccumulators.com/feed/", 
        "https://www.laliga.com/en-GB/rss/laliga-santander/news",
        "https://www.skysports.com/rss/11826",
        "https://www.theguardian.com/football/laligafootball/rss"
    ],
    "F1": [
        "https://www.formula1.com/en/latest/all.xml",
        "https://www.autosport.com/rss/f1/news/"
    ],
    "MotoGP": [
        "https://www.motogp.com/en/news/rss",
        "https://www.autosport.com/rss/motogp/news/"
    ],
    "Crypto": [
        "https://cointelegraph.com/rss",
        "https://www.coindesk.com/arc/outboundfeeds/rss/"
    ],
    "Cycling": [
        "http://feeds2.feedburner.com/cyclingnews/news",
        "https://cycling.today/feed"
    ],
    "Space Exploration": [
        "https://spacenews.com/feed",
        "https://www.space.com/feeds/all"
    ],
    "Tesla": [
        "https://insideevs.com/rss/articles/all",
        "https://electrek.co/feed/"
    ]
}

# Content strategies
PREMIUM_CONTENT_STRATEGIES = {
    "EPL": {"cta_templates": ["How does this reshape the Premier League's economic landscape?", "What's the ROI on this move for club stakeholders?", "Which clubs are positioned to capitalize on this trend?"]},
    "Champions League": {"cta_templates": ["Which team has the tactical advantage in this matchup?", "How does this impact Champions League qualification scenarios?", "Which tactical approach will dominate this tie?"]},
    "Europa League": {"cta_templates": ["Which underdog team could surprise in this competition?", "How does Europa League success translate to domestic form?", "Which tactical innovations are we seeing emerge?"]},
    "La Liga": {"cta_templates": ["How does this tactical shift impact league dynamics?", "What's the economic impact on Spanish football?", "Which clubs are positioned to capitalize on this?"]},
    "F1": {"cta_templates": ["Which team benefits most from this technical development?", "How will this innovation transfer to consumer automotive?", "What's the competitive advantage timeline here?"]},
    "Crypto": {"cta_templates": ["What's the regulatory precedent this sets?", "How will institutional portfolios adjust to this?", "What's the systemic risk assessment here?"]},
    "Tesla": {"cta_templates": ["What's Tesla's moat in this competitive landscape?", "How does this accelerate the EV adoption curve?", "Which legacy automakers face the biggest disruption?"]},
    "Space Exploration": {"cta_templates": ["Which sectors benefit from this space technology spillover?", "What's the commercial viability timeline?", "How does this impact the space economy valuation?"]},
    "Cycling": {"cta_templates": ["How will this technology disrupt the cycling industry?", "What's the market opportunity for equipment manufacturers?", "Which demographic trends does this capitalize on?"]},
    "MotoGP": {"cta_templates": ["Which motorcycle manufacturers gain competitive edge?", "How will this tech transfer to consumer bikes?", "Which partnerships are positioned to scale this?"]}
}

TRENDING_HASHTAGS = {
    "EPL": {"primary": ["#PremierLeague", "#EPL"], "secondary": ["#Arsenal", "#ManCity", "#Liverpool"], "trending": ["#MatchDay"]},
    "Champions League": {"primary": ["#ChampionsLeague", "#UCL"], "secondary": ["#Arsenal", "#RealMadrid", "#Barcelona"], "trending": ["#UCLNight"]},
    "Europa League": {"primary": ["#EuropaLeague", "#UEL"], "secondary": ["#Arsenal", "#ManUnited"], "trending": ["#UELFootball"]},
    "La Liga": {"primary": ["#LaLiga"], "secondary": ["#RealMadrid", "#Barcelona"], "trending": ["#SpanishFootball"]},
    "F1": {"primary": ["#F1"], "secondary": ["#Verstappen", "#Hamilton"], "trending": ["#Racing"]},
    "Crypto": {"primary": ["#Bitcoin"], "secondary": ["#Ethereum", "#BTC"], "trending": ["#CryptoNews"]},
    "Tesla": {"primary": ["#Tesla"], "secondary": ["#ElonMusk", "#EV"], "trending": ["#Innovation"]},
    "Space Exploration": {"primary": ["#Space"], "secondary": ["#NASA", "#Mars"], "trending": ["#SpaceExploration"]},
    "Cycling": {"primary": ["#Cycling"], "secondary": ["#TourDeFrance"], "trending": ["#CyclingLife"]},
    "MotoGP": {"primary": ["#MotoGP"], "secondary": ["#GrandPrix"], "trending": ["#Racing"]}
}

openai_client = OpenAI(api_key=OPENAI_API_KEY)
auth = tweepy.OAuth1UserHandler(TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET)
twitter_api = tweepy.API(auth)
twitter_client = tweepy.Client(consumer_key=TWITTER_API_KEY, consumer_secret=TWITTER_API_SECRET, access_token=TWITTER_ACCESS_TOKEN, access_token_secret=TWITTER_ACCESS_SECRET)

# =========================
# LOGGING
# =========================

if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s", handlers=[RotatingFileHandler('logs/bot_activity.log', maxBytes=10*1024*1024, backupCount=5), RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3), logging.StreamHandler()])

def write_log(message, level="info"):
    if level == "error":
        logging.error(message)
    else:
        logging.info(message)

# =========================
# REPLY SYSTEM
# =========================

class TargetedReplySystem:
    def __init__(self):
        self.reply_log_file = "replied_tweets.json"
        self.daily_reply_limit = 3
        self.load_reply_log()
    def load_reply_log(self):
        try:
            if os.path.exists(self.reply_log_file):
                with open(self.reply_log_file, 'r') as f:
                    self.reply_log = json.load(f)
            else:
                self.reply_log = {"date": datetime.now(pytz.UTC).strftime("%Y-%m-%d"), "today_count": 0, "replied_ids": []}
        except:
            self.reply_log = {"date": datetime.now(pytz.UTC).strftime("%Y-%m-%d"), "today_count": 0, "replied_ids": []}
    def save_reply_log(self):
        with open(self.reply_log_file, 'w') as f:
            json.dump(self.reply_log, f, indent=2)
    def can_reply_today(self):
        current_date = datetime.now(pytz.UTC).strftime("%Y-%m-%d")
        if self.reply_log["date"] != current_date:
            self.reply_log = {"date": current_date, "today_count": 0, "replied_ids": []}
            self.save_reply_log()
        return self.reply_log["today_count"] < self.daily_reply_limit
    def execute_reply_campaign(self):
        write_log("Reply campaign temporarily disabled")

reply_system = TargetedReplySystem()

# =========================
# DAY AND TIME TRACKING
# =========================

def get_current_day_info():
    """Get comprehensive current day and time information"""
    current_datetime = datetime.now(pytz.UTC)
    current_day = current_datetime.weekday()  # 0=Monday, 6=Sunday
    current_time = current_datetime.strftime("%H:%M")
    day_name = DAY_NAMES[current_day]
    return {
        "datetime": current_datetime,
        "day_number": current_day,
        "day_name": day_name,
        "time": current_time
    }

def is_champions_league_day():
    """Check if today is Champions League day (Tuesday=1, Wednesday=2, Thursday=3)"""
    day_info = get_current_day_info()
    return day_info["day_number"] in [1, 2, 3]

def is_weekend_league_day():
    """Check if today is weekend league day (Saturday=5, Sunday=6)"""
    day_info = get_current_day_info()
    return day_info["day_number"] in [5, 6]

def is_champions_league_time():
    """Check if we're in Champions League posting window (Tue-Thu, 16:00-01:00 UTC)"""
    day_info = get_current_day_info()
    # Must be Champions League day AND within posting hours
    return is_champions_league_day() and day_info["time"] in CHAMPIONS_LEAGUE_TIMES

def is_weekend_league_time():
    """Check if we're in weekend league posting window (Sat-Sun, 14:00-00:00 UTC)"""
    day_info = get_current_day_info()
    # Must be weekend day AND within posting hours
    return is_weekend_league_day() and day_info["time"] in WEEKEND_LEAGUE_TIMES

def get_football_matchday_category():
    """Get football category ONLY during matchday windows, return None for normal scheduling"""
    day_info = get_current_day_info()
    
    if is_champions_league_time():
        category = random.choice(["Champions League"] * 7 + ["Europa League"] * 3)
        write_log(f"FOOTBALL MATCHDAY MODE - {day_info['day_name']} {day_info['time']} - Selected: {category}")
        return category
    
    elif is_weekend_league_time():
        category = random.choice(["EPL"] * 6 + ["La Liga"] * 4)
        write_log(f"FOOTBALL MATCHDAY MODE - {day_info['day_name']} {day_info['time']} - Selected: {category}")
        return category
    
    # Outside matchday windows - return None to trigger normal scheduling
    return None

# =========================
# HELPER FUNCTIONS
# =========================

def add_visual_elements_to_tweet(tweet_text, category):
    emojis_map = {"EPL": "⚽", "Champions League": "⚽", "Europa League": "⚽", "La Liga": "⚽", "F1": "🏎️", "Crypto": "📊", "Tesla": "⚡", "Space Exploration": "🚀", "Cycling": "🚴", "MotoGP": "🏍️"}
    if category in emojis_map and not (tweet_text and tweet_text[0] in "⚽📊🔄🏆⚡🏎️📈🔧🏁🚨⚖️₿🚀🔋🏭🔭🛰️🔴🌙✨🚴⛰️🏍️🎲"):
        return f"{emojis_map[category]} {tweet_text}"
    return tweet_text

def get_contextual_cta(category, title):
    strategy = PREMIUM_CONTENT_STRATEGIES.get(category)
    if strategy and strategy.get("cta_templates"):
        return random.choice(strategy["cta_templates"])
    return "What's your take on this?"

def get_trending_hashtags(category):
    hashtag_data = TRENDING_HASHTAGS.get(category)
    if not hashtag_data:
        return []
    selected = random.sample(hashtag_data["primary"], 1)
    if hashtag_data["secondary"]:
        selected.extend(random.sample(hashtag_data["secondary"], 1))
    return selected[:2]

def optimize_hashtags_for_reach(tweet_text, category):
    hashtags = get_trending_hashtags(category)
    if not hashtags:
        return tweet_text
    hashtag_text = " " + " ".join(hashtags)
    return tweet_text + hashtag_text if len(tweet_text + hashtag_text) <= 275 else tweet_text

def fetch_rss(feed_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(feed_url, headers=headers, timeout=15)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        return [{"title": entry.title, "url": entry.link} for entry in feed.entries[:3]]
    except Exception as e:
        write_log(f"Error fetching RSS from {feed_url}: {e}")
        return []

def get_articles_for_category(category):
    feeds = RSS_FEEDS.get(category, [])
    for feed in feeds[:2]:
        articles = fetch_rss(feed)
        if articles:
            return articles
    return []

def is_premium_posting_time():
    day_info = get_current_day_info()
    return day_info["time"] in PREMIUM_POSTING_TIMES

def is_global_posting_time():
    day_info = get_current_day_info()
    return day_info["time"] in GLOBAL_POSTING_TIMES

def detect_category_with_timing_strategy():
    """
    Smart category selection with day-aware football matchday priority:
    1. FIRST PRIORITY: Football matchday windows (specific days + hours)
    2. SECOND PRIORITY: Normal scheduling (premium/global times or random)
    """
    day_info = get_current_day_info()
    
    # PRIORITY 1: Check if we're in a football matchday window
    matchday_category = get_football_matchday_category()
    if matchday_category:
        # We're in a matchday window (right day AND right time)
        return matchday_category
    
    # PRIORITY 2: Normal scheduling (outside matchday windows)
    categories = list(RSS_FEEDS.keys())
    
    # Remove football categories from normal scheduling
    non_football_categories = [cat for cat in categories if cat not in FOOTBALL_CATEGORIES]
    
    # Log that we're in normal scheduling mode
    if is_champions_league_day():
        write_log(f"NORMAL SCHEDULE - {day_info['day_name']} {day_info['time']} (outside UCL hours 16:00-01:00)")
    elif is_weekend_league_day():
        write_log(f"NORMAL SCHEDULE - {day_info['day_name']} {day_info['time']} (outside weekend league hours 14:00-00:00)")
    else:
        write_log(f"NORMAL SCHEDULE - {day_info['day_name']} {day_info['time']}")
    
    # During premium posting times, prioritize business categories
    if is_premium_posting_time():
        available_priority = [cat for cat in BUSINESS_CATEGORIES if cat in non_football_categories]
        if available_priority and random.random() < 0.7:
            category = random.choice(available_priority)
            write_log(f"  -> Business category for premium time: {category}")
            return category
    
    # During global posting times, prioritize global categories
    if is_global_posting_time():
        available_priority = [cat for cat in GLOBAL_CATEGORIES if cat in non_football_categories]
        if available_priority and random.random() < 0.7:
            category = random.choice(available_priority)
            write_log(f"  -> Global category: {category}")
            return category
    
    # Random selection from non-football categories
    if non_football_categories:
        category = random.choice(non_football_categories)
        write_log(f"  -> Random category: {category}")
        return category
    
    # Fallback to any category
    return random.choice(categories)

def generate_premium_targeted_content(title, category):
    contextual_cta = get_contextual_cta(category, title)
    prompt = f'Create a Twitter post about: {title}\n\nCategory: {category}\n\nRequirements:\n- Professional tone for decision-makers\n- Strategic insights\n- End with: {contextual_cta}\n- Under 200 characters\n\nWrite ONLY the tweet text:'
    try:
        response = openai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": f"You create professional content for {category} targeting business professionals."}, {"role": "user", "content": prompt}], max_tokens=100, temperature=0.7)
        return response.choices[0].message.content.strip()
    except Exception as e:
        write_log(f"Premium content generation failed: {e}")
        return f"Breaking: {title[:150]}... {contextual_cta}"

def generate_content_aware_post(title, category):
    try:
        prompt = f'Create an engaging Twitter post about: {title}\n\nCategory: {category}\nRequirements:\n- Under 200 characters\n- Ask thought-provoking questions\n- Drive engagement\n\nWrite ONLY the tweet text:'
        response = openai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": "Create viral Twitter content that drives engagement."}, {"role": "user", "content": prompt}], max_tokens=100, temperature=0.8)
        return response.choices[0].message.content.strip()
    except Exception as e:
        write_log(f"GPT generation failed: {e}")
        return f"Breaking: {title[:120]}... What's your take?"

def has_been_posted(url):
    if not os.path.exists(POSTED_LOG):
        return False
    with open(POSTED_LOG, "r") as f:
        return url.strip() in f.read()

def log_posted(url):
    with open(POSTED_LOG, "a") as f:
        f.write(url.strip() + "\n")

def can_post_now():
    global last_post_time
    if last_post_time is None:
        return True
    time_since_last = datetime.now(pytz.UTC) - last_post_time
    return time_since_last.total_seconds() >= (POST_INTERVAL_MINUTES * 60)

def shorten_url_with_fallback(long_url):
    try:
        response = requests.get(f"http://tinyurl.com/api-create.php?url={long_url}", timeout=5)
        if response.status_code == 200 and response.text.strip().startswith('http'):
            return response.text.strip()
    except:
        pass
    return long_url

def post_main_content(category):
    global last_post_time
    if not can_post_now() or not quota_manager.can_write(1):
        write_log("Cannot post - rate limited or quota exhausted")
        return False
    
    articles = get_articles_for_category(category)
    for article in articles:
        if has_been_posted(article["url"]):
            continue
        
        if is_premium_posting_time() or category in BUSINESS_CATEGORIES:
            tweet_text = generate_premium_targeted_content(article["title"], category)
        else:
            tweet_text = generate_content_aware_post(article["title"], category)
        
        tweet_text = add_visual_elements_to_tweet(tweet_text, category)
        short_url = shorten_url_with_fallback(article["url"])
        full_tweet = f"{tweet_text}\n\n{short_url}"
        full_tweet = optimize_hashtags_for_reach(full_tweet, category)
        
        if len(full_tweet) > 280:
            full_tweet = full_tweet[:277] + "..."
        
        try:
            twitter_client.create_tweet(text=full_tweet)
            quota_manager.use_write(1)
            log_posted(article["url"])
            last_post_time = datetime.now(pytz.UTC)
            write_log(f"POSTED successfully - {category}: {article['title'][:50]}...")
            return True
        except Exception as e:
            write_log(f"Error posting: {e}")
            return False
    
    write_log(f"No new articles to post for {category}")
    return False

def should_post_main_content():
    """
    Determine if we should post based on:
    1. Football matchday windows (specific days + hours)
    2. Regular posting schedule times
    """
    day_info = get_current_day_info()
    
    # Check if we're in a football matchday window
    if is_champions_league_time() or is_weekend_league_time():
        return True
    
    # Check regular posting schedule
    if day_info["time"] in MAIN_POSTING_TIMES:
        return True
    
    return False

def should_run_reply_campaign():
    return False

def run_main_content_job():
    try:
        day_info = get_current_day_info()
        write_log(f"=== CONTENT JOB START - {day_info['day_name']} {day_info['time']} ===")
        
        category = detect_category_with_timing_strategy()
        success = post_main_content(category)
        
        if not success and quota_manager.can_write(1):
            categories = list(RSS_FEEDS.keys())
            backup = random.choice([c for c in categories if c != category])
            write_log(f"Trying backup category: {backup}")
            post_main_content(backup)
        
        write_log(f"=== CONTENT JOB END ===")
    except Exception as e:
        write_log(f"Error in main content job: {e}", level="error")

def run_reply_job():
    try:
        reply_system.execute_reply_campaign()
    except Exception as e:
        write_log(f"Error in reply campaign: {e}", level="error")

def start_conservative_scheduler():
    write_log("="*60)
    write_log("STARTING TWITTER BOT WITH DAY-AWARE FOOTBALL MATCHDAY TARGETING")
    write_log("="*60)
    write_log("")
    write_log("FOOTBALL MATCHDAY SCHEDULE:")
    write_log("  Champions League Days: Tuesday, Wednesday, Thursday")
    write_log("  Champions League Hours: 16:00-01:00 UTC")
    write_log("  Weekend League Days: Saturday, Sunday")
    write_log("  Weekend League Hours: 14:00-00:00 UTC")
    write_log("")
    write_log("NORMAL SCHEDULE (All other times):")
    write_log(f"  Premium Times: {', '.join(PREMIUM_POSTING_TIMES)}")
    write_log(f"  Global Times: {', '.join(GLOBAL_POSTING_TIMES)}")
    write_log("")
    
    quota_status = quota_manager.get_quota_status()
    write_log(f"MONTHLY QUOTA: Reads {quota_status['reads_used']}/100, Writes {quota_status['writes_used']}/500")
    write_log("="*60)
    write_log("")
    
    last_checked_minute = None
    
    while True:
        try:
            day_info = get_current_day_info()
            current_minute = day_info["time"]
            
            if current_minute != last_checked_minute:
                # Determine current mode
                if is_champions_league_time():
                    mode = "FOOTBALL MATCHDAY (Champions League)"
                elif is_weekend_league_time():
                    mode = "FOOTBALL MATCHDAY (Weekend League)"
                else:
                    mode = "NORMAL SCHEDULE"
                
                write_log(f"[{mode}] Checking: {day_info['day_name']} {current_minute}")
                
                # Check for main content posting
                if should_post_main_content():
                    write_log(f"[{mode}] POSTING TIME TRIGGERED")
                    run_main_content_job()
                
                # Check for reply campaign
                if should_run_reply_campaign():
                    write_log(f"Reply campaign time: {current_minute}")
                    run_reply_job()
                
                last_checked_minute = current_minute
            
            time.sleep(30)
        
        except Exception as e:
            write_log(f"ERROR in scheduler loop: {e}", level="error")
            time.sleep(60)

# =========================
# HEALTH CHECK SERVER
# =========================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        
        quota_status = quota_manager.get_quota_status()
        day_info = get_current_day_info()
        
        # Determine current mode
        if is_champions_league_time():
            current_mode = "ACTIVE - Champions League/Europa League"
            mode_emoji = "🏆"
        elif is_weekend_league_time():
            current_mode = "ACTIVE - Premier League/La Liga"
            mode_emoji = "⚽"
        else:
            current_mode = "NORMAL SCHEDULING"
            mode_emoji = "📅"
        
        status = f"""Twitter Bot Status: RUNNING

Current Time: {day_info['day_name']}, {day_info['time']} UTC
Current Mode: {mode_emoji} {current_mode}

Monthly Quota:
- Reads: {quota_status['reads_used']}/100 ({quota_status['reads_remaining']} remaining)
- Writes: {quota_status['writes_used']}/500 ({quota_status['writes_remaining']} remaining)

Football Matchday Schedule:
- Champions League (Tue/Wed/Thu 16:00-01:00): {"ACTIVE" if is_champions_league_time() else "Inactive"}
- Weekend Leagues (Sat/Sun 14:00-00:00): {"ACTIVE" if is_weekend_league_time() else "Inactive"}

Day Status:
- Is Champions League Day: {is_champions_league_day()}
- Is Weekend League Day: {is_weekend_league_day()}

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
    port = int(os.environ.get('PORT', 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        write_log(f"Health server starting on port {port}")
        server.serve_forever()
    except Exception as e:
        write_log(f"Health server failed: {e}", level="error")

# =========================
# INITIALIZATION
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

def validate_env_vars():
    required = ["OPENAI_API_KEY", "TWITTER_API_KEY", "TWITTER_API_SECRET", "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

# =========================
# MAIN EXECUTION
# =========================

if __name__ == "__main__":
    write_log("")
    write_log("="*70)
    write_log("TWITTER BOT STARTUP - DAY-AWARE FOOTBALL MATCHDAY TARGETING")
    write_log("="*70)
    write_log("")
    
    # Validate environment
    try:
        validate_env_vars()
        write_log("Environment variables validated successfully")
    except Exception as e:
        write_log(f"CRITICAL: {e}", level="error")
        exit(1)
    
    # Test authentication
    if not test_auth():
        write_log("CRITICAL: Authentication failed. Bot cannot run.", level="error")
        exit(1)
    
    write_log("")
    
    # Display quota status
    quota_status = quota_manager.get_quota_status()
    write_log("QUOTA STATUS:")
    write_log(f"  Monthly reads: {quota_status['reads_used']}/100 ({quota_status['reads_remaining']} remaining)")
    write_log(f"  Monthly writes: {quota_status['writes_used']}/500 ({quota_status['writes_remaining']} remaining)")
    write_log("")
    
    # Display current day info
    day_info = get_current_day_info()
    write_log("CURRENT STATUS:")
    write_log(f"  Day: {day_info['day_name']}")
    write_log(f"  Time: {day_info['time']} UTC")
    write_log(f"  Champions League Day: {is_champions_league_day()}")
    write_log(f"  Weekend League Day: {is_weekend_league_day()}")
    write_log(f"  In Matchday Window: {is_champions_league_time() or is_weekend_league_time()}")
    write_log("")
    
    # Display feature list
    write_log("ENHANCED FEATURES:")
    write_log("  ✓ Day-aware football matchday targeting")
    write_log("  ✓ Champions League/Europa (Tue-Thu 16:00-01:00 UTC)")
    write_log("  ✓ Premier League/La Liga (Sat-Sun 14:00-00:00 UTC)")
    write_log("  ✓ Normal diverse scheduling (all other times)")
    write_log("  ✓ Visual elements with smart emojis")
    write_log("  ✓ Premium targeting with contextual CTAs")
    write_log("  ✓ Smart quota management")
    write_log("")
    
    # Start health server in background
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    write_log("Health server started in background")
    write_log("")
    
    # Start the scheduler
    write_log("Starting main scheduler...")
    write_log("="*70)
    write_log("")
    
    try:
        start_conservative_scheduler()
    except KeyboardInterrupt:
        write_log("")
        write_log("="*70)
        write_log("Bot stopped by user (Ctrl+C)")
        write_log("="*70)
    except Exception as e:
        write_log(f"CRITICAL ERROR: {e}", level="error")
        raise

