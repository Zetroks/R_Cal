import os

from fastapi import HTTPException, Header
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends

from . import database
from . import database_models

SECRET_KEY = os.environ.get("CAL_SECRET_KEY", "")
BOT_SECRET = os.environ.get("CAL_BOT_SECRET", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("CAL_TOKEN_EXPIRE_MINUTES", "60"))

if not SECRET_KEY:
    raise RuntimeError("CAL_SECRET_KEY is not set. Copy .env.example to .env and fill it.")

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def get_password_hash(password):
    return pwd_context.hash(password)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


def authenticate_user(username: str, password: str) -> database_models.User | None:
    user = database.EventRepository.get().get_user(username)
    if not user:
        return None
    # if not verify_password(password, user["hashed_password"]):
    if not verify_password(password, get_password_hash(user.password)):
        return None
    return user


def get_bot(x_bot_token: str = Header(None)) -> bool:
    if not x_bot_token or x_bot_token != BOT_SECRET:
        return False
    return True


def get_current_user(
        token: str = Depends(oauth2_scheme),
        telegram_id: int = Header(None),
        is_bot: bool = Depends(get_bot)
) -> database_models.User:
    # -----------------------
    # 1. JWT AUTH (DESKTOP)
    # -----------------------
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")

            if username is None:
                raise HTTPException(status_code=401)
            user = database.EventRepository.get().get_user(username)
            if user is None:
                raise HTTPException(status_code=401)
            return user

        except JWTError:
            raise HTTPException(status_code=401)
    # -----------------------
    # 2. BOT AUTH (TELEGRAM)
    # -----------------------
    #TODO: ADD HMAC BOT AUTH
    # CLIENT
    # def sign(secret, telegram_id, timestamp):
    #     msg = f"{telegram_id}:{timestamp}"
    #     return hmac.new(
    #         secret.encode(),
    #         msg.encode(),
    #         hashlib.sha256
    #     ).hexdigest()
    # SERVER
    # def verify(secret, telegram_id, timestamp, signature):
    #     msg = f"{telegram_id}:{timestamp}"
    #     expected = hmac.new(
    #         secret.encode(),
    #         msg.encode(),
    #         hashlib.sha256
    #     ).hexdigest()
    #     return hmac.compare_digest(expected, signature)
    # if abs(now - timestamp) > 60:
    #     reject()

    if is_bot:
        if telegram_id is None:
            raise HTTPException(
                status_code=400,
                detail="telegram_id required for bot requests"
            )

        user = database.EventRepository.get().get_user_by_telegram_id(telegram_id)

        if not user:
            raise HTTPException(status_code=401, detail="Telegram user not found")

        return user

    # -----------------------
    # 3. NO AUTH
    # -----------------------
    raise HTTPException(status_code=401, detail="Not authenticated")
