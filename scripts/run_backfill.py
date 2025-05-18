# /backfill_social_7d.py

import logging
import time
import datetime
import pytz
import pandas as pd
from typing import List, Optional
import json

# Setup project path for imports if running script directly
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = current_dir
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    print(f"Added project root to sys.path: {project_root}")

# Import project modules
import config
from database import db_utils
from data_collection import binance_client, reddit_client, twitter_client
from sentiment_analysis import analyzer
# Import the sentiment job logic helper from scheduler
try:
    from orchestration.scheduler import run_sentiment_analysis_job_logic
except ImportError:
    log.error("Could not import run_sentiment_analysis_job_logic from scheduler. Sentiment analysis step will be skipped.")
    # Define a dummy function if import fails to avoid NameError later
    def run_sentiment_analysis_job_logic():
        log.warning("Sentiment analysis logic function not available.")
        pass


# --- Configuration ---
logging.basicConfig(level=config.LOG_LEVEL,
                    format='%(asctime)s - %(levelname)s [%(name)s:%(lineno)d] %(message)s')
log = logging.getLogger(__name__)

# --- Backfill Functions ---

def backfill_reddit_7d():
    """Fetches recent Reddit posts (approx last 7 days) and stores them."""
    log.info("--- Starting Reddit 7-Day Backfill ---")
    try:
        # Fetching more posts increases chance of getting 7 days, but subject to limits
        # PRAW's .new() limit is typically 1000 max.
        # For a true 7-day backfill, iterating backwards or using Pushshift might be needed,
        # but we'll use .new() with a higher limit for simplicity here.
        post_limit = 500 # Fetch more posts per subreddit than the regular job
        posts = reddit_client.fetch_new_subreddit_posts(config.TARGET_SUBREDDITS, post_limit_per_subreddit=post_limit)

        if posts:
             # Filter for the last 7 days locally
             now_utc = datetime.datetime.now(pytz.utc)
             seven_days_ago = now_utc - pd.Timedelta(days=7)
             recent_posts = [p for p in posts if p.get('created_utc_dt') and p['created_utc_dt'] >= seven_days_ago]
             log.info(f"Filtered {len(posts)} fetched posts down to {len(recent_posts)} from the last 7 days.")

             # Prepare for DB insertion
             records_to_insert = []
             for post in recent_posts:
                  record = {
                      'post_id': post.get('post_id'),
                      'subreddit': post.get('subreddit'),
                      'title': post.get('title'),
                      'selftext': post.get('selftext'),
                      'url': post.get('url'),
                      'score': post.get('score'),
                      'num_comments': post.get('num_comments'),
                      'created_utc': post.get('created_utc_dt') # Use datetime object
                  }
                  if record['post_id']: # Ensure primary key is present
                       records_to_insert.append(record)

             if records_to_insert:
                  db_utils.bulk_insert_data(records_to_insert, db_utils.reddit_data, unique_column='post_id')
             else:
                  log.info("Reddit Backfill: No valid recent posts prepared for insertion.")
        else:
            log.info("Reddit Backfill: No posts fetched.")
    except Exception as e:
        log.error(f"Error in Reddit Backfill Job: {e}", exc_info=True)
    log.info("--- Reddit 7-Day Backfill Finished ---")


