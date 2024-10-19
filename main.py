from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from urllib.parse import quote
import os
import base64
import hashlib
import logging
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
from database import (
    FilmCategory,
    LiveChannel,
    Series,
    SeriesCategory,
    SeriesEpisode,
    User,
    RefreshData,
    UserInfo,
    get_db,
    LiveCategory,
    FilmStream,
    FilmDetail,
    EpgListing,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


class ConnectionInfo(BaseModel):
    base_url: str
    username: str
    password: str


class CachedApiClient:
    def __init__(self):
        pass

    def query_api(
        self,
        connection_info: ConnectionInfo,
        url_path: str,
        force_refresh: bool = False,
        db: Session = None,
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        full_url = f"{connection_info.base_url}{url_path}"

        if "player_api.php?username=" in url_path and "action=" not in url_path:
            # This is a user_info request, use database
            return self._get_user_info_from_db(connection_info, force_refresh, db)

        print(f"Fetching data from API for {url_path}")
        response = requests.get(full_url)
        response.raise_for_status()
        data = response.json()
        timestamp = datetime.now()
        return data, timestamp, timestamp + timedelta(hours=24)

    def get_user_info(
        self,
        connection_info: ConnectionInfo,
        force_refresh: bool = False,
        db: Session = Depends(get_db),
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        refresh_data = (
            db.query(RefreshData).filter(RefreshData.data_type == "user_info").first()
        )
        user_info = db.query(UserInfo).first()

        if (
            force_refresh
            or not refresh_data
            or not user_info
            or datetime.utcnow() - refresh_data.last_refresh > timedelta(hours=24)
        ):
            # Fetch data from API
            url = f"{connection_info.base_url}/player_api.php?username={connection_info.username}&password={connection_info.password}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # Update or create UserInfo
            if not user_info:
                user_info = UserInfo()

            user_info.username = data["user_info"]["username"]
            user_info.password = data["user_info"]["password"]
            user_info.message = data["user_info"]["message"]
            user_info.auth = data["user_info"]["auth"]
            user_info.status = data["user_info"]["status"]
            user_info.exp_date = data["user_info"]["exp_date"]
            user_info.is_trial = data["user_info"]["is_trial"]
            user_info.active_cons = data["user_info"]["active_cons"]
            user_info.created_at = data["user_info"]["created_at"]
            user_info.max_connections = data["user_info"]["max_connections"]
            user_info.allowed_output_formats = data["user_info"][
                "allowed_output_formats"
            ]

            user_info.server_url = data["server_info"]["url"]
            user_info.server_port = data["server_info"]["port"]
            user_info.server_https_port = data["server_info"]["https_port"]
            user_info.server_protocol = data["server_info"]["server_protocol"]
            user_info.server_rtmp_port = data["server_info"]["rtmp_port"]
            user_info.server_timezone = data["server_info"]["timezone"]
            user_info.server_timestamp_now = data["server_info"]["timestamp_now"]
            user_info.server_time_now = data["server_info"]["time_now"]

            db.add(user_info)

            # Update or create RefreshData
            if not refresh_data:
                refresh_data = RefreshData(data_type="user_info")
            refresh_data.last_refresh = datetime.utcnow()
            db.add(refresh_data)

            db.commit()
            db.refresh(user_info)
            db.refresh(refresh_data)

        # Convert UserInfo object to dictionary
        user_info_dict = {
            "user_info": {
                "username": user_info.username,
                "password": user_info.password,
                "message": user_info.message,
                "auth": user_info.auth,
                "status": user_info.status,
                "exp_date": user_info.exp_date,
                "is_trial": user_info.is_trial,
                "active_cons": user_info.active_cons,
                "created_at": user_info.created_at,
                "max_connections": user_info.max_connections,
                "allowed_output_formats": user_info.allowed_output_formats,
            },
            "server_info": {
                "url": user_info.server_url,
                "port": user_info.server_port,
                "https_port": user_info.server_https_port,
                "server_protocol": user_info.server_protocol,
                "rtmp_port": user_info.server_rtmp_port,
                "timezone": user_info.server_timezone,
                "timestamp_now": user_info.server_timestamp_now,
                "time_now": user_info.server_time_now,
            },
        }

        return (
            user_info_dict,
            refresh_data.last_refresh,
            refresh_data.last_refresh + timedelta(hours=24),
        )

    def _get_user_info_from_db(
        self, connection_info: ConnectionInfo, force_refresh: bool, db: Session
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        refresh_data = (
            db.query(RefreshData).filter(RefreshData.data_type == "user_info").first()
        )
        user_info = db.query(UserInfo).first()

        if (
            force_refresh
            or not refresh_data
            or not user_info
            or datetime.utcnow() - refresh_data.last_refresh > timedelta(hours=24)
        ):
            # Fetch data from API
            url = f"{connection_info.base_url}/player_api.php?username={connection_info.username}&password={connection_info.password}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # Update or create UserInfo
            if not user_info:
                user_info = UserInfo()

            # Update user_info fields
            user_info.username = data["user_info"]["username"]
            user_info.password = data["user_info"]["password"]
            user_info.message = data["user_info"]["message"]
            user_info.auth = data["user_info"]["auth"]
            user_info.status = data["user_info"]["status"]
            user_info.exp_date = data["user_info"]["exp_date"]
            user_info.is_trial = data["user_info"]["is_trial"]
            user_info.active_cons = data["user_info"]["active_cons"]
            user_info.created_at = data["user_info"]["created_at"]
            user_info.max_connections = data["user_info"]["max_connections"]
            user_info.allowed_output_formats = data["user_info"][
                "allowed_output_formats"
            ]

            # Update server_info fields
            user_info.server_url = data["server_info"]["url"]
            user_info.server_port = data["server_info"]["port"]
            user_info.server_https_port = data["server_info"]["https_port"]
            user_info.server_protocol = data["server_info"]["server_protocol"]
            user_info.server_rtmp_port = data["server_info"]["rtmp_port"]
            user_info.server_timezone = data["server_info"]["timezone"]
            user_info.server_timestamp_now = data["server_info"]["timestamp_now"]
            user_info.server_time_now = data["server_info"]["time_now"]

            db.add(user_info)

            # Update or create RefreshData
            if not refresh_data:
                refresh_data = RefreshData(data_type="user_info")
            refresh_data.last_refresh = datetime.utcnow()
            db.add(refresh_data)

            db.commit()
            db.refresh(user_info)
            db.refresh(refresh_data)

        # Convert UserInfo object to dictionary
        user_info_dict = {
            "user_info": {
                "username": user_info.username,
                "password": user_info.password,
                "message": user_info.message,
                "auth": user_info.auth,
                "status": user_info.status,
                "exp_date": user_info.exp_date,
                "is_trial": user_info.is_trial,
                "active_cons": user_info.active_cons,
                "created_at": user_info.created_at,
                "max_connections": user_info.max_connections,
                "allowed_output_formats": user_info.allowed_output_formats,
            },
            "server_info": {
                "url": user_info.server_url,
                "port": user_info.server_port,
                "https_port": user_info.server_https_port,
                "server_protocol": user_info.server_protocol,
                "rtmp_port": user_info.server_rtmp_port,
                "timezone": user_info.server_timezone,
                "timestamp_now": user_info.server_timestamp_now,
                "time_now": user_info.server_time_now,
            },
        }

        return (
            user_info_dict,
            refresh_data.last_refresh,
            refresh_data.last_refresh + timedelta(hours=24),
        )

    def get_live_category(
        self,
        connection_info: ConnectionInfo,
        force_refresh: bool = False,
        db: Session = None,
    ) -> Tuple[List[Dict[str, Any]], datetime, datetime]:
        return self._get_live_categories_from_db(connection_info, force_refresh, db)

    def _get_live_categories_from_db(
        self, connection_info: ConnectionInfo, force_refresh: bool, db: Session
    ) -> Tuple[List[Dict[str, Any]], datetime, datetime]:
        refresh_data = (
            db.query(RefreshData)
            .filter(RefreshData.data_type == "live_categories")
            .first()
        )

        if (
            force_refresh
            or not refresh_data
            or datetime.utcnow() - refresh_data.last_refresh > timedelta(hours=24)
        ):
            # Fetch data from API
            url = f"{connection_info.base_url}/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_live_categories"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # Clear existing live categories
            db.query(LiveCategory).delete()

            # Add new live categories
            for category in data:
                new_category = LiveCategory(
                    category_id=category["category_id"],
                    category_name=category["category_name"],
                    parent_id=category["parent_id"],
                )
                db.add(new_category)

            # Update or create RefreshData
            if not refresh_data:
                refresh_data = RefreshData(data_type="live_categories")
            refresh_data.last_refresh = datetime.utcnow()
            db.add(refresh_data)

            db.commit()
            db.refresh(refresh_data)

        # Fetch live categories from database
        live_categories = db.query(LiveCategory).all()

        # Convert LiveCategory objects to dictionary
        live_categories_list = [
            {
                "category_id": category.category_id,
                "category_name": category.category_name,
                "parent_id": category.parent_id,
            }
            for category in live_categories
        ]

        return (
            live_categories_list,
            refresh_data.last_refresh,
            refresh_data.last_refresh + timedelta(hours=24),
        )

    def get_live_streams_by_category(
        self,
        connection_info: ConnectionInfo,
        category_id: int,
        force_refresh: bool = False,
        db: Session = None,
    ) -> List[Dict[str, Any]]:
        return self._get_live_channels_from_db(
            connection_info, category_id, force_refresh, db
        )

    def _get_live_channels_from_db(
        self,
        connection_info: ConnectionInfo,
        category_id: int,
        force_refresh: bool,
        db: Session,
    ) -> List[Dict[str, Any]]:
        refresh_data = (
            db.query(RefreshData)
            .filter(RefreshData.data_type == f"live_channels_{category_id}")
            .first()
        )

        if (
            force_refresh
            or not refresh_data
            or datetime.utcnow() - refresh_data.last_refresh > timedelta(hours=24)
        ):
            # Fetch data from API
            url = f"{connection_info.base_url}/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_live_streams&category_id={category_id}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # Clear existing live channels for this category
            db.query(LiveChannel).filter(
                LiveChannel.category_id == str(category_id)
            ).delete()

            # Add new live channels
            for channel in data:
                new_channel = LiveChannel(
                    num=channel["num"],
                    name=channel["name"],
                    stream_type=channel["stream_type"],
                    stream_id=channel["stream_id"],
                    stream_icon=channel["stream_icon"],
                    epg_channel_id=channel.get("epg_channel_id", ""),
                    added=channel["added"],
                    category_id=str(category_id),
                    custom_sid=channel.get("custom_sid", ""),
                    tv_archive=channel.get("tv_archive", 0),
                    direct_source=channel.get("direct_source", ""),
                    tv_archive_duration=channel.get("tv_archive_duration", 0),
                )
                db.add(new_channel)

            # Update or create RefreshData
            if not refresh_data:
                refresh_data = RefreshData(data_type=f"live_channels_{category_id}")
            refresh_data.last_refresh = datetime.utcnow()
            db.add(refresh_data)

            db.commit()

        # Fetch live channels from database
        live_channels = (
            db.query(LiveChannel)
            .filter(LiveChannel.category_id == str(category_id))
            .all()
        )

        # Convert LiveChannel objects to dictionary and add computed fields
        live_channels_list = []
        for channel in live_channels:
            channel_dict = {
                "num": channel.num,
                "name": channel.name,
                "stream_type": channel.stream_type,
                "stream_id": channel.stream_id,
                "stream_icon": channel.stream_icon,
                "epg_channel_id": channel.epg_channel_id,
                "added": channel.added,
                "category_id": channel.category_id,
                "custom_sid": channel.custom_sid,
                "tv_archive": channel.tv_archive,
                "direct_source": channel.direct_source,
                "tv_archive_duration": channel.tv_archive_duration,
                "added_date": datetime.fromtimestamp(int(channel.added)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "play_link": f"{connection_info.base_url}/live/{connection_info.username}/{connection_info.password}/{channel.stream_id}.ts",
                "cached_icon": cache_icon(channel.stream_icon),
            }
            live_channels_list.append(channel_dict)

        return live_channels_list

    def get_series_category(
        self,
        connection_info: ConnectionInfo,
        force_refresh: bool = False,
        db: Session = None,
    ) -> Tuple[List[Dict[str, Any]], datetime, datetime]:
        return self._get_series_categories_from_db(connection_info, force_refresh, db)

    def _get_series_categories_from_db(
        self, connection_info: ConnectionInfo, force_refresh: bool, db: Session
    ) -> Tuple[List[Dict[str, Any]], datetime, datetime]:
        refresh_data = (
            db.query(RefreshData)
            .filter(RefreshData.data_type == "series_categories")
            .first()
        )

        if (
            force_refresh
            or not refresh_data
            or datetime.utcnow() - refresh_data.last_refresh > timedelta(hours=24)
        ):
            # Fetch data from API
            url = f"{connection_info.base_url}/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_series_categories"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # Clear existing series categories
            db.query(SeriesCategory).delete()

            # Add new series categories
            for category in data:
                new_category = SeriesCategory(
                    category_id=category["category_id"],
                    category_name=category["category_name"],
                    parent_id=category["parent_id"],
                )
                db.add(new_category)

            # Update or create RefreshData
            if not refresh_data:
                refresh_data = RefreshData(data_type="series_categories")
            refresh_data.last_refresh = datetime.utcnow()
            db.add(refresh_data)

            db.commit()
            db.refresh(refresh_data)

        # Fetch series categories from database
        series_categories = db.query(SeriesCategory).all()

        # Convert SeriesCategory objects to dictionary
        series_categories_list = [
            {
                "category_id": category.category_id,
                "category_name": category.category_name,
                "parent_id": category.parent_id,
            }
            for category in series_categories
        ]

        return (
            series_categories_list,
            refresh_data.last_refresh,
            refresh_data.last_refresh + timedelta(hours=24),
        )

    def get_series_by_category(
        self,
        connection_info: ConnectionInfo,
        category_id: int,
        force_refresh: bool = False,
        db: Session = None,
    ) -> List[Dict[str, Any]]:
        return self._get_series_from_db(connection_info, category_id, force_refresh, db)

    def _get_series_from_db(
        self,
        connection_info: ConnectionInfo,
        category_id: int,
        force_refresh: bool,
        db: Session,
    ) -> List[Dict[str, Any]]:
        refresh_data = (
            db.query(RefreshData)
            .filter(RefreshData.data_type == f"series_{category_id}")
            .first()
        )

        if (
            force_refresh
            or not refresh_data
            or datetime.utcnow() - refresh_data.last_refresh > timedelta(hours=24)
        ):
            # Fetch data from API
            url = f"{connection_info.base_url}/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_series&category_id={category_id}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # Clear existing series for this category
            db.query(Series).filter(Series.category_id == str(category_id)).delete()

            # Add new series
            for series in data:
                new_series = Series(
                    series_id=series["series_id"],
                    name=series["name"],
                    cover=series["cover"],
                    plot=series["plot"],
                    cast=series["cast"],
                    director=series["director"],
                    genre=series["genre"],
                    release_date=series["releaseDate"],
                    last_modified=series["last_modified"],
                    rating=series["rating"],
                    rating_5based=series["rating_5based"],
                    backdrop_path=series["backdrop_path"],
                    youtube_trailer=series["youtube_trailer"],
                    episode_run_time=series["episode_run_time"],
                    category_id=str(category_id),
                )
                db.add(new_series)

            # Update or create RefreshData
            if not refresh_data:
                refresh_data = RefreshData(data_type=f"series_{category_id}")
            refresh_data.last_refresh = datetime.utcnow()
            db.add(refresh_data)

            db.commit()

        # Fetch series from database
        series_list = (
            db.query(Series).filter(Series.category_id == str(category_id)).all()
        )

        # Convert Series objects to dictionary and add computed fields
        series_data = []
        for series in series_list:
            series_dict = {
                "num": 1,  # This field is not in the database, so we're setting a default value
                "name": series.name,
                "series_id": series.series_id,
                "cover": series.cover,
                "plot": series.plot,
                "cast": series.cast,
                "director": series.director,
                "genre": series.genre,
                "releaseDate": series.release_date,
                "last_modified": series.last_modified,
                "rating": series.rating,
                "rating_5based": series.rating_5based,
                "backdrop_path": series.backdrop_path,
                "youtube_trailer": series.youtube_trailer,
                "episode_run_time": series.episode_run_time,
                "category_id": series.category_id,
                "added_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cached_cover": cache_icon(series.cover),
                "release_date": series.release_date,
            }
            series_data.append(series_dict)

        return series_data

    def get_series_streams_by_series(
        self,
        connection_info: ConnectionInfo,
        series_id: int,
        force_refresh: bool = False,
        db: Session = None,
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        if db is None:
            logger.error("Database session is None in get_series_streams_by_series")
            raise HTTPException(status_code=500, detail="Database session error")
        return self._get_series_streams_from_db(
            connection_info, series_id, force_refresh, db
        )

    def _get_series_streams_from_db(
        self,
        connection_info: ConnectionInfo,
        series_id: int,
        force_refresh: bool,
        db: Session,
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        refresh_data = (
            db.query(RefreshData)
            .filter(RefreshData.data_type == f"series_streams_{series_id}")
            .first()
        )

        if (
            force_refresh
            or not refresh_data
            or datetime.utcnow() - refresh_data.last_refresh > timedelta(hours=24)
        ):
            # Fetch data from API
            url = f"{connection_info.base_url}/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_series_info&series_id={series_id}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # Clear existing episodes for this series
            db.query(SeriesEpisode).filter(
                SeriesEpisode.series_id == series_id
            ).delete()

            # Add new episodes
            for season, episodes in data.get("episodes", {}).items():
                for episode in episodes:
                    new_episode = SeriesEpisode(
                        series_id=series_id,
                        season=int(season),
                        episode=episode["episode_num"],
                        title=episode["title"],
                        container_extension=episode["container_extension"],
                        plot=episode.get("plot", ""),
                        duration=episode.get("duration", ""),
                        rating=episode.get("rating", 0.0),
                        info=episode.get("info", {}),
                    )
                    db.add(new_episode)

            # Update series info
            series = db.query(Series).filter(Series.series_id == series_id).first()
            if series:
                series.name = data["info"]["name"]
                series.cover = data["info"]["cover"]
                series.plot = data["info"]["plot"]
                series.cast = data["info"]["cast"]
                series.director = data["info"]["director"]
                series.genre = data["info"]["genre"]
                series.release_date = data["info"]["releaseDate"]
                series.last_modified = data["info"]["last_modified"]
                series.rating = data["info"]["rating"]
                series.rating_5based = data["info"]["rating_5based"]
                series.backdrop_path = data["info"]["backdrop_path"]
                series.youtube_trailer = data["info"].get("youtube_trailer", "")
                series.episode_run_time = data["info"]["episode_run_time"]
                db.add(series)

            # Update or create RefreshData
            if not refresh_data:
                refresh_data = RefreshData(data_type=f"series_streams_{series_id}")
            refresh_data.last_refresh = datetime.utcnow()
            db.add(refresh_data)

            db.commit()

        # Fetch series and episodes from database
        series = db.query(Series).filter(Series.series_id == series_id).first()
        episodes = (
            db.query(SeriesEpisode).filter(SeriesEpisode.series_id == series_id).all()
        )

        # Convert to dictionary
        series_info = {
            "seasons": {},  # You might want to add seasons information if available
            "info": {
                "name": series.name,
                "cover": series.cover,
                "plot": series.plot,
                "cast": series.cast,
                "director": series.director,
                "genre": series.genre,
                "releaseDate": series.release_date,
                "last_modified": series.last_modified,
                "rating": series.rating,
                "rating_5based": series.rating_5based,
                "backdrop_path": series.backdrop_path,
                "youtube_trailer": series.youtube_trailer,
                "episode_run_time": series.episode_run_time,
                "category_id": series.category_id,
            },
            "episodes": {},
        }

        for episode in episodes:
            if episode.season not in series_info["episodes"]:
                series_info["episodes"][episode.season] = []

            episode_dict = {
                "id": str(episode.id),
                "episode_num": episode.episode,
                "title": episode.title,
                "container_extension": episode.container_extension,
                "plot": episode.plot,
                "duration": episode.duration,
                "rating": episode.rating,
                "info": episode.info,
            }
            episode_dict["play_link"] = (
                f"{connection_info.base_url}/series/{connection_info.username}/{connection_info.password}/{episode_dict['id']}.{episode_dict['container_extension']}"
            )

            series_info["episodes"][episode.season].append(episode_dict)

        return (
            series_info,
            refresh_data.last_refresh,
            refresh_data.last_refresh + timedelta(hours=24),
        )

    def get_film_categories(
        self,
        connection_info: ConnectionInfo,
        force_refresh: bool = False,
        db: Session = None,
    ) -> Tuple[List[Dict[str, Any]], datetime, datetime]:
        return self._get_film_categories_from_db(connection_info, force_refresh, db)

    def _get_film_categories_from_db(
        self, connection_info: ConnectionInfo, force_refresh: bool, db: Session
    ) -> Tuple[List[Dict[str, Any]], datetime, datetime]:
        refresh_data = (
            db.query(RefreshData)
            .filter(RefreshData.data_type == "film_categories")
            .first()
        )

        if (
            force_refresh
            or not refresh_data
            or datetime.utcnow() - refresh_data.last_refresh > timedelta(hours=24)
        ):
            # Fetch data from API
            url = f"{connection_info.base_url}/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_vod_categories"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # Clear existing film categories
            db.query(FilmCategory).delete()

            # Add new film categories
            for category in data:
                new_category = FilmCategory(
                    category_id=category["category_id"],
                    category_name=category["category_name"],
                    parent_id=category["parent_id"],
                )
                db.add(new_category)

            # Update or create RefreshData
            if not refresh_data:
                refresh_data = RefreshData(data_type="film_categories")
            refresh_data.last_refresh = datetime.utcnow()
            db.add(refresh_data)

            db.commit()
            db.refresh(refresh_data)

        # Fetch film categories from database
        film_categories = db.query(FilmCategory).all()

        # Convert FilmCategory objects to dictionary
        film_categories_list = [
            {
                "category_id": category.category_id,
                "category_name": category.category_name,
                "parent_id": category.parent_id,
            }
            for category in film_categories
        ]

        return (
            film_categories_list,
            refresh_data.last_refresh,
            refresh_data.last_refresh + timedelta(hours=24),
        )

    def get_film_streams_by_category(
        self,
        connection_info: ConnectionInfo,
        category_id: int,
        force_refresh: bool = False,
        db: Session = None,
    ) -> List[Dict[str, Any]]:
        return self._get_film_streams_from_db(
            connection_info, category_id, force_refresh, db
        )

    def _get_film_streams_from_db(
        self,
        connection_info: ConnectionInfo,
        category_id: int,
        force_refresh: bool,
        db: Session,
    ) -> List[Dict[str, Any]]:
        refresh_data = (
            db.query(RefreshData)
            .filter(RefreshData.data_type == f"film_streams_{category_id}")
            .first()
        )

        if (
            force_refresh
            or not refresh_data
            or datetime.utcnow() - refresh_data.last_refresh > timedelta(hours=24)
        ):
            # Fetch data from API
            url = f"{connection_info.base_url}/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_vod_streams&category_id={category_id}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # Clear existing film streams for this category
            db.query(FilmStream).filter(
                FilmStream.category_id == str(category_id)
            ).delete()

            # Add new film streams
            for stream in data:
                new_stream = FilmStream(
                    num=stream["num"],
                    name=stream["name"],
                    stream_type=stream["stream_type"],
                    stream_id=stream["stream_id"],
                    stream_icon=stream["stream_icon"],
                    rating=stream["rating"],
                    rating_5based=stream["rating_5based"],
                    added=stream["added"],
                    category_id=str(category_id),
                    container_extension=stream["container_extension"],
                    custom_sid=stream.get("custom_sid", ""),
                    direct_source=stream.get("direct_source", ""),
                )
                db.add(new_stream)

            # Update or create RefreshData
            if not refresh_data:
                refresh_data = RefreshData(data_type=f"film_streams_{category_id}")
            refresh_data.last_refresh = datetime.utcnow()
            db.add(refresh_data)

            db.commit()

        # Fetch film streams from database
        film_streams = (
            db.query(FilmStream)
            .filter(FilmStream.category_id == str(category_id))
            .all()
        )

        # Convert FilmStream objects to dictionary and add computed fields
        film_streams_list = []
        for stream in film_streams:
            stream_dict = {
                "num": stream.num,
                "name": stream.name,
                "stream_type": stream.stream_type,
                "stream_id": stream.stream_id,
                "stream_icon": stream.stream_icon,
                "rating": stream.rating,
                "rating_5based": stream.rating_5based,
                "added": stream.added,
                "category_id": stream.category_id,
                "container_extension": stream.container_extension,
                "custom_sid": stream.custom_sid,
                "direct_source": stream.direct_source,
                "added_date": datetime.fromtimestamp(int(stream.added)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "play_link": f"{connection_info.base_url}/movie/{connection_info.username}/{connection_info.password}/{stream.stream_id}.{stream.container_extension}",
                "cached_icon": cache_icon(stream.stream_icon),
            }
            film_streams_list.append(stream_dict)

        return film_streams_list

    def get_film_details(
        self,
        connection_info: ConnectionInfo,
        vod_id: int,
        force_refresh: bool = False,
        db: Session = None,
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        if db is None:
            logger.error("Database session is None in get_film_details")
            raise HTTPException(status_code=500, detail="Database session error")
        return self._get_film_details_from_db(
            connection_info, vod_id, force_refresh, db
        )

    def _get_film_details_from_db(
        self,
        connection_info: ConnectionInfo,
        vod_id: int,
        force_refresh: bool,
        db: Session,
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        refresh_data = (
            db.query(RefreshData)
            .filter(RefreshData.data_type == f"film_details_{vod_id}")
            .first()
        )
        film_detail = (
            db.query(FilmDetail).filter(FilmDetail.stream_id == vod_id).first()
        )

        if (
            force_refresh
            or not refresh_data
            or not film_detail
            or datetime.utcnow() - refresh_data.last_refresh > timedelta(hours=24)
        ):
            # Fetch data from API
            url = f"{connection_info.base_url}/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_vod_info&vod_id={vod_id}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # Update or create FilmDetail
            if not film_detail:
                film_detail = FilmDetail(stream_id=vod_id)

            # Update all fields
            film_detail.name = data["info"].get("name", "")
            film_detail.o_name = data["info"].get("o_name", "")
            film_detail.stream_icon = data["info"].get("movie_image", "")
            film_detail.cover_big = data["info"].get("cover_big", "")
            film_detail.movie_image = data["info"].get("movie_image", "")
            film_detail.plot = data["info"].get("plot", "")
            film_detail.cast = data["info"].get("cast", "")
            film_detail.director = data["info"].get("director", "")
            film_detail.genre = data["info"].get("genre", "")
            film_detail.release_date = data["info"].get("releasedate", "")
            film_detail.rating = data["info"].get("rating", "")
            film_detail.rating_5based = data["info"].get("rating_5based", 0.0)
            film_detail.duration_secs = data["info"].get("duration_secs", 0)
            film_detail.duration = data["info"].get("duration", "")
            film_detail.youtube_trailer = data["info"].get("youtube_trailer", "")
            film_detail.tmdb_id = data["info"].get("tmdb_id", "")
            film_detail.kinopoisk_url = data["info"].get("kinopoisk_url", "")
            film_detail.episode_run_time = data["info"].get("episode_run_time", "")
            film_detail.actors = data["info"].get("actors", "")
            film_detail.description = data["info"].get("description", "")
            film_detail.age = data["info"].get("age", "")
            film_detail.mpaa_rating = data["info"].get("mpaa_rating", "")
            film_detail.rating_count_kinopoisk = data["info"].get(
                "rating_count_kinopoisk", 0
            )
            film_detail.country = data["info"].get("country", "")
            film_detail.backdrop_path = data["info"].get("backdrop_path", [])
            film_detail.bitrate = data["info"].get("bitrate", 0)
            film_detail.video = data["info"].get("video", [])
            film_detail.audio = data["info"].get("audio", [])
            film_detail.container_extension = data["movie_data"].get(
                "container_extension", ""
            )

            db.add(film_detail)

            # Update or create RefreshData
            if not refresh_data:
                refresh_data = RefreshData(data_type=f"film_details_{vod_id}")
            refresh_data.last_refresh = datetime.utcnow()
            db.add(refresh_data)

            db.commit()
            db.refresh(film_detail)
            db.refresh(refresh_data)

        # Convert FilmDetail object to dictionary
        film_info = {
            "info": {
                "name": film_detail.name,
                "o_name": film_detail.o_name,
                "movie_image": film_detail.movie_image,
                "cover_big": film_detail.cover_big,
                "plot": film_detail.plot,
                "cast": film_detail.cast,
                "director": film_detail.director,
                "genre": film_detail.genre,
                "releasedate": film_detail.release_date,
                "rating": film_detail.rating,
                "rating_5based": film_detail.rating_5based,
                "duration_secs": film_detail.duration_secs,
                "duration": film_detail.duration,
                "youtube_trailer": film_detail.youtube_trailer,
                "tmdb_id": film_detail.tmdb_id,
                "kinopoisk_url": film_detail.kinopoisk_url,
                "episode_run_time": film_detail.episode_run_time,
                "actors": film_detail.actors,
                "description": film_detail.description,
                "age": film_detail.age,
                "mpaa_rating": film_detail.mpaa_rating,
                "rating_count_kinopoisk": film_detail.rating_count_kinopoisk,
                "country": film_detail.country,
                "backdrop_path": film_detail.backdrop_path,
                "bitrate": film_detail.bitrate,
                "video": film_detail.video,
                "audio": film_detail.audio,
            },
            "movie_data": {
                "stream_id": film_detail.stream_id,
                "container_extension": film_detail.container_extension,
            },
        }

        film_info["play_link"] = (
            f"{connection_info.base_url}/movie/{connection_info.username}/{connection_info.password}/{film_detail.stream_id}.{film_detail.container_extension}"
        )

        return (
            film_info,
            refresh_data.last_refresh,
            refresh_data.last_refresh + timedelta(hours=24),
        )

    def get_epg_info(
        self, connection_info: ConnectionInfo, stream_id: int, db: Session
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        return self._get_epg_info_from_db(connection_info, stream_id, db)

    def _get_epg_info_from_db(
        self,
        connection_info: ConnectionInfo,
        stream_id: int,
        db: Session,
    ) -> Tuple[Dict[str, Any], datetime, datetime]:
        refresh_data = (
            db.query(RefreshData)
            .filter(RefreshData.data_type == f"epg_{stream_id}")
            .first()
        )

        if (
            not refresh_data
            or datetime.utcnow() - refresh_data.last_refresh > timedelta(hours=24)
        ):
            # Fetch data from API
            url = f"{connection_info.base_url}/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_simple_data_table&stream_id={stream_id}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # Clear existing EPG listings for this stream
            db.query(EpgListing).filter(EpgListing.stream_id == stream_id).delete()

            # Add new EPG listings
            for listing in data.get("epg_listings", []):
                new_listing = EpgListing(
                    epg_id=listing["epg_id"],
                    title=listing["title"],
                    lang=listing["lang"],
                    start=datetime.strptime(listing["start"], "%Y-%m-%d %H:%M:%S"),
                    end=datetime.strptime(listing["end"], "%Y-%m-%d %H:%M:%S"),
                    description=listing["description"],
                    channel_id=listing["channel_id"],
                    start_timestamp=int(listing["start_timestamp"]),
                    stop_timestamp=int(listing["stop_timestamp"]),
                    now_playing=bool(listing["now_playing"]),
                    has_archive=bool(listing["has_archive"]),
                    stream_id=stream_id,
                )
                db.add(new_listing)

            # Update or create RefreshData
            if not refresh_data:
                refresh_data = RefreshData(data_type=f"epg_{stream_id}")
            refresh_data.last_refresh = datetime.utcnow()
            db.add(refresh_data)

            db.commit()

        # Fetch EPG listings from database
        epg_listings = (
            db.query(EpgListing).filter(EpgListing.stream_id == stream_id).all()
        )

        # Process EPG listings
        processed_listings = self._process_epg_listings(epg_listings)

        epg_info = {"epg_listings": processed_listings}

        return (
            epg_info,
            refresh_data.last_refresh,
            refresh_data.last_refresh + timedelta(hours=24),
        )

    def _process_epg_listings(self, listings):
        processed_listings = []
        for listing in listings:
            processed_listing = {
                "id": str(listing.id),
                "epg_id": listing.epg_id,
                "title": base64.b64decode(listing.title.encode()).decode(
                    "utf-8", errors="replace"
                ),
                "lang": listing.lang,
                "start": listing.start.strftime("%Y-%m-%d %H:%M:%S"),
                "end": listing.end.strftime("%Y-%m-%d %H:%M:%S"),
                "description": base64.b64decode(listing.description.encode()).decode(
                    "utf-8", errors="replace"
                ),
                "channel_id": listing.channel_id,
                "start_timestamp": listing.start_timestamp,
                "stop_timestamp": listing.stop_timestamp,
                "now_playing": listing.now_playing,
                "has_archive": listing.has_archive,
            }
            processed_listings.append(processed_listing)
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
    db: Session = Depends(get_db),
):
    if error is not None:
        if error == "authfail":
            error = "You need to be admin"
        else:
            error = "something broke"
    user_data, fetch_time, expiry_time = client.get_user_info(
        connection_info, force_refresh, db
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
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")
    live_categories, fetch_time, expiry_time = client.get_live_category(
        connection_info, force_refresh, db
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
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")
    series_categories, fetch_time, expiry_time = client.get_series_category(
        connection_info, force_refresh, db
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
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")
    streams = client.get_live_streams_by_category(
        connection_info, category_id, force_refresh, db
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
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")
    series = client.get_series_by_category(
        connection_info, category_id, force_refresh, db
    )
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
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")
    series_info, fetch_time, expiry_time = client.get_series_streams_by_series(
        connection_info, series_id, force_refresh, db
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
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")
    film_categories, fetch_time, expiry_time = client.get_film_categories(
        connection_info, force_refresh, db
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
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")
    streams = client.get_film_streams_by_category(
        connection_info, category_id, force_refresh, db
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
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")
    film_info, fetch_time, expiry_time = client.get_film_details(
        connection_info, vod_id, force_refresh, db
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
    stream_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")
    epg_info, _, _ = client.get_epg_info(connection_info, stream_id, db)
    return epg_info


@app.get("/epg_page/{stream_id}", response_class=HTMLResponse)
async def get_epg_page(
    stream_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")
    try:
        epg_info, fetch_time, expiry_time = client.get_epg_info(
            connection_info, stream_id, db
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
    type: str,
    id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")

    if type not in ["episode", "film"]:
        raise HTTPException(status_code=400, detail="Invalid stream type")

    try:
        if type == "episode":
            series_id, episode_id = id.split("_")
            series_info, _, _ = client.get_series_streams_by_series(
                connection_info, int(series_id), db=db
            )

            if not series_info:
                raise HTTPException(status_code=404, detail="Series not found")

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
            film_info, _, _ = client.get_film_details(connection_info, int(id), db=db)

            if not film_info:
                raise HTTPException(status_code=404, detail="Film not found")

            play_link = film_info.get("play_link")
            if not play_link:
                logger.error(f"Play link not found for film_id: {id}")
                raise HTTPException(
                    status_code=500, detail="Unable to generate play link"
                )

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
    except KeyError as e:
        logger.error(f"KeyError in stream_video: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Missing key in film info: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error in stream_video: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="An error occurred while processing your request"
        )


@app.get("/empty")
async def empty_content():
    return " "


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
