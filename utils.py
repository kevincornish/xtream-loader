import hashlib
import os
from typing import List, Optional, Union
from datetime import datetime

import requests


ICONS_DIR = "static/icons"


def cache_icon(icon_url: str) -> str:
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
            print(f"Downloaded icon: {icon_url}")
        except requests.RequestException as e:
            print(f"Error downloading icon {icon_url}: {e}")
            return None

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
