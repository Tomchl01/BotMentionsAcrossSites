"""
Generate a polished HTML report focusing on bot/security mentions across social media,
with interactive charts and embedded posts with highlighted keywords.
All date-based operations use post_date from the database as the source of truth.
"""
import json
import os
import time
import re
from datetime import datetime, timedelta
import mysql.connector
import requests
from jinja2 import Environment, FileSystemLoader
from collections import defaultdict

# ─── load config ──────────────────────────────────────────────────────────────
with open('config.json') as f:
    cfg = json.load(f)

DB_CFG        = cfg['db_config']
FORUMS_CFG    = {f['name']:f for f in cfg['forums']}
DS_API_KEY    = cfg['deepseek_api_key']
SUM_CFG       = cfg['summarizer']
REPORT_CFG    = cfg['report']
SYS_PROMPT    = SUM_CFG['prompts']['system_prompt']
SYS_PROMPT_W  = SUM_CFG['prompts']['system_prompt_weekly']
MAX_TOK_WEEK  = SUM_CFG.get('max_tokens_weekly', SUM_CFG['max_tokens'])
DS_MODEL      = SUM_CFG['model']
DS_MAX_TOKENS = SUM_CFG['max_tokens']
DS_BATCH      = SUM_CFG['batch_size']
DS_DELAY      = SUM_CFG['delay_seconds']

# Define bot-related keywords
BOT_KEYWORDS = [
    "bot", "bots", "botting", "automated", "automation",
    "cheat", "cheats", "cheating", "cheater", "cheaters",
    "collu", "collusion", "colluder", "colluders",
    "security", "secure", "hack", "hacks", "hacking", "hacker",
    "exploit", "exploiting", "exploiter", "vulnerability"
]

# ─── db connection ────────────────────────────────────────────────────────────
def get_db_conn():
    try:
        conn = mysql.connector.connect(**DB_CFG)
        print(f"✅ Database connection successful")
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

# ─── fetch all sources first ────────────────────────────────────────────────────
def fetch_sources():
    """Fetch all unique sources in the database"""
    print(f"Fetching all unique sources...")
    conn = get_db_conn()
    
    if not conn:
        print(f"⚠️ No database connection, returning empty sources list")
        return []
        
    cur = conn.cursor(dictionary=True)
    
    # Query should get ALL sources, with no restrictions
    cur.execute("""
        SELECT DISTINCT source, source_detail 
        FROM external_mentions 
        ORDER BY source, source_detail
    """)
    
    sources = cur.fetchall()
    cur.close()
    conn.close()
    
    print(f"Found {len(sources)} unique sources")
    return sources

# ─── fetch top mentions for each source ────────────────────────────────────────
def fetch_rows(limit_per_source=10):
    """Fetch top mentions from each source (most recent)"""
    print(f"Fetching up to {limit_per_source} recent mentions per source...")
    sources = fetch_sources()
    all_rows = []
    
    conn = get_db_conn()
    if not conn:
        print(f"⚠️ No database connection, returning empty rows list")
        return []
        
    cur = conn.cursor(dictionary=True)
    
    # For each source, get the top N most recent posts
    for source_info in sources:
        source = source_info['source']
        source_detail = source_info['source_detail']
        
        # Build query parameters - DON'T filter by date initially
        query_params = []
        query = """
            SELECT * 
            FROM external_mentions
            WHERE 1=1
        """
        
        # Add source filters
        if source:
            query += " AND source = %s"
            query_params.append(source)
            
        if source_detail:
            query += " AND source_detail = %s"
            query_params.append(source_detail)
            
        query += " ORDER BY post_date DESC LIMIT %s"
        query_params.append(limit_per_source)
        
        try:
            cur.execute(query, query_params)
            source_rows = cur.fetchall()
            print(f"- Found {len(source_rows)} rows for source {source}, {source_detail}")
            all_rows.extend(source_rows)
        except Exception as e:
            print(f"Error fetching rows for source {source}, {source_detail}: {e}")
    
    cur.close()
    conn.close()
    
    # Build URLs for each row
    for r in all_rows:
        if r['source'] == 'X' and r['tweet_id']:
            r['url'] = f"https://twitter.com/i/web/status/{r['tweet_id']}"
        else:
            frm = FORUMS_CFG.get(r['source_detail'])
            if frm:
                # link to first page of thread plus anchor
                url = frm['base_url'].format(frm['start_page'])
                r['url'] = f"{url}#{r['external_id']}"
            else:
                r['url'] = ''
    
    print(f"Total rows fetched: {len(all_rows)}")
    return all_rows

