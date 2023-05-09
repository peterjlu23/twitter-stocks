import tweepy
import re
import os
from datetime import datetime, timezone, timedelta
import humanize
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import streamlit as st
import requests
import html2text
from bs4 import BeautifulSoup
import math
from urllib.parse import quote
import functools
import time
import re

class TokenBucket:
    def __init__(self, tokens, fill_rate):
        self.capacity = float(tokens)
        self.tokens = float(tokens)
        self.fill_rate = float(fill_rate)
        self.timestamp = time.monotonic()

    def get_tokens(self):
        now = time.monotonic()
        delta = now - self.timestamp
        self.timestamp = now
        self.tokens = min(self.capacity, self.tokens + delta * self.fill_rate)
        return self.tokens

    def consume(self, tokens):
        tokens_available = self.get_tokens()
        if tokens <= tokens_available:
            self.tokens -= tokens
            return True
        return False

bucket = TokenBucket(tokens=15, fill_rate=1)  # Adjust tokens and fill_rate according to your requirements

@st.cache(allow_output_mutation=True, ttl=300)
def search_tweets_cached(api, query_string, count, tweet_mode, max_id, result_type):
    return api.search_tweets(query_string, count=count, tweet_mode=tweet_mode, max_id=max_id, result_type=result_type)

def search_tweets(api, query_string, count, tweet_mode, max_id, result_type):
    return functools.partial(search_tweets_cached, api, query_string, count, tweet_mode, max_id, result_type)

def get_tweet_embed_html(tweet_id, user_screen_name):
    url = f"https://publish.twitter.com/oembed?url=https://twitter.com/{user_screen_name}/status/{tweet_id}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data['html']
    return None

def linkify(text):
    url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
    return url_pattern.sub(r'<a href="\g<0>" target="_blank" rel="noopener noreferrer">\g<0></a>', text)

def tweet_contains_banned_hashtags(tweet, banned_hashtags):
    hashtags = [hashtag["text"].lower() for hashtag in tweet["entities"]["hashtags"]]
    return any(hashtag in banned_hashtags for hashtag in hashtags)

# Authenticate with Twitter API
consumer_key = os.environ.get("TWITTER_CONSUMER_KEY")
consumer_secret = os.environ.get("TWITTER_CONSUMER_SECRET")
access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
access_token_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
auth.set_access_token(access_token, access_token_secret)
api = tweepy.API(auth, parser=tweepy.parsers.JSONParser())

# Prompt the user to enter the stock symbol
symbol = st.text_input("Enter stock symbol (e.g. AAPL):")

