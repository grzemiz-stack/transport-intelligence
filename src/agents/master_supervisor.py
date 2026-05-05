"""Master Supervisor - centralny punkt zarzadzania wszystkimi Country Supervisorami.

Rejestruje supervisorow krajowych, monitoruje ich status, koreluje zdarzenia
miedzy krajami (np. na tych samych trasach), dynamicznie priorytetyzuje
czestotliwosc scrapowania, obsluguje real-time alert system,
agreguje dane finansowe z danymi operacyjnymi.

WAZNE: Alerty real-time tez przechodza przez legal_filter przed wyslaniem.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agents.base_supervisor import CountrySupervisor
from src.agents.countries.registry import get_active_countries, get_config_path
from src.pipeline.correlator import EventCorrelator

logger = logging.getLogger(__name__)

MONITOR_INTERVAL_SECONDS = 300  # 5 minut
CORRELATION_INTERVAL_SECONDS = 1800  # 30 minut
ERROR_THRESHOLD_FOR_ALERT = 20


class MasterSupervisor:
    """Glowny supervisor zarzadzajacy wszystkimi Country Supervisorami.

    Atrybuty:
        supervisors: slownik country_code -> CountrySupervisor
        alert_counts: licznik alertow per kraj (do priorytetyzacji)
        correlator: EventCorrelator do wykrywania wzorcow
        alert_queue: kolejka alertow real-time
    """

    def __init__(self):
        self.supervisors: dict[str, CountrySupervisor] = {}
        self.alert_counts: dict[str, int] = {}
        self._running = False
        self._alert_queue: asyncio.Queue = asyncio.Queue()
        self._collected_events: list[dict] = []
        self._supervisor_tasks: dict[str, asyncio.Task] = {}
        self._monitor_task: asyncio.Task | None = None
        self._correlation_task: asyncio.Task | None = None
        self.correlator = EventCorrelator()
        self._logger = logging.getLogger("master_supervisor")

    # -- rejestracja krajow -----------------------------------------------------

    async def register_country(self, country_code: str, config_path: str | Path) -> None:
        """Tworzy CountrySupervisor dla danego kraju i rejestruje go."""
        code = country_code.upper()
        if code in self.supervisors:
            self._logger.warning("Kraj %s juz zarejestrowany — pomijam", code)
            return

        supervisor = CountrySupervisor(code, Path(config_path))
        supervisor.set_master_supervisor(self)
        self.supervisors[code] = supervisor
        self.alert_counts[code] = 0
        self._logger.info("Zarejestrowano kraj %s (config: %s)", code, config_path)

    async def register_all_countries(self) -> None:
        """Iteruje po registry.get_active_countries() i rejestruje kazdy kraj."""
        active = get_active_countries()
        registered = 0
        for code, meta in active.items():
            config_path = get_config_path(code)
            if config_path and config_path.exists():
                await self.register_country(code, config_path)
                registered += 1
            else:
                self._logger.debug(
                    "Pomijam %s (%s) — brak config.yaml", code, meta.name,
                )
        self._logger.info(
            "Zarejestrowano %d/%d aktywnych krajow", registered, len(active)
        )

    def unregister_country(self, country_code: str) -> None:
        """Wyrejestrowuje Country Supervisora."""
        code = country_code.upper()
        self.supervisors.pop(code, None)
        self.alert_counts.pop(code, None)

    # -- start / stop -----------------------------------------------------------

    async def start_all(self) -> None:
        """Uruchamia wszystkie country supervisory jako taski + monitor + correlation."""
        self._running = True

        for code, supervisor in self.supervisors.items():
            task = asyncio.create_task(
                self._run_supervisor(supervisor), name=f"supervisor_{code}"
            )
            self._supervisor_tasks[code] = task

        # Monitor loop
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(), name="master_monitor"
        )

        # Correlation loop
        self._correlation_task = asyncio.create_task(
            self._correlation_loop(), name="master_correlation"
        )

        self._logger.info(
            "Uruchomiono %d supervisorow + monitor + correlator", len(self.supervisors)
        )

    async def _run_supervisor(self, supervisor: CountrySupervisor) -> None:
        """Wrapper uruchamiajacy supervisora z obsluga bledow."""
        try:
            await supervisor.run()
        except Exception as e:
            self._logger.error(
                "Supervisor %s zakonczyl sie bledem: %s",
                supervisor.country_code, e,
            )

    async def stop_all(self) -> None:
        """Zatrzymuje wszystkie Country Supervisory, monitor i correlator."""
        self._running = False

        # Zatrzymaj monitor i correlator
        for task in (self._monitor_task, self._correlation_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Zatrzymaj supervisorow
        for code, supervisor in self.supervisors.items():
            await supervisor.stop_agents()

        for code, task in self._supervisor_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._supervisor_tasks.clear()

        self._logger.info("Wszystkie kraje zatrzymane")

    # -- status -----------------------------------------------------------------

    async def get_status_all(self) -> dict[str, Any]:
        """Zbiera status ze wszystkich krajow.

        Zwraca agregat: total_agents, running, errors, events per country.
        """
        statuses: dict[str, Any] = {}
        total_agents = 0
        total_running = 0
        total_errors = 0
        total_events = 0

        for code, supervisor in self.supervisors.items():
            status = supervisor.report_status()
            statuses[code] = status
            total_agents += status.get("agents_count", 0)
            total_running += status.get("agents_running", 0)
            stats = status.get("stats", {})
            total_errors += stats.get("errors", 0)
            total_events += stats.get("events_collected", 0)

        return {
            "countries": statuses,
            "summary": {
                "total_countries": len(self.supervisors),
                "total_agents": total_agents,
                "total_running": total_running,
                "total_errors": total_errors,
                "total_events_collected": total_events,
                "alert_counts": self.alert_counts.copy(),
            },
        }

    async def get_status_country(self, country_code: str) -> dict | None:
        """Zwraca status pojedynczego kraju."""
        supervisor = self.supervisors.get(country_code.upper())
        if supervisor:
            return supervisor.report_status()
        return None

    # -- zbieranie danych -------------------------------------------------------

    async def collect_all_data(self) -> list[dict]:
        """Zbiera przefiltrowane dane ze wszystkich krajow."""
        all_data = []
        for code, supervisor in self.supervisors.items():
            try:
                data = await supervisor.collect_data()
                all_data.extend(data)
            except Exception as e:
                self._logger.error("Blad zbierania danych z %s: %s", code, e)
        return all_data

    async def receive_country_data(self, country_code: str, events: list[dict]) -> None:
        """Odbiera dane od country supervisora (callback)."""
        self._collected_events.extend(events)
        self._logger.debug(
            "Odebrano %d eventow od %s (bufor: %d)",
            len(events), country_code, len(self._collected_events),
        )

    # -- petla monitoringu ------------------------------------------------------

    async def _monitor_loop(self) -> None:
        """Co 5 minut sprawdza health wszystkich krajow.

        Loguje status. Jesli kraj ma duzo bledow -> alert.
        """
        while self._running:
            try:
                await asyncio.sleep(MONITOR_INTERVAL_SECONDS)
                self._logger.info("=== Health check all countries ===")

                for code, supervisor in self.supervisors.items():
                    try:
                        health = await supervisor.health_check()
                        stats = supervisor.stats

                        # Loguj status
                        running_count = sum(
                            1 for a in health.values() if a.get("status") == "running"
                        )
                        self._logger.info(
                            "  %s: %d/%d agents running, %d events, %d errors",
                            code, running_count, len(health),
                            stats.events_collected, stats.errors,
                        )

                        # Alert jesli za duzo bledow
                        if stats.errors > ERROR_THRESHOLD_FOR_ALERT:
                            await self.generate_alert({
                                "title": f"High error rate in {code}",
                                "description": f"Country {code} has {stats.errors} errors",
                                "source_url": "internal://monitor",
                                "timestamp": datetime.utcnow().isoformat(),
                                "country_code": code,
                                "trust_score": 1.0,
                                "is_official": True,
                                "event_type": "system_alert",
                            })

                    except Exception as e:
                        self._logger.error("Health check failed for %s: %s", code, e)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error("Blad w monitor loop: %s", e)

    # -- petla korelacji --------------------------------------------------------

    async def _correlation_loop(self) -> None:
        """Co 30 minut zbiera eventy i przepuszcza przez correlator.

        Jesli znaleziono wzorce -> generate_alert().
        """
        while self._running:
            try:
                await asyncio.sleep(CORRELATION_INTERVAL_SECONDS)

                # Zbierz buforowane eventy
                events = self._collected_events.copy()
                self._collected_events.clear()

                if not events:
                    self._logger.debug("Brak eventow do korelacji")
                    continue

                self._logger.info("Korelacja: %d eventow", len(events))

                # Uruchom korelacje
                correlations = self.correlator.correlate(events)

                if correlations:
                    self._logger.info("Znaleziono %d korelacji", len(correlations))
                    for corr in correlations:
                        if corr.get("confidence", 0) >= 0.5:
                            await self._alert_from_correlation(corr)
                else:
                    self._logger.debug("Brak korelacji")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error("Blad w correlation loop: %s", e)

    async def _alert_from_correlation(self, correlation: dict) -> None:
        """Tworzy alert z korelacji."""
        countries = correlation.get("countries", [])
        alert_event = {
            "title": f"Correlation detected: {correlation.get('type', 'UNKNOWN')}",
            "description": (
                f"Pattern {correlation['type']} with {correlation.get('event_count', 0)} events "
                f"across countries: {', '.join(countries)}. "
                f"Confidence: {correlation.get('confidence', 0):.0%}"
            ),
            "source_url": "internal://correlator",
            "timestamp": datetime.utcnow().isoformat(),
            "country_code": countries[0] if countries else "EU",
            "trust_score": correlation.get("confidence", 0.5),
            "is_official": True,
            "event_type": "correlation_alert",
            "correlation": correlation,
        }
        await self.generate_alert(alert_event)

    # -- korelacja cross-country ------------------------------------------------

    async def cross_country_correlate(self) -> list[dict]:
        """Zbiera eventy cross-country i uzywa correlator.find_cross_country_routes()."""
        events = await self.collect_all_data()
        if not events:
            return []

        correlations = self.correlator.find_cross_country_routes(events)
        self._logger.info(
            "Cross-country correlation: %d eventow -> %d korelacji",
            len(events), len(correlations),
        )
        return correlations

    # -- priorytetyzacja --------------------------------------------------------

    async def adjust_priority(self, country_code: str, factor: float) -> None:
        """Zmniejsza/zwieksza scrape_interval agentow danego kraju.

        factor < 1.0 = czestsze scrapowanie (wyzszy priorytet)
        factor > 1.0 = rzadsze scrapowanie (nizszy priorytet)
        Min interval: 5 minut.
        """
        code = country_code.upper()
        supervisor = self.supervisors.get(code)
        if not supervisor:
            self._logger.warning("Nie znaleziono supervisora dla %s", code)
            return

        factor = max(0.1, min(5.0, factor))

        for agent in supervisor.agents.values():
            original = agent.scrape_interval_minutes
            agent.scrape_interval_minutes = max(5, int(original * factor))

        self._logger.info(
            "Priorytet %s zmieniony (factor: %.2f)", code, factor,
        )

    async def _auto_adjust_priorities(self) -> None:
        """Automatycznie dostosowuje priorytety na podstawie alert_counts."""
        for code, count in self.alert_counts.items():
            if count > 50:
                await self.adjust_priority(code, 0.25)
            elif count > 20:
                await self.adjust_priority(code, 0.5)
            elif count > 10:
                await self.adjust_priority(code, 0.75)

    # -- alerty -----------------------------------------------------------------

    async def generate_alert(self, event: dict) -> dict | None:
        """Generuje alert real-time po przepuszczeniu przez legal_filter.

        WAZNE: Alerty tez przechodza przez legal_filter przed wyslaniem.
        """
        from src.pipeline.legal_filter import LegalFilter

        legal_filter = LegalFilter()
        filtered = legal_filter.filter_event(event)
        if filtered is None:
            self._logger.debug("Alert odrzucony przez legal_filter")
            return None

        country_code = event.get("country_code", "")
        if country_code:
            self.alert_counts[country_code] = self.alert_counts.get(country_code, 0) + 1

        alert = {
            "type": "real_time_alert",
            "event": filtered,
            "generated_at": datetime.utcnow().isoformat(),
            "country_code": country_code,
            "severity": self._calculate_severity(event),
        }
        await self._alert_queue.put(alert)
        self._logger.info(
            "Alert wygenerowany: %s [%s] %s",
            alert["severity"], country_code, filtered.get("title", "?")[:80],
        )
        return alert

    def _calculate_severity(self, event: dict) -> str:
        """Oblicza poziom waznosci alertu."""
        trust = event.get("trust_score", 0.0)
        event_type = event.get("event_type", "")

        # Korelacje maja wyzszy severity
        if event_type == "correlation_alert":
            confidence = event.get("correlation", {}).get("confidence", 0)
            if confidence >= 0.8:
                return "critical"
            elif confidence >= 0.5:
                return "high"
            return "medium"

        if trust >= 0.9 and event.get("is_official"):
            return "critical"
        elif trust >= 0.7:
            return "high"
        elif trust >= 0.4:
            return "medium"
        return "low"

    # -- agregacja finansowa ----------------------------------------------------

    async def financial_risk_aggregation(self, events: list[dict]) -> dict:
        """Agreguje dane finansowe z danymi operacyjnymi.

        Laczy informacje o kondycji finansowej firm (upadlosci, zaleglosci)
        z incydentami operacyjnymi (kradzieze, wypadki) dla pelnego obrazu ryzyka.
        """
        financial_types = {"bankruptcy", "restructuring", "payment_issue"}
        operational_types = {"theft_cargo", "theft_fuel", "theft_vehicle", "damage"}

        companies: dict[str, dict] = defaultdict(lambda: {
            "financial_events": [],
            "operational_events": [],
            "total_financial_impact": 0.0,
            "countries": set(),
        })

        for ev in events:
            company = ev.get("company_name") or ev.get("company")
            if not company:
                continue
            key = company.lower()
            et = ev.get("event_type", "")
            if et in financial_types:
                companies[key]["financial_events"].append(ev)
            elif et in operational_types:
                companies[key]["operational_events"].append(ev)
            impact = ev.get("financial_impact_eur")
            if impact:
                companies[key]["total_financial_impact"] += float(impact)
            cc = ev.get("country_code")
            if cc:
                companies[key]["countries"].add(cc)

        # Scoring ryzyka
        risk_profiles: list[dict] = []
        for company_name, data in companies.items():
            fin_count = len(data["financial_events"])
            ops_count = len(data["operational_events"])

            if fin_count == 0 and ops_count == 0:
                continue

            # Risk score: 0-100
            risk_score = 0
            if fin_count > 0:
                risk_score += min(40, fin_count * 15)
            if ops_count > 0:
                risk_score += min(30, ops_count * 10)
            if fin_count > 0 and ops_count > 0:
                risk_score += 20  # bonus za polaczenie
            if data["total_financial_impact"] > 100000:
                risk_score += 10

            risk_score = min(100, risk_score)

            risk_profiles.append({
                "company": company_name,
                "risk_score": risk_score,
                "financial_event_count": fin_count,
                "operational_event_count": ops_count,
                "total_financial_impact_eur": round(data["total_financial_impact"], 2),
                "countries": list(data["countries"]),
                "risk_level": (
                    "critical" if risk_score >= 80
                    else "high" if risk_score >= 60
                    else "medium" if risk_score >= 30
                    else "low"
                ),
            })

        # Sortuj po risk_score malejaco
        risk_profiles.sort(key=lambda x: x["risk_score"], reverse=True)

        return {
            "total_companies_analyzed": len(risk_profiles),
            "high_risk_count": sum(1 for r in risk_profiles if r["risk_score"] >= 60),
            "risk_profiles": risk_profiles,
            "generated_at": datetime.utcnow().isoformat(),
        }

    # -- health check -----------------------------------------------------------

    async def health_check_all(self) -> dict[str, dict]:
        """Uruchamia health check na wszystkich krajach."""
        results = {}
        for code, supervisor in self.supervisors.items():
            try:
                results[code] = await supervisor.health_check()
            except Exception as e:
                results[code] = {"error": str(e)}
        return results

    # -- glowna petla -----------------------------------------------------------

    async def run(self) -> None:
        """Glowna petla:
        1. register_all_countries()
        2. start_all()
        3. while is_running: sleep (praca odbywa sie w taskach)
        """
        self._logger.info("=== Master Supervisor START ===")
        await self.register_all_countries()
        await self.start_all()

        self._logger.info(
            "Master Supervisor uruchomiony: %d krajow, gotowy",
            len(self.supervisors),
        )

        while self._running:
            await asyncio.sleep(1)

        self._logger.info("=== Master Supervisor STOP ===")