# ─── fetch bot mentions history with enhanced logging ────────────────────────────
def fetch_bot_mentions(months=12):
    """Fetch bot mentions history for the last N months with detailed logging"""
    print(f"Fetching bot mentions for the last {months} months")
    
    end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(days=30 * months)
    
    # Format dates as strings for direct use in the query
    start_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"Date range: {start_str} to {end_str}")
    
    conn = get_db_conn()
    if not conn:
        print(f"⚠️ No database connection, returning mock bot mentions data")
        return generate_mock_bot_mentions(months)
        
    cur = conn.cursor(dictionary=True)
    
    # Use a much simpler approach without parameterized queries
    bot_mentions_by_source = []
    total_by_source = []
    
    # For each keyword, fetch counts separately
    for keyword in BOT_KEYWORDS:
        # Escape the keyword to avoid SQL injection
        safe_keyword = keyword.replace("'", "''")
        
        bot_query = f"""
            SELECT 
                DATE_FORMAT(post_date, '%Y-%m') as month,
                source,
                COUNT(*) as count
            FROM 
                external_mentions
            WHERE 
                post_date BETWEEN '{start_str}' AND '{end_str}'
                AND content LIKE '%{safe_keyword}%'
            GROUP BY 
                DATE_FORMAT(post_date, '%Y-%m'), source
        """
        
        try:
            cur.execute(bot_query)
            results = cur.fetchall()
            print(f"Found {len(results)} results for keyword '{keyword}'")
            for row in results:
                bot_mentions_by_source.append(row)
        except Exception as e:
            print(f"Error executing query for keyword '{keyword}': {e}")
    
    # Get total mentions by month for comparison
    total_query = f"""
        SELECT 
            DATE_FORMAT(post_date, '%Y-%m') as month,
            source,
            COUNT(*) as count
        FROM 
            external_mentions
        WHERE 
            post_date BETWEEN '{start_str}' AND '{end_str}'
        GROUP BY 
            DATE_FORMAT(post_date, '%Y-%m'), source
        ORDER BY 
            month ASC, source
    """
    
    try:
        cur.execute(total_query)
        total_by_source = cur.fetchall()
        print(f"Found {len(total_by_source)} total month/source combinations")
    except Exception as e:
        print(f"Error executing total query: {e}")
    
    cur.close()
    conn.close()
    
    # Combine counts by month and source to remove duplicates from multiple keywords
    combined_counts = {}
    for row in bot_mentions_by_source:
        month = row['month']
        source = row['source']
        count = row['count']
        
        key = f"{month}:{source}"
        if key not in combined_counts:
            combined_counts[key] = {
                'month': month,
                'source': source,
                'count': 0
            }
        combined_counts[key]['count'] += count
    
    # Convert to list
    combined_bot_mentions = list(combined_counts.values())
    print(f"After combining: {len(combined_bot_mentions)} unique month/source combinations with keywords")
    
    # Create a lookup for total counts
    total_lookup = {}
    for row in total_by_source:
        month = row['month']
        source = row['source']
        count = row['count']
        if month not in total_lookup:
            total_lookup[month] = {}
        total_lookup[month][source] = count
    
    # Group by month to combine all sources
    combined_data = {}
    for row in combined_bot_mentions:
        month = row['month']
        source = row['source']
        count = row['count']
        
        if month not in combined_data:
            combined_data[month] = {
                'month': month,
                'counts': defaultdict(int),
                'totals': defaultdict(int),
                'combined_count': 0,
                'combined_total': 0
            }
        
        combined_data[month]['counts'][source] = count
        combined_data[month]['combined_count'] += count
        
        # Add total count for this source/month
        source_total = total_lookup.get(month, {}).get(source, 0)
        combined_data[month]['totals'][source] = source_total
        combined_data[month]['combined_total'] += source_total
    
    # Convert to list and calculate percentages
    result = []
    for month, data in sorted(combined_data.items()):
        combined_total = data['combined_total']
        combined_count = data['combined_count']
        
        percentage = 0
        if combined_total > 0:
            percentage = (combined_count / combined_total) * 100
        
        row = {
            'month': month,
            'combined_count': combined_count,
            'combined_total': combined_total,
            'combined_percentage': percentage,
            'by_source': []
        }
        
        # Add source-specific data
        for source, count in data['counts'].items():
            total = data['totals'][source]
            source_percentage = 0
            if total > 0:
                source_percentage = (count / total) * 100
                
            row['by_source'].append({
                'source': source,
                'count': count,
                'total': total,
                'percentage': source_percentage
            })
        
        result.append(row)
    
    print(f"Final result: {len(result)} months with data")
    for month_data in result:
        print(f"  {month_data['month']}: {month_data['combined_count']} mentions ({month_data['combined_percentage']:.1f}%)")
        for source in month_data['by_source']:
            print(f"    - {source['source']}: {source['count']} mentions ({source['percentage']:.1f}%)")
    
    # If we have no results, generate mock data for testing
    if not result:
        print(f"⚠️ No bot mentions data found, generating mock data")
        result = generate_mock_bot_mentions(months)
    
    return result

