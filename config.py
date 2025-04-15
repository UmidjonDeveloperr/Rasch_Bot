import os
from dotenv import load_dotenv
from typing import Dict, Any

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class for the application"""

    # Bot configuration
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    #ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))  # Default to 0 if not set
    ADMIN_IDS: list = [int(admin_id.strip()) for admin_id in os.getenv("ADMIN_IDS", "").split(',') if admin_id.strip().isdigit()]
    # Database configuration - using your password
    DATABASE_URL: str = os.getenv("DATABASE_URL")

    @staticmethod
    def get_db_config() -> Dict[str, Any]:
        """Parse DATABASE_URL into asyncpg-compatible configuration"""
        if Config.DATABASE_URL.startswith("postgresql"):
            from urllib.parse import urlparse
            url = urlparse(Config.DATABASE_URL)

            # Ensure all parts are properly set
            if not all([url.hostname, url.username, url.password, url.path]):
                raise ValueError("Invalid DATABASE_URL format")

            return {
                'user': url.username,
                'password': url.password,
                'database': url.path[1:],  # Remove leading slash
                'host': url.hostname,
                'port': url.port or 5432
            }
        else:
            # Fallback configuration with your Railway credentials
            return {
                'user': "postgres",
                'password': "UNujKLBAAGIFskpCjWCjCMpVDDaURvnc",
                'database': "railway",
                'host': "monorail.proxy.rlwy.net",  # Use external hostname
                'port': 12345  # Use your actual external port
            }

ADMIN_IDS = Config.ADMIN_IDS
BOT_TOKEN = Config.BOT_TOKEN
DB_CONFIG = Config.get_db_config()

# Validate critical configurations
if not Config.BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required in environment variables")

if __name__ == "__main__":
    print("=== Configuration Verification ===")
    print(f"Bot token: {'*****' if Config.BOT_TOKEN else 'Not set'}")
    print(f"Admin ID: {Config.ADMIN_IDS}")
    print(f"Database URL: {Config.DATABASE_URL.split('@')[0]}@*****")

    db_config = Config.get_db_config()
    db_config['password'] = '*****'  # Hide password in output
    print("DB Config:", db_config)