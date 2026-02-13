import os
import requests
import time
import logging

class InstagramPoster:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.ig_id = os.getenv("IG_ID")
        self.token = os.getenv("META_TOKEN")
        self.base_url = f"https://graph.facebook.com/v18.0/{self.ig_id}"

    def post_video(self, video_url, caption):
        return self._create_publish_container(video_url, caption, "VIDEO")

    def post_image(self, image_url, caption):
        return self._create_publish_container(image_url, caption, "IMAGE")

    def _create_publish_container(self, media_url, caption, media_type):
        # 1. Create Container
        url = f"{self.base_url}/media"
        
        payload = {
            "access_token": self.token,
            "caption": caption,
            "media_type": "REELS" if media_type == "VIDEO" else "IMAGE"
        }
        
        if media_type == "VIDEO":
            payload["video_url"] = media_url
            payload["share_to_feed"] = "true"
        else:
            payload["image_url"] = media_url

        self.logger.info(f"   ⏳ IG: Sending {media_type} URL to Meta...")
        
        try:
            res = requests.post(url, data=payload, timeout=60)
            self.logger.info(f"   📩 Response Code: {res.status_code}")
            
            if res.status_code != 200:
                raise Exception(f"IG Create Failed: {res.text}")
            
            creation_id = res.json()['id']
            self.logger.info(f"   ✅ Container Created ID: {creation_id}")

            # 2. Poll Status (Critical for Video)
            if media_type == "VIDEO":
                self.logger.info("   ⏳ IG: Waiting for video processing...")
                status = "IN_PROGRESS"
                attempts = 0
                max_attempts = 20
                
                while status != "FINISHED" and attempts < max_attempts:
                    time.sleep(5)
                    attempts += 1
                    
                    stat_res = requests.get(
                        f"https://graph.facebook.com/v18.0/{creation_id}",
                        params={"fields": "status_code", "access_token": self.token},
                        timeout=30
                    )
                    
                    if stat_res.status_code != 200:
                        self.logger.warning(f"   ⚠️ IG Poll Error: {stat_res.text}")
                        continue
                        
                    status = stat_res.json().get('status_code', 'ERROR')
                    self.logger.info(f"      - Attempt {attempts}: {status}")
                    
                    if status == "ERROR":
                        raise Exception("IG Video Processing Failed (Status: ERROR)")

                if status != "FINISHED":
                    raise Exception("IG Video Processing Timeout")

            # 3. Publish
            self.logger.info("   ⏳ IG: Publishing...")
            pub_url = f"{self.base_url}/media_publish"
            pub_res = requests.post(pub_url, data={
                "creation_id": creation_id, 
                "access_token": self.token
            }, timeout=60)
            
            if pub_res.status_code != 200:
                raise Exception(f"IG Publish Failed: {pub_res.text}")
                
            self.logger.info(f"   ✅ IG Published Successfully ID: {pub_res.json()['id']}")
            return True

        except requests.exceptions.Timeout:
            self.logger.error("   ❌ IG Connection Timed Out")
            raise Exception("Timeout")
        except Exception as e:
            self.logger.error(f"   ❌ IG Error: {e}")
            raise e