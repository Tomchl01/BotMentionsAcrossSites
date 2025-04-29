import json
import re
import time
import logging
from datetime import datetime, timedelta
from tqdm import tqdm
import tweepy

from database.connection import create_twitter_connection
from database.queries import get_last_tweet_time, get_existing_hashes, insert_tweet
from utils.hashing import generate_hash

# ── Logging to console + file ──────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')

fh = logging.FileHandler('logs/twitter_scraper.log')
fh.setLevel(logging.INFO)
fh.setFormatter(formatter)
logger.addHandler(fh)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)

# ── Load config ────────────────────────────────────────────────────────────────
with open('config.json') as f:
    cfg = json.load(f)

BEARER_TOKEN  = cfg['twitter']['bearer_token']
QUERY         = cfg['twitter']['query']
SOURCE        = 'X'
SOURCE_DETAIL = 'ACR_POKER'

# ── Issue-keywords regex ───────────────────────────────────────────────────────
ISSUE_KEYWORDS = [
    r"\bbug\b", r"\berror\b", r"\bissue\b",
    r"\bdeposit\b", r"\brefund\b",
    r"\bdown\b", r"\b(bot|bots)\b"
]
ISSUE_REGEX = re.compile("|".join(ISSUE_KEYWORDS), re.IGNORECASE)

# ── Tweepy client ─────────────────────────────────────────────────────────────
client = tweepy.Client(bearer_token=BEARER_TOKEN, wait_on_rate_limit=True)

# ── Main fetch function ───────────────────────────────────────────────────────
def fetch_and_store_tweets():
    logger.info("Starting Twitter scraper")
    conn = create_twitter_connection()
    existing = get_existing_hashes(conn, SOURCE_DETAIL)
    last_time = get_last_tweet_time(conn, SOURCE_DETAIL)

    # determine start_time (no earlier than 7 days ago)
    if last_time:
        start = last_time - timedelta(days=1)
    else:
        start = datetime.utcnow() - timedelta(days=7)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    if start < seven_days_ago:
        start = seven_days_ago

    start_str = start.isoformat(timespec='seconds') + 'Z'
    end_str   = (datetime.utcnow() - timedelta(minutes=1)).isoformat(timespec='seconds') + 'Z'

    logger.info(f"Fetching tweets from {start_str} to {end_str}")

    # paginate through recent tweets with author expansion
    paginator = tweepy.Paginator(
        client.search_recent_tweets,
        query=QUERY,
        start_time=start_str,
        end_time=end_str,
        expansions=["author_id"],
        tweet_fields=["created_at","public_metrics","conversation_id"],
        user_fields=["username","verified"],
        max_results=100
    )

    tweets = []
    for page in paginator:
        if page.data:
            tweets.extend(page.data)
        else:
            break

    inserted = 0
    for t in tqdm(tweets, desc="Filtering tweets", unit="tw"):
        text = t.text
        # post-filter by issue keywords
        if not ISSUE_REGEX.search(text):
            continue

        # skip if no author_id
        if t.author_id is None:
            logger.info(f"Skipping tweet {t.id}: missing author_id")
            continue

        # fallback conversation_id to tweet id if missing
        conv_id = t.conversation_id or t.id

        pd = t.created_at.strftime("%Y-%m-%d %H:%M:%S")
        ch = generate_hash(SOURCE_DETAIL, t.id, text, pd)
        if ch in existing:
            continue

        record = (
            SOURCE, SOURCE_DETAIL,
            int(t.id),
            text,
            pd,
            int(t.author_id),
            int(conv_id),
            t.public_metrics.get("like_count", 0),
            t.public_metrics.get("retweet_count", 0),
            t.public_metrics.get("reply_count", 0),
            t.public_metrics.get("quote_count", 0),
            ch
        )
        insert_tweet(conn, record)
        existing.add(ch)
        inserted += 1

    conn.close()
    logger.info(f"Inserted {inserted} new tweets.")

# ── If run directly ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    fetch_and_store_tweets()
