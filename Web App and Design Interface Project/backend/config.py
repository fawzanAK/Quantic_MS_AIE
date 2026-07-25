import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://cafe_fausse_user:password@localhost:5432/cafe_fausse"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TOTAL_TABLES = int(os.environ.get("TOTAL_TABLES", 30))