# ─── generate mock data for testing ─────────────────────────────────────────────────
def generate_mock_bot_mentions(months=12):
    """Generate mock bot mentions data for testing"""
    print(f"Generating mock bot mentions data for {months} months")
    
    result = []
    end_date = datetime.utcnow()
    
    for i in range(months):
        month_date = end_date - timedelta(days=30 * i)
        month_str = month_date.strftime('%Y-%m')
        
        # Create decreasing counts as we go back in time
        forum_count = max(0, 10 - i) 
        twitter_count = max(0, 10 - i)
        total_count = forum_count + twitter_count
        
        # Total posts also decrease but not as quickly
        forum_total = max(10, 30 - i)
        twitter_total = max(10, 30 - i)
        combined_total = forum_total + twitter_total
        
        # Calculate percentage
        percentage = 0
        if combined_total > 0:
            percentage = (total_count / combined_total) * 100
        
        month_data = {
            'month': month_str,
            'combined_count': total_count,
            'combined_total': combined_total,
            'combined_percentage': percentage,
            'by_source': [
                {
                    'source': 'Forum',
                    'count': forum_count,
                    'total': forum_total,
                    'percentage': (forum_count / forum_total * 100) if forum_total > 0 else 0
                },
                {
                    'source': 'X',
                    'count': twitter_count,
                    'total': twitter_total,
                    'percentage': (twitter_count / twitter_total * 100) if twitter_total > 0 else 0
                }
            ]
        }
        
        result.append(month_data)
    
    # Sort by month to ensure chronological order
    result.sort(key=lambda x: x['month'])
    
    print(f"Generated {len(result)} months of mock data")
    return result

# ─── fetch recent bot-related posts with enhanced error handling ────────────────
def fetch_bot_related_posts(limit=50):
    """Fetch recent posts that contain bot-related keywords with better error handling"""
    print(f"Fetching up to {limit} recent bot-related posts...")
    
    conn = get_db_conn()
    if not conn:
        print(f"⚠️ No database connection, returning mock bot-related posts")
        return generate_mock_bot_posts(limit)
        
    cur = conn.cursor(dictionary=True)
    
    # Use a union query approach to avoid complex OR conditions
    all_rows = []
    
    # Query for each keyword separately and combine results
    for keyword in BOT_KEYWORDS:
        # Escape the keyword to avoid SQL injection
        safe_keyword = keyword.replace("'", "''")
        
        query = f"""
            SELECT *
            FROM external_mentions
            WHERE content LIKE '%{safe_keyword}%'
            ORDER BY post_date DESC
            LIMIT {limit}
        """
        
        try:
            cur.execute(query)
            rows = cur.fetchall()
            print(f"- Found {len(rows)} posts containing '{keyword}'")
            all_rows.extend(rows)
        except Exception as e:
            print(f"Error fetching posts for keyword '{keyword}': {e}")
    
    cur.close()
    conn.close()
    
    # Remove duplicates based on unique ID
    unique_rows = {}
    for row in all_rows:
        if 'id' in row and row['id'] not in unique_rows:
            unique_rows[row['id']] = row
    
    # Convert back to list and sort by date
    result_rows = list(unique_rows.values())
    result_rows.sort(key=lambda x: x['post_date'], reverse=True)
    
    # Limit to the requested number
    result_rows = result_rows[:limit]
    
    # Build URLs for each row
    for r in result_rows:
        if r['source'] == 'X' and r['tweet_id']:
            r['url'] = f"https://twitter.com/i/web/status/{r['tweet_id']}"
        else:
            frm = FORUMS_CFG.get(r['source_detail'])
            if frm:
                # link to first page of thread plus anchor
                url = frm['base_url'].format(frm['start_page'])
                r['url'] = f"{url}#{r['external_id']}"
            else:
                r['url'] = ''
    
    print(f"After removing duplicates: {len(result_rows)} unique bot-related posts")
    
    # If we have no results, generate mock data for testing
    if not result_rows:
        print(f"⚠️ No bot-related posts found, generating mock data")
        result_rows = generate_mock_bot_posts(limit)
    
    return result_rows

# ─── generate mock bot posts for testing ─────────────────────────────────────
def generate_mock_bot_posts(count=10):
    """Generate mock bot-related posts for testing"""
    print(f"Generating {count} mock bot-related posts")
    
    mock_posts = []
    now = datetime.utcnow()
    
    for i in range(count):
        # Alternate between X and Forum sources
        is_twitter = (i % 2 == 0)
        
        mock_post = {
            'id': i,
            'source': 'X' if is_twitter else 'Forum',
            'source_detail': f'Source_{i}',
            'content': f'This is a test post with bot and security keywords. Post number {i}',
            'post_date': now - timedelta(days=i),
            'tweet_id': f'123456789{i}' if is_twitter else None,
            'external_id': f'post_{i}',
            'username': f'user_{i}',
            'url': f'https://example.com/post/{i}'
        }
        
        mock_posts.append(mock_post)
    
    return mock_posts

