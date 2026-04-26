"""Flask app config"""
import os
import tempfile
from dotenv import load_dotenv

load_dotenv()

# Anchor all paths to this file's directory so cwd never matters.
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _safe_dir(default_subdir):
    """Return a writable directory.

    Prefer <backend>/<sub>; if that path contains characters that SQLite or
    subprocess pipes can't handle on the current code page (e.g. CJK in a
    Windows OneDrive path), fall back to %TEMP%/skill_report/<sub>.
    """
    primary = os.path.join(BASE_DIR, default_subdir)
    try:
        primary.encode('ascii')
        os.makedirs(primary, exist_ok=True)
        return primary
    except (UnicodeEncodeError, OSError):
        fallback = os.path.join(tempfile.gettempdir(), 'skill_report', default_subdir)
        os.makedirs(fallback, exist_ok=True)
        return fallback


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'

    DB_TYPE = os.environ.get('DB_TYPE', 'sqlite')

    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = int(os.environ.get('DB_PORT', 3306))
    DB_NAME = os.environ.get('DB_NAME', 'skill_report')
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')

    DATA_DIR = _safe_dir('data')
    UPLOAD_FOLDER = _safe_dir('uploads')
    OUTPUT_FOLDER = _safe_dir('output')

    SQLITE_PATH = os.environ.get('SQLITE_PATH') or os.path.join(DATA_DIR, 'skill_report.db')

    if DB_TYPE == 'mysql':
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
            f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
        )
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + SQLITE_PATH.replace('\\', '/')

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]

class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True

class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}