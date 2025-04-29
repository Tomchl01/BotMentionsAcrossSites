import logging
from datetime import datetime

# Forum functions

def get_last_scraped_page(conn, forum_name):
    cursor = conn.cursor()
    cursor.execute("SELECT last_page FROM last_scraped WHERE forum_name = %s;", (forum_name,))
    row = cursor.fetchone()
    cursor.close()
    return row[0] if row else None


def update_last_scraped_page(conn, forum_name, last_page):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO last_scraped (forum_name, last_page)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE last_page = %s;
        """,
        (forum_name, last_page, last_page)
    )
    conn.commit()
    cursor.close()


def get_existing_hashes(conn, source_detail):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT content_hash FROM external_mentions WHERE source_detail = %s;",
        (source_detail,)
    )
    hashes = {row[0] for row in cursor.fetchall()}
    cursor.close()
    return hashes


def insert_post(conn, data):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT IGNORE INTO external_mentions 
          (source, source_detail, external_id, username, post_date, content, mention_bot, content_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """,
        data
    )
    conn.commit()
    cursor.close()

# Twitter functions

def get_last_tweet_time(conn, source_detail):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MAX(post_date) FROM external_mentions WHERE source = 'X' AND source_detail = %s;",
        (source_detail,)
    )
    row = cursor.fetchone()
    cursor.close()
    return row[0] if row and row[0] else None


def insert_tweet(conn, record):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO external_mentions
          (source, source_detail, tweet_id, content, post_date,
           author_id, conversation_id, like_count, retweet_count, reply_count, quote_count, content_hash)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          content       = VALUES(content),
          like_count    = VALUES(like_count),
          retweet_count = VALUES(retweet_count),
          reply_count   = VALUES(reply_count),
          quote_count   = VALUES(quote_count);
        """,
        record
    )
    conn.commit()
    cursor.close()
