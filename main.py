import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from config import Config
from handlers import router
from db_rasch import TestManager

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, types.Message):
            user = event.from_user
            logger.info(
                f"New MESSAGE - User: {user.full_name} (@{user.username}) "
                f"ID: {user.id}, Chat: {event.chat.id}, "
                f"Type: {event.content_type}, Text: '{event.text or '<no text>'}'"
            )
        elif isinstance(event, types.CallbackQuery):
            user = event.from_user
            logger.info(
                f"New CALLBACK - User: {user.full_name} (@{user.username}) "
                f"ID: {user.id}, Chat: {event.message.chat.id if event.message else 'N/A'}, "
                f"Data: '{event.data}'"
            )

        return await handler(event, data)


async def on_startup():
    """Initialize database and perform startup tasks"""
    try:
        await TestManager.initialize_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.critical(f"Startup failed: {e}", exc_info=True)
        raise


async def on_shutdown():
    """Cleanup tasks before shutdown"""
    try:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Shutdown error: {e}", exc_info=True)


async def main():
    """Main application entry point"""
    try:
        bot = Bot(
            token=Config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        dp = Dispatcher()

        # Set up middleware for both messages and callbacks
        dp.message.middleware(LoggingMiddleware())
        dp.callback_query.middleware(LoggingMiddleware())

        # Include routers
        dp.include_router(router)

        # Perform startup tasks
        await on_startup()

        # Clean previous updates
        await bot.delete_webhook(drop_pending_updates=True)

        logger.info("Bot started successfully")
        await dp.start_polling(bot)

    except Exception as e:
        logger.critical(f"Fatal error in main: {e}", exc_info=True)
    finally:
        await on_shutdown()
        if 'bot' in locals():
            await bot.session.close()
            logger.info("Bot session closed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Unexpected error: {e}", exc_info=True)