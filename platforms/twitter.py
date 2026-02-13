import os
import tweepy
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class TwitterPoster:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # 1. Load Credentials
        api_key = os.getenv("TWITTER_API_KEY")
        api_secret = os.getenv("TWITTER_API_SECRET")
        access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

        if not all([api_key, api_secret, access_token, access_token_secret]):
            self.logger.error("❌ CRITICAL: Missing Twitter Credentials in .env")
            raise ValueError("Missing Twitter Credentials")

        # 2. CREATE ROBUST SESSION (Fixes SSL/Connection Errors)
        self.session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["POST", "GET"],
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

        # 3. Authenticate v1.1 (Media Upload)
        auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_token_secret)
        self.api_v1 = tweepy.API(auth)
        self.api_v1.session = self.session

        # 4. Authenticate v2 (Tweet Creation)
        self.client_v2 = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            wait_on_rate_limit=True,
        )
        self.client_v2.session = self.session

    def post_image(self, file_path, caption):
        return self._upload_media(file_path, caption, is_video=False)

    def post_video(self, file_path, caption):
        return self._upload_media(file_path, caption, is_video=True)

    def _upload_media(self, file_path, caption, is_video=False):
        try:
            if not os.path.exists(file_path):
                self.logger.error(f"❌ File not found: {file_path}")
                return False

            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            self.logger.info(f"   📂 File Size: {size_mb:.2f} MB")

            # Upload to v1.1
            if is_video:
                self.logger.info("   ⏳ Twitter: Uploading VIDEO (v1.1)...")
                media = self.api_v1.media_upload(file_path, media_category="tweet_video")
            else:
                self.logger.info("   ⏳ Twitter: Uploading IMAGE (v1.1)...")
                media = self.api_v1.media_upload(file_path)

            media_id = media.media_id
            self.logger.info(f"   ⏳ Media ID: {media_id}")

            # Post Tweet v2
            self.logger.info("   ⏳ Twitter: Posting Tweet (v2)...")
            response = self.client_v2.create_tweet(text=caption, media_ids=[media_id])

            if response.data and "id" in response.data:
                self.logger.info(f"   ✅ Twitter Posted! ID: {response.data['id']}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"   ❌ Twitter Error: {e}")
            raise e
