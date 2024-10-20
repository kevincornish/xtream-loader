from typing import Optional
from passlib.context import CryptContext
from datetime import timedelta, datetime
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
from fastapi import HTTPException, Depends, status, Request
from database import User, get_db
from config import ALGORITHM, SECRET_KEY

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def authenticate_user(db: Session, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        token = request.cookies.get("access_token")
        if not token:
            return None
        try:
            token = token.split()[1]  # Remove "Bearer " prefix
        except IndexError:
            return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        return None
    return user


def user_has_streams_access(current_user: User = Depends(get_current_user)):
    if not current_user or not current_user.streams_access:
        raise HTTPException(status_code=403, detail="Access denied")
    return current_user


def user_has_series_access(current_user: User = Depends(get_current_user)):
    if not current_user or not current_user.series_access:
        raise HTTPException(status_code=403, detail="Access denied")
    return current_user


def user_has_films_access(current_user: User = Depends(get_current_user)):
    if not current_user or not current_user.films_access:
        raise HTTPException(status_code=403, detail="Access denied")
    return current_user