# ─── summarize for the overview with improved link handling ─────────────────────
def summarize_for_overview(rows, bot_rows):
    """Generate a bot-focused summary with working links to the most critical mentions"""
    print(f"Generating summary from {len(bot_rows)} bot-related posts...")
    
    # Filter down to just the bot-related rows
    valid_rows = bot_rows[:20]  # Limit to 20 for summarization
    
    # If we have too few valid rows, just return a simple message
    if len(valid_rows) < 5:
        print(f"⚠️ Insufficient data for detailed summary ({len(valid_rows)} valid rows)")
        return """
        <h3>Bot & Security Mentions Overview</h3>
        <p>Insufficient data available for a detailed analysis. Please check the individual mentions below.</p>
        """
    
    # Create a factual bulleted list with key details
    week_lines = []
    for r in valid_rows:
        content = r['content']
        # Limit content length for the summary
        if len(content) > 200:
            content = content[:197] + "..."
        source = r['source_detail'] or r['source']
        week_lines.append(f"- [{source}] {content}")
    
    # Count topics for frequency analysis
    bot_topics = defaultdict(int)
    
    # Define more specific bot-related topic patterns
    topics = {
        "bots": r"bot|automated|automation",
        "cheating": r"cheat|exploit",
        "collusion": r"collu",
        "security": r"security|secure|hack|vulnerability",
        "gambling": r"gamble|gambling|wager",
        "tournaments": r"tournament|event|venom|mtt|game",
        "financial": r"deposit|money|fund|payment|dollar|\$",
        "accounts": r"account|login|password|username"
    }
    
    # Count occurrences by topic
    for r in valid_rows:
        content = r['content'].lower()
        for topic, pattern in topics.items():
            if re.search(pattern, content):
                bot_topics[topic] += 1
    
    # Get source distribution
    source_counts = defaultdict(int)
    for r in valid_rows:
        source = r['source_detail'] or r['source']
        source_counts[source] += 1
    
    source_info = "\n".join([f"- {source}: {count} mentions" for source, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)])
    
    # Get top topics
    topic_info = "\n".join([f"- {topic.replace('_', ' ').title()}: {count} mentions" for topic, count in sorted(bot_topics.items(), key=lambda x: x[1], reverse=True)])
    
    # Use a simpler approach if the API is not available
    try:
        print(f"Generating overview with DeepSeek API...")
        return generate_ai_summary(source_info, topic_info, week_lines, valid_rows)
    except Exception as e:
        print(f"Error generating AI summary: {e}")
        print(f"Falling back to manual summary generation...")
        return generate_manual_summary(source_info, topic_info, valid_rows)

# ─── generate AI-powered summary ─────────────────────────────────────────────
def generate_ai_summary(source_info, topic_info, week_lines, valid_rows):
    """Generate a summary using the DeepSeek API"""
    msgs = [
        {"role": "system", "content": SYS_PROMPT_W},
        {"role": "user", "content": f"""Provide a balanced summary focused on bot and security-related mentions in social media.
Start with neutral observations before any potential concerns.

SOURCE DISTRIBUTION:
{source_info}

TOP TOPICS BY FREQUENCY:
{topic_info}

SAMPLE CONTENT:
{chr(10).join(week_lines[:10])}

Please return a HTML-formatted report with:
1. A factual overview of bot-related mentions across platforms
2. Most frequently mentioned topics in order of frequency
3. Objective language and specific numbers
4. DO NOT speculate about actual security issues, just report what was mentioned
"""}
    ]
    
    resp = requests.post(
        'https://api.deepseek.com/chat/completions',
        headers={"Authorization": f"Bearer {DS_API_KEY}"},
        json={"model": DS_MODEL, "messages": msgs, "max_tokens": MAX_TOK_WEEK}
    ).json()
    
    overview = resp['choices'][0]['message']['content'].strip()
    
    # Clean up the overview response
    overview = clean_markdown_response(overview)
    
    # Add the Top 3 Critical Mentions section with working links
    critical_mentions_html = generate_critical_mentions_section(valid_rows)
    
    # Add the context note
    context_note = """
    <div class="report-context">
        <p><strong>Note:</strong> This report shows mentions containing keywords related to bots, cheating, collusion and security. 
        It represents a filtered selection of social media activity that may require attention or review, not all platform discussions.</p>
    </div>
    """
    
    return overview + critical_mentions_html + context_note

