from datetime import timedelta
import os
import logging
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, Depends, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from utils import calculate_refresh_time
from config import (
    API_BASE_URL,
    API_USERNAME,
    API_PASSWORD,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from auth import (
    authenticate_user,
    get_password_hash,
    create_access_token,
    get_current_user,
)
from api_client import ConnectionInfo, client
from database import (
    User,
    get_db,
)
from routes import live_streams, series, films, epg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers
app.include_router(live_streams.router)
app.include_router(series.router)
app.include_router(films.router)
app.include_router(epg.router)

# Ensure the icons directory exists
ICONS_DIR = "static/icons"
os.makedirs(ICONS_DIR, exist_ok=True)

connection_info = ConnectionInfo(
    base_url=API_BASE_URL,
    username=API_USERNAME,
    password=API_PASSWORD,
)


@app.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request,
    current_user: User = Depends(get_current_user),
    force_refresh: bool = Query(False),
    error: str = Query(None),
    db: Session = Depends(get_db),
):
    if error is not None:
        if error == "authfail":
            error = "You need to be admin"
        else:
            error = "something broke"
    user_data, fetch_time, expiry_time = client.get_user_info(
        connection_info, force_refresh, db
    )
    refresh_time = calculate_refresh_time(expiry_time)
    if not current_user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user_info": user_data["user_info"],
            "server_info": user_data["server_info"],
            "fetch_time": fetch_time.strftime("%Y-%m-%d %H:%M:%S"),
            "refresh_time": refresh_time,
            "current_user": current_user,
            "error": error,
        },
    )


# FIXME: support for mkv, avi etc
@app.get("/stream/{type}/{id}")
async def stream_video(
    type: str,
    id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")

    if type not in ["episode", "film"]:
        raise HTTPException(status_code=400, detail="Invalid stream type")

    try:
        if type == "episode":
            series_id, episode_id = id.split("_")
            series_info, _, _ = client.get_series_streams_by_series(
                connection_info, int(series_id), db=db
            )

            if not series_info:
                raise HTTPException(status_code=404, detail="Series not found")

            episode = next(
                (
                    ep
                    for season in series_info["episodes"].values()
                    for ep in season
                    if ep["id"] == episode_id
                ),
                None,
            )
            if not episode:
                raise HTTPException(status_code=404, detail="Episode not found")

            play_link = episode["play_link"]
            title = f"{series_info['info']['name']} - Episode {episode['episode_num']}"
        else:
            film_info, _, _ = client.get_film_details(connection_info, int(id), db=db)

            if not film_info:
                raise HTTPException(status_code=404, detail="Film not found")

            play_link = film_info.get("play_link")
            if not play_link:
                logger.error(f"Play link not found for film_id: {id}")
                raise HTTPException(
                    status_code=500, detail="Unable to generate play link"
                )

            title = film_info["info"]["name"]

        return templates.TemplateResponse(
            "video_player.html",
            {
                "request": request,
                "play_link": play_link,
                "title": title,
                "current_user": current_user,
            },
        )
    except KeyError as e:
        logger.error(f"KeyError in stream_video: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Missing key in film info: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error in stream_video: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="An error occurred while processing your request"
        )


@app.get("/empty")
async def empty_content():
    return " "


# Login and logout routes
@app.post("/token")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Incorrect username or password"},
            status_code=400,
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="access_token", value=f"Bearer {access_token}", httponly=True
    )
    return response


@app.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login")
    response.delete_cookie("access_token")
    return response


# Login page
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# Admin routes
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login")
    if not current_user.is_admin:
        return RedirectResponse(url="/?error=authfail")
    users = db.query(User).all()
    return templates.TemplateResponse(
        "admin.html", {"request": request, "users": users, "current_user": current_user}
    )


@app.post("/admin/add_user")
async def add_user(
    username: str = Form(...),
    password: str = Form(...),
    is_admin: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse(url="/login")
    if not current_user.is_admin:
        return RedirectResponse(url="/?error=authfail")
    db_user = User(
        username=username,
        hashed_password=get_password_hash(password),
        is_admin=is_admin,
    )
    db.add(db_user)
    db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/delete_user/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse(url="/login")
    if not current_user.is_admin:
        return RedirectResponse(url="/?error=authfail")
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        db.delete(user)
        db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
