import os
import json
import time
import logging
import sys
from collections import defaultdict
from dotenv import load_dotenv

# Core Modules
from core.retry_manager import SmartRetry
from core.verifier import MediaVerifier

# Project Modules
from modules.dropbox_handler import DropboxHandler
from modules.caption_generator import CaptionGenerator
from modules.utils import setup_logging

# Platform Classes
from platforms.instagram import InstagramPoster
from platforms.facebook import FacebookPoster
from platforms.threads import ThreadsPoster
from platforms.twitter import TwitterPoster
from platforms.telegram import TelegramPoster
from platforms.discord import DiscordPoster
from platforms.tumblr import TumblrPoster


# ============================================
# INIT
# ============================================

load_dotenv()
logger = setup_logging()

PLATFORM_RESULTS = defaultdict(lambda: {
    "success": 0,
    "failed": 0,
    "skipped": 0
})


# ============================================
# CAPTION BUILDER (Non-Tumblr Platforms)
# ============================================

def build_caption(payload, platform_name):
    if isinstance(payload, dict):
        text = str(payload.get("text", "")).strip()
        brand = str(payload.get("brand_tag", "")).strip()
        tags = payload.get("tags", [])

        limits = {"instagram": 4, "facebook": 4, "twitter": 3}
        tag_limit = limits.get(platform_name, 4)

        if isinstance(tags, str):
            tags = tags.split(",") if "," in tags else tags.split()

        tag_string = " ".join([f"#{str(t).lstrip('#')}" for t in tags[:tag_limit]])

        return f"{text}\n\n{tag_string}\n\n{brand}".strip()

    return str(payload)

def safe_trim_caption(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text

    logger.warning(f"Caption trimmed to {limit} characters")
    return text[:limit].rsplit(" ", 1)[0]


# ============================================
# SAFE POST WRAPPER
# ============================================

def safe_post(platform_name, platform_obj, method_name,
              file_arg, caption, retry_engine,
              local_path, media_type):

    # Media verification
    is_safe, msg = MediaVerifier.verify(local_path, platform_name, media_type)

    if not is_safe:
        logger.warning(f"{platform_name.upper()} skipped: {msg}")
        PLATFORM_RESULTS[platform_name]["skipped"] += 1
        return False

    try:
        logger.info(f"{platform_name.upper()} uploading...")

        method = getattr(platform_obj, method_name)

        result = retry_engine.execute(method, file_arg, caption)

        if result is True:
            PLATFORM_RESULTS[platform_name]["success"] += 1
            logger.info(f"{platform_name.upper()} success")
            return True

        else:
            PLATFORM_RESULTS[platform_name]["failed"] += 1
            logger.error(f"{platform_name.upper()} failed (API returned False)")
            return False

    except Exception as e:
        PLATFORM_RESULTS[platform_name]["failed"] += 1
        logger.exception(f"{platform_name.upper()} exception: {str(e)}")
        return False


# ============================================
# FINAL SUMMARY
# ============================================

def print_final_summary(enabled_platforms, total_platforms, dbx, platforms):

    total_success = sum(d["success"] for d in PLATFORM_RESULTS.values())
    total_failed = sum(d["failed"] for d in PLATFORM_RESULTS.values())
    total_skipped = sum(d["skipped"] for d in PLATFORM_RESULTS.values())

    dropbox_stats = dbx.get_folder_stats()

    summary_lines = []
    summary_lines.append("=" * 60)
    summary_lines.append("UNIVERSAL WORKFLOW FINAL SUMMARY")
    summary_lines.append("=" * 60)
    summary_lines.append(f"Enabled Platforms : {len(enabled_platforms)}")
    summary_lines.append(f"Disabled Platforms: {total_platforms - len(enabled_platforms)}")
    summary_lines.append("-" * 60)
    summary_lines.append(f"Total Success     : {total_success}")
    summary_lines.append(f"Total Failed      : {total_failed}")
    summary_lines.append(f"Total Skipped     : {total_skipped}")
    summary_lines.append("=" * 60)

    for name in enabled_platforms:
        data = PLATFORM_RESULTS[name]
        summary_lines.append(
            f"{name.upper():10} -> "
            f"S:{data['success']} | "
            f"F:{data['failed']} | "
            f"SK:{data['skipped']}"
        )

    summary_lines.append("=" * 60)
    summary_lines.append("DROPBOX REMAINING FILES")
    summary_lines.append("-" * 60)
    summary_lines.append(f"IG Videos       : {dropbox_stats['video_ig']}")
    summary_lines.append(f"General Videos  : {dropbox_stats['video_general']}")
    summary_lines.append(f"Images          : {dropbox_stats['images']}")
    summary_lines.append("-" * 60)
    summary_lines.append(f"TOTAL FILES     : {dropbox_stats['total']}")
    summary_lines.append("=" * 60)

    final_summary = "\n".join(summary_lines)

    logger.info("\n" + final_summary)

    

    # Cron-safe exit
    if total_success == 0 and total_failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)

