"""Twitter client wrapper for tweet ingestion."""

import time
from typing import Dict, List, Optional, Tuple

import pytz
import tweepy

# Use absolute imports for the new structure
from hydrobot.config.settings import settings
from hydrobot.utils.logger_setup import get_logger

# Use the configured logger
log = get_logger(__name__)

# --- Twitter Client Initialization ---
_twitter_client_v2: Optional[tweepy.Client] = None


def get_twitter_client_v2() -> Optional[tweepy.Client]:
    """Initializes and returns the Tweepy API v2 client singleton using settings."""
    global _twitter_client_v2
    if _twitter_client_v2 is None:
        # Get credentials from the central settings object
        twitter_settings = getattr(settings, "twitter", None)
        if not twitter_settings:
            log.error(
                "Twitter configuration section ('twitter') not found in settings."
            )
            return None

        bearer_token_obj = getattr(twitter_settings, "bearer_token", None)
        if not bearer_token_obj:
            log.error(
                "Twitter Bearer Token not configured in settings.twitter.bearer_token"
            )
            return None

        # Use get_secret_value() for the secret
        bearer_token = bearer_token_obj.get_secret_value()
        if not bearer_token:
            log.error("Twitter Bearer Token value is empty in settings.")
            return None

        try:
            log.info("Initializing Tweepy client for Twitter API v2...")
            # Use bearer token for app-only authentication
            _twitter_client_v2 = tweepy.Client(
                bearer_token=bearer_token, wait_on_rate_limit=False
            )  # Handle rate limits manually
            log.info("Tweepy client object created successfully (using Bearer Token).")

        except tweepy.errors.TweepyException as e:
            log.error(
                f"TweepyException initializing Twitter client: {e}", exc_info=True
            )
            _twitter_client_v2 = None
        except Exception as e:
            log.error(
                f"Unexpected error initializing Twitter client: {e}", exc_info=True
            )
            _twitter_client_v2 = None
    return _twitter_client_v2


def build_twitter_query(
    symbols: List[str], base_keywords: Optional[List[str]] = None
) -> str:
    """
    Builds a search query string for the Twitter API v2 Recent Search endpoint.
    Uses base_keywords from settings.twitter.query_keywords if not provided.
    Focuses on cashtags and hashtags for the given symbols, combined with base keywords.
    Excludes retweets and requires English language.

    Args:
        symbols (List[str]): List of cryptocurrency symbols (e.g., ['BTC', 'ETH']).
        base_keywords (List[str], optional): General keywords. Defaults to settings.twitter.query_keywords.

    Returns:
        str: A formatted query string for the Twitter API. Empty string if no symbols/keywords.
    """
    twitter_settings = getattr(settings, "twitter", None)
    if base_keywords is None:
        base_keywords = (
            getattr(twitter_settings, "query_keywords", []) if twitter_settings else []
        )
        log.debug(f"Using base keywords from settings: {base_keywords}")

    if not symbols and not base_keywords:
        log.warning("Cannot build Twitter query without symbols or keywords.")
        return ""

    symbol_query_parts = []
    if symbols:
        # Create hashtag parts for each symbol (Twitter API v2 prefers hashtags over cashtags for search)
        symbol_parts = []
        for symbol in symbols:
            # Clean symbol (remove pairs like USDT, ensure uppercase)
            s_upper = (
                symbol.upper()
                .replace("USDT", "")
                .replace("BUSD", "")
                .replace("USD", "")
            )
            if s_upper:
                symbol_parts.append(f"#{s_upper}")
        if symbol_parts:
            symbol_query_parts.append(f"({' OR '.join(symbol_parts)})")

    keyword_query_parts = []
    if base_keywords:
        # Quote keywords with spaces
        keyword_part = " ".join([f'"{k}"' if " " in k else k for k in base_keywords])
        keyword_query_parts.append(f"({keyword_part})")

    # Combine symbol and keyword parts (using OR for broader reach)
    combined_terms = " OR ".join(symbol_query_parts + keyword_query_parts)
    if not combined_terms:
        log.warning("No valid symbols or keywords resulted in query terms.")
        return ""

    # Add language filter and exclude retweets
    full_query = f"({combined_terms}) lang:en -is:retweet"

    # Twitter query length limit (512 for standard v2 basic/elevated)
    max_len = 512
    if len(full_query) > max_len:
        log.warning(
            f"Generated Twitter query exceeds max length ({max_len}). Truncating: {full_query}"
        )
        # Simple truncation, might break logic.
        full_query = full_query[:max_len].rsplit(" ", 1)[0]  # Try to cut at last space
        log.warning(f"Truncated query: {full_query}")

    log.debug(f"Generated Twitter Query: {full_query}")
    return full_query.strip()


