"""Reddit client wrapper for subreddit news ingestion."""

import praw
import datetime
import pytz
from prawcore.exceptions import ResponseException, RequestException, PrawcoreException
from typing import List, Dict, Optional

# Use absolute imports for the new structure
from hydrobot.config.settings import settings
from hydrobot.utils.logger_setup import get_logger

# Use the configured logger
log = get_logger(__name__)

# --- Reddit Client Initialization ---
_reddit_client: Optional[praw.Reddit] = None

def get_reddit_client() -> Optional[praw.Reddit]:
    """Initializes and returns the PRAW Reddit instance singleton using settings."""
    global _reddit_client
    if _reddit_client is None:
        # Get credentials from the central settings object
        reddit_settings = getattr(settings, 'reddit', None)
        if not reddit_settings:
            log.error("Reddit configuration section ('reddit') not found in settings.")
            return None

        client_id = getattr(reddit_settings, 'client_id', None)
        client_secret_obj = getattr(reddit_settings, 'client_secret', None)
        user_agent = getattr(reddit_settings, 'user_agent', 'hydrobot_default_agent') # Provide a default
        username = getattr(reddit_settings, 'username', None)
        password_obj = getattr(reddit_settings, 'password', None)

        # Use get_secret_value() for sensitive fields
        client_secret = client_secret_obj.get_secret_value() if client_secret_obj else None
        password = password_obj.get_secret_value() if password_obj else None

        # Validate required credentials
        required_creds = [client_id, client_secret, user_agent]
        if not all(required_creds):
            log.error("Reddit API credentials (client ID, secret, user agent) are not fully configured in settings.reddit.")
            return None

        # Prepare credentials for PRAW, handling optional username/password
        praw_kwargs = {
            "client_id": client_id,
            "client_secret": client_secret,
            "user_agent": user_agent,
            "read_only": True # Set to False if write actions are needed
        }
        if username and password:
            praw_kwargs["username"] = username
            praw_kwargs["password"] = password
            log.info("Initializing PRAW Reddit instance with username/password...")
        else:
            log.info("Initializing PRAW Reddit instance (read_only mode)...")

        try:
            _reddit_client = praw.Reddit(**praw_kwargs)
            log.info(f"PRAW Reddit instance initialized successfully (user: {username or 'read-only'}).")
        except PrawcoreException as e:
            log.error(f"PRAW Error initializing Reddit instance: {e}", exc_info=True)
            _reddit_client = None
        except Exception as e:
            log.error(f"Unexpected error initializing PRAW Reddit instance: {e}", exc_info=True)
            _reddit_client = None
    return _reddit_client

def fetch_new_subreddit_posts(subreddit_names: List[str] = None, post_limit_per_subreddit: int = None) -> List[Dict]:
    """
    Fetches the newest posts (submissions) from specified subreddits.
    Uses subreddit_names and post_limit from settings if not provided.

    Args:
        subreddit_names (list, optional): A list of subreddit names (without 'r/'). Defaults to settings.reddit.target_subreddits.
        post_limit_per_subreddit (int, optional): Max number of posts to fetch. Defaults to settings.reddit.post_limit.

    Returns:
        list: A list of dictionaries representing posts. Empty list on failure.
              Includes 'created_utc_dt' key with timezone-aware UTC datetime.
    """
    reddit = get_reddit_client()
    if reddit is None:
        log.error("Cannot fetch Reddit posts, PRAW instance not available.")
        return []

    # Use settings if arguments are None, accessing via settings.reddit
    reddit_settings = getattr(settings, 'reddit', None)
    if subreddit_names is None:
        subreddit_names = getattr(reddit_settings, 'target_subreddits', []) if reddit_settings else []
        log.info(f"Using target subreddits from settings: {subreddit_names}")
    if post_limit_per_subreddit is None:
        post_limit_per_subreddit = getattr(reddit_settings, 'post_limit', 25) if reddit_settings else 25 # Default limit 25
        log.info(f"Using post limit from settings: {post_limit_per_subreddit}")

    if not isinstance(subreddit_names, list) or not subreddit_names:
        log.error("Subreddit list is invalid or empty.")
        return []

    reddit_posts = []
    log.info(f"Fetching up to {post_limit_per_subreddit} new posts from subreddits: {subreddit_names}")

    for sub_name in subreddit_names:
        try:
            log.debug(f"Accessing subreddit: r/{sub_name}")
            subreddit = reddit.subreddit(sub_name)
            # Fetch newest posts using .new()
            new_posts = subreddit.new(limit=post_limit_per_subreddit)

            count = 0
            for post in new_posts:
                # Skip stickied posts if desired (often mod announcements)
                if post.stickied:
                    log.debug(f"Skipping stickied post in r/{sub_name}: {post.id}")
                    continue

                # Combine title and selftext for analysis later
                post_text_combined = post.title
                if post.is_self and post.selftext:
                    post_text_combined += "\n" + post.selftext

                # Convert timestamp to timezone-aware datetime object
                created_utc_dt = datetime.datetime.fromtimestamp(post.created_utc, tz=pytz.utc)

                reddit_posts.append({
                    'post_id': post.id,
                    'subreddit': sub_name.lower(), # Store lowercase for consistency
                    'title': post.title,
                    'selftext': post.selftext if post.is_self else None,
                    'text_combined': post_text_combined, # For easier sentiment analysis input
                    'url': f"https://www.reddit.com{post.permalink}",
                    'score': post.score,
                    'num_comments': post.num_comments,
                    'created_utc_dt': created_utc_dt, # Store as datetime object
                    # 'fetched_at' will be added by the database insertion logic
                })
                count += 1
            log.info(f"Fetched {count} posts from r/{sub_name}")

        except ResponseException as e:
            # Handle HTTP errors (e.g., 404 Not Found, 403 Forbidden, 5xx Server Errors)
            log.error(f"PRAW HTTP error fetching from r/{sub_name}: {e.response.status_code} - {e}")
        except RequestException as e:
             # Handle network-related errors (e.g., connection timeout)
             log.error(f"PRAW request error fetching from r/{sub_name}: {e}")
        except PrawcoreException as e:
             # Handle other PRAW-specific errors
             log.error(f"PRAW core error processing subreddit r/{sub_name}: {e}", exc_info=True)
        except Exception as e:
            # Catch any other unexpected errors
            log.error(f"General error processing subreddit r/{sub_name}: {e}", exc_info=True)

    log.info(f"Finished fetching Reddit posts. Total items collected: {len(reddit_posts)}")
    return reddit_posts

