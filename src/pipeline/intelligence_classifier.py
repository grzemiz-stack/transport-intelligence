"""IntelligenceClassifier — batch job klasyfikujacy eventy do tier-ow.

Uruchamiany co 5 minut przez scheduler.
Przetwarza eventy bez intelligence_tier (NULL) w batchach.
"""

import logging
import time

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Event
from src.pipeline.intelligence_filter import IntelligenceFilter

logger = logging.getLogger("intelligence_classifier")

BATCH_SIZE = 100


class IntelligenceClassifier:
    """Batch processor that classifies unclassified events."""

    def __init__(self):
        self.filter = IntelligenceFilter()

    async def run(self, session: AsyncSession) -> dict:
        """Classify all events with intelligence_tier IS NULL.

        Returns dict with counts: {processed, tier_1, tier_2, tier_3, tier_4}.
        """
        start = time.time()

        # Count unclassified
        count_q = select(func.count(Event.id)).where(Event.intelligence_tier.is_(None))
        total_unclassified = (await session.execute(count_q)).scalar() or 0

        if total_unclassified == 0:
            logger.info("No unclassified events found")
            return {"processed": 0, "tier_1": 0, "tier_2": 0, "tier_3": 0, "tier_4": 0}

        logger.info("Found %d unclassified events", total_unclassified)

        stats = {"processed": 0, "tier_1": 0, "tier_2": 0, "tier_3": 0, "tier_4": 0}

        # Process in batches
        offset = 0
        while offset < total_unclassified:
            q = (
                select(Event)
                .where(Event.intelligence_tier.is_(None))
                .order_by(Event.date_collected.desc())
                .limit(BATCH_SIZE)
            )
            result = await session.execute(q)
            events = result.scalars().all()

            if not events:
                break

            for event in events:
                tier_result = self.filter.classify(
                    title=event.title or "",
                    description=event.description or event.raw_text or "",
                    event_type=event.event_type,
                    tags=event.tags,
                )

                event.intelligence_tier = tier_result.tier
                event.intelligence_category = tier_result.category
                event.intelligence_confidence = tier_result.confidence

                stats["processed"] += 1
                stats[f"tier_{tier_result.tier}"] += 1

            await session.commit()
            offset += len(events)

            logger.info(
                "Classified batch: %d/%d events (T1:%d T2:%d T3:%d T4:%d)",
                stats["processed"], total_unclassified,
                stats["tier_1"], stats["tier_2"], stats["tier_3"], stats["tier_4"],
            )

        duration = time.time() - start
        logger.info(
            "Classification complete: %d events in %.1fs — T1:%d T2:%d T3:%d T4:%d",
            stats["processed"], duration,
            stats["tier_1"], stats["tier_2"], stats["tier_3"], stats["tier_4"],
        )
        return stats


async def run_classification():
    """Standalone entry point for scheduler job."""
    from src.db.postgres import async_session

    classifier = IntelligenceClassifier()
    async with async_session() as session:
        return await classifier.run(session)
