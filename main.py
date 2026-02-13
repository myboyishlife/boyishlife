import os
import json
import time
import logging
import sys
from dotenv import load_dotenv

# Core Safety Modules
from core.retry_manager import SmartRetry
from core.verifier import MediaVerifier

# Project Modules
from modules.dropbox_handler import DropboxHandler
from modules.caption_generator import CaptionGenerator
from modules.utils import setup_logging

# Platforms
from platforms.instagram import InstagramPoster
from platforms.facebook import FacebookPoster
from platforms.threads import ThreadsPoster
from platforms.twitter import TwitterPoster
from platforms.telegram import TelegramPoster
from platforms.discord import DiscordPoster
from platforms.tumblr import TumblrPoster

load_dotenv()
logger = setup_logging()
SUMMARY = []

def build_caption(caption_payload):
    """Combines Text + Tags + Brand for platforms that don't have separate tags."""
    if isinstance(caption_payload, dict):
        text = caption_payload.get("text", "").strip()
        tags = " ".join([f"#{t}" for t in caption_payload.get("tags", [])])
        brand = caption_payload.get("brand_tag", "")
        return f"{text}\n\n{tags}\n\n{brand}".strip()
    return str(caption_payload)

def load_config():
    """Loads configuration dynamically from JSON."""
    with open('config.json', 'r') as f:
        return json.load(f)

def safe_post(platform_name, platform_obj, method_name, file_arg, caption, retries=1, 
              retry_engine=None, local_path=None, media_type=None):
    """
    Enhanced safe_post with SmartRetry and MediaVerifier integration.
    Maintains backward compatibility with original safe_post function.
    """
    # Media Verification Step (if local_path provided)
    if local_path and os.path.exists(local_path):
        is_safe, msg = MediaVerifier.verify(local_path, platform_name, media_type)
        if not is_safe:
            logger.warning(f"⚠️ {platform_name.upper()}: Skipped ({msg})")
            SUMMARY.append(f"⚠️ {platform_name.upper()}: Skipped ({msg})")
            return False
    
    # Use SmartRetry if provided, otherwise use original retry logic
    if retry_engine:
        try:
            logger.info(f"🚀 {platform_name.upper()} Starting with SmartRetry...")
            start_time = time.time()
            
            if not hasattr(platform_obj, method_name):
                logger.warning(f"⚠️ {platform_name} does not support {method_name}. Skipping.")
                return False
            
            method = getattr(platform_obj, method_name)
            
            # Execute with SmartRetry engine
            result = retry_engine.execute(method, file_arg, caption)

            if result == "SKIPPED":
                logger.warning(f"{platform_name} skipped due to media validation/API rejection.")
                SUMMARY.append(f"{platform_name.upper()}: Skipped (media error)")
                return False
            
            duration = time.time() - start_time
            logger.info(f"✅ {platform_name} Success! (Took {duration:.1f}s)")
            SUMMARY.append(f"✅ {platform_name.upper()}: Success ({duration:.1f}s)")
            return True
            
        except Exception as e:
            logger.error(f"❌ {platform_name} Failed: {e}")
            SUMMARY.append(f"❌ {platform_name.upper()}: Failed ({str(e)})")
            return False
    else:
        # Original retry logic (fallback)
        for attempt in range(retries + 1):
            try:
                logger.info(f"🚀 {platform_name.upper()} Attempt {attempt + 1}...")
                start_time = time.time()
                
                if not hasattr(platform_obj, method_name):
                    logger.warning(f"⚠️ {platform_name} does not support {method_name}. Skipping.")
                    return False
                
                method = getattr(platform_obj, method_name)
                method(file_arg, caption)
                
                duration = time.time() - start_time
                logger.info(f"✅ {platform_name} Success! (Took {duration:.1f}s)")
                SUMMARY.append(f"✅ {platform_name.upper()}: Success ({duration:.1f}s)")
                return True
                
            except Exception as e:
                logger.error(f"❌ {platform_name} Failed: {e}")
                if attempt < retries:
                    time.sleep(5)
                else:
                    SUMMARY.append(f"❌ {platform_name.upper()}: Failed ({str(e)})")
                    return False

