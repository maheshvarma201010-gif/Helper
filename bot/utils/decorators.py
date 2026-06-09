import asyncio
import logging
from functools import wraps
from pyrogram import errors

logger = logging.getLogger(__name__)

def retry_on_flood(max_retries=3, delay=2):
    """
    Decorator to retry a function if it encounters Telegram errors,
    specifically handling FloodWait and temporary connection issues.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except errors.FloodWait as e:
                    logger.warning(f"FloodWait: Waiting {e.value}s before retry (Attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(e.value + 1)
                except (errors.InternalServerError, errors.ServiceUnavailable) as e:
                    logger.warning(f"Telegram Server Error: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    last_err = e
                except Exception as e:
                    # For other errors, we might not want to retry or handle specifically
                    logger.error(f"Error in {func.__name__}: {e}")
                    raise e
            if last_err:
                raise last_err
        return wrapper
    return decorator