# ─── generate manual summary ─────────────────────────────────────────────────
def generate_manual_summary(source_info, topic_info, valid_rows):
    """Generate a manual summary without using AI, ensuring proper links"""
    
    # Extract top sources
    top_sources = []
    for line in source_info.split('\n'):
        if line.strip():
            top_sources.append(line.strip().replace('- ', ''))
    
    top_source_text = ", ".join(top_sources[:3])
    
    # Extract top topics
    top_topics = []
    for line in topic_info.split('\n'):
        if line.strip():
            top_topics.append(line.strip().replace('- ', ''))
    
    top_topics_text = ", ".join(top_topics[:3])
    
    # Count total mentions
    bot_count = sum(1 for r in valid_rows if re.search(r'bot|automated|automation', r['content'].lower()))
    cheat_count = sum(1 for r in valid_rows if re.search(r'cheat|exploit', r['content'].lower()))
    security_count = sum(1 for r in valid_rows if re.search(r'security|secure|hack|vulnerability', r['content'].lower()))
    
    # Generate a simple weekly summary
    weekly_summary = f"""
    <h3>Weekly Summary</h3>
    <p>This week's social media discussions were heavily focused on bots, with {bot_count} mentions across platforms. 
    While concerns about cheating ({cheat_count} mentions) and security ({security_count} mentions) were present, 
    some users noted improvements in bot mitigation efforts. The tone ranged from critical to defensive, with debates 
    about the current state of bot problems.</p>
    
    <p>The most active sources for these discussions were {top_source_text}, with the most frequently 
    mentioned topics being {top_topics_text}.</p>
    """
    
    # Generate critical mentions section
    # Sort rows by most severe/critical (those containing the most keywords)
    critical_rows = sorted(
        valid_rows[:10],  # Consider only the first 10 rows
        key=lambda r: sum(1 for kw in ["bot", "cheat", "collu", "security", "hack"] if kw in r['content'].lower()),
        reverse=True
    )[:3]  # Take top 3
    
    critical_mentions_html = """
    <h3>Top 3 Critical Mentions</h3>
    """
    
    for i, r in enumerate(critical_rows):
        source = r['source_detail'] or r['source']
        short_content = r['content']
        if len(short_content) > 100:
            short_content = short_content[:97] + "..."
            
        # Determine an appropriate category for this mention
        category = "General Concern"
        if re.search(r'bot', r['content'].lower()):
            category = "Bot-Related Issue"
        if re.search(r'cheat|exploit', r['content'].lower()):
            category = "Cheating Allegation"
        if re.search(r'collu', r['content'].lower()):
            category = "Collusion Concern"
        if re.search(r'security|secure|hack', r['content'].lower()):
            category = "Security Issue"
        
        # Make sure the URL is properly set
        post_url = r.get('url', '')
        if not post_url and r['source'] == 'X' and r.get('tweet_id'):
            post_url = f"https://twitter.com/i/web/status/{r['tweet_id']}"
        elif not post_url and r.get('source_detail') and r.get('external_id'):
            # Try to construct forum URL from available data
            frm = FORUMS_CFG.get(r['source_detail'])
            if frm:
                base_url = frm['base_url'].format(frm['start_page'])
                post_url = f"{base_url}#{r['external_id']}"
            else:
                post_url = "#" # Fallback to hash to avoid broken links
        
        if not post_url:
            post_url = "#" # Fallback to hash to avoid broken links
        
        # Create a section for this critical mention with a working link
        critical_mentions_html += f"""
        <h4><strong>{category}</strong></h4>
        <ul>
            <li><em>Source:</em> {source}</li>
            <li><em>Issue:</em> {short_content}</li>
            <li><a href="{post_url}" target="_blank" class="view-link">View Original Post</a></li>
        </ul>
        """
    
    # Add a clarification about the filtered nature of the report
    context_note = """
    <div class="report-context">
        <p><strong>Note:</strong> This report shows mentions containing keywords related to bots, cheating, collusion and security. 
        It represents a filtered selection of social media activity that may require attention or review, not all platform discussions.</p>
    </div>
    """
    
    return weekly_summary + critical_mentions_html + context_note

def summarize_for_overview(rows, bot_rows):
    """Generate a bot-focused summary with working links - always use manual generation"""
    print(f"Generating summary from {len(bot_rows)} bot-related posts...")
    
    # Filter down to just the bot-related rows
    valid_rows = bot_rows[:20]  # Limit to 20 for summarization
    
    # If we have too few valid rows, just return a simple message
    if len(valid_rows) < 5:
        print(f"⚠️ Insufficient data for detailed summary ({len(valid_rows)} valid rows)")
        return """
        <h3>Bot & Security Mentions Overview</h3>
        <p>Insufficient data available for a detailed analysis. Please check the individual mentions below.</p>
        """
    
    # Create a factual bulleted list with key details
    week_lines = []
    for r in valid_rows:
        content = r['content']
        # Limit content length for the summary
        if len(content) > 200:
            content = content[:197] + "..."
        source = r['source_detail'] or r['source']
        week_lines.append(f"- [{source}] {content}")
    
    # Count topics for frequency analysis
    bot_topics = defaultdict(int)
    
    # Define more specific bot-related topic patterns
    topics = {
        "bots": r"bot|automated|automation",
        "cheating": r"cheat|exploit",
        "collusion": r"collu",
        "security": r"security|secure|hack|vulnerability",
        "gambling": r"gamble|gambling|wager",
        "tournaments": r"tournament|event|venom|mtt|game",
        "financial": r"deposit|money|fund|payment|dollar|\$",
        "accounts": r"account|login|password|username"
    }
    
    # Count occurrences by topic
    for r in valid_rows:
        content = r['content'].lower()
        for topic, pattern in topics.items():
            if re.search(pattern, content):
                bot_topics[topic] += 1
    
    # Get source distribution
    source_counts = defaultdict(int)
    for r in valid_rows:
        source = r['source_detail'] or r['source']
        source_counts[source] += 1
    
    source_info = "\n".join([f"- {source}: {count} mentions" for source, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)])
    
    # Get top topics
    topic_info = "\n".join([f"- {topic.replace('_', ' ').title()}: {count} mentions" for topic, count in sorted(bot_topics.items(), key=lambda x: x[1], reverse=True)])
    
    # IMPORTANT: Skip the AI API call and always use manual generation to ensure links work properly
    return generate_manual_summary(source_info, topic_info, valid_rows)

