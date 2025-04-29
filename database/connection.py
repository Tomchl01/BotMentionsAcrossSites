import json
import mysql.connector

# Load entire config once
with open('config.json', 'r') as f:
    cfg = json.load(f)

def create_forum_connection():
    """Connect to your forum_scraper database."""
    # Support both 'db_forum' and legacy 'db_config'
    db_cfg = cfg.get('db_forum', cfg.get('db_config'))
    return mysql.connector.connect(**db_cfg)

def create_twitter_connection():
    """Connect to your xapidata Twitter database."""
    return mysql.connector.connect(**cfg['db_twitter'])

# For backwards-compatibility
create_connection = create_forum_connection
