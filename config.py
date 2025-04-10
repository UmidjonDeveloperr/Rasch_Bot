import os
from dotenv import load_dotenv
from typing import Dict, Any

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class for the application"""

    # Bot configuration
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))  # Default to 0 if not set

    # Database configuration - using your password
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://rasch_bot_user:raschdb_2005@localhost:5432/rasch_bot_db"
    )

    @staticmethod
    def get_db_config() -> Dict[str, Any]:
        """Parse DATABASE_URL into asyncpg-compatible configuration"""
        if Config.DATABASE_URL.startswith("postgresql"):
            # Parse PostgreSQL URL
            from urllib.parse import urlparse
            url = urlparse(Config.DATABASE_URL)

            return {
                'user': url.username or 'rasch_bot_user',
                'password': url.password or 'raschdb_2005',
                'database': url.path[1:] if url.path else 'rasch_bot_db',
                'host': url.hostname or 'localhost',
                'port': url.port or 5432
            }
        else:
            # Fallback configuration
            return {
                'user': os.getenv("DB_USER", "rasch_bot_user"),
                'password': os.getenv("DB_PASSWORD", "raschdb_2005"),
                'database': os.getenv("DB_NAME", "rasch_bot_db"),
                'host': os.getenv("DB_HOST", "localhost"),
                'port': int(os.getenv("DB_PORT", "5432"))
            }

ADMIN_ID = Config.ADMIN_ID
BOT_TOKEN = Config.BOT_TOKEN
DB_CONFIG = Config.get_db_config()

# Validate critical configurations
if not Config.BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required in environment variables")

if __name__ == "__main__":
    print("=== Configuration Verification ===")
    print(f"Bot token: {'*****' if Config.BOT_TOKEN else 'Not set'}")
    print(f"Admin ID: {Config.ADMIN_ID}")
    print(f"Database URL: {Config.DATABASE_URL.split('@')[0]}@*****")

    db_config = Config.get_db_config()
    db_config['password'] = '*****'  # Hide password in output
    print("DB Config:", db_config)