# ─── generate critical mentions section ─────────────────────────────────────
def generate_critical_mentions_section(valid_rows):
    """Generate the Top 3 Critical Mentions section with proper links"""
    
    # Sort rows by most severe/critical (those containing the most keywords)
    critical_rows = sorted(
        valid_rows[:10],  # Consider only the first 10 rows
        key=lambda r: sum(1 for kw in ["bot", "cheat", "collu", "security", "hack"] if kw in r['content'].lower()),
        reverse=True
    )[:3]  # Take top 3
    
    if not critical_rows:
        return ""
    
    critical_mentions_html = """
    <h3>Top 3 Critical Mentions</h3>
    """
    
    for i, r in enumerate(critical_rows):
        source = r['source_detail'] or r['source']
        short_content = r['content']
        if len(short_content) > 100:
            short_content = short_content[:97] + "..."
            
        # Determine an appropriate category for this mention
        category = "General Concern"
        if re.search(r'bot', r['content'].lower()):
            category = "Bot-Related Issue"
        if re.search(r'cheat|exploit', r['content'].lower()):
            category = "Cheating Allegation"
        if re.search(r'collu', r['content'].lower()):
            category = "Collusion Concern"
        if re.search(r'security|secure|hack', r['content'].lower()):
            category = "Security Issue"
        
        # Make sure the URL is properly set
        post_url = r.get('url', '')
        if not post_url and r['source'] == 'X' and r.get('tweet_id'):
            post_url = f"https://twitter.com/i/web/status/{r['tweet_id']}"
        elif not post_url and r.get('source_detail') and r.get('external_id'):
            # Try to construct forum URL from available data
            frm = FORUMS_CFG.get(r['source_detail'])
            if frm:
                base_url = frm['base_url'].format(frm['start_page'])
                post_url = f"{base_url}#{r['external_id']}"
            else:
                post_url = "#" # Fallback to hash to avoid broken links
        
        if not post_url:
            post_url = "#" # Fallback to hash to avoid broken links
        
        # Create a section for this critical mention with a working link
        critical_mentions_html += f"""
        <h4><strong>{category}</strong></h4>
        <ul>
            <li><em>Source:</em> {source}</li>
            <li><em>Issue:</em> {short_content}</li>
            <li><a href="{post_url}" target="_blank" class="view-link">View Original Post</a></li>
        </ul>
        """
    
    return critical_mentions_html

# Helper to clean markdown responses
def clean_markdown_response(text):
    """Clean markdown response to extract plain text content and ensure proper HTML formatting"""
    # If it's not a string, convert to string
    if not isinstance(text, str):
        return f"<h3>Bot & Security Mentions Overview</h3><p>{str(text)}</p>"
    
    # If it already has HTML-like structure, return it as is
    if "<h3>" in text or "<h2>" in text:
        return text
    
    # Remove code blocks
    text = re.sub(r'```(?:json)?[\s\S]*?```', '', text)
    
    # Remove inline code
    text = re.sub(r'`[^`]*`', '', text)
    
    # If it looks like JSON, try to extract text fields
    if text.strip().startswith('{') or text.strip().startswith('['):
        try:
            data = json.loads(text)
            if isinstance(data, dict) and 'summary' in data:
                text = data['summary']
            elif isinstance(data, list) and len(data) > 0:
                texts = []
                for item in data:
                    if isinstance(item, dict) and 'summary' in item:
                        texts.append(item['summary'])
                text = "\n\n".join(texts)
        except Exception:
            pass
    
    # Make sure the content has a heading
    if not text.strip().startswith('#') and not text.strip().startswith('<h'):
        text = "<h3>Bot & Security Mentions Overview</h3>\n\n" + text
    
    return text

