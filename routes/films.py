from datetime import datetime
import os
import logging
from fastapi import APIRouter, Depends, Query, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import User, get_db
from api_client import client, ConnectionInfo
from utils import calculate_refresh_time, cache_backdrop
from auth import user_has_films_access
from urllib.parse import quote
from config import API_BASE_URL, API_PASSWORD, API_USERNAME
from utils import cache_icons_background

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/films", response_class=HTMLResponse)
async def film_page(
    request: Request,
    current_user: User = Depends(user_has_films_access),
    force_refresh: bool = Query(False),
    db: Session = Depends(get_db),
    connection_info: ConnectionInfo = Depends(
        lambda: ConnectionInfo(
            base_url=API_BASE_URL,
            username=API_USERNAME,
            password=API_PASSWORD,
        )
    ),
):
    if not current_user:
        return RedirectResponse(url="/login")
    film_categories, fetch_time, expiry_time = client.get_film_categories(
        connection_info, force_refresh, db=db
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


@router.get("/films/refresh-all", response_class=HTMLResponse)
async def refresh_all_films(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(user_has_films_access),
    db: Session = Depends(get_db),
    connection_info: ConnectionInfo = Depends(
        lambda: ConnectionInfo(
            base_url=API_BASE_URL,
            username=API_USERNAME,
            password=API_PASSWORD,
        )
    ),
):
    if not current_user:
        return RedirectResponse(url="/login")

    try:
        # Refresh all films
        film_categories, fetch_time, expiry_time = client.get_film_categories(
            connection_info, force_refresh=True, db=db
        )
        refresh_time = calculate_refresh_time(expiry_time)

        background_tasks.add_task(
            cache_icons_background,
            client.get_all_films(connection_info, db=db)[0],
            "films",
        )

        return templates.TemplateResponse(
            "films.html",
            {
                "request": request,
                "film_categories": film_categories,
                "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
                "refresh_time": refresh_time,
                "current_user": current_user,
                "all_films_refreshed": True,
            },
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error refreshing all films: {str(e)}")
        return templates.TemplateResponse(
            "films.html",
            {
                "request": request,
                "film_categories": [],
                "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "refresh_time": "24 hours",
                "current_user": current_user,
                "all_films_refreshed": False,
                "error_message": "An error occurred while refreshing film data.",
            },
            status_code=500,
        )


@router.get("/film-category/{category_id}")
async def get_film_category_streams(
    category_id: int,
    request: Request,
    current_user: User = Depends(user_has_films_access),
    force_refresh: bool = False,
    db: Session = Depends(get_db),
    connection_info: ConnectionInfo = Depends(
        lambda: ConnectionInfo(
            base_url=os.getenv("API_BASE_URL"),
            username=os.getenv("API_USERNAME"),
            password=os.getenv("API_PASSWORD"),
        )
    ),
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


@router.get("/film/{vod_id}", response_class=HTMLResponse)
async def get_film_details(
    vod_id: int,
    request: Request,
    current_user: User = Depends(user_has_films_access),
    force_refresh: bool = Query(False),
    db: Session = Depends(get_db),
    connection_info: ConnectionInfo = Depends(
        lambda: ConnectionInfo(
            base_url=os.getenv("API_BASE_URL"),
            username=os.getenv("API_USERNAME"),
            password=os.getenv("API_PASSWORD"),
        )
    ),
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
