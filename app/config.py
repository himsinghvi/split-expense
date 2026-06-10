import os
import secrets

# Change in production via environment variables
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
SESSION_SECRET = os.environ.get("SESSION_SECRET", SECRET_KEY)
JWT_SECRET = os.environ.get("JWT_SECRET", SECRET_KEY)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days
