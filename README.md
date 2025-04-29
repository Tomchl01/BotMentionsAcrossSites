# 📊 OneScraperForALL  
**Automated Social Listening & Risk Intelligence for Online Poker Sites**

> *“In a landscape flooded with noise, finding the signal is the edge.”*

---

## 🧠 Overview

**OneScraperForALL** is a modular, production-ready scraping pipeline designed for **monitoring online poker platforms across forums and social media**. It transforms unstructured player feedback, suspicion reports, and sentiment trends into actionable, timestamped intelligence.

This system is built for teams that care about **game integrity, support responsiveness, and reputational risk**.

We didn’t build this “just to try AI.”  
We built it because **manual scanning doesn’t scale**, and visibility into user pain points shouldn’t be buried 3 pages deep in a thread or lost in a Reddit rant.

---

## ⚙️ What It Does

- **Scrapes trusted forums** (like 2+2) and **social platforms** (like Reddit)
- **Filters posts** for key risk signals: fraud claims, bot suspicions, collusion allegations, etc.
- **Cleans, hashes, deduplicates**, and **stores posts** into a normalized database
- Optionally tags flagged content based on mention of automated behavior
- Integrates into a summarization and reporting layer via AI/LLM

---

## 🔍 Use Case Example

> Your integrity team wants to be alerted when players begin discussing suspected bots operating on your site, especially if multiple users mention similar timing or table behavior.

This pipeline continuously scrapes relevant subreddits and poker forums. It automatically flags posts mentioning terms like "bot", "fraud", or "collusion" **alongside your brand name**, cleans and stores the data, and makes it available for summary or escalation.

---

## 📁 Project Structure

OneScraperForALL/ ├── reddit_scraper.py # PRAW-based Reddit module ├── forum_scraper.py # BeautifulSoup forum module ├── database/ │ ├── connection.py │ └── queries.py ├── utils/ │ ├── cleaning.py │ ├── hashing.py │ └── config_loader.py ├── config.json # API keys, scraper settings (ignored in version control) ├── logs/ └── README.md


---

## 🛡️ Security & Privacy

- `config.json` is excluded via `.gitignore` and must be manually created with credentials.
- We recommend rotating API keys regularly and **not committing secrets to version control**.
- Sensitive file history should be scrubbed using `git filter-repo` or similar tools (we did).

---

## 🧪 Requirements

- Python 3.9+
- `praw`, `beautifulsoup4`, `tqdm`, `psycopg2` (or your database connector)
- A PostgreSQL or SQLite-compatible schema with `insert_post()` and `get_existing_hashes()` logic

---

## 🔧 Setup Instructions

1. Clone the repo:
    ```bash
    git clone https://github.com/your-username/OneScraperForALL.git
    cd OneScraperForALL
    ```

2. Set up your config file:
    ```json
    {
      "reddit": {
        "client_id": "YOUR_CLIENT_ID",
        "client_secret": "YOUR_SECRET",
        "user_agent": "PokerAnalyzerBot:v1.0 (by u/your_username)",
        "subreddits": ["poker", "onlinepoker"]
      }
    }
    ```

3. Run the scrapers:
    ```bash
    python forum_scraper.py
    python reddit_scraper.py
    ```

---

## 💬 Why This Matters

The integrity of a poker platform is defined not just by its policies, but by its responsiveness to public signals. With user-generated content growing by the minute, systems that transform **online chatter into structured, interpretable data** are no longer optional — they're foundational.

This project is our step toward building that foundation.

---
