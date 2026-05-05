"""Harmonogram automatycznego generowania raportow.

Uruchamia generowanie raportow co 2 tygodnie i co miesiac
za pomoca APScheduler.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.reports.generator import ReportGenerator

logger = logging.getLogger(__name__)


class ReportScheduler:
    """Scheduler raportow cyklicznych."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.report_generator = ReportGenerator()
        self.jobs: dict[str, dict] = {}
        self._alert_queue: asyncio.Queue | None = None

    # ------------------------------------------------------------------
    # Schedule configuration
    # ------------------------------------------------------------------

    def schedule_biweekly(self, countries: list[str], language: str = "en"):
        """Dodaje job: co 2 tygodnie w poniedzialek o 6:00 UTC."""
        job_id = f"biweekly_{language}"
        job = self.scheduler.add_job(
            self._run_biweekly,
            trigger=CronTrigger(day_of_week="mon", hour=6, minute=0),
            kwargs={"countries": countries, "language": language},
            id=job_id,
            name=f"Biweekly report ({language})",
            max_instances=1,
            # APScheduler CronTrigger runs every Monday; we skip every other one
            # by checking inside _run_biweekly
        )
        self.jobs[job_id] = {
            "type": "biweekly",
            "countries": countries,
            "language": language,
            "job": job,
            "last_run": None,
        }
        logger.info("Scheduled biweekly report: every 2 weeks, Mon 06:00 UTC, lang=%s", language)

    def schedule_monthly(self, countries: list[str], language: str = "en"):
        """Dodaje job: 1-go dnia miesiaca o 6:00 UTC."""
        job_id = f"monthly_{language}"
        job = self.scheduler.add_job(
            self._run_monthly,
            trigger=CronTrigger(day=1, hour=6, minute=0),
            kwargs={"countries": countries, "language": language},
            id=job_id,
            name=f"Monthly report ({language})",
            max_instances=1,
        )
        self.jobs[job_id] = {
            "type": "monthly",
            "countries": countries,
            "language": language,
            "job": job,
            "last_run": None,
        }
        logger.info("Scheduled monthly report: 1st of month, 06:00 UTC, lang=%s", language)

    def schedule_sales(self, countries: list[str], language: str = "pl"):
        """Dodaje job: 1-go i 15-go dnia miesiaca o 6:00 UTC."""
        job_id = f"sales_{language}"
        job = self.scheduler.add_job(
            self._run_sales,
            trigger=CronTrigger(day="1,15", hour=6, minute=0),
            kwargs={"countries": countries, "language": language},
            id=job_id,
            name=f"Sales report ({language})",
            max_instances=1,
        )
        self.jobs[job_id] = {
            "type": "sales",
            "countries": countries,
            "language": language,
            "job": job,
            "last_run": None,
        }
        logger.info(
            "Scheduled sales report: 1st & 15th of month, 06:00 UTC, lang=%s",
            language,
        )

    def schedule_alert_check(self, alert_queue: asyncio.Queue | None = None):
        """Dodaje job: co 15 minut sprawdza alert_queue."""
        self._alert_queue = alert_queue
        job_id = "alert_check"
        job = self.scheduler.add_job(
            self._run_alert_check,
            trigger=IntervalTrigger(minutes=15),
            id=job_id,
            name="Alert check (every 15 min)",
            max_instances=1,
        )
        self.jobs[job_id] = {
            "type": "alert_check",
            "job": job,
            "last_run": None,
        }
        logger.info("Scheduled alert check: every 15 minutes")

    # ------------------------------------------------------------------
    # Job runners
    # ------------------------------------------------------------------

    async def _run_biweekly(self, countries: list[str], language: str = "en"):
        """Generuje raport 2-tygodniowy.

        Sprawdza czy minelo 14 dni od ostatniego raportu (zeby nie
        generowac co tydzien, bo CronTrigger jest co poniedzialek).
        """
        job_id = f"biweekly_{language}"
        last_run = self.jobs.get(job_id, {}).get("last_run")

        if last_run and (datetime.utcnow() - last_run).days < 12:
            logger.debug("Skipping biweekly — last run was %s", last_run)
            return

        period_end = date.today()
        period_start = period_end - timedelta(days=14)

        logger.info("Generating biweekly report: %s to %s", period_start, period_end)

        # Placeholder: in production, fetch events from database
        events = await self._fetch_events(period_start, period_end, countries)

        try:
            path = await self.report_generator.generate_biweekly(
                events, countries, period_start, period_end, language,
            )
            logger.info("Biweekly report saved: %s", path)
            if job_id in self.jobs:
                self.jobs[job_id]["last_run"] = datetime.utcnow()
        except Exception:
            logger.exception("Failed to generate biweekly report")

    async def _run_monthly(self, countries: list[str], language: str = "en"):
        """Generuje raport miesieczny za poprzedni miesiac."""
        today = date.today()
        # Previous month
        first_of_this_month = today.replace(day=1)
        period_end = first_of_this_month - timedelta(days=1)
        period_start = period_end.replace(day=1)

        logger.info("Generating monthly report: %s to %s", period_start, period_end)

        events = await self._fetch_events(period_start, period_end, countries)

        try:
            path = await self.report_generator.generate_monthly(
                events, countries, period_start, period_end, language,
            )
            logger.info("Monthly report saved: %s", path)
            job_id = f"monthly_{language}"
            if job_id in self.jobs:
                self.jobs[job_id]["last_run"] = datetime.utcnow()
        except Exception:
            logger.exception("Failed to generate monthly report")

    async def _run_sales(self, countries: list[str], language: str = "pl"):
        """Generuje sales intelligence report."""
        logger.info("Generating sales report, lang=%s", language)
        try:
            from src.reports.live_generator import LiveReportGenerator
            gen = LiveReportGenerator()
            path = await gen.generate_sales_report(
                period_days=14, language=language, countries=countries,
            )
            logger.info("Sales report saved: %s", path)
            job_id = f"sales_{language}"
            if job_id in self.jobs:
                self.jobs[job_id]["last_run"] = datetime.utcnow()
        except Exception:
            logger.exception("Failed to generate sales report")

    async def _run_alert_check(self):
        """Sprawdza alert_queue i generuje raporty alertowe."""
        if not self._alert_queue:
            return

        processed = 0
        while not self._alert_queue.empty():
            try:
                alert = self._alert_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            related_events = alert.get("related_events", [])
            language = alert.get("language", "en")

            try:
                path = await self.report_generator.generate_alert_report(
                    alert, related_events, language,
                )
                logger.info("Alert report generated: %s", path)
                processed += 1
            except Exception:
                logger.exception("Failed to generate alert report")

        if processed:
            logger.info("Processed %d alert(s)", processed)
            if "alert_check" in self.jobs:
                self.jobs["alert_check"]["last_run"] = datetime.utcnow()

    # ------------------------------------------------------------------
    # Data fetching (stub — to be wired to database)
    # ------------------------------------------------------------------

    async def _fetch_events(
        self, period_start: date, period_end: date, countries: list[str],
    ) -> list[dict]:
        """Pobiera eventy z bazy danych.

        Stub — w produkcji laczy sie z PostgreSQL przez src.db.postgres.
        """
        # TODO: integrate with database layer
        logger.debug(
            "Fetching events for %s to %s, countries=%s (stub — returning empty)",
            period_start, period_end, countries,
        )
        return []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Uruchamia scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("ReportScheduler started with %d job(s)", len(self.jobs))

    def stop(self):
        """Zatrzymuje scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("ReportScheduler stopped")

    def get_scheduled_jobs(self) -> list[dict]:
        """Zwraca liste zaplanowanych jobow z next_run_time."""
        result = []
        for job_id, info in self.jobs.items():
            job = info.get("job")
            next_run = None
            if job:
                try:
                    next_run = str(job.next_run_time) if job.next_run_time else None
                except Exception:
                    pass

            result.append({
                "job_id": job_id,
                "type": info.get("type"),
                "countries": info.get("countries", []),
                "language": info.get("language", ""),
                "last_run": str(info.get("last_run")) if info.get("last_run") else None,
                "next_run": next_run,
            })
        return result
