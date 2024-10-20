import hashlib
import logging
import os
from random import randint
import threading
from time import sleep
from typing import Any, List, Optional, Union, Dict
from datetime import datetime
import requests
import asyncio
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ICONS_DIR = "static/icons"


class DownloadCounter:
    def __init__(self, total):
        self.total = total
        self.current = 0
        self.lock = threading.Lock()

    def increment(self):
        with self.lock:
            self.current += 1
            logger.info(
                f"Downloaded {self.current}/{self.total} icons. {self.total - self.current} remaining."
            )


async def cache_icons_background(
    data_list: List[Dict[str, Any]], data_type: str = "series"
):
    icon_urls = [
        item.get("cover" if data_type == "series" else "stream_icon")
        for item in data_list
        if item.get("cover" if data_type == "series" else "stream_icon")
    ]

    total_icons = len(icon_urls)
    counter = DownloadCounter(total_icons)

    logger.info(f"Starting download of {total_icons} icons")

    with ThreadPoolExecutor(max_workers=10) as executor:
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(executor, cache_icon, icon_url, counter)
            for icon_url in icon_urls
        ]
        await asyncio.gather(*tasks)

    logger.info(f"Finished downloading all {total_icons} icons")


def cache_icon(icon_url: str, counter: DownloadCounter = None) -> str:
    # Generate a unique filename based on the URL
    filename = hashlib.md5(icon_url.encode()).hexdigest() + ".png"
    filepath = os.path.join(ICONS_DIR, filename)

    # If the file doesn't exist, download it
    if not os.path.exists(filepath):
        try:
            response = requests.get(icon_url)
            response.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(response.content)
            sleep_time = randint(3, 5)
            logger.info(
                f"Downloaded icon: {icon_url}, sleeping for {sleep_time} seconds"
            )
            sleep(
                sleep_time
            )  # adding a random sleep here so we don't get banned / limited by poster website
            if counter:
                counter.increment()
        except requests.RequestException as e:
            logger.error(f"Error downloading icon {icon_url}: {e}")
            return None
    elif counter:
        counter.increment()

    return f"/static/icons/{filename}"


def cache_backdrop(backdrop_path: Union[str, List[str]]) -> Optional[str]:
    if not backdrop_path:
        return None

    # If backdrop_path is a list, use the first item
    if isinstance(backdrop_path, list):
        if not backdrop_path:
            return None
        backdrop_url = backdrop_path[0]
    else:
        backdrop_url = backdrop_path

    # Generate a unique filename based on the URL
    filename = hashlib.md5(backdrop_url.encode()).hexdigest() + ".jpg"
    filepath = os.path.join(ICONS_DIR, filename)

    # If the file doesn't exist, download it
    if not os.path.exists(filepath):
        try:
            response = requests.get(backdrop_url)
            response.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(response.content)
            print(f"Downloaded backdrop: {backdrop_url}")
        except requests.RequestException as e:
            print(f"Error downloading backdrop {backdrop_url}: {e}")
            return None

    return f"/static/icons/{filename}"


def calculate_refresh_time(expiry_time: datetime) -> str:
    time_until_refresh = expiry_time - datetime.now()
    hours, remainder = divmod(time_until_refresh.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours} hours and {minutes} minutes"


def format_timestamp(timestamp):
    if isinstance(timestamp, datetime):
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    else:
        return str(timestamp)
