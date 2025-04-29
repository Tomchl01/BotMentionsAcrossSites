import requests
import time
import logging
import sys
import json
from bs4 import BeautifulSoup
from tqdm import tqdm

from database.connection import create_connection
from database.queries import (
    get_last_scraped_page,
    update_last_scraped_page,
    get_existing_hashes,
    insert_post
)
from utils.cleaning import clean_text, clean_date, contains_bot_mention
from utils.hashing import generate_hash

# ── Logging setup: file + console ─────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# File handler
fh = logging.FileHandler('logs/scraper.log')
fh.setLevel(logging.INFO)
fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
logger.addHandler(fh)

# Console handler
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
logger.addHandler(ch)

print("=== Starting scraper (console) ===", flush=True)

# ── Load configuration ─────────────────────────────────────────────────────────
with open('config.json') as f:
    config = json.load(f)

# ── Helper functions ───────────────────────────────────────────────────────────
def get_html(url):
    """Fetch URL, return HTML or None on error/404."""
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logging.error(f"Error fetching {url}: {e}")
        return None

def parse_page(html, forum_name, page_number, existing_hashes):
    """
    Parse a forum page’s HTML, return list of valid new posts:
    (source, source_detail, external_id, username, post_date, content, mention_bot, content_hash)
    """
    soup = BeautifulSoup(html, 'html.parser')
    posts = []

    import re
    post_containers = soup.find_all('div', id=lambda x: x and re.fullmatch(r"post\d+", x))
    for post in post_containers:

        pid = post.get("id")
        # Skip placeholders/invalid IDs
        if not pid or "post_message_" in pid:
            logging.info(f"Skipping invalid post id: {pid}")
            continue

        # Username
        user_tag = post.find('a', class_='h2')
        if not user_tag:
            logging.info(f"Skipping {pid}: missing username")
            continue
        user = user_tag.text.strip()

        # Content
        msg_div = post.find('div', class_='post__message')
        if not msg_div:
            logging.info(f"Skipping {pid}: missing content div")
            continue
        content = clean_text(msg_div.text)
        if not content:
            logging.info(f"Skipping {pid}: empty content")
            continue

        # Date
        date_div = post.find('div', class_='caption--small')
        date_text = date_div.get_text(strip=True) if date_div else ''
        pd = clean_date(date_text)
        if pd == "0000-00-00 00:00:00":
            logging.info(f"Skipping {pid}: invalid date '{date_text}'")
            continue

        # Bot flag & hash
        bot_flag = contains_bot_mention(content)
        chash = generate_hash(forum_name, pid, user, pd, content)
        if chash in existing_hashes:
            logging.info(f"Skipping duplicate post: {pid}")
            continue

        posts.append(("2+2 Forum", forum_name, pid, user, pd, content, bot_flag, chash))

    return posts

# ── Main scraping routine ──────────────────────────────────────────────────────
def scrape_forum():
    conn = create_connection()

    for forum in config['forums']:
        name = forum['name']
        existing = get_existing_hashes(conn, name)
        last = get_last_scraped_page(conn, name)
        page = last + 1 if last else forum['start_page']

        logging.info(f"Starting {name} at page {page}")
        print(f"[{name}] Starting at page {page}", flush=True)

        with tqdm(desc=f"Scraping {name}", unit="page") as bar:
            while True:
                url = forum['base_url'].format(page)
                html = get_html(url)
                if html is None:
                    logging.info(f"[{name}][Page {page}] No HTML; stopping.")
                    print(f"[{name}][Page {page}] No HTML; stopping.", flush=True)
                    break

                new_posts = parse_page(html, name, page, existing)
                if not new_posts:
                    logging.info(f"[{name}][Page {page}] 0 new posts; stopping.")
                    print(f"[{name}][Page {page}] 0 new posts; stopping.", flush=True)
                    break

                for p in new_posts:
                    insert_post(conn, p)
                    existing.add(p[-1])

                update_last_scraped_page(conn, name, page)
                logging.info(f"[{name}][Page {page}] Inserted {len(new_posts)} posts")
                page += 1
                bar.update(1)
                time.sleep(1)

    conn.close()

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    scrape_forum()
