from datetime import datetime
import os
import logging
from fastapi import APIRouter, Depends, Query, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import User, get_db
from api_client import client, ConnectionInfo
from utils import calculate_refresh_time, cache_backdrop, cache_icons_background
from auth import get_current_user
from urllib.parse import quote
from config import API_BASE_URL, API_PASSWORD, API_USERNAME

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/series", response_class=HTMLResponse)
async def series_page(
    request: Request,
    current_user: User = Depends(get_current_user),
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
    series_categories, fetch_time, expiry_time = client.get_series_category(
        connection_info, force_refresh, db=db
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


@router.get("/series/refresh-all", response_class=HTMLResponse)
async def refresh_all_series(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
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
        # First, refresh categories
        series_categories, _, _ = client.get_series_category(connection_info, db=db)

        # Then, refresh all series
        all_series, fetch_time, _ = client.get_all_series(
            connection_info, force_refresh=True, db=db
        )

        background_tasks.add_task(cache_icons_background, all_series)

        db.commit()

        return templates.TemplateResponse(
            "series.html",
            {
                "request": request,
                "series_categories": series_categories,
                "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
                "current_user": current_user,
                "all_series_refreshed": True,
            },
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error refreshing all series: {str(e)}")
        return templates.TemplateResponse(
            "series.html",
            {
                "request": request,
                "series_categories": [],
                "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "current_user": current_user,
                "all_series_refreshed": False,
                "error_message": "An error occurred while refreshing series data.",
            },
            status_code=500,
        )


@router.get("/series/{series_id}", response_class=HTMLResponse)
async def get_series_episodes(
    series_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
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


@router.get("/series-category/{category_id}")
async def get_series_category_shows(
    category_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
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
    series = client.get_series_by_category(
        connection_info, category_id, force_refresh, db
    )
    return templates.TemplateResponse(
        "series_list.html",
        {"request": request, "series": series, "current_user": current_user},
    )
