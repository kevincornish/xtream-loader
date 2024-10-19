import logging
from datetime import datetime
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    JSON,
    Float,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SQLALCHEMY_DATABASE_URL = "sqlite:///./xtream_loader.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)


class RefreshData(Base):
    __tablename__ = "refresh_data"

    id = Column(Integer, primary_key=True, index=True)
    data_type = Column(String, unique=True, index=True)
    last_refresh = Column(DateTime, default=datetime.utcnow)


class UserInfo(Base):
    __tablename__ = "user_info"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    password = Column(String)
    message = Column(String)
    auth = Column(Integer)
    status = Column(String)
    exp_date = Column(String)
    is_trial = Column(String)
    active_cons = Column(String)
    created_at = Column(String)
    max_connections = Column(String)
    allowed_output_formats = Column(JSON)

    # Server info
    server_url = Column(String)
    server_port = Column(String)
    server_https_port = Column(String)
    server_protocol = Column(String)
    server_rtmp_port = Column(String)
    server_timezone = Column(String)
    server_timestamp_now = Column(Integer)
    server_time_now = Column(String)


class LiveCategory(Base):
    __tablename__ = "live_categories"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(String, unique=True, index=True)
    category_name = Column(String)
    parent_id = Column(Integer)


class LiveChannel(Base):
    __tablename__ = "live_channels"

    id = Column(Integer, primary_key=True, index=True)
    num = Column(Integer)
    name = Column(String)
    stream_type = Column(String)
    stream_id = Column(Integer, unique=True, index=True)
    stream_icon = Column(String)
    epg_channel_id = Column(String)
    added = Column(String)
    category_id = Column(String, index=True)
    custom_sid = Column(String)
    tv_archive = Column(Integer)
    direct_source = Column(String)
    tv_archive_duration = Column(Integer)


class EpgListing(Base):
    __tablename__ = "epg_listings"

    id = Column(Integer, primary_key=True, index=True)
    epg_id = Column(String, index=True)
    title = Column(String)
    lang = Column(String)
    start = Column(DateTime)
    end = Column(DateTime)
    description = Column(String)
    channel_id = Column(String, index=True)
    start_timestamp = Column(Integer)
    stop_timestamp = Column(Integer)
    now_playing = Column(Boolean)
    has_archive = Column(Boolean)
    stream_id = Column(Integer, index=True)


class FilmCategory(Base):
    __tablename__ = "film_categories"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(String, unique=True, index=True)
    category_name = Column(String)
    parent_id = Column(Integer)


class FilmStream(Base):
    __tablename__ = "film_streams"

    id = Column(Integer, primary_key=True, index=True)
    num = Column(Integer)
    name = Column(String)
    stream_type = Column(String)
    stream_id = Column(Integer, unique=True, index=True)
    stream_icon = Column(String)
    rating = Column(String)
    rating_5based = Column(Float)
    added = Column(String)
    category_id = Column(String, index=True)
    container_extension = Column(String)
    custom_sid = Column(String)
    direct_source = Column(String)


class FilmDetail(Base):
    __tablename__ = "film_details"

    id = Column(Integer, primary_key=True, index=True)
    stream_id = Column(Integer, unique=True, index=True)
    name = Column(String)
    o_name = Column(String, nullable=True)
    stream_icon = Column(String)
    cover_big = Column(String, nullable=True)
    movie_image = Column(String, nullable=True)
    plot = Column(String, nullable=True)
    cast = Column(String, nullable=True)
    director = Column(String, nullable=True)
    genre = Column(String, nullable=True)
    release_date = Column(String, nullable=True)
    rating = Column(String, nullable=True)
    rating_5based = Column(Float, nullable=True)
    duration_secs = Column(Integer, nullable=True)
    duration = Column(String, nullable=True)
    youtube_trailer = Column(String, nullable=True)
    container_extension = Column(String, nullable=True)
    tmdb_id = Column(String, nullable=True)
    kinopoisk_url = Column(String, nullable=True)
    episode_run_time = Column(String, nullable=True)
    actors = Column(String, nullable=True)
    description = Column(String, nullable=True)
    age = Column(String, nullable=True)
    mpaa_rating = Column(String, nullable=True)
    rating_count_kinopoisk = Column(Integer, nullable=True)
    country = Column(String, nullable=True)
    backdrop_path = Column(JSON, nullable=True)
    bitrate = Column(Integer, nullable=True)
    video = Column(JSON, nullable=True)
    audio = Column(JSON, nullable=True)


class SeriesCategory(Base):
    __tablename__ = "series_categories"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(String, unique=True, index=True)
    category_name = Column(String)
    parent_id = Column(Integer)


class Series(Base):
    __tablename__ = "series"

    id = Column(Integer, primary_key=True, index=True)
    series_id = Column(Integer, unique=True, index=True)
    name = Column(String)
    cover = Column(String)
    plot = Column(String)
    cast = Column(String)
    director = Column(String)
    genre = Column(String)
    release_date = Column(String)
    last_modified = Column(String)
    rating = Column(String)
    rating_5based = Column(Float)
    backdrop_path = Column(JSON)
    youtube_trailer = Column(String)
    episode_run_time = Column(String)
    category_id = Column(String, index=True)


class SeriesEpisode(Base):
    __tablename__ = "series_episodes"

    id = Column(Integer, primary_key=True, index=True)
    series_id = Column(Integer, index=True)
    season = Column(Integer)
    episode = Column(Integer)
    title = Column(String)
    container_extension = Column(String)
    plot = Column(String)
    duration = Column(String)
    rating = Column(Float)
    info = Column(JSON)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Database error occurred: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()
