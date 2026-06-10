import re
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def normalize_mobile(raw: str) -> str:
    """Digits only, min 10 chars (E.164 body without +)."""
    s = (raw or "").strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) < 10 or len(digits) > 15:
        raise ValueError("Enter a valid mobile number (10–15 digits).")
    return digits


def hash_password(plain: str) -> str:
    if len(plain) < 6:
        raise ValueError("Password must be at least 6 characters.")
    return _pwd.hash(plain[:72])


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain[:72], hashed)


def create_access_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": exp}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError) as e:
        raise ValueError("Invalid token") from e