def backfill_twitter_7d():
    """Fetches recent tweets (approx last 7 days via Recent Search) and stores them."""
    log.info("--- Starting Twitter 7-Day Backfill ---")
    # Note: Twitter Basic v2 Recent Search has limits (e.g., monthly cap, requests/15min).
    # This might not fetch *all* relevant tweets if volume is high.
    try:
        symbols = binance_client.get_target_symbols()
        base_symbols = list(set([s.replace('USDT', '').replace('BUSD','') for s in symbols]))

        if not base_symbols:
            log.warning("Twitter Backfill: No base symbols found.")
            return

        all_tweets_to_insert = []
        max_total_tweets_backfill = 5000 # Allow fetching more for backfill if possible within limits
        results_per_page = 100 # Max per page for recent search

        # Combine symbols into batches for querying to reduce number of API calls
        query_batch_size = 10 # Adjust as needed based on query length limits
        log.info(f"Twitter Backfill: Processing {len(base_symbols)} symbols in batches of {query_batch_size}...")

        for i in range(0, len(base_symbols), query_batch_size):
             if len(all_tweets_to_insert) >= max_total_tweets_backfill:
                 log.warning(f"Twitter Backfill: Reached max total tweets limit ({max_total_tweets_backfill}). Stopping fetch.")
                 break

             symbol_batch = base_symbols[i:i+query_batch_size]
             # Combine with general keywords for broader search during backfill
             query = twitter_client.build_twitter_query(symbols=symbol_batch, base_keywords=config.TWITTER_QUERY_KEYWORDS)
             if not query: continue

             log.info(f"Twitter Backfill: Fetching tweets for query: {query}")
             # Don't use since_id for backfill - we want the last 7 days regardless of previous runs
             fetched_tweets, _ = twitter_client.search_recent_tweets(
                 query,
                 max_total_results=max_total_tweets_backfill - len(all_tweets_to_insert), # Fetch remaining quota
                 results_per_page=results_per_page
             )

             if fetched_tweets:
                 log.info(f"Twitter Backfill: Fetched {len(fetched_tweets)} tweets for batch.")
                 for tweet in fetched_tweets:
                      record = {
                          'tweet_id': tweet.get('tweet_id'),
                          'author_id': tweet.get('author_id'),
                          'text': tweet.get('text'),
                          'created_at': tweet.get('created_at_utc'), # Use datetime object
                          'public_metrics': tweet.get('public_metrics'), # Store as JSON
                          'hashtags': tweet.get('hashtags'), # Store as list/JSON
                          'cashtags': tweet.get('cashtags') # Store as list/JSON
                      }
                      if record['tweet_id']:
                           # Ensure JSON serializable if needed
                           if isinstance(record['public_metrics'], dict) and db_utils.JSON_TYPE: pass
                           elif isinstance(record['public_metrics'], dict): record['public_metrics'] = json.dumps(record['public_metrics'])

                           if isinstance(record['hashtags'], list) and db_utils.JSON_TYPE: pass
                           elif isinstance(record['hashtags'], list): record['hashtags'] = json.dumps(record['hashtags'])

                           if isinstance(record['cashtags'], list) and db_utils.JSON_TYPE: pass
                           elif isinstance(record['cashtags'], list): record['cashtags'] = json.dumps(record['cashtags'])

                           all_tweets_to_insert.append(record)
             else:
                  log.info(f"Twitter Backfill: No tweets found for batch query: {query}")

             time.sleep(3) # Be more conservative with delays during backfill

        if all_tweets_to_insert:
            db_utils.bulk_insert_data(all_tweets_to_insert, db_utils.twitter_data, unique_column='tweet_id')
        else:
            log.info("Twitter Backfill: No new valid tweets prepared for insertion across all symbols.")

    except Exception as e:
        log.error(f"Error in Twitter Backfill Job: {e}", exc_info=True)
    log.info("--- Twitter 7-Day Backfill Finished ---")


# --- Main Execution ---
if __name__ == "__main__":
    log.info("--- Starting Social Media 7-Day Backfill Script ---")

    # Initialize DB (ensure tables exist)
    if not db_utils.init_db():
        log.critical("Database initialization failed. Exiting backfill.")
        sys.exit(1)

    # --- Run Backfill Tasks ---
    # 1. Reddit
    backfill_reddit_7d()

    # 2. Twitter
    backfill_twitter_7d()

    # 3. Sentiment Analysis on newly added historical data
    log.info("Running sentiment analysis on backfilled social data...")
    # This will analyze any unanalyzed posts/tweets just added
    run_sentiment_analysis_job_logic()

    log.info("--- Social Media 7-Day Backfill Script Finished ---")
    print("\nSocial media backfill process complete. Check logs for details and errors.")

