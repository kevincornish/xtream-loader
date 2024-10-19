from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import get_db, User, Series, FilmStream, LiveChannel
from auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100),
    search_type: str = Query(..., regex="^(series|movies|tv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if search_type == "series":
        results = (
            db.query(Series)
            .filter(or_(Series.name.ilike(f"%{q}%"), Series.plot.ilike(f"%{q}%")))
            .all()
        )
    elif search_type == "movies":
        results = (
            db.query(FilmStream)
            .filter(
                or_(
                    FilmStream.name.ilike(f"%{q}%"),
                    FilmStream.stream_type.ilike(f"%{q}%"),
                )
            )
            .all()
        )
    else:  # TV channels
        results = (
            db.query(LiveChannel)
            .filter(
                or_(
                    LiveChannel.name.ilike(f"%{q}%"),
                    LiveChannel.stream_type.ilike(f"%{q}%"),
                )
            )
            .all()
        )

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "query": q,
            "search_type": search_type,
            "results": results,
            "current_user": current_user,
        },
    )