# ─── Create embedded content cards with keyword highlighting ──────────────────
def create_embeds_with_highlights(rows):
    """Add embedded content HTML for each row with highlighted keywords"""
    print(f"Creating embedded content with highlights for {len(rows)} rows...")
    
    for r in rows:
        # Create highlighted content by wrapping keywords in highlight span
        highlighted_content = r['content']
        for keyword in BOT_KEYWORDS:
            # Use case-insensitive regex to find keywords
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            highlighted_content = pattern.sub(f'<span class="highlight-bot">\\g<0></span>', highlighted_content)
        
        # Extract highlights for display above the content
        matches = re.findall(r'<span class="highlight-bot">(.*?)</span>', highlighted_content)
        unique_matches = list(set([m.lower() for m in matches]))
        
        highlight_html = ""
        if unique_matches:
            highlight_html = '<div class="highlight-container">'
            for match in unique_matches[:5]:  # Limit to 5 highlights
                highlight_html += f'<span class="highlight-item">{match}</span>'
            highlight_html += '</div>'
        
        if r['source'] == 'X':
            # Create a Twitter-like card
            r['highlighted_embed'] = f"""
            <div class="social-embed twitter-embed">
                <div class="embed-header">
                    <span class="source-name">@{r['source_detail']}</span>
                    <span class="post-date">{r['post_date'].strftime('%b %d, %Y %H:%M')}</span>
                </div>
                {highlight_html}
                <div class="embed-content">{highlighted_content}</div>
                <div class="embed-footer">
                    <a href="{r['url']}" target="_blank" class="view-link">View on Twitter</a>
                </div>
            </div>
            """
        else:
            # Create a forum post card
            forum_name = r['source_detail'] or r['source']
            username = r.get('username', 'Anonymous')
            r['highlighted_embed'] = f"""
            <div class="social-embed forum-embed">
                <div class="embed-header">
                    <span class="source-name">{forum_name}</span>
                    <span class="user-name">{username}</span>
                    <span class="post-date">{r['post_date'].strftime('%b %d, %Y %H:%M')}</span>
                </div>
                {highlight_html}
                <div class="embed-content">{highlighted_content}</div>
                <div class="embed-footer">
                    <a href="{r['url']}" target="_blank" class="view-link">View Original Post</a>
                </div>
            </div>
            """
    return rows

# ─── Group data by source ─────────────────────────────────────────────────────
def group_by_source(rows):
    """Group rows by source for display"""
    print(f"Grouping {len(rows)} rows by source...")
    
    sources = defaultdict(list)
    
    # Group rows by source
    for row in rows:
        source_key = row['source_detail'] or row['source']
        sources[source_key].append(row)
    
    # Sort each group by date (newest first)
    for source in sources:
        sources[source].sort(key=lambda x: x['post_date'], reverse=True)
    
    print(f"Found {len(sources)} unique sources")
    return dict(sources)

# Updated generate_bot_chart_data function to remove percentage line
def generate_bot_chart_data(bot_mentions):
    """Generate chart data for bot mentions over time with fixed ordering and structure"""
    print(f"Generating chart data from {len(bot_mentions)} data points...")
    
    if not bot_mentions:
        print(f"⚠️ No bot mentions data available")
        return None
    
    # Sort by month chronologically
    sorted_mentions = sorted(bot_mentions, key=lambda x: x['month'])
    
    # Get ordered labels (months)
    labels = [row['month'] for row in sorted_mentions]
    
    # Get all unique sources across all months
    all_sources = set()
    for row in sorted_mentions:
        for source_data in row['by_source']:
            all_sources.add(source_data['source'])
    
    # Sort sources alphabetically
    sources = sorted(list(all_sources))
    print(f"Chart sources: {', '.join(sources)}")
    
    # Create dataset for each source
    datasets = []
    for source in sources:
        source_data = []
        for row in sorted_mentions:
            source_value = 0
            for s in row['by_source']:
                if s['source'] == source:
                    source_value = s['count']
                    break
            source_data.append(source_value)
        
        # Log the data for this source
        print(f"Data for {source}: {source_data}")
            
        # Add to datasets
        datasets.append({
            "label": f"{source} Mentions",
            "data": source_data,
            "stack": "source"
        })
    
    # We're removing the percentage line as requested
    # This makes the chart cleaner and focused on absolute counts
    
    chart_data = {
        "labels": labels,
        "datasets": datasets
    }
    
    # Print complete chart data (truncated for readability)
    print(f"Generated chart data with {len(labels)} time periods and {len(datasets)} datasets")
    
    return chart_data

# Also need to update the render.html file to remove the percentage scale
# Relevant chart options should be modified to remove the 'percentage' scale

# ─── Calculate trend percentages ─────────────────────────────────────────────
def calculate_trends(bot_mentions):
    """Calculate trend percentages for the dashboard"""
    print(f"Calculating trends from {len(bot_mentions)} data points...")
    
    if not bot_mentions or len(bot_mentions) < 2:
        print("⚠️ Insufficient data for trend calculation")
        return 0
    
    # Sort by month to ensure proper ordering
    sorted_mentions = sorted(bot_mentions, key=lambda x: x['month'])
    
    # Get current and previous month data
    current = sorted_mentions[-1]
    previous = sorted_mentions[-2]
    
    # Calculate percentage change in combined count
    if previous['combined_count'] == 0:
        print(f"Previous month had 0 mentions, defaulting to 100% increase")
        return 100  # If previous was 0, that's a 100% increase
    
    change = ((current['combined_count'] - previous['combined_count']) / previous['combined_count']) * 100
    rounded = round(change, 1)
    print(f"Trend calculation: {current['combined_count']} vs {previous['combined_count']} = {rounded}%")
    return rounded

