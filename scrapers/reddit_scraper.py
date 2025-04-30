import praw
import json
import logging
from datetime import datetime, timedelta
from tqdm import tqdm
import re

from database.connection import create_connection
from database.queries import get_existing_hashes, insert_post
from utils.cleaning import clean_text
from utils.hashing import generate_hash

# ── Logging setup ──────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ── Load config ────────────────────────────────────────
with open("config.json") as f:
    config = json.load(f)

reddit_cfg = config["reddit"]
DAYS_BACK = 60
SUBREDDITS = ["poker", "onlinepoker"]

BRANDS = [
    "acr", "acr poker", "winning poker", "winning poker network", "wpn"
]
RISKS = [
    "bot", "bots", "cheat", "cheating", "collusion", "fraud", "automation"
]

# ── Matching functions ─────────────────────────────────
def match_terms(text, terms):
    """Return all keywords from `terms` found in text as full words"""
    text = text.lower()
    return [term for term in terms if re.search(rf"\b{re.escape(term)}\b", text)]

# ── Main Reddit scraper ────────────────────────────────
def fetch_and_store_reddit_posts():
    logger.info("🔍 Starting Reddit scraping...")

    reddit = praw.Reddit(
        client_id=reddit_cfg["client_id"],
        client_secret=reddit_cfg["client_secret"],
        user_agent=reddit_cfg["user_agent"]
    )

    conn = create_connection()
    existing_hashes = get_existing_hashes(conn, "Reddit")
    total_inserted = 0

    cutoff_time = datetime.utcnow() - timedelta(days=DAYS_BACK)

    for sub_name in SUBREDDITS:
        logger.info(f"📡 Reading r/{sub_name}...")
        subreddit = reddit.subreddit(sub_name)

        with tqdm(desc=f"r/{sub_name}", unit="post") as bar:
            for post in subreddit.new(limit=500):
                created = datetime.utcfromtimestamp(post.created_utc)
                if created < cutoff_time:
                    continue

                content_raw = f"{post.title} {post.selftext or ''}"
                content = clean_text(content_raw)
                brand_hits = match_terms(content, BRANDS)
                risk_hits = match_terms(content, RISKS)

                if not (brand_hits and risk_hits):
                    bar.update(1)
                    continue

                post_hash = generate_hash("Reddit", post.id, str(post.author), created.strftime('%Y-%m-%d %H:%M:%S'), content)
                if post_hash in existing_hashes:
                    bar.update(1)
                    continue

                post_tuple = (
                    "Reddit",              # source
                    f"r/{sub_name}",       # source_detail
                    post.id,               # external_id
                    str(post.author),      # username
                    created.strftime('%Y-%m-%d %H:%M:%S'),
                    content,               # cleaned content
                    True,                  # mention_bot (matched risk)
                    post_hash              # hash
                )

                insert_post(conn, post_tuple)
                existing_hashes.add(post_hash)
                total_inserted += 1
                bar.update(1)

    conn.close()
    logger.info(f"✅ Finished Reddit scrape: {total_inserted} new posts inserted.")

# ── Manual run ─────────────────────────────────────────
if __name__ == "__main__":
    fetch_and_store_reddit_posts()