# MAIN WORKFLOW
# ============================================

def main():

    logger.info("=" * 50)
    logger.info("UNIVERSAL ROTATING WORKFLOW STARTED")
    logger.info("=" * 50)

    config = json.load(open("config.json", "r"))

    dbx = DropboxHandler(config["dropbox"])
    ai = CaptionGenerator(config)
    p_conf = config["platforms"]

    retry_engine = SmartRetry(
        max_attempts=config["settings"].get("retry_count", 3)
    )

    delay = config["settings"].get("post_delay", 10)

    mapping = {
        "instagram": InstagramPoster,
        "facebook": FacebookPoster,
        "threads": ThreadsPoster,
        "twitter": TwitterPoster,
        "telegram": TelegramPoster,
        "discord": DiscordPoster,
        "tumblr": TumblrPoster,
    }

    total_platforms = len(mapping)

    platforms = {
        name: cls()
        for name, cls in mapping.items()
        if p_conf.get(name, {}).get("enabled")
    }

    enabled_names = list(platforms.keys())

    sources = [
        {"id": "ig", "flag": "upload_from_ig", "media": "video", "cap": "instagram"},
        {"id": "general", "flag": "upload_from_general", "media": "video", "cap": "general_video"},
        {"id": "image", "flag": "upload_from_images", "media": "image", "cap": "image"},
    ]

    for src in sources:

        file = dbx.get_file(src["id"])

        targets = [
            p for p in platforms
            if p_conf[p].get(src["flag"])
        ]

        if not file or not targets:
            continue

        logger.info(f"\nProcessing {src['id'].upper()} → {file.name}")

        local_path = dbx.download_file(file)
        public_url = dbx.get_temp_link(file)

        caption_payload = ai.generate(file.name, src["cap"])

        file_failed = False

        for p_name in targets:

            method = "post_video" if src["media"] == "video" else "post_image"

            # Tumblr handles caption internally
            if p_name == "tumblr":
                final_caption = caption_payload
            else:
                limit = p_conf[p_name].get("limit", 2000)
                formatted = build_caption(caption_payload, p_name)
                final_caption = safe_trim_caption(formatted, limit)

            posted = False

            # URL-first platforms
            if p_name in ["instagram", "threads"]:
                posted = safe_post(
                    p_name,
                    platforms[p_name],
                    method,
                    public_url,
                    final_caption,
                    retry_engine,
                    local_path,
                    src["media"]
                )

            # Fallback or normal platforms
            if not posted:
                result = safe_post(
                    p_name,
                    platforms[p_name],
                    method,
                    local_path,
                    final_caption,
                    retry_engine,
                    local_path,
                    src["media"]
                )

                if not result:
                    file_failed = True

            time.sleep(delay)

        if os.path.exists(local_path):
            os.remove(local_path)

        if not file_failed:
            dbx.delete_file(file)
            logger.info("Dropbox file deleted (all targets success)")
        else:
            dbx.move_to_failed(file, src["id"])
            logger.warning("File moved to failed folder due to upload failures")

    print_final_summary(enabled_names, total_platforms, dbx, platforms)



if __name__ == "__main__":
    main()