def search_recent_tweets(
    query: str,
    max_total_results: int = 100,
    results_per_page: int = 100,
    since_id: Optional[str] = None,
) -> Tuple[List[Dict], Optional[str]]:
    """
    Searches for recent tweets matching the query using Twitter API v2 (handles pagination).

    Args:
        query (str): The search query string.
        max_total_results (int): Max tweets to fetch across pages.
        results_per_page (int): Max tweets per API request (10-100).
        since_id (str, optional): Returns results with a Tweet ID greater than this ID.

    Returns:
        Tuple[List[Dict], Optional[str]]:
            - List of tweet dictionaries.
            - The 'newest_id' from the metadata of the *last successful* response,
              suitable for use as 'since_id' in the next poll. None if no tweets or error.
    """
    client = get_twitter_client_v2()
    if not client:
        log.error("Cannot search tweets, Twitter client not available.")
        return [], None
    if not query:
        log.warning("Empty query provided, skipping Twitter search.")
        return [], None

    log.info(
        f"Searching recent tweets with query: '{query}', aiming for max {max_total_results} results, since_id: {since_id}..."
    )

    all_tweets_list = []
    newest_id_overall = None
    next_page_token = None
    fetched_count = 0
    max_pages_to_fetch = (max_total_results + results_per_page - 1) // results_per_page

    # Define the fields we want to retrieve for each tweet
    tweet_fields = ["created_at", "public_metrics", "entities", "author_id"]

    backoff_time = 1  # Initial backoff time in seconds

    for page_num in range(max_pages_to_fetch):
        if fetched_count >= max_total_results:
            log.info(
                f"Reached max_total_results limit ({max_total_results}). Stopping pagination."
            )
            break

        page_max_results = min(results_per_page, 100, max_total_results - fetched_count)
        if page_max_results < 10:
            page_max_results = 10

        log.debug(
            f"Fetching Twitter page {page_num + 1}, max_results={page_max_results}, next_token={next_page_token}, since_id={since_id}"
        )

        try:
            response = client.search_recent_tweets(
                query=query,
                max_results=page_max_results,
                tweet_fields=tweet_fields,
                next_token=next_page_token,
                since_id=since_id,
            )

            backoff_time = 1

            if response.errors:
                log.error(
                    f"Twitter API returned errors on page {page_num + 1}: {response.errors}"
                )
                is_rate_limit = any(
                    error.get("code") == 429 or error.get("status") == 429
                    for error in response.errors
                )
                if is_rate_limit:
                    log.warning(
                        "Twitter API rate limit hit (429 in errors). Retrying after backoff."
                    )
                    time.sleep(backoff_time)
                    backoff_time = min(backoff_time * 2, 300)
                    continue
                else:
                    log.error(
                        "Non-rate-limit error received from Twitter API. Stopping pagination."
                    )
                    break

            current_page_tweets = []
            if response.data:
                log.info(
                    f"Received {len(response.data)} tweets on page {page_num + 1}."
                )
                for tweet in response.data:
                    try:
                        hashtags = (
                            [tag["tag"] for tag in tweet.entities.get("hashtags", [])]
                            if tweet.entities
                            else []
                        )
                        cashtags = (
                            [tag["tag"] for tag in tweet.entities.get("cashtags", [])]
                            if tweet.entities
                            else []
                        )

                        created_at_utc = (
                            tweet.created_at.replace(tzinfo=pytz.utc)
                            if tweet.created_at
                            else None
                        )

                        current_page_tweets.append(
                            {
                                "tweet_id": str(tweet.id),
                                "author_id": (
                                    str(tweet.author_id) if tweet.author_id else None
                                ),
                                "text": tweet.text,
                                "created_at": created_at_utc,
                                "public_metrics": tweet.public_metrics or {},
                                "hashtags": hashtags,
                                "cashtags": cashtags,
                            }
                        )
                    except Exception as item_err:
                        log.error(
                            f"Error processing individual tweet: {item_err}. Tweet data: {tweet}",
                            exc_info=True,
                        )

                all_tweets_list.extend(current_page_tweets)
                fetched_count += len(current_page_tweets)

                if page_num == 0 and response.meta and "newest_id" in response.meta:
                    newest_id_overall = response.meta["newest_id"]
                    log.debug(
                        f"Captured newest_id from first page metadata: {newest_id_overall}"
                    )

            if response.meta and "next_token" in response.meta:
                next_page_token = response.meta["next_token"]
                log.debug("Found next_token, will fetch next page.")
                time.sleep(1.1)
            else:
                log.debug(
                    "No next_token found, pagination complete for this query run."
                )
                break

        except tweepy.errors.TweepyException as e:
            if (
                isinstance(e, tweepy.errors.HTTPException)
                and e.response is not None
                and e.response.status_code == 429
            ):
                log.warning(
                    f"Twitter API rate limit hit (429 Exception). Retrying after {backoff_time}s backoff."
                )
                time.sleep(backoff_time)
                backoff_time = min(backoff_time * 2, 300)
                continue
            else:
                log.error(
                    f"TweepyException searching tweets (Page {page_num + 1}): {e}",
                    exc_info=True,
                )
                break
        except Exception as e:
            log.error(
                f"Unexpected error searching tweets (Page {page_num + 1}): {e}",
                exc_info=True,
            )
            break

    log.info(
        f"Finished Twitter search for query. Total tweets fetched in this run: {len(all_tweets_list)}"
    )
    return all_tweets_list, newest_id_overall


