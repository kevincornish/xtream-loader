import os
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import User, get_db
from api_client import client, ConnectionInfo
from utils import calculate_refresh_time, cache_backdrop
from auth import get_current_user
from urllib.parse import quote
from config import API_BASE_URL, API_PASSWORD, API_USERNAME

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/films", response_class=HTMLResponse)
async def film_page(
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


@router.get("/film-category/{category_id}")
async def get_film_category_streams(
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
    current_user: User = Depends(get_current_user),
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