# --- Example Usage (for testing) ---
if __name__ == '__main__':
    # Setup basic logging using the centralized setup function
    # Note: This setup might conflict if logging is already configured globally.
    # Consider removing this block or making it conditional.
    from hydrobot.utils.logger_setup import setup_logging
    import logging # Import standard logging only for fallback in __main__
    try:
        # Use log level from settings if available
        log_level_setting = getattr(settings, 'log_level', 'INFO')
        setup_logging(log_level_setting)
        log.info("Logging setup for __main__ test.")
    except Exception as e:
        print(f"Error setting up logging from settings: {e}")
        logging.basicConfig(level="INFO", format='%(asctime)s - %(levelname)s [%(name)s] %(message)s')
        log = logging.getLogger(__name__) # Fallback logger

    print("--- Testing Reddit Client (using settings.reddit) ---")

    # Check credentials loaded via settings.reddit
    reddit_settings = getattr(settings, 'reddit', None)
    creds_ok = False
    if reddit_settings:
        client_id = getattr(reddit_settings, 'client_id', None)
        client_secret_obj = getattr(reddit_settings, 'client_secret', None)
        user_agent = getattr(reddit_settings, 'user_agent', None)
        if all([client_id, client_secret_obj, user_agent]):
             creds_ok = True
        else:
            print("\nERROR: Reddit API credentials not fully configured in settings.reddit.")
    else:
        print("\nERROR: 'reddit' section not found in settings.")

    if creds_ok:
        # Use settings for target subs and limit
        target_subs = getattr(reddit_settings, 'target_subreddits', [])[:2] # Test with first 2 configured subreddits
        limit = getattr(reddit_settings, 'post_limit', 5)
        print(f"\nFetching latest posts from subreddits: {target_subs} (limit: {limit})...")

        posts_list = fetch_new_subreddit_posts(subreddit_names=target_subs, post_limit_per_subreddit=limit)

        if posts_list:
            print(f"Fetched {len(posts_list)} total posts.")
            print("\nFirst post details:")
            first_post = posts_list[0]
            for key, value in first_post.items():
                 # Truncate long text fields for display
                 if key in ['selftext', 'text_combined'] and value and len(value) > 100:
                     print(f"  {key}: {value[:100]}...")
                 else:
                     print(f"  {key}: {value}")
            # Verify UTC conversion
            if first_post.get('created_utc_dt'):
                print(f"  Created (UTC): {first_post['created_utc_dt']}")
                print(f"  Is UTC Timezone Aware: {first_post['created_utc_dt'].tzinfo is not None}")
        else:
            print("Could not fetch any Reddit posts. Check logs for errors.")

    print("\n--- Test Complete ---")

