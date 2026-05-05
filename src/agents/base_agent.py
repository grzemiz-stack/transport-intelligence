"""Klasa bazowa dla wszystkich agentow zbierajacych dane.

Definiuje wspolny interfejs: fetch(), parse(), validate(), send_to_supervisor().
Kazdy agent dziedziczy po BaseAgent i implementuje logike specyficzna dla zrodla.
Obsluguje retry logic z exponential backoff, configurowalny interwal scrapowania,
logging per agent oraz wymusza metadata na kazdym zebranym zdarzeniu.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "TransportIntelligence/1.0 (Research Bot)"
DEFAULT_TIMEOUT = 30.0


class SourceType(str, Enum):
    """Typ zrodla danych agenta."""

    POLICE = "police"
    NEWS = "news"
    FORUM = "forum"
    TELEGRAM = "telegram"
    REDDIT = "reddit"
    ALERTS = "alerts"
    FINANCIAL = "financial"


@dataclass
class RawRecord:
    """Surowy rekord pobrany przez agenta.

    Kazdy rekord MUSI zawierac pelne metadata zrodla:
    source_url, source_name, trust_score, is_official, timestamp, country_code.
    """

    source_name: str
    source_url: str
    title: str
    text: str
    country_code: str
    trust_score: float
    is_official: bool
    source_type: SourceType
    language: str | None = None
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """Abstrakcyjna klasa bazowa agenta zbierajacego dane.

    Atrybuty:
        country_code: kod ISO 2-literowy kraju (np. 'DE', 'PL')
        language: kod jezyka (np. 'de', 'pl')
        source_type: typ zrodla (police/news/forum/telegram/reddit/alerts/financial)
        source_name: nazwa zrodla danych
        source_url: URL zrodla danych
        trust_score: wiarygodnosc zrodla (0.0 - 1.0)
        is_official_source: czy zrodlo jest oficjalne (policja, rejestr sadowy)
        scrape_interval_minutes: interwal scrapowania w minutach
        max_retries: maksymalna liczba ponownych prob przy bledzie
        base_retry_delay: bazowe opoznienie retry w sekundach (exponential backoff)
    """

    def __init__(
        self,
        country_code: str,
        language: str,
        source_type: SourceType,
        source_name: str,
        source_url: str,
        trust_score: float = 0.5,
        is_official: bool = False,
        scrape_interval_minutes: int = 30,
        event_queue: asyncio.Queue | None = None,
        max_retries: int = 3,
        base_retry_delay: float = 5.0,
    ):
        self.country_code = country_code.upper()
        self.language = language
        self.source_type = source_type
        self.source_name = source_name
        self.source_url = source_url
        self.trust_score = max(0.0, min(1.0, trust_score))
        self.is_official_source = is_official
        self.scrape_interval_minutes = scrape_interval_minutes
        self.max_retries = max_retries
        self.base_retry_delay = base_retry_delay
        self._event_queue = event_queue
        self._running = False
        self._supervisor = None
        self._last_heartbeat: datetime | None = None
        self._session: httpx.AsyncClient | None = None
        self.retry_count = 0
        self.last_run: datetime | None = None
        self.events_collected = 0
        self.errors_count = 0
        self._logger = logging.getLogger(
            f"{country_code.lower()}.{source_type.value}.{source_name}"
        )

    # -- nazwa agenta (compat) --------------------------------------------------

    @property
    def name(self) -> str:
        return f"{self.country_code.lower()}_{self.source_type.value}_{self.source_name}"

    # -- httpx session -----------------------------------------------------------

    async def get_session(self) -> httpx.AsyncClient:
        """Lazy-init httpx.AsyncClient z timeout=30s i custom User-Agent."""
        if self._session is None or self._session.is_closed:
            self._session = httpx.AsyncClient(
                timeout=httpx.Timeout(DEFAULT_TIMEOUT),
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
        return self._session

    # -- abstrakcyjne metody do nadpisania per agent ----------------------------

    @abstractmethod
    async def fetch(self) -> str:
        """Pobiera surowy HTML/JSON ze zrodla. Do nadpisania per agent."""
        ...

    @abstractmethod
    async def parse(self, raw_data: str) -> list[dict]:
        """Parsuje surowe dane na liste eventow.

        Kazdy event dict MUSI zawierac: title, description, date, source_url, raw_text.
        """
        ...

    # -- walidacja i metadata ----------------------------------------------------

    async def validate(self, events: list[dict]) -> list[dict]:
        """Waliduje przetworzone eventy — odrzuca niekompletne lub bez zrodla.

        Event bez source_url jest ZAWSZE odrzucany (wymog prawny).
        Dodaje metadata: country_code, language, source_name, source_type,
        trust_score, is_official, collected_at.
        """
        valid = []
        for ev in events:
            if not ev.get("source_url"):
                self._logger.warning("Odrzucono event bez source_url: %s", ev.get("title", "?"))
                continue
            if not ev.get("title") and not ev.get("description") and not ev.get("raw_text"):
                self._logger.warning("Odrzucono event bez tresci")
                continue
            ev.setdefault("country_code", self.country_code)
            ev.setdefault("language", self.language)
            ev.setdefault("source_name", self.source_name)
            ev.setdefault("source_type", self.source_type.value)
            ev.setdefault("trust_score", self.trust_score)
            ev.setdefault("is_official", self.is_official_source)
            ev.setdefault("collected_at", datetime.utcnow().isoformat())
            valid.append(ev)
        return valid

    # -- wysylanie do supervisora ------------------------------------------------

    async def send_to_supervisor(self, events: list[dict]) -> None:
        """Wysyla przetworzone eventy do kolejki supervisora."""
        if not events:
            return
        if self._event_queue is not None:
            for ev in events:
                await self._event_queue.put(ev)
            self._logger.info("Wyslano %d eventow do kolejki supervisora", len(events))
        elif self._supervisor is not None:
            await self._supervisor.receive_data(self.name, events)
            self._logger.info("Wyslano %d eventow do supervisora", len(events))
        else:
            self._logger.warning("Brak przypisanego supervisora ani kolejki — %d eventow utraconych", len(events))

    # -- thread helper for blocking parse() ------------------------------------

    def _parse_in_thread(self, raw_data: str) -> list[dict]:
        """Run async parse() in a dedicated event loop on a worker thread."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.parse(raw_data))
        finally:
            loop.close()

    # -- cykl scrapowania --------------------------------------------------------

    async def run_once(self) -> list[dict]:
        """Wykonuje pojedynczy cykl: fetch -> parse -> validate.

        Przy bledzie: retry z exponential backoff (2^retry * 5 sekund).
        Aktualizuje last_run, events_collected, errors_count.
        """
        self._last_heartbeat = datetime.utcnow()
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                raw_data = await self.fetch()
                events = await asyncio.get_running_loop().run_in_executor(
                    None, self._parse_in_thread, raw_data
                )
                validated = await self.validate(events)
                self.last_run = datetime.utcnow()
                self.events_collected += len(validated)
                self.retry_count = 0
                self._logger.info(
                    "Zebrano %d eventow (proba %d/%d)", len(validated), attempt, self.max_retries
                )
                self._last_heartbeat = datetime.utcnow()
                return validated
            except Exception as e:
                last_error = e
                self.errors_count += 1
                self.retry_count = attempt
                delay = self.base_retry_delay * (2 ** (attempt - 1))
                self._logger.warning(
                    "Blad w probie %d/%d: %s — retry za %.0fs",
                    attempt,
                    self.max_retries,
                    e,
                    delay,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(delay)

        self._logger.error("Wszystkie proby wyczerpane. Ostatni blad: %s", last_error)
        self._last_heartbeat = datetime.utcnow()
        return []

    async def run_loop(self) -> None:
        """Uruchamia agenta w petli z configurowalnym interwalem."""
        self._running = True
        self._logger.info("Start petli (interwal: %d min)", self.scrape_interval_minutes)
        while self._running:
            try:
                events = await self.run_once()
                await self.send_to_supervisor(events)
            except Exception as e:
                self._logger.error("Nieoczekiwany blad w petli: %s", e)
            await asyncio.sleep(self.scrape_interval_minutes * 60)

    async def stop(self) -> None:
        """Zatrzymuje petle agenta i zamyka session."""
        self._running = False
        if self._session is not None and not self._session.is_closed:
            await self._session.aclose()
            self._session = None
        self._logger.info("Zatrzymany")

    # -- status / introspection --------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Czy agent jest uruchomiony."""
        return self._running

    @property
    def last_heartbeat(self) -> datetime | None:
        """Czas ostatniego heartbeatu."""
        return self._last_heartbeat

    def get_status(self) -> dict:
        """Zwraca status agenta."""
        return {
            "source_name": self.source_name,
            "source_url": self.source_url,
            "country_code": self.country_code,
            "source_type": self.source_type.value,
            "is_running": self._running,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "events_collected": self.events_collected,
            "errors_count": self.errors_count,
            "trust_score": self.trust_score,
            "is_official": self.is_official_source,
        }

    def set_supervisor(self, supervisor) -> None:
        """Przypisuje supervisora do agenta."""
        self._supervisor = supervisor

    def set_event_queue(self, queue: asyncio.Queue) -> None:
        """Ustawia kolejke eventow do supervisora."""
        self._event_queue = queue
