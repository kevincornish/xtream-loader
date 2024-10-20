from datetime import datetime
from fastapi import APIRouter, Depends, Query, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import User, get_db
from api_client import client, ConnectionInfo
from utils import calculate_refresh_time, cache_icons_background
from auth import get_current_user
from config import API_BASE_URL, API_PASSWORD, API_USERNAME

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/streams", response_class=HTMLResponse)
async def streams_page(
    request: Request,
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
    live_categories, fetch_time, expiry_time = client.get_live_category(
        connection_info, db=db
    )
    all_streams, _, _ = client.get_all_live_streams(connection_info, db=db)
    refresh_time = calculate_refresh_time(expiry_time)

    return templates.TemplateResponse(
        "streams.html",
        {
            "request": request,
            "live_categories": live_categories,
            "all_streams": all_streams,
            "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
            "refresh_time": refresh_time,
            "current_user": current_user,
        },
    )


@router.get("/streams/refresh-all", response_class=HTMLResponse)
async def refresh_all_streams(
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
        live_categories, _, _ = client.get_live_category(
            connection_info, force_refresh=True, db=db
        )

        # Then, refresh all streams
        all_streams, fetch_time, _ = client.get_all_live_streams(
            connection_info, force_refresh=True, db=db
        )

        background_tasks.add_task(cache_icons_background, all_streams, "live")

        db.commit()

        return templates.TemplateResponse(
            "streams.html",
            {
                "request": request,
                "live_categories": live_categories,
                "all_streams": all_streams,
                "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
                "refresh_time": "24 hours",
                "current_user": current_user,
                "all_streams_refreshed": True,
            },
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error refreshing all streams: {str(e)}")
        return templates.TemplateResponse(
            "streams.html",
            {
                "request": request,
                "live_categories": [],
                "all_streams": [],
                "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "refresh_time": "24 hours",
                "current_user": current_user,
                "all_streams_refreshed": False,
                "error_message": "An error occurred while refreshing stream data.",
            },
            status_code=500,
        )
