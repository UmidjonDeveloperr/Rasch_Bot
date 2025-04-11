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
        "postgresql://postgres:UNujKLBAAGIFskpCjWCjCMpVDDaURvnc@postgres.railway.internal:5432/railway"
    )

    @staticmethod
    def get_db_config() -> Dict[str, Any]:
        """Parse DATABASE_URL into asyncpg-compatible configuration"""
        if Config.DATABASE_URL.startswith("postgresql"):
            # Parse PostgreSQL URL
            from urllib.parse import urlparse
            url = urlparse(Config.DATABASE_URL)

            return {
                'user': url.username or 'postgres',
                'password': url.password or 'UNujKLBAAGIFskpCjWCjCMpVDDaURvnc',
                'database': url.path[1:] if url.path else 'railway',
                'host': url.hostname or 'postgres.railway.internal',
                'port': url.port or 5432
            }
        else:
            # Fallback configuration
            return {
                'user': os.getenv("DB_USER", "postgres"),
                'password': os.getenv("DB_PASSWORD", "UNujKLBAAGIFskpCjWCjCMpVDDaURvnc"),
                'database': os.getenv("DB_NAME", "railway"),
                'host': os.getenv("DB_HOST", "postgres.railway.internal"),
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