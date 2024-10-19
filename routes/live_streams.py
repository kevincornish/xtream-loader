import os
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import User, get_db
from api_client import client, ConnectionInfo
from utils import calculate_refresh_time
from fastapi.responses import HTMLResponse, RedirectResponse
from auth import get_current_user
from config import API_BASE_URL, API_PASSWORD, API_USERNAME

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/streams", response_class=HTMLResponse)
async def streams_page(
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


@router.get("/live-category/{category_id}")
async def get_live_category_streams(
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
    streams = client.get_live_streams_by_category(
        connection_info, category_id, force_refresh, db
    )
    return templates.TemplateResponse(
        "stream_list.html",
        {"request": request, "streams": streams, "current_user": current_user},
    )