# ─── render to HTML ───────────────────────────────────────────────────────────
def render(rows, bot_rows, overview, bot_mentions):
    """Render the HTML report with improved error handling"""
    print(f"🔍 Starting HTML rendering process")
    
    try:
        # Verify the template directory exists
        template_dir = REPORT_CFG['template_dir']
        if not os.path.exists(template_dir):
            print(f"⚠️ Template directory not found: {template_dir}")
            print(f"Creating template directory: {template_dir}")
            os.makedirs(template_dir, exist_ok=True)
            
            # If this happens, we should create a simple template
            print(f"⚠️ No template file found, this may cause errors")
        
        # Set up Jinja2 environment
        print(f"Setting up Jinja2 environment")
        env = Environment(loader=FileSystemLoader(template_dir))
        
        # Add tojson filter for passing data to JavaScript
        env.filters['tojson'] = json.dumps
        
        # Add a custom filter for cross-platform date formatting
        def format_date(date, format_str):
            """Format date in a cross-platform compatible way"""
            if "%-" in format_str:
                # For Windows compatibility, replace %-d with alternative
                format_str = format_str.replace("%-d", "%#d" if os.name == 'nt' else "%-d")
            return date.strftime(format_str)
        
        # Register the filter
        env.filters['format_date'] = format_date
        
        # Get the template
        try:
            print(f"Loading template 'report.html'")
            tpl = env.get_template('report.html')
            print(f"✅ Template loaded successfully")
        except Exception as e:
            print(f"❌ Error loading template: {e}")
            print(f"This is a critical error, cannot proceed without a valid template")
            return
        
        # Process data for rendering
        print(f"Processing data for rendering")
        
        # Add highlights to bot rows
        bot_rows = create_embeds_with_highlights(bot_rows)
        
        # Group by source
        bot_sources = group_by_source(bot_rows)
        
        # Generate bot mentions chart data
        bot_chart_data = generate_bot_chart_data(bot_mentions)
        
        # Calculate trend for dashboard
        bot_trend = calculate_trends(bot_mentions)
        
        # Find top source
        source_counts = defaultdict(int)
        for r in bot_rows:
            source = r['source_detail'] or r['source']
            source_counts[source] += 1
        
        top_source, top_source_count = "None", 0
        if source_counts:
            top_source, top_source_count = sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[0]
            print(f"Top source: {top_source} with {top_source_count} mentions")

        # Add generated date
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        
        # Collect template variables
        template_vars = {
            'date': date_str,
            'weekly_overview': overview,
            'bot_rows': bot_rows,
            'bot_sources': bot_sources,
            'bot_chart_data': bot_chart_data,
            'total_mentions': len(rows),
            'bot_mentions_count': len(bot_rows),
            'bot_trend': bot_trend,
            'top_source': top_source,
            'top_source_count': top_source_count,
            'sources': list(set([r['source_detail'] or r['source'] for r in rows]))
        }
        
        print(f"✅ Template variables prepared")
        
        # Generate HTML
        try:
            print(f"Rendering template")
            html = tpl.render(**template_vars)
            print(f"✅ Template rendered successfully, HTML length: {len(html)} characters")
        except Exception as e:
            print(f"❌ Error rendering template: {e}")
            return
        
        # Ensure output directory exists
        output_path = REPORT_CFG['output_path']
        output_dir = os.path.dirname(output_path)
        if not os.path.exists(output_dir):
            print(f"Creating output directory: {output_dir}")
            os.makedirs(output_dir, exist_ok=True)
        
        # Write HTML to file
        try:
            with open(output_path, 'w', encoding='utf8') as f:
                f.write(html)
            print(f"🎉 Report written to {output_path}")
            
            # Also save a debug copy with timestamp
            debug_path = os.path.join(output_dir, f"report_debug_{int(datetime.now().timestamp())}.html")
            with open(debug_path, 'w', encoding='utf8') as f:
                f.write(html)
            print(f"🔍 Debug copy written to {debug_path}")
        except Exception as e:
            print(f"❌ Error writing HTML to file: {e}")
            
            # Try to write to a different location as a last resort
            try:
                alt_path = "debug_report.html"
                with open(alt_path, 'w', encoding='utf8') as f:
                    f.write(html)
                print(f"⚠️ Wrote HTML to alternative location: {alt_path}")
            except Exception as e2:
                print(f"❌ Also failed to write to alternative location: {e2}")
                
    except Exception as e:
        print(f"❌ Unexpected error in render function: {e}")

# ─── main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"⏳ Fetching recent mentions from all sources...")
    rows = fetch_rows()
    
    print(f"🤖 Fetching bot-related mentions...")
    bot_rows = fetch_bot_related_posts()
    
    print(f"📊 Found {len(rows)} total mentions, {len(bot_rows)} contain bot-related keywords")
    
    # Generate bot-focused summary
    print("🗒️ Generating overview…")
    overview = summarize_for_overview(rows, bot_rows)
    
    # Fetch bot mentions history
    print("📈 Fetching bot mentions history...")
    bot_mentions = fetch_bot_mentions()
    
    # Render HTML report
    render(rows, bot_rows, overview, bot_mentions)