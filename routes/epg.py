import os
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import User, get_db
from api_client import client, ConnectionInfo
from utils import calculate_refresh_time, format_timestamp
from auth import get_current_user
from datetime import datetime
from config import API_BASE_URL, API_PASSWORD, API_USERNAME

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/epg/{stream_id}")
async def get_epg(
    stream_id: int,
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
    epg_info, _, _ = client.get_epg_info(connection_info, stream_id, db)
    return epg_info


@router.get("/epg_page/{stream_id}", response_class=HTMLResponse)
async def get_epg_page(
    stream_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
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