# --- Example Usage (for testing) ---
_LATEST_TWEET_ID_STORE_TEST = {}

if __name__ == "__main__":
    import logging

    from hydrobot.utils.logger_setup import setup_logging

    try:
        log_level_setting = getattr(settings, "log_level", "INFO")
        setup_logging(log_level_setting)
        log.info("Logging setup for __main__ test using centralized setup.")
    except Exception as e:
        print(f"Error setting up logging from settings: {e}")
        logging.basicConfig(
            level="INFO",
            format="%(asctime)s - %(levelname)s [%(name)s:%(lineno)d] %(message)s",
        )
        log = logging.getLogger(__name__)

    print("--- Testing Twitter Client (using settings.twitter) ---")

    twitter_settings = getattr(settings, "twitter", None)
    creds_ok = False
    if twitter_settings:
        bearer_token_obj = getattr(twitter_settings, "bearer_token", None)
        if bearer_token_obj and bearer_token_obj.get_secret_value():
            creds_ok = True
        else:
            print(
                "\nERROR: Twitter Bearer Token not configured or empty in settings.twitter.bearer_token"
            )
    else:
        print("\nERROR: 'twitter' section not found in settings.")

    if creds_ok:
        test_symbols = getattr(twitter_settings, "target_symbols", ["BTC", "ETH"])[:2]
        test_keywords = getattr(twitter_settings, "query_keywords", ["price"])
        test_query = build_twitter_query(
            symbols=test_symbols, base_keywords=test_keywords
        )

        if test_query:
            print(f"\nGenerated Query: {test_query}")

            query_key_test = f"test_{'_'.join(test_symbols).lower()}"
            print(f"Using persistence key: {query_key_test}")

            print("\n--- Fetch 1 (Using stored Since ID if available) ---")
            since_id_for_run = _LATEST_TWEET_ID_STORE_TEST.get(query_key_test)
            print(f"Using since_id: {since_id_for_run}")
            tweets1, newest_id1 = search_recent_tweets(
                query=test_query,
                max_total_results=20,
                results_per_page=10,
                since_id=since_id_for_run,
            )
            if tweets1:
                print(f"Fetched {len(tweets1)} tweets.")
                print("First tweet:", tweets1[0]["text"][:100] + "...")
                print(f"Newest ID from this run's metadata (if any): {newest_id1}")
                if newest_id1:
                    print(
                        f"Updating stored newest ID for {query_key_test} to {newest_id1}"
                    )
                    _LATEST_TWEET_ID_STORE_TEST[query_key_test] = newest_id1
            else:
                print("No new tweets found in Fetch 1.")
                print(f"Newest ID from this run's metadata (if any): {newest_id1}")

            print("\nWaiting 5 seconds before next fetch...")
            time.sleep(5)

            print("\n--- Fetch 2 (Using Since ID from previous run) ---")
            since_id_for_run = _LATEST_TWEET_ID_STORE_TEST.get(query_key_test)
            print(f"Using since_id: {since_id_for_run}")
            tweets2, newest_id2 = search_recent_tweets(
                query=test_query,
                max_total_results=20,
                results_per_page=10,
                since_id=since_id_for_run,
            )
            if tweets2:
                print(f"Fetched {len(tweets2)} tweets.")
                print("First tweet:", tweets2[0]["text"][:100] + "...")
                print(f"Newest ID from this run's metadata (if any): {newest_id2}")
                if newest_id2:
                    print(
                        f"Updating stored newest ID for {query_key_test} to {newest_id2}"
                    )
                    _LATEST_TWEET_ID_STORE_TEST[query_key_test] = newest_id2
            else:
                print("No new tweets found in Fetch 2 (as expected potentially).")
                print(f"Newest ID from this run's metadata (if any): {newest_id2}")

        else:
            print("Could not generate a valid test query.")

    print("\n--- Test Complete ---")
