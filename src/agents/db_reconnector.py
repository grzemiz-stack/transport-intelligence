"""DBReconnector — reconnects to PostgreSQL with exponential backoff."""

import asyncio
import logging

from sqlalchemy import text

logger = logging.getLogger("watchdog.db_reconnector")


class DBReconnector:
    """Stateless reconnector: dispose pool, retry SELECT 1 up to 3 times."""

    MAX_RETRIES = 3
    BASE_DELAY = 2  # seconds — backoff: 2, 4, 8

    async def check_and_reconnect(self) -> bool:
        from src.db.postgres import async_session, engine

        # Dispose stale connections
        await engine.dispose()

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                async with async_session() as session:
                    await session.execute(text("SELECT 1"))
                logger.info("DB reconnect OK (attempt %d/%d)", attempt, self.MAX_RETRIES)
                return True
            except Exception as e:
                delay = self.BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "DB reconnect attempt %d/%d failed: %s — retry in %ds",
                    attempt, self.MAX_RETRIES, e, delay,
                )
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(delay)

        logger.error("DB reconnect FAILED after %d attempts", self.MAX_RETRIES)
        return False
