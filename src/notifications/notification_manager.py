"""NotificationManager — koordynuje wysylke notyfikacji do subskrybentow."""

import logging
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Alert,
    Company,
    CrimeHotspot,
    Event,
    Severity,
    Subscriber,
    SubscriptionTier,
)
from src.db.postgres import async_session
from src.notifications.email_sender import EmailSender

logger = logging.getLogger(__name__)


class NotificationManager:
    """Zarzadza wysylka notyfikacji email do subskrybentow."""

    def __init__(self):
        self.email_sender = EmailSender()

    async def notify_alert(self, alert: Alert, db: AsyncSession | None = None) -> int:
        """Wysyla notyfikacje o alercie do pasujacych subskrybentow.

        Returns: liczba wyslanych emaili.
        """
        alert_countries = alert.country_codes or []
        alert_severity = (alert.severity or "medium").lower()

        # Tylko CRITICAL i HIGH
        if alert_severity not in ("critical", "high"):
            return 0

        sent_count = 0

        async def _do(session: AsyncSession):
            nonlocal sent_count

            # Pobierz aktywnych subskrybentow z tierem PREMIUM_ALERTS lub ENTERPRISE_API
            result = await session.execute(
                select(Subscriber).where(
                    Subscriber.is_active.is_(True),
                    Subscriber.subscription_tier.in_([
                        SubscriptionTier.PREMIUM_ALERTS.value,
                        SubscriptionTier.ENTERPRISE_API.value,
                    ]),
                )
            )
            subscribers = result.scalars().all()

            for sub in subscribers:
                # Filtruj po krajach subskrybenta
                sub_countries = sub.subscribed_countries or []
                if sub_countries and alert_countries:
                    if not set(alert_countries) & set(sub_countries):
                        continue

                alert_dict = {
                    "id": str(alert.id),
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "title": alert.title,
                    "description": alert.description,
                    "country_codes": alert_countries,
                    "region": alert.region,
                    "triggered_at": (
                        alert.triggered_at.strftime("%Y-%m-%d %H:%M UTC")
                        if alert.triggered_at else ""
                    ),
                    "related_events": [],
                }

                ok = await self.email_sender.send_alert_email(
                    alert_dict, [sub.contact_email],
                )
                if ok:
                    sent_count += 1

            # Oznacz alert jako notification_sent
            if sent_count > 0:
                alert.notification_sent = True
                await session.commit()

        if db is not None:
            await _do(db)
        else:
            async with async_session() as session:
                # Re-fetch alert in this session so we can update it
                result = await session.execute(
                    select(Alert).where(Alert.id == alert.id)
                )
                alert_obj = result.scalar_one_or_none()
                if alert_obj:
                    alert = alert_obj
                    await _do(session)

        if sent_count:
            logger.info("Alert notification sent to %d subscribers: %s", sent_count, alert.title)
        return sent_count

    async def notify_report(self, report: dict, pdf_path: str | None = None) -> int:
        """Wysyla notyfikacje o nowym raporcie do subskrybentow.

        Returns: liczba wyslanych emaili.
        """
        sent_count = 0
        report_countries = report.get("countries") or []

        async with async_session() as session:
            result = await session.execute(
                select(Subscriber).where(
                    Subscriber.is_active.is_(True),
                )
            )
            subscribers = result.scalars().all()

            for sub in subscribers:
                sub_countries = sub.subscribed_countries or []
                if sub_countries and report_countries:
                    if not set(report_countries) & set(sub_countries):
                        continue

                ok = await self.email_sender.send_report_email(
                    report, [sub.contact_email], pdf_path=pdf_path,
                )
                if ok:
                    sent_count += 1

        if sent_count:
            logger.info("Report notification sent to %d subscribers: %s", sent_count, report.get("title"))
        return sent_count

    async def send_daily_digest(self) -> int:
        """Wysyla dzienny digest — podsumowanie z ostatnich 24h.

        Returns: liczba wyslanych emaili.
        """
        sent_count = 0
        now = datetime.utcnow()
        day_ago = now - timedelta(hours=24)

        async with async_session() as session:
            # Zbierz dane z ostatnich 24h
            events_result = await session.execute(
                select(Event).where(Event.date_collected >= day_ago)
            )
            recent_events = events_result.scalars().all()

            alerts_result = await session.execute(
                select(Alert).where(Alert.triggered_at >= day_ago)
            )
            recent_alerts = alerts_result.scalars().all()

            hotspots_result = await session.execute(
                select(CrimeHotspot).where(CrimeHotspot.last_calculated >= day_ago)
            )
            new_hotspots = hotspots_result.scalars().all()

            companies_result = await session.execute(
                select(Company)
                .where(Company.risk_score >= 0.7)
                .order_by(Company.risk_score.desc())
                .limit(5)
            )
            at_risk = companies_result.scalars().all()

            # Buduj summary
            critical_count = sum(
                1 for e in recent_events if e.severity == Severity.CRITICAL.value
            )

            per_country: dict[str, int] = Counter(
                e.country_code for e in recent_events
            )

            top_events = [
                {
                    "title": e.title[:120],
                    "severity": e.severity,
                    "country": e.country_code,
                }
                for e in sorted(
                    recent_events,
                    key=lambda x: (
                        {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(
                            x.severity, 5
                        ),
                        x.date_collected or datetime.min,
                    ),
                )[:10]
            ]

            summary = {
                "total_events": len(recent_events),
                "critical_count": critical_count,
                "alerts_count": len(recent_alerts),
                "top_events": top_events,
                "new_hotspots": [
                    {
                        "region": h.region,
                        "country": h.country_code,
                        "event_count": h.event_count,
                        "trend": h.trend,
                    }
                    for h in new_hotspots[:5]
                ],
                "companies_at_risk": [
                    {
                        "name": c.name,
                        "country": c.country_code,
                        "risk_score": round(c.risk_score, 2),
                    }
                    for c in at_risk
                ],
                "per_country": dict(per_country.most_common(10)),
                "period_start": day_ago.strftime("%Y-%m-%d %H:%M UTC"),
                "period_end": now.strftime("%Y-%m-%d %H:%M UTC"),
            }

            # Pobierz subskrybentow
            subs_result = await session.execute(
                select(Subscriber).where(Subscriber.is_active.is_(True))
            )
            subscribers = subs_result.scalars().all()

            for sub in subscribers:
                ok = await self.email_sender.send_digest_email(
                    summary, [sub.contact_email],
                )
                if ok:
                    sent_count += 1

        if sent_count:
            logger.info(
                "Daily digest sent to %d subscribers — %d events, %d alerts",
                sent_count, len(recent_events), len(recent_alerts),
            )
        return sent_count