def main():
    logger.info("==========================================")
    logger.info("🚀 WORKFLOW STARTED - PRODUCTION CORE MODE")
    logger.info("==========================================")
    
    config = load_config()
    dbx = DropboxHandler(config['dropbox'])
    ai = CaptionGenerator(config)
    p_conf = config['platforms']
    
    # Initialize Core Engines
    retry_engine = SmartRetry(max_attempts=config['settings'].get('retry_count', 1))
    retries = config['settings'].get('retry_count', 1)
    delay = config['settings'].get('post_delay', 10)

    # 1. Initialize ALL Enabled Platforms
    platforms = {}
    if p_conf['instagram']['enabled']: platforms['instagram'] = InstagramPoster()
    if p_conf['facebook']['enabled']: platforms['facebook'] = FacebookPoster()
    if p_conf['threads']['enabled']: platforms['threads'] = ThreadsPoster()
    if p_conf['twitter']['enabled']: platforms['twitter'] = TwitterPoster()
    if p_conf['telegram']['enabled']: platforms['telegram'] = TelegramPoster()
    if p_conf['discord']['enabled']: platforms['discord'] = DiscordPoster()
    if p_conf['tumblr']['enabled']: platforms['tumblr'] = TumblrPoster()

    # ======================================================
    # PIPELINE 1: INSTAGRAM REELS (Strict "video_ig")
    # ======================================================
    target_platforms = [p for p in platforms if p_conf[p]['type'] == 'video_ig']
    
    if target_platforms:
        logger.info("\n--- PIPELINE 1: IG VIDEO SOURCE ---")
        ig_file = dbx.get_file('ig')
        if ig_file:
            logger.info(f"📹 Selected: {ig_file.name}")
            ig_url = dbx.get_temp_link(ig_file)
            caption_payload = ai.generate(ig_file.name, "instagram")
            
            success_count = 0
            for p in target_platforms:
                if p == 'tumblr':
                    final_cap = caption_payload
                else:
                    final_cap = build_caption(caption_payload)[:p_conf[p]['limit']]
                
                # Use enhanced safe_post with retry_engine
                if safe_post(p, platforms[p], 'post_video', ig_url, final_cap, 
                           retries, retry_engine):
                    success_count += 1
            
            if success_count > 0:
                logger.info("🗑️ Deleting IG Source file...")
                dbx.delete_file(ig_file)
            else:
                logger.warning("⛔ IG Source NOT deleted")
        else:
            logger.info("📭 No files in IG folder.")

    # ======================================================
    # PIPELINE 2: GENERAL VIDEO (Dynamic)
    # ======================================================
    target_platforms = [p for p in platforms if p_conf[p]['type'] in ['video_gen', 'mixed']]
    
    if target_platforms:
        logger.info("\n--- PIPELINE 2: GENERAL VIDEO SOURCE ---")
        gen_file = dbx.get_file('general')
        if gen_file:
            logger.info(f"📹 Selected: {gen_file.name}")
            logger.info(f"  Targets: {target_platforms}")
            local_path = dbx.download_file(gen_file)
            caption_payload = ai.generate(gen_file.name, "general_video")
            
            success_count = 0
            for p in target_platforms:
                if p == 'tumblr':
                    final_cap = caption_payload
                else:
                    final_cap = build_caption(caption_payload)[:p_conf[p]['limit']]
                
                # Determine file argument based on platform
                if p in ['threads', 'instagram']:
                    file_arg = dbx.get_temp_link(gen_file)
                else:
                    file_arg = local_path
                
                # Use enhanced safe_post with MediaVerifier and retry_engine
                if safe_post(p, platforms[p], 'post_video', file_arg, final_cap,
                           retries, retry_engine, local_path, 'video'):
                    success_count += 1
                    time.sleep(delay)
            
            if os.path.exists(local_path): os.remove(local_path)
            
            if success_count > 0:
                logger.info("🗑️ Deleting General Video Source file...")
                dbx.delete_file(gen_file)
            else:
                logger.warning("⛔ General Video NOT deleted")
        else:
            logger.info("📭 No files in General Video folder.")

    # ======================================================
    # PIPELINE 3: IMAGES (Dynamic)
    # ======================================================
    target_platforms = [p for p in platforms if p_conf[p]['type'] in ['image', 'mixed']]

    if target_platforms:
        logger.info("\n--- PIPELINE 3: IMAGE SOURCE ---")
        img_file = dbx.get_file('image')
        if img_file:
            logger.info(f"📸 Selected: {img_file.name}")
            logger.info(f"  Targets: {target_platforms}")
            local_path = dbx.download_file(img_file)
            public_url = dbx.get_temp_link(img_file)
            caption_payload = ai.generate(img_file.name, "image")
            
            success_count = 0
            for p in target_platforms:
                if p == 'tumblr':
                    final_cap = caption_payload
                else:
                    final_cap = build_caption(caption_payload)[:p_conf[p]['limit']]
                
                # Determine file argument based on platform
                if p in ['threads', 'instagram']:
                    file_arg = public_url
                else:
                    file_arg = local_path
                
                # Use enhanced safe_post with MediaVerifier and retry_engine
                if safe_post(p, platforms[p], 'post_image', file_arg, final_cap,
                           retries, retry_engine, local_path, 'image'):
                    success_count += 1
                    time.sleep(delay)
            
            if os.path.exists(local_path): os.remove(local_path)
            
            if success_count > 0:
                logger.info("🗑️ Deleting Image Source file...")
                dbx.delete_file(img_file)
            else:
                logger.warning("⛔ Image NOT deleted")
        else:
            logger.info("📭 No files in Image folder.")

    # ======================================================
    # FINAL PRODUCTION SUMMARY
    # ======================================================
    print("\n" + "="*40)
    print("📊 FINAL EXECUTION SUMMARY")
    print("="*40)
    if not SUMMARY:
        print("   No actions were performed.")
    else:
        for item in SUMMARY: print(item)
    print("="*40 + "\n")

    # ======================================================
    # SAFE EXIT STRATEGY (GitHub Status Guard)
    # ======================================================
    # If any summary item contains a failure emoji, exit with code 1
    errors_detected = any("❌" in item for item in SUMMARY)
    
    if errors_detected:
        logger.error("🚫 Workflow finished with errors.")
        sys.exit(1)  # GitHub Action will show RED
    else:
        logger.info("✅ Workflow finished successfully.")
        sys.exit(0)  # GitHub Action will show GREEN

if __name__ == "__main__":
    main()
