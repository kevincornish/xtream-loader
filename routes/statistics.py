from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db, FilmStream, Series, LiveChannel, User
from auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/statistics", response_class=HTMLResponse)
async def statistics_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")

    total_movies = db.query(FilmStream).count()
    total_series = db.query(Series).count()
    total_live_channels = db.query(LiveChannel).count()
    total_users = db.query(User).count()

    stats = {
        "total_movies": total_movies,
        "total_series": total_series,
        "total_live_channels": total_live_channels,
        "total_users": total_users,
    }

    return templates.TemplateResponse(
        "statistics.html",
        {"request": request, "stats": stats, "current_user": current_user},
    )
