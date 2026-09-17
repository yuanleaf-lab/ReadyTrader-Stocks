from unittest.mock import MagicMock, patch

from intelligence.core import (
    SentimentCache,
    analyze_social_sentiment,
    fetch_financial_news,
    fetch_rss_news,
    get_cached_sentiment_score,
    get_market_news,
    get_market_sentiment,
)


def test_get_market_sentiment_success():
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "fear_and_greed": {
                "rating": "greed",
                "now": 65.0
            }
        }
        mock_get.return_value = mock_response
        
        sentiment = get_market_sentiment()
        assert "CNN Fear & Greed: GREED (65.0)" in sentiment

def test_get_market_sentiment_failure():
    with patch("requests.get", side_effect=Exception("API Down")):
        sentiment = get_market_sentiment()
        assert "Error fetching CNN Fear & Greed" in sentiment

def test_analyze_social_sentiment_no_keys():
    # Ensure env vars are unset
    with patch.dict("os.environ", {}, clear=True):
        res = analyze_social_sentiment("AAPL")
        # Correctly matching the actual output from core.py
        assert "No providers configured" in res

def test_sentiment_cache():
    cache = SentimentCache()
    cache.set("AAPL", 0.8, ["Everything is awesome"])
    
    cached = cache.get("AAPL")
    assert cached["score"] == 0.8
    assert "Everything is awesome" in cached["explainability_string"]
    
    # Test expiry
    # We patch time.time to control "now"
    # When cache.set was called, it used real time.
    # So we need to ensure our patched time is >> real time.
    import time
    future_time = time.time() + 4000
    
    with patch("time.time", return_value=future_time):
        assert cache.get("AAPL") is None

def test_get_cached_sentiment_score():
    with patch("intelligence.core._sentiment_cache") as mock_cache:
        mock_cache.get.return_value = {"score": 0.5}
        assert get_cached_sentiment_score("AAPL") == 0.5
        
        mock_cache.get.return_value = None
        assert get_cached_sentiment_score("GOOG") == 0.0

def test_get_market_news_no_key():
    with patch.dict("os.environ", {}, clear=True):
        res = get_market_news()
        assert "ALPHAVANTAGE_API_KEY missing" in res

def test_get_market_news_success():
    with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test"}):
        with patch("requests.get") as mock_get:
            mock_get.return_value.json.return_value = {
                "feed": [
                    {"title": "Stock Up", "source": "CNBC"}
                ]
            }
            res = get_market_news()
            assert "Stock Up" in res

def test_fetch_rss_news_no_lib():
    with patch("intelligence.core.feedparser", None):
        res = fetch_rss_news("AAPL")
        assert "feedparser library not installed" in res

def test_fetch_rss_news_success():
    # Only if feedparser is installed (it is in main env, but maybe verify)
    # Use mock
    with patch("intelligence.core.feedparser") as mock_fp:
        entry = MagicMock()
        entry.title = "AAPL releases iPhone 20"
        entry.summary = "It is great"
        
        mock_feed = MagicMock()
        mock_feed.entries = [entry]
        mock_fp.parse.return_value = mock_feed
        
        res = fetch_rss_news("AAPL")
        assert "AAPL releases iPhone 20" in res

def test_fetch_financial_news_no_key():
    with patch.dict("os.environ", {}, clear=True):
        res = fetch_financial_news("AAPL")
        assert "NEWSAPI_KEY missing" in res

def test_fetch_financial_news_success():
    with patch.dict("os.environ", {"NEWSAPI_KEY": "test"}):
        with patch("intelligence.core.NewsApiClient") as MockClient:
            client_inst = MockClient.return_value
            client_inst.get_everything.return_value = {
                "status": "ok",
                "articles": [
                    {"title": "Boom", "source": {"name": "Test"}}
                ]
            }
            res = fetch_financial_news("AAPL")
            assert "Boom" in res

def test_analyze_social_sentiment_mocked_success():
    with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "x", "REDDIT_CLIENT_ID": "r", "REDDIT_CLIENT_SECRET": "s"}):
        with patch("intelligence.core.tweepy") as mock_tweepy:
            with patch("intelligence.core.praw") as mock_praw:
                # Mock Twitter
                mock_client = MagicMock()
                mock_tweet = MagicMock()
                mock_tweet.text = "AAPL is going up #bullish"
                mock_client.search_recent_tweets.return_value = MagicMock(data=[mock_tweet])
                mock_tweepy.Client.return_value = mock_client
                
                # Mock Reddit
                mock_reddit = MagicMock()
                mock_sub = MagicMock()
                mock_post = MagicMock()
                mock_post.title = "AAPL DD"
                mock_sub.search.return_value = [mock_post]
                mock_reddit.subreddit.return_value = mock_sub
                mock_praw.Reddit.return_value = mock_reddit

                res = analyze_social_sentiment("AAPL")
                assert "Twitter: Found 1" in res
                assert "Reddit: Found 1" in res
