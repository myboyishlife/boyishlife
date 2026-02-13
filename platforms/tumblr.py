import os
import pytumblr
import logging


class TumblrPoster:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.client = pytumblr.TumblrRestClient(
            os.getenv("TUMBLR_CONSUMER_KEY"),
            os.getenv("TUMBLR_CONSUMER_SECRET"),
            os.getenv("TUMBLR_OAUTH_TOKEN"),
            os.getenv("TUMBLR_OAUTH_TOKEN_SECRET"),
        )
        self.blog_name = os.getenv("TUMBLR_BLOG_NAME")

    def post_image(self, file_path, caption_data):
        # 1. Structured Data extraction
        if isinstance(caption_data, dict):
            text = f"{caption_data.get('text', '')}\n\n{caption_data.get('brand_tag', '')}"
            tags = caption_data.get("tags", [])
        else:
            text, tags = str(caption_data), []

        try:
            response = self.client.create_photo(
                self.blog_name,
                state="published",
                caption=text,
                tags=tags,      # <--- Separate column!
                data=[file_path]
            )
            return "id" in response
        except Exception as e:
            self.logger.error(f"Tumblr Error: {e}")
            raise e

    def post_video(self, file_path, caption_data):
        # 2. Add dictionary support for videos too
        if isinstance(caption_data, dict):
            text = f"{caption_data.get('text', '')}\n\n{caption_data.get('brand_tag', '')}"
            tags = caption_data.get("tags", [])
        else:
            text, tags = str(caption_data), []

        try:
            response = self.client.create_video(
                self.blog_name,
                state="published",
                caption=text,
                tags=tags,      # <--- Correct column for videos
                data=[file_path]
            )
            return "id" in response
        except Exception as e:
            self.logger.error(f"Tumblr Video Error: {e}")
            raise e
