from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
import base64
import logging
import requests
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from database import (
    FilmCategory,
    LiveChannel,
    Series,
    SeriesCategory,
    SeriesEpisode,
    RefreshData,
    UserInfo,
    get_db,
    LiveCategory,
    FilmStream,
    FilmDetail,
    EpgListing,
)
from utils import cache_icon

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConnectionInfo:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.username = username
        self.password = password


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
        # Check if we have series for this category in the database
        existing_series = db.query(Series).filter(Series.category_id == str(category_id)).all()
        
        if existing_series and not force_refresh:
            logger.info(f"Retrieved {len(existing_series)} series for category {category_id} from database")
            return self._convert_series_to_dict(existing_series)
        
        # If no existing series or force refresh, fetch from API
        return self._get_series_from_db(connection_info, category_id, force_refresh, db)

    def _convert_series_to_dict(self, series_list):
        return [
            {
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
            for series in series_list
        ]

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

    def get_all_series(
        self,
        connection_info: ConnectionInfo,
        force_refresh: bool = False,
        db: Session = None,
    ) -> Tuple[List[Dict[str, Any]], datetime, datetime]:
        refresh_data = (
            db.query(RefreshData).filter(RefreshData.data_type == "all_series").first()
        )

        if (
            force_refresh
            or not refresh_data
            or datetime.utcnow() - refresh_data.last_refresh > timedelta(hours=24)
        ):
            url = f"{connection_info.base_url}/player_api.php?username={connection_info.username}&password={connection_info.password}&action=get_series"
            try:
                response = requests.get(url)
                response.raise_for_status()
                data = response.json()

                logger.info(f"Fetched {len(data)} series from API")

                try:
                    # Clear existing series
                    deleted_count = db.query(Series).delete()
                    logger.info(
                        f"Cleared {deleted_count} existing series from database"
                    )

                    # Add new series in batches
                    new_series_count = 0
                    batch_size = 500
                    for i in range(0, len(data), batch_size):
                        batch = data[i : i + batch_size]
                        series_objects = []
                        for series in batch:
                            new_series = Series(
                                series_id=series["series_id"],
                                category_id=series["category_id"],
                                name=series["name"],
                                cover=series["cover"],
                                plot=series.get("plot", ""),
                                cast=series.get("cast", ""),
                                director=series.get("director", ""),
                                genre=series.get("genre", ""),
                                release_date=series.get("releaseDate", ""),
                                last_modified=series.get("last_modified", ""),
                                rating=series.get("rating", ""),
                                rating_5based=series.get("rating_5based", 0.0),
                                backdrop_path=series.get("backdrop_path", []),
                                youtube_trailer=series.get("youtube_trailer", ""),
                                episode_run_time=series.get("episode_run_time", ""),
                            )
                            series_objects.append(new_series)

                        db.bulk_save_objects(series_objects)
                        db.flush()
                        new_series_count += len(series_objects)
                        logger.info(
                            f"Added batch of {len(series_objects)} series. Total: {new_series_count}"
                        )

                    logger.info(
                        f"Finished adding {new_series_count} new series to database"
                    )

                    # Update or create RefreshData
                    if not refresh_data:
                        refresh_data = RefreshData(data_type="all_series")
                    refresh_data.last_refresh = datetime.utcnow()
                    db.add(refresh_data)

                    db.flush()
                    logger.info("Successfully flushed all changes to database")

                    # Verify the number of series in the database
                    actual_count = db.query(Series).count()
                    logger.info(
                        f"Actual number of series in database after refresh: {actual_count}"
                    )

                    if actual_count != new_series_count:
                        logger.warning(
                            f"Discrepancy in series count. Expected: {new_series_count}, Actual: {actual_count}"
                        )

                except SQLAlchemyError as e:
                    logger.error(f"Error updating database: {str(e)}")
                    raise

            except requests.RequestException as e:
                logger.error(f"Error fetching data from API: {str(e)}")
                raise

        # Fetch all series from database
        all_series = db.query(Series).all()
        logger.info(f"Retrieved {len(all_series)} series from database")

        # Convert Series objects to dictionary
        series_list = [
            {
                "series_id": series.series_id,
                "category_id": series.category_id,
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
            }
            for series in all_series
        ]

        return (
            series_list,
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


client = CachedApiClient()
