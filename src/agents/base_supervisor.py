"""Klasa bazowa Country Supervisora - zarzadza agentami danego kraju.

Country Supervisor laduje konfiguracje ze swojego config.yaml,
uruchamia/zatrzymuje/restartuje agentow (police, news, forums, telegram,
reddit, alerts, financial), zbiera od nich dane i przepuszcza
przez pipeline (source_validator -> anonymizer -> gdpr_filter -> legal_filter)
PRZED wyslaniem wyzej.
Monitoruje heartbeat agentow (5 min timeout -> restart).
Prowadzi statystyki: zebrane eventy, odfiltrowane, bledy, uptime.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import yaml
from bs4 import BeautifulSoup

from src.agents.base_agent import BaseAgent, SourceType

logger = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT_MINUTES = 5
COLLECT_INTERVAL_SECONDS = 10
HEARTBEAT_CHECK_INTERVAL_SECONDS = 60

SOURCE_TYPE_MAP: dict[str, SourceType] = {
    "police": SourceType.POLICE,
    "news": SourceType.NEWS,
    "forums": SourceType.FORUM,
    "telegram": SourceType.TELEGRAM,
    "reddit": SourceType.REDDIT,
    "alerts": SourceType.ALERTS,
    "financial": SourceType.FINANCIAL,
}


@dataclass
class SupervisorStats:
    """Statystyki Country Supervisora."""

    events_collected: int = 0
    events_filtered_legal: int = 0
    events_filtered_gdpr: int = 0
    events_anonymized: int = 0
    errors: int = 0
    start_time: datetime | None = None
    last_collection: datetime | None = None

    @property
    def uptime_seconds(self) -> float:
        if self.start_time is None:
            return 0.0
        return (datetime.utcnow() - self.start_time).total_seconds()

    def to_dict(self) -> dict:
        return {
            "events_collected": self.events_collected,
            "events_filtered_legal": self.events_filtered_legal,
            "events_filtered_gdpr": self.events_filtered_gdpr,
            "events_anonymized": self.events_anonymized,
            "errors": self.errors,
            "uptime_seconds": self.uptime_seconds,
            "last_collection": self.last_collection.isoformat() if self.last_collection else None,
        }


# ---------------------------------------------------------------------------
# GenericWebAgent — domyslna implementacja fetch/parse przez httpx + BS4
# ---------------------------------------------------------------------------


class GenericWebAgent(BaseAgent):
    """Generyczny agent webowy — pobiera strone przez httpx i parsuje BS4.

    Uzywany jako domyslna implementacja gdy brak specjalizowanego agenta
    per source type / country.
    """

    async def fetch(self) -> str:
        """Pobiera surowy HTML ze source_url przez httpx GET."""
        session = await self.get_session()
        response = await session.get(self.source_url)
        response.raise_for_status()
        return response.text

    async def parse(self, raw_data: str) -> list[dict]:
        """Parsuje HTML przez BeautifulSoup — wyciaga artykuly/newsy.

        Szuka:
        - tytulow (h1, h2, h3, article title, .title, .headline)
        - tresci (p wewnatrz article, .content, .body, .entry-content)
        - dat (time[datetime], .date, .published, meta[pubdate])
        - linkow (a[href])
        """
        soup = BeautifulSoup(raw_data, "html.parser")
        events: list[dict] = []

        # Szukaj artykulow / elementow z trescia
        articles = soup.find_all("article")
        if not articles:
            # Fallback: szukaj sekcji z naglowkami
            articles = self._find_article_blocks(soup)

        for article in articles:
            title = self._extract_title(article)
            description = self._extract_description(article)
            date = self._extract_date(article)
            link = self._extract_link(article)
            raw_text = article.get_text(separator=" ", strip=True)

            if not title and not description:
                continue

            events.append({
                "title": title or "",
                "description": description or "",
                "date": date or "",
                "source_url": link or self.source_url,
                "raw_text": raw_text[:5000],  # limit surowego tekstu
            })

        # Jesli nie znaleziono artykulow, sprobuj ekstrakcji z calej strony
        if not events:
            page_text = soup.get_text(separator=" ", strip=True)
            if len(page_text) > 50:
                events.append({
                    "title": self._extract_page_title(soup) or self.source_name,
                    "description": page_text[:2000],
                    "date": datetime.utcnow().isoformat(),
                    "source_url": self.source_url,
                    "raw_text": page_text[:5000],
                })

        return events

    # -- helpery ekstrakcji ------------------------------------------------------

    def _find_article_blocks(self, soup: BeautifulSoup) -> list:
        """Fallback: szuka blokow z naglowkami h2/h3 jako pseudo-artykulow."""
        blocks = []
        for heading in soup.find_all(["h2", "h3"]):
            parent = heading.find_parent(["div", "section", "li"])
            if parent and parent not in blocks:
                blocks.append(parent)
        return blocks[:20]  # max 20 blokow

    def _extract_title(self, element) -> str | None:
        """Wyciaga tytul z elementu."""
        for tag in ["h1", "h2", "h3"]:
            found = element.find(tag)
            if found:
                return found.get_text(strip=True)
        for cls in ["title", "headline", "entry-title"]:
            found = element.find(class_=cls)
            if found:
                return found.get_text(strip=True)
        return None

    def _extract_description(self, element) -> str | None:
        """Wyciaga opis/tresc z elementu."""
        for cls in ["content", "body", "entry-content", "summary", "excerpt"]:
            found = element.find(class_=cls)
            if found:
                return found.get_text(separator=" ", strip=True)[:2000]
        paragraphs = element.find_all("p")
        if paragraphs:
            text = " ".join(p.get_text(strip=True) for p in paragraphs[:5])
            return text[:2000] if text else None
        return None

    def _extract_date(self, element) -> str | None:
        """Wyciaga date z elementu."""
        time_tag = element.find("time")
        if time_tag:
            return time_tag.get("datetime") or time_tag.get_text(strip=True)
        for cls in ["date", "published", "pubdate", "timestamp"]:
            found = element.find(class_=cls)
            if found:
                return found.get_text(strip=True)
        meta = element.find("meta", attrs={"property": "article:published_time"})
        if meta:
            return meta.get("content", "")
        return None

    def _extract_link(self, element) -> str | None:
        """Wyciaga link z elementu."""
        a_tag = element.find("a", href=True)
        if a_tag:
            href = a_tag["href"]
            if href.startswith("http"):
                return href
            # Proba zbudowania absolutnego URL
            if href.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(self.source_url)
                return f"{parsed.scheme}://{parsed.netloc}{href}"
        return None

    def _extract_page_title(self, soup: BeautifulSoup) -> str | None:
        """Wyciaga tytul strony."""
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True)
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return None


# ---------------------------------------------------------------------------
# CountrySupervisor
# ---------------------------------------------------------------------------


class CountrySupervisor:
    """Supervisor zarzadzajacy agentami jednego kraju.

    Atrybuty:
        country_code: kod ISO 2-literowy kraju
        country_name: pelna nazwa kraju
        languages: lista jezykow uzywanych w kraju
        timezone: strefa czasowa kraju
        region: region europejski (Western/Eastern/Southern/Northern/Southeastern)
        agents: slownik agentow (name -> BaseAgent)
        config: zaladowana konfiguracja z config.yaml
        stats: statystyki przetwarzania
    """

    def __init__(self, country_code: str, config_path: str | Path):
        self.country_code = country_code.upper()
        self.config_path = Path(config_path)
        self.config: dict = {}
        self.country_name: str = ""
        self.languages: list[str] = []
        self.timezone: str = "UTC"
        self.region: str = ""
        self.agents: dict[str, BaseAgent] = {}
        self._agent_tasks: dict[str, asyncio.Task] = {}
        self._heartbeat_task: asyncio.Task | None = None
        self._running = False
        self._master_supervisor = None
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.stats = SupervisorStats()
        self._logger = logging.getLogger(f"supervisor.{country_code.lower()}")

    # -- konfiguracja -----------------------------------------------------------

    def load_config(self) -> dict:
        """Laduje konfiguracje kraju z pliku config.yaml. Waliduje strukture."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config nie znaleziony: {self.config_path}")

        with open(self.config_path) as f:
            self.config = yaml.safe_load(f)

        if not self.config:
            raise ValueError(f"Pusty config: {self.config_path}")

        country_cfg = self.config.get("country", {})
        if not country_cfg.get("code"):
            raise ValueError(f"Brak 'country.code' w {self.config_path}")

        self.country_name = country_cfg.get("name", self.country_code)
        self.languages = country_cfg.get("languages", [])
        self.timezone = country_cfg.get("timezone", "UTC")
        self.region = country_cfg.get("region", "")
        return self.config

    # -- tworzenie agentow ------------------------------------------------------

    def create_agents(self) -> None:
        """Tworzy instancje agentow na podstawie config.yaml.

        Dla kazdego source_type (police, news, forums, ...) i kazdego zrodla
        w danym typie tworzy GenericWebAgent z odpowiednimi parametrami
        i przekazuje mu event_queue.
        """
        sources_cfg = self.config.get("sources", {})
        language = self.languages[0] if self.languages else "en"

        for source_type_key, sources in sources_cfg.items():
            source_type = SOURCE_TYPE_MAP.get(source_type_key)
            if source_type is None:
                self._logger.warning("Nieznany typ zrodla: %s — pomijam", source_type_key)
                continue

            if not isinstance(sources, list):
                continue

            for source_cfg in sources:
                name = source_cfg.get("name", "unknown")
                url = source_cfg.get("url", "")
                trust = source_cfg.get("trust_score", 0.5)
                is_official = source_cfg.get("is_official", False)
                interval = source_cfg.get("scrape_interval_minutes", 30)

                if not url or url == "placeholder":
                    self._logger.debug("Pomijam zrodlo '%s' — brak URL", name)
                    continue

                agent = GenericWebAgent(
                    country_code=self.country_code,
                    language=language,
                    source_type=source_type,
                    source_name=name,
                    source_url=url,
                    trust_score=trust,
                    is_official=is_official,
                    scrape_interval_minutes=interval,
                    event_queue=self.event_queue,
                )
                self.register_agent(agent)

        self._logger.info(
            "Utworzono %d agentow dla %s (%s)",
            len(self.agents), self.country_name, self.country_code,
        )

    # -- rejestracja agentow ----------------------------------------------------

    def register_agent(self, agent: BaseAgent) -> None:
        """Rejestruje agenta pod tym supervisorem."""
        agent.set_supervisor(self)
        agent.set_event_queue(self.event_queue)
        self.agents[agent.name] = agent
        self._logger.debug("Zarejestrowano agenta '%s' (%s)", agent.name, agent.source_type.value)

    # -- start / stop / restart --------------------------------------------------

    async def start_agents(self) -> None:
        """Uruchamia wszystkich zarejestrowanych agentow w osobnych taskach."""
        self._running = True
        self.stats.start_time = datetime.utcnow()
        for name, agent in self.agents.items():
            task = asyncio.create_task(agent.run_loop(), name=f"agent_{name}")
            self._agent_tasks[name] = task
            self._logger.info("Uruchomiono agenta '%s'", name)

        # Uruchom heartbeat monitor
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_monitor(), name=f"heartbeat_{self.country_code}"
        )

    async def stop_agents(self) -> None:
        """Zatrzymuje wszystkich agentow i heartbeat monitor."""
        self._running = False

        # Zatrzymaj heartbeat
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Zatrzymaj agentow
        for name, agent in self.agents.items():
            await agent.stop()
        for name, task in self._agent_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._agent_tasks.clear()
        self._logger.info("Wszystkie agenty zatrzymane")

    async def restart_agent(self, agent_name: str) -> None:
        """Restartuje pojedynczego agenta."""
        if agent_name in self._agent_tasks:
            old_task = self._agent_tasks[agent_name]
            if not old_task.done():
                old_task.cancel()
                try:
                    await old_task
                except asyncio.CancelledError:
                    pass

        agent = self.agents.get(agent_name)
        if agent:
            await agent.stop()
            task = asyncio.create_task(agent.run_loop(), name=f"agent_{agent_name}")
            self._agent_tasks[agent_name] = task
            self._logger.info("Zrestartowano agenta '%s'", agent_name)

    # -- health check & heartbeat ------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Sprawdza stan zdrowia agentow. Restartuje po 5 min braku heartbeatu."""
        now = datetime.utcnow()
        status = {}
        for name, agent in self.agents.items():
            if agent.last_heartbeat is None:
                agent_status = "not_started"
            elif now - agent.last_heartbeat > timedelta(minutes=HEARTBEAT_TIMEOUT_MINUTES):
                agent_status = "unresponsive"
                self._logger.warning("Agent '%s' nie odpowiada — restart", name)
                await self.restart_agent(name)
            elif agent.is_running:
                agent_status = "running"
            else:
                agent_status = "stopped"
            status[name] = {
                "status": agent_status,
                "last_heartbeat": agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
                "source_type": agent.source_type.value,
                "trust_score": agent.trust_score,
                "is_official": agent.is_official_source,
                "events_collected": agent.events_collected,
                "errors_count": agent.errors_count,
            }
        return status

    async def _heartbeat_monitor(self) -> None:
        """Co 60 sekund sprawdza heartbeat agentow. Restartuje martwe (>5 min)."""
        while self._running:
            try:
                await asyncio.sleep(HEARTBEAT_CHECK_INTERVAL_SECONDS)
                now = datetime.utcnow()
                for name, agent in self.agents.items():
                    if (
                        agent.last_heartbeat is not None
                        and agent.is_running
                        and now - agent.last_heartbeat > timedelta(minutes=HEARTBEAT_TIMEOUT_MINUTES)
                    ):
                        self._logger.warning(
                            "Heartbeat timeout: agent '%s' (last: %s) — restart",
                            name, agent.last_heartbeat.isoformat(),
                        )
                        self.stats.errors += 1
                        await self.restart_agent(name)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error("Blad w heartbeat monitor: %s", e)

    # -- odbieranie danych od agentow -------------------------------------------

    async def receive_data(self, agent_name: str, records: list[dict]) -> None:
        """Odbiera dane od agenta — enrichuje metadata i wrzuca do kolejki."""
        for record in records:
            record["country_code"] = self.country_code
            record["agent_name"] = agent_name
            record["received_at"] = datetime.utcnow().isoformat()
            await self.event_queue.put(record)
        self._logger.debug("Odebrano %d rekordow od '%s'", len(records), agent_name)

    # -- zbieranie i filtrowanie danych -----------------------------------------

    async def collect_data(self) -> list[dict]:
        """Zbiera eventy z kolejki i przepuszcza przez pipeline.

        Pipeline:
        1. source_validator.is_legal_to_scrape()
        2. anonymizer.anonymize_personal_data()
        3. gdpr_filter.check_compliance()
        4. legal_filter.filter_event()

        Aktualizuje stats (collected, filtered_legal, filtered_gdpr, anonymized).
        Zwraca przefiltrowane eventy.
        """
        from src.pipeline.anonymizer import Anonymizer
        from src.pipeline.gdpr_filter import GDPRFilter
        from src.pipeline.legal_filter import LegalFilter
        from src.pipeline.source_validator import SourceValidator

        # Oproznij kolejke
        raw_events: list[dict] = []
        while not self.event_queue.empty():
            try:
                event = self.event_queue.get_nowait()
                raw_events.append(event)
            except asyncio.QueueEmpty:
                break

        if not raw_events:
            return []

        self.stats.events_collected += len(raw_events)

        validator = SourceValidator()
        anonymizer = Anonymizer()
        gdpr_filter = GDPRFilter()
        legal_filter = LegalFilter()

        filtered: list[dict] = []

        for event in raw_events:
            try:
                # 1. Walidacja legalnosci zrodla
                source_url = event.get("source_url", "")
                if source_url and not validator.is_legal_to_scrape(source_url):
                    self._logger.debug("Event odrzucony — zrodlo nielegalne: %s", source_url)
                    self.stats.events_filtered_legal += 1
                    continue

                # 2. Anonimizacja danych osobowych
                anonymized = False
                for field_name in ("title", "description", "raw_text"):
                    text = event.get(field_name, "")
                    if text and anonymizer.contains_personal_data(text):
                        event[field_name] = anonymizer.anonymize_personal_data(text)
                        is_official = event.get("is_official", False)
                        event[field_name] = anonymizer.anonymize_vehicle_plates(
                            event[field_name], is_official_source=is_official
                        )
                        anonymized = True
                if anonymized:
                    self.stats.events_anonymized += 1

                # 3. Sprawdzenie GDPR compliance
                gdpr_result = gdpr_filter.check_compliance(event)
                if gdpr_result.get("status") == "non_compliant":
                    self._logger.debug("Event odrzucony — GDPR non_compliant: %s", event.get("title", "?"))
                    self.stats.events_filtered_gdpr += 1
                    continue
                if gdpr_result.get("status") == "needs_review":
                    event["_needs_legal_review"] = True

                # 4. Filtr prawny
                legal_result = legal_filter.filter_event(event)
                if legal_result is None:
                    self._logger.debug("Event odrzucony — legal filter: %s", event.get("title", "?"))
                    self.stats.events_filtered_legal += 1
                    continue

                filtered.append(legal_result)

            except Exception as e:
                self.stats.errors += 1
                self._logger.error("Blad przetwarzania eventu: %s", e)

        self.stats.last_collection = datetime.utcnow()
        self._logger.info(
            "Zebrano %d -> przefiltrowano -> %d eventow (legal: -%d, gdpr: -%d)",
            len(raw_events), len(filtered),
            self.stats.events_filtered_legal, self.stats.events_filtered_gdpr,
        )
        return filtered

    # -- raportowanie statusu ----------------------------------------------------

    def report_status(self) -> dict:
        """Generuje raport statusu dla Master Supervisora."""
        return {
            "country_code": self.country_code,
            "country_name": self.country_name,
            "region": self.region,
            "running": self._running,
            "agents_count": len(self.agents),
            "agents_running": sum(1 for a in self.agents.values() if a.is_running),
            "stats": self.stats.to_dict(),
            "last_collection": self.stats.last_collection.isoformat() if self.stats.last_collection else None,
        }

    # -- glowna petla supervisora -----------------------------------------------

    async def run(self) -> None:
        """Glowna petla supervisora: tworzy agentow, uruchamia, zbiera dane.

        1. load_config()
        2. create_agents()
        3. start_agents()
        4. while is_running: collect_data() co 10 sekund
        """
        self.load_config()
        self.create_agents()
        await self.start_agents()

        self._logger.info(
            "Supervisor %s (%s) uruchomiony — %d agentow",
            self.country_name, self.country_code, len(self.agents),
        )

        while self._running:
            try:
                events = await self.collect_data()
                if events and self._master_supervisor is not None:
                    await self._master_supervisor.receive_country_data(
                        self.country_code, events
                    )
            except Exception as e:
                self.stats.errors += 1
                self._logger.error("Blad w petli supervisora: %s", e)
            await asyncio.sleep(COLLECT_INTERVAL_SECONDS)

    # -- powiazanie z master supervisorem ---------------------------------------

    def set_master_supervisor(self, master) -> None:
        """Przypisuje Master Supervisora."""
        self._master_supervisor = master
