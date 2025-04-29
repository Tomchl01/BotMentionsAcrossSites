from scrapers.forum_scraper import scrape_forum
from scrapers.twitter_scraper import fetch_and_store_tweets
import subprocess

def run_scrapers():
    print("📡 Running forum and Twitter scrapers...")
    scrape_forum()
    fetch_and_store_tweets()

def generate_report():
    print("📝 Generating HTML report...")
    try:
        subprocess.run(["python", "Report_Sumarization.py"], check=True)
        print("✅ Report successfully generated at docs/index.html")
    except subprocess.CalledProcessError as e:
        print(f"❌ Report generation failed: {e}")

if __name__ == "__main__":
    run_scrapers()
    generate_report()
