import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging

class TelegramPoster:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        self.token = os.getenv("TELEGRAM_POST_BOT_TOKEN") 
        self.chat_id = os.getenv("TELEGRAM_POST_CHAT_ID")

        if not self.token or not self.chat_id:
            raise ValueError("Missing Telegram Credentials")

        self.base_url = f"https://api.telegram.org/bot{self.token}"
        
        self.session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["POST"]
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def post_video(self, file_path, caption):
        url = f"{self.base_url}/sendVideo"
        
        if not os.path.exists(file_path):
             self.logger.error(f"❌ File not found: {file_path}")
             return

        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        self.logger.info(f"   📂 File Size: {size_mb:.2f} MB")
        self.logger.info("   ⏳ Telegram: Uploading Video...")

        with open(file_path, 'rb') as f:
            data = {'chat_id': str(self.chat_id), 'caption': caption}
            files = {'video': f}
            try:
                res = self.session.post(url, data=data, files=files, timeout=60)
                self.logger.info(f"   📩 Response Code: {res.status_code}")
                self._check_response(res)
            except requests.exceptions.Timeout:
                self.logger.error("   ❌ Telegram Timeout")
                raise Exception("Timeout")
            except Exception as e:
                self.logger.error(f"   ❌ Telegram Error: {e}")
                raise e

    def post_image(self, file_path, caption):
        url = f"{self.base_url}/sendPhoto"
        
        if not os.path.exists(file_path):
             self.logger.error(f"❌ File not found: {file_path}")
             return
        
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        self.logger.info(f"   📂 File Size: {size_mb:.2f} MB")
        self.logger.info("   ⏳ Telegram: Uploading Image...")

        with open(file_path, 'rb') as f:
            data = {'chat_id': str(self.chat_id), 'caption': caption}
            files = {'photo': f}
            try:
                res = self.session.post(url, data=data, files=files, timeout=60)
                self.logger.info(f"   📩 Response Code: {res.status_code}")
                self._check_response(res)
            except requests.exceptions.Timeout:
                self.logger.error("   ❌ Telegram Timeout")
                raise Exception("Timeout")
            except Exception as e:
                self.logger.error(f"   ❌ Telegram Error: {e}")
                raise e

    def _check_response(self, res):
        if res.status_code != 200:
            raise Exception(f"Telegram API Error: {res.text}")
        self.logger.info("   ✅ Telegram Content Posted")