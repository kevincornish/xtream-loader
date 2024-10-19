from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from urllib.parse import quote
import os
import json
import base64
import hashlib
import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, Depends, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from passlib.context import CryptContext
from database import User, get_db


# Load environment variables
load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Ensure the icons directory exists
ICONS_DIR = "static/icons"
os.makedirs(ICONS_DIR, exist_ok=True)

# Authentication settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


# Authentication functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def authenticate_user(db: Session, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        token = request.cookies.get("access_token")
        if not token:
            return None
        try:
            token = token.split()[1]  # Remove "Bearer " prefix
        except IndexError:
            return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        return None
    return user


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class ConnectionInfo(BaseModel):
    base_url: str
    username: str
    password: str


class CachedApiClient:
    CACHE_VERSION = 1

    def __init__(self, cache_file: str = "api_cache.json"):
        self.cache_file = cache_file
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict[str, Any]:
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "r") as f:
                try:
                    cache_data = json.load(f)
                    # Check cache version and update if necessary
                    if cache_data.get("version", 0) < self.CACHE_VERSION:
                        print("Updating cache format...")
                        return {}  # Return empty cache to force refresh

                    for key, value in cache_data.get("data", {}).items():
                        if isinstance(value, dict) and "timestamp" in value:
                            try:
                                value["timestamp"] = datetime.fromisoformat(
                                    value["timestamp"]
                                )
                            except (TypeError, ValueError):
                                # If timestamp can't be parsed, consider the cache entry invalid
                                del cache_data["data"][key]
                    return cache_data.get("data", {})
                except json.JSONDecodeError:
                    print("Cache file is corrupted. Starting with a fresh cache.")
                    return {}
        return {}

    def _save_cache(self):
        with open(self.cache_file, "w") as f:
            json.dump(
                {"version": self.CACHE_VERSION, "data": self.cache},
                f,
                cls=DateTimeEncoder,
            )

    def query_api(
        self,
        connection_info: ConnectionInfo,
        url_path: str,
        force_refresh: bool = False,
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        full_url = f"{connection_info.base_url}{url_path}"
        cache_key = f"{full_url}_{connection_info.username}"

        if not force_refresh and cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if isinstance(cached_data.get("timestamp"), datetime):
                cached_time = cached_data["timestamp"]
                if datetime.now() - cached_time < timedelta(hours=24):
                    print(f"Using cached data for {url_path}")
                    return (
                        cached_data["data"],
                        cached_time,
                        cached_time + timedelta(hours=24),
                    )

        print(f"Fetching data from API for {url_path}")
        response = requests.get(full_url)
        response.raise_for_status()
        data = response.json()
        timestamp = datetime.now()
        self.cache[cache_key] = {"data": data, "timestamp": timestamp}
        self._save_cache()
        return data, timestamp, timestamp + timedelta(hours=24)

    def get_user_info(
        self, connection_info: ConnectionInfo, force_refresh: bool = False
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        return self.query_api(
            connection_info,
            f"/player_api.php?username={connection_info.username}&password={connection_info.password}",
            force_refresh=force_refresh,
        )

    def get_live_category(
        self, connection_info: ConnectionInfo, force_refresh: bool = False
    ) -> Tuple[List[Dict[str, Any]], datetime, datetime]:
        return self.query_api(
            connection_info,
            f"/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_live_categories",
            force_refresh=force_refresh,
        )

    def get_live_streams_by_category(
        self,
        connection_info: ConnectionInfo,
        category_id: int,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        streams, _, _ = self.query_api(
            connection_info,
            f"/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_live_streams&category_id={category_id}",
            force_refresh=force_refresh,
        )

        for stream in streams:
            stream["added_date"] = datetime.fromtimestamp(
                int(stream["added"])
            ).strftime("%Y-%m-%d %H:%M:%S")

            stream["play_link"] = (
                f"{connection_info.base_url}/live/{connection_info.username}/{connection_info.password}/{stream['stream_id']}.ts"
            )

            if stream["stream_icon"]:
                stream["cached_icon"] = cache_icon(stream["stream_icon"])
            else:
                stream["cached_icon"] = None

        return streams

    def get_series_category(
        self, connection_info: ConnectionInfo, force_refresh: bool = False
    ) -> Tuple[List[Dict[str, Any]], datetime, datetime]:
        return self.query_api(
            connection_info,
            f"/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_series_categories",
            force_refresh=force_refresh,
        )

    def get_series_by_category(
        self,
        connection_info: ConnectionInfo,
        category_id: int,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        series, _, _ = self.query_api(
            connection_info,
            f"/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_series&category_id={category_id}",
            force_refresh=force_refresh,
        )

        for show in series:
            try:
                last_modified = parse_datetime(show["last_modified"])
            except ValueError as e:
                print(
                    f"Error parsing last_modified for show {show.get('name', 'Unknown')}: {e}"
                )
                last_modified = datetime.now()  # Use current time as a fallback

            show["added_date"] = last_modified.strftime("%Y-%m-%d %H:%M:%S")
            show["last_modified"] = last_modified.strftime("%Y-%m-%d %H:%M:%S")

            if show["cover"]:
                show["cached_cover"] = cache_icon(show["cover"])
            else:
                show["cached_cover"] = None

            show["episode_run_time"] = show.get("episode_run_time", "N/A")
            show["release_date"] = show.get("releaseDate", "N/A")

        return series

    def get_series_streams_by_series(
        self,
        connection_info: ConnectionInfo,
        series_id: int,
        force_refresh: bool = False,
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        series_info, fetch_time, expiry_time = self.query_api(
            connection_info,
            f"/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_series_info&series_id={series_id}",
            force_refresh=force_refresh,
        )

        for season in series_info.get("episodes", {}).values():
            for episode in season:
                episode["play_link"] = (
                    f"{connection_info.base_url}/series/{connection_info.username}/{connection_info.password}/{episode['id']}.{episode['container_extension']}"
                )

                if "info" in episode:
                    episode["duration"] = episode["info"].get("duration", "N/A")
                    episode["plot"] = episode["info"].get("plot", "No plot available")
                    episode["rating"] = episode["info"].get("rating", "N/A")
                else:
                    episode["duration"] = "N/A"
                    episode["plot"] = "No plot available"
                    episode["rating"] = "N/A"

        return series_info, fetch_time, expiry_time

    def get_film_categories(
        self, connection_info: ConnectionInfo, force_refresh: bool = False
    ) -> Tuple[List[Dict[str, Any]], datetime, datetime]:
        return self.query_api(
            connection_info,
            f"/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_vod_categories",
            force_refresh=force_refresh,
        )

    def get_film_details(
        self,
        connection_info: ConnectionInfo,
        vod_id: int,
        force_refresh: bool = False,
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        return self.query_api(
            connection_info,
            f"/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_vod_info&vod_id={vod_id}",
            force_refresh=force_refresh,
        )

    def get_film_streams_by_category(
        self,
        connection_info: ConnectionInfo,
        category_id: int,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        streams, _, _ = self.query_api(
            connection_info,
            f"/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_vod_streams&category_id={category_id}",
            force_refresh=force_refresh,
        )

        for stream in streams:
            stream["added_date"] = datetime.fromtimestamp(
                int(stream["added"])
            ).strftime("%Y-%m-%d %H:%M:%S")

            stream["play_link"] = (
                f"{connection_info.base_url}/movie/{connection_info.username}/{connection_info.password}/{stream['stream_id']}.{stream['container_extension']}"
            )

            if stream["stream_icon"]:
                stream["cached_icon"] = cache_icon(stream["stream_icon"])
            else:
                stream["cached_icon"] = None

        return streams

    def get_epg_info(
        self, connection_info: ConnectionInfo, stream_id: int
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        epg_info, fetch_time, expiry_time = self.query_api(
            connection_info,
            f"/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_simple_data_table&stream_id={stream_id}",
        )

        epg_info["epg_listings"] = self._process_epg_listings(
            epg_info.get("epg_listings", [])
        )

        return epg_info, fetch_time, expiry_time

    # FIXME: EPG failing on cached results, something todo with the storing and retriving of the base64 data.
    def _process_epg_listings(self, listings):
        processed_listings = []
        for program in listings:
            try:
                processed_program = {
                    "title": (
                        base64.b64decode(program["title"].encode()).decode(
                            "utf-8", errors="replace"
                        )
                        if isinstance(program["title"], str)
                        else program["title"]
                    ),
                    "description": (
                        base64.b64decode(program["description"].encode()).decode(
                            "utf-8", errors="replace"
                        )
                        if isinstance(program["description"], str)
                        else program["description"]
                    ),
                    "start": (
                        datetime.fromtimestamp(int(program["start_timestamp"]))
                        if "start_timestamp" in program
                        else program.get("start")
                    ),
                    "end": (
                        datetime.fromtimestamp(int(program["stop_timestamp"]))
                        if "stop_timestamp" in program
                        else program.get("end")
                    ),
                }
                processed_program.update(
                    {
                        k: v
                        for k, v in program.items()
                        if k
                        not in [
                            "title",
                            "description",
                            "start_timestamp",
                            "stop_timestamp",
                            "start",
                            "end",
                        ]
                    }
                )
                processed_listings.append(processed_program)
            except Exception as e:
                print(f"Error processing program: {e}")
                processed_listings.append(
                    program
                )  # Add the original program data if processing fails
        return processed_listings


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


def parse_datetime(date_value: Union[str, int, float]) -> datetime:
    if isinstance(date_value, (int, float)):
        # It's a timestamp
        return datetime.fromtimestamp(date_value)
    elif isinstance(date_value, str):
        # It's a string, try parsing with different formats
        formats = [
            "%Y-%m-%d %H:%M:%S",  # e.g., "2024-05-31 10:27:57"
            "%Y-%m-%d",  # e.g., "2024-05-31"
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_value, fmt)
            except ValueError:
                continue
        # If all parsing attempts fail, raise an exception
        raise ValueError(f"Unable to parse date string: {date_value}")
    else:
        raise ValueError(f"Unsupported date value type: {type(date_value)}")


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


client = CachedApiClient()

connection_info = ConnectionInfo(
    base_url=os.getenv("API_BASE_URL"),
    username=os.getenv("API_USERNAME"),
    password=os.getenv("API_PASSWORD"),
)


@app.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request,
    current_user: User = Depends(get_current_user),
    force_refresh: bool = Query(False),
    error: str = Query(None),
):
    if error is not None:
        if error == "authfail":
            error = "You need to be admin"
        else:
            error = "something broke"
    user_data, fetch_time, expiry_time = client.get_user_info(
        connection_info, force_refresh
    )
    refresh_time = calculate_refresh_time(expiry_time)
    if not current_user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user_info": user_data["user_info"],
            "server_info": user_data["server_info"],
            "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
            "refresh_time": refresh_time,
            "current_user": current_user,
            "error": error,
        },
    )


@app.get("/streams", response_class=HTMLResponse)
async def streams_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    force_refresh: bool = Query(False),
):
    if not current_user:
        return RedirectResponse(url="/login")
    live_categories, fetch_time, expiry_time = client.get_live_category(
        connection_info, force_refresh
    )
    refresh_time = calculate_refresh_time(expiry_time)

    return templates.TemplateResponse(
        "streams.html",
        {
            "request": request,
            "live_categories": live_categories,
            "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
            "refresh_time": refresh_time,
            "current_user": current_user,
        },
    )


@app.get("/series", response_class=HTMLResponse)
async def series_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    force_refresh: bool = Query(False),
):
    if not current_user:
        return RedirectResponse(url="/login")
    series_categories, fetch_time, expiry_time = client.get_series_category(
        connection_info, force_refresh
    )
    refresh_time = calculate_refresh_time(expiry_time)

    return templates.TemplateResponse(
        "series.html",
        {
            "request": request,
            "series_categories": series_categories,
            "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
            "refresh_time": refresh_time,
            "current_user": current_user,
        },
    )


@app.get("/live-category/{category_id}")
async def get_live_category_streams(
    category_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    force_refresh: bool = False,
):
    if not current_user:
        return RedirectResponse(url="/login")
    streams = client.get_live_streams_by_category(
        connection_info, category_id, force_refresh
    )
    return templates.TemplateResponse(
        "stream_list.html",
        {"request": request, "streams": streams, "current_user": current_user},
    )


@app.get("/series-category/{category_id}")
async def get_series_category_shows(
    category_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    force_refresh: bool = False,
):
    if not current_user:
        return RedirectResponse(url="/login")
    series = client.get_series_by_category(connection_info, category_id, force_refresh)
    return templates.TemplateResponse(
        "series_list.html",
        {"request": request, "series": series, "current_user": current_user},
    )


@app.get("/series/{series_id}", response_class=HTMLResponse)
async def get_series_episodes(
    series_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    force_refresh: bool = Query(False),
):
    if not current_user:
        return RedirectResponse(url="/login")
    series_info, fetch_time, expiry_time = client.get_series_streams_by_series(
        connection_info, series_id, force_refresh
    )
    refresh_time = calculate_refresh_time(expiry_time)

    backdrop_path = series_info["info"].get("backdrop_path")
    series_info["info"]["cached_backdrop"] = cache_backdrop(backdrop_path)

    youtube_trailer = series_info["info"].get("youtube_trailer")
    if youtube_trailer:
        if isinstance(youtube_trailer, list):
            youtube_trailer = youtube_trailer[0] if youtube_trailer else None
        series_info["info"]["youtube_trailer"] = (
            quote(youtube_trailer) if youtube_trailer else None
        )

    return templates.TemplateResponse(
        "series_details.html",
        {
            "request": request,
            "series_info": series_info,
            "series_id": series_id,
            "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
            "refresh_time": refresh_time,
            "current_user": current_user,
        },
    )


@app.get("/films", response_class=HTMLResponse)
async def film_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    force_refresh: bool = Query(False),
):
    if not current_user:
        return RedirectResponse(url="/login")
    film_categories, fetch_time, expiry_time = client.get_film_categories(
        connection_info, force_refresh
    )
    refresh_time = calculate_refresh_time(expiry_time)

    return templates.TemplateResponse(
        "films.html",
        {
            "request": request,
            "film_categories": film_categories,
            "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
            "refresh_time": refresh_time,
            "current_user": current_user,
        },
    )


@app.get("/film-category/{category_id}")
async def get_film_category_streams(
    category_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    force_refresh: bool = False,
):
    if not current_user:
        return RedirectResponse(url="/login")
    streams = client.get_film_streams_by_category(
        connection_info, category_id, force_refresh
    )
    return templates.TemplateResponse(
        "film_list.html",
        {"request": request, "streams": streams, "current_user": current_user},
    )


@app.get("/film/{vod_id}", response_class=HTMLResponse)
async def get_film_details(
    vod_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    force_refresh: bool = Query(False),
):
    if not current_user:
        return RedirectResponse(url="/login")
    film_info, fetch_time, expiry_time = client.get_film_details(
        connection_info, vod_id, force_refresh
    )
    refresh_time = calculate_refresh_time(expiry_time)

    backdrop_path = film_info["info"].get("backdrop_path")
    film_info["info"]["cached_backdrop"] = cache_backdrop(backdrop_path)

    youtube_trailer = film_info["info"].get("youtube_trailer")
    if youtube_trailer:
        film_info["info"]["youtube_trailer"] = quote(youtube_trailer)

    film_info["play_link"] = (
        f"{connection_info.base_url}/movie/{connection_info.username}/{connection_info.password}/{film_info['movie_data']['stream_id']}.{film_info['movie_data']['container_extension']}"
    )

    return templates.TemplateResponse(
        "film_details.html",
        {
            "request": request,
            "film_info": film_info,
            "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
            "refresh_time": refresh_time,
            "connection_info": connection_info,
            "current_user": current_user,
        },
    )


@app.get("/epg/{stream_id}")
async def get_epg(
    stream_id: int, request: Request, current_user: User = Depends(get_current_user)
):
    if not current_user:
        return RedirectResponse(url="/login")
    epg_info, _, _ = client.get_epg_info(connection_info, stream_id)
    return epg_info


@app.get("/epg_page/{stream_id}", response_class=HTMLResponse)
async def get_epg_page(
    stream_id: int, request: Request, current_user: User = Depends(get_current_user)
):
    if not current_user:
        return RedirectResponse(url="/login")
    try:
        epg_info, fetch_time, expiry_time = client.get_epg_info(
            connection_info, stream_id
        )
    except Exception as e:
        print(f"Error fetching EPG info: {str(e)}")
        epg_info = {"error": f"Failed to fetch EPG info: {str(e)}"}
        fetch_time = datetime.now()
        expiry_time = fetch_time

    return templates.TemplateResponse(
        "epg_info.html",
        {
            "request": request,
            "epg_info": epg_info,
            "stream_id": stream_id,
            "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
            "refresh_time": calculate_refresh_time(expiry_time),
            "format_timestamp": format_timestamp,
            "current_user": current_user,
        },
    )


# FIXME: support for mkv, avi etc
@app.get("/stream/{type}/{id}")
async def stream_video(
    type: str, id: str, request: Request, current_user: User = Depends(get_current_user)
):
    if not current_user:
        return RedirectResponse(url="/login")
    if type not in ["episode", "film"]:
        raise HTTPException(status_code=400, detail="Invalid stream type")

    if type == "episode":
        series_id, episode_id = id.split("_")
        series_info, _, _ = client.get_series_streams_by_series(
            connection_info, int(series_id)
        )
        episode = next(
            (
                ep
                for season in series_info["episodes"].values()
                for ep in season
                if ep["id"] == episode_id
            ),
            None,
        )
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")
        play_link = episode["play_link"]
        title = f"{series_info['info']['name']} - Episode {episode['episode_num']}"
    else:
        film_info, _, _ = client.get_film_details(connection_info, int(id))
        play_link = film_info["play_link"]
        title = film_info["info"]["name"]

    return templates.TemplateResponse(
        "video_player.html",
        {
            "request": request,
            "play_link": play_link,
            "title": title,
            "current_user": current_user,
        },
    )


@app.get("/empty")
async def empty_content():
    return ""


# Login and logout routes
@app.post("/token")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Incorrect username or password"},
            status_code=400,
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="access_token", value=f"Bearer {access_token}", httponly=True
    )
    return response


@app.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login")
    response.delete_cookie("access_token")
    return response


# Login page
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# Admin routes
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")
    if not current_user.is_admin:
        return RedirectResponse(url="/?error=authfail")
    users = db.query(User).all()
    return templates.TemplateResponse(
        "admin.html", {"request": request, "users": users, "current_user": current_user}
    )


@app.post("/admin/add_user")
async def add_user(
    username: str = Form(...),
    password: str = Form(...),
    is_admin: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse(url="/login")
    if not current_user.is_admin:
        return RedirectResponse(url="/?error=authfail")
    db_user = User(
        username=username,
        hashed_password=get_password_hash(password),
        is_admin=is_admin,
    )
    db.add(db_user)
    db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/delete_user/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse(url="/login")
    if not current_user.is_admin:
        return RedirectResponse(url="/?error=authfail")
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        db.delete(user)
        db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