if symbol:
    if not bucket.consume(1):  # Consume 1 token for each request
        st.error("You've reached the request limit. Please wait before making more requests.")
    else:
        # Define banned words, users, hashtags, and emojis
        banned_words = ["discord", "chatroom", "top analyst", "price target", "trading rooms", "trading room", "buy alert", "short signal", "max pain", "private channel", "instant help", "click here", "$gme", "$hold", "most profitable", "crypto community", "live alert", "free lessons", "free trial", "best analysis", "cryptocurrency", "meme"]
        banned_users = ["TWAOptions", "OptionsProOI", "OptionsMaxPain", "CQGInc", "SwingTradeBot", "StocksCreamun", "RRli18", "Slayer10Stock", "MoneyForFun_", "SalvatoreP1987", "XTRADERS9", "WallStSnacks", "jimcramer"]
        banned_hashtags = ["#success", "#wealth", "#meme", "#stocks", "#tothemoon", "#redditarmy", "#yolo", "#fomo", "#cryptocurrency", "#crypto", "#GME", "#gamestop"]
        banned_emojis = ["📈", "📉", "🚀"]

        # Add filter tabs at the top
        filter_option = st.radio("Filter tweets by:", ('Latest', 'Top'))

        # Filter out unwanted tweets and search for the stock symbol in the 500 latest English tweets
        filtered_tweets = []
        query_string = f"${symbol} lang:en"
        max_id = None

        # Add a counter variable
        fetch_count = 0
        max_fetches = 5

        while fetch_count < max_fetches:  # Keep fetching tweets until there are no more results or the counter reaches the limit
            result_type = "recent" if filter_option.lower() == "latest" else "popular"
            search_result = api.search_tweets(
                query_string,
                count=100,
                tweet_mode="extended",
                max_id=max_id,
                result_type=result_type,
            )

            if len(search_result["statuses"]) == 0:
                break

            for tweet in search_result["statuses"]:
                # Update max_id for the next API call
                if max_id is None or tweet["id"] < max_id:
                    max_id = tweet["id"] - 1

                if tweet["retweeted"] or "RT @" in tweet["full_text"][:4]:
                    continue
                text = tweet["full_text"].lower()
                if any(word.lower() in text for word in banned_words):
                    continue
                if any(f"@{user}" in text for user in banned_users):
                    continue
                symbols = [word for word in text.split() if word.startswith("$")]
                if len(symbols) >= 5:
                    continue

                filtered_tweets.append(tweet)

            # Increment the counter
            fetch_count += 1

        # Fetch the popular tweets
        if filter_option.lower() == "top":
            popular_tweets = api.search_tweets(
                query_string,
                count=100,
                tweet_mode="extended",
                result_type="popular",
            )["statuses"]

            # Merge filtered_tweets and popular_tweets, removing duplicates
            tweet_ids = set(tweet["id"] for tweet in filtered_tweets)
            filtered_tweets = filtered_tweets + [tweet for tweet in popular_tweets if tweet["id"] not in tweet_ids]

            filtered_tweets = [
                tweet
                for tweet in filtered_tweets
                if tweet["user"]["screen_name"] not in banned_users
                and not tweet_contains_banned_hashtags(tweet, banned_hashtags)
            ]

            # Sort the remaining tweets by engagement metrics
            filtered_tweets = sorted(filtered_tweets, key=lambda x: (x['retweet_count'], x['favorite_count'], x['user']['followers_count']), reverse=True)

        # Filter out similar tweets based on cosine similarity
        if len(filtered_tweets) > 1:
            text_list = [tweet['full_text'] for tweet in filtered_tweets if 'full_text' in tweet]
            vectorizer = TfidfVectorizer(min_df=2)
            try:
                vectors = vectorizer.fit_transform(text_list)
                similarity_matrix = cosine_similarity(vectors)
                filtered_tweets = [filtered_tweets[i] for i in range(len(similarity_matrix)) if all(similarity_matrix[i][j] < 0.8 for j in range(i+1,len(similarity_matrix)))]
            except ValueError:
                # If a ValueError is raised due to an empty vocabulary, just skip filtering by cosine similarity
                pass

        # Display the results in the specified format
        st.markdown(f'<h2 style="font-size: 1.3em;">Showing 40 {filter_option.lower()} English tweets about ${symbol.upper()}:</h2>', unsafe_allow_html=True)

        for i, tweet in enumerate(filtered_tweets):
            profile_image = tweet['user']['profile_image_url_https']
            name = tweet['user']['name']
            screen_name = tweet['user']['screen_name']
            text = re.sub(r'(https?://\S+)', r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', tweet['full_text'])
            soup = BeautifulSoup(text, 'html.parser')
            plain_text = soup.get_text()
            tweet_url = f"https://twitter.com/{screen_name}/status/{tweet['id_str']}"
            created_at = datetime.strptime(tweet['created_at'], '%a %b %d %H:%M:%S +0000 %Y')
            local_time = created_at.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=-10)))
            local_time_str = local_time.strftime('%I:%M %p HST · %b %-d, %Y')  # Changed format to remove leading zero
            retweet_count = tweet['retweet_count']
            favorite_count = tweet['favorite_count']

            # Check if there's any media attached to the tweet
            media_url = None
            if 'media' in tweet['entities']:
                media = tweet['entities']['media'][0]
                media_type = media['type']
                if media_type in ('photo', 'animated_gif'):
                    media_url = media['media_url_https']

            st.write(f'<div style="display: flex; align-items: flex-start; margin-bottom: 10px;">'
                    f'<img src="{profile_image}" style="border-radius: 50%; width: 48px; height: 48px; margin-right: 10px;" />'
                    f'<div style="display: flex; flex-direction: column;">'
                    f'<div style="display: flex; align-items: center;">'
                    f'<a href="https://twitter.com/{screen_name}" target="_blank" rel="noopener noreferrer" style="text-decoration: none; color: inherit;"><strong style="font-size: 1em;">{name}</strong></a>'
                    f'<span style="color: #555; font-weight: normal; font-style: normal; font-family: Arial, sans-serif; margin-left: 5px; font-size: 0.9em;">@{screen_name}</span>'
                    f'</div>'
                    f'<span style="color: #555; font-weight: normal; font-style: normal; font-family: Arial, sans-serif; font-size: 1em;">{linkify(plain_text)}</span>'                    
                    f'<div style="display: block;"><a href="{tweet_url}" target="_blank" rel="noopener noreferrer" style="color: #999; text-decoration: none; font-size: 0.9em; margin-top: -10px;">{humanize.naturaltime(datetime.now(timezone(timedelta(hours=-10))) - local_time)}&nbsp;&nbsp;•&nbsp;&nbsp;{local_time.strftime("%b %-d")}</a></div>'
                    f'</div>'
                    f'</div>', unsafe_allow_html=True)

            # Display media if available
            if media_url:
                if media_type == 'photo':
                    st.write(f'<div style="text-align: center;">'
                            f'<a href="{media_url}" data-lightbox="tweet-media" data-title="Attached image">'
                            f'<img src="{media_url}" class="tweet-media" alt="Attached image" style="width: 100%; max-width: 500px; margin-bottom: 5px;" />'
                            f'</a></div>', unsafe_allow_html=True)
                elif media_type == 'animated_gif':
                    st.write(f'<div style="text-align: center;">'
                            f'<a href="{media_url}" data-lightbox="tweet-media" data-title="Attached GIF">'
                            f'<img src="{media_url}" class="tweet-media" alt="Attached GIF" style="width: 100%; max-width: 500px; margin-bottom: 5px;" />'
                            f'</a></div>', unsafe_allow_html=True)

            st.write(f'<div style="display: flex; flex-direction: column; align-items: flex-start; width: 100%; margin-top: 1px; font-size: 0.8em; color: #999; margin-left: 58px;">'
                    f'<div style="display: flex;">'
                    f'<span>🔁 {retweet_count}</span>'
                    f'<span style="margin-left: 10px;">❤️ {favorite_count}</span>'
                    f'</div>'
                    f'</div>', unsafe_allow_html=True)

            # Add a light gray line between tweets
            st.markdown('<hr style="border: 1px solid #ddd; margin-top: 10px; margin-bottom: 10px;">', unsafe_allow_html=True)