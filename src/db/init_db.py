"""Inicjalizacja bazy danych: migracje Alembic + seed demo data.

Uzycie:
    python -m src.db.init_db --migrate   # run alembic upgrade head
    python -m src.db.init_db --seed      # migrate + seed demo data
    python -m src.db.init_db --drop      # drop all tables
    python -m src.db.init_db --reset     # drop + migrate + seed
"""

import argparse
import asyncio
import random
import subprocess
import sys
import uuid
import warnings
from datetime import date, datetime, timedelta

warnings.filterwarnings("ignore", message=".*datetime.datetime.utcnow.*")
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.config import settings
from src.api.auth import hash_password
from src.db.models import (
    Base, Source, Company, Event, Report, Alert, CrimeHotspot,
    CompanyFinancial, EventCorrelation, AuditLog, Subscriber, AgentStatus, User,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_alembic_upgrade():
    """Run alembic upgrade head using subprocess."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Alembic upgrade failed:\n{result.stderr}")
        sys.exit(1)
    print("Alembic upgrade head — done.")


async def drop_all_tables():
    """Drop all tables including alembic_version."""
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
    await engine.dispose()
    print("Tables dropped.")


def _dt(days_ago: int, hour: int = 10, minute: int = 0) -> datetime:
    return datetime.utcnow().replace(hour=hour, minute=minute, second=0, microsecond=0) - timedelta(days=days_ago)


def _d(days_ago: int) -> date:
    return (datetime.utcnow() - timedelta(days=days_ago)).date()


async def seed_demo_data():
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Check if already seeded
        result = await session.execute(text("SELECT count(*) FROM events"))
        count = result.scalar()
        if count and count > 0:
            print(f"Database already has {count} events. Skipping seed.")
            await engine.dispose()
            return

        # ── SOURCES ──────────────────────────────────────────────
        sources = []
        source_data = [
            ("Policja Wielkopolska", "police", "https://policja.gov.pl/wlkp", "PL", 0.95, True),
            ("KWP Wroclaw", "police", "https://dolnoslaska.policja.gov.pl", "PL", 0.95, True),
            ("KWP Lodz", "police", "https://lodzka.policja.gov.pl", "PL", 0.94, True),
            ("Polizei NRW", "police", "https://polizei.nrw", "DE", 0.93, True),
            ("Polizei Sachsen", "police", "https://polizei.sachsen.de", "DE", 0.93, True),
            ("Polizei Brandenburg", "police", "https://polizei.brandenburg.de", "DE", 0.92, True),
            ("Gendarmerie Nationale", "police", "https://gendarmerie.interieur.gouv.fr", "FR", 0.91, True),
            ("Polizia di Stato", "police", "https://poliziadistato.it", "IT", 0.90, True),
            ("Politie Nederland", "police", "https://politie.nl", "NL", 0.93, True),
            ("Policia Nacional", "police", "https://policia.es", "ES", 0.90, True),
            ("ISCTR Romania", "financial", "https://isctr.ro", "RO", 0.98, True),
            ("KRS - Rejestr Sadowy", "financial", "https://ekrs.ms.gov.pl", "PL", 0.99, True),
            ("Cegjegyzek Hungary", "financial", "https://e-cegjegyzek.hu", "HU", 0.97, True),
            ("France Info", "news", "https://franceinfo.fr", "FR", 0.85, False),
            ("TransportMonitor.ro", "news", "https://transportmonitor.ro", "RO", 0.70, False),
            ("Trans.INFO", "news", "https://trans.info", "PL", 0.80, False),
            ("DVZ Deutsche Verkehrs-Zeitung", "news", "https://dvz.de", "DE", 0.82, False),
            ("Transport Forum PL", "forum", "https://forum.transport.pl", "PL", 0.55, False),
            ("Transport Forum HR", "forum", "https://forum.transport.hr", "HR", 0.50, False),
            ("LKW Forum DE", "forum", "https://lkw-forum.de", "DE", 0.52, False),
        ]
        for name, stype, url, cc, ts, official in source_data:
            s = Source(name=name, source_type=stype, url=url, country_code=cc,
                       trust_score=ts, is_official=official, is_active=True,
                       last_scraped=_dt(0), total_events_collected=random.randint(10, 500))
            sources.append(s)
            session.add(s)
        await session.flush()

        src_map = {s.name: s.id for s in sources}

        # ── COMPANIES ────────────────────────────────────────────
        companies = []
        company_data = [
            ("TransEuropa GmbH", "DE", "carrier", "healthy", 15.0, "HRB 123456"),
            ("Nordic Freight AB", "SE", "carrier", "healthy", 8.0, "556789-0123"),
            ("PolTruck sp. z o.o.", "PL", "carrier", "bankrupt", 95.0, "KRS 0000456789"),
            ("MedTrans International B.V.", "NL", "carrier", "healthy", 22.0, "KvK 12345678"),
            ("SpedLogistics Kft", "HU", "forwarder", "restructuring", 68.0, "Cg. 01-09-123456"),
            ("CargoPrime s.r.o.", "CZ", "carrier", "healthy", 12.0, "IČO 87654321"),
            ("Balkan Express d.o.o.", "HR", "carrier", "warning", 72.0, "OIB 12345678901"),
            ("FreshLine sp. z o.o.", "PL", "carrier", "healthy", 28.0, "KRS 0000567890"),
            ("RoTrans SRL", "RO", "carrier", "critical", 88.0, "J40/12345/2018"),
            ("Alpen Spedition GmbH", "AT", "forwarder", "healthy", 5.0, "FN 234567a"),
            ("Spedition Mueller AG", "DE", "carrier", "healthy", 10.0, "HRB 789012"),
            ("EuroCarriers S.A.", "FR", "carrier", "healthy", 18.0, "SIREN 123456789"),
            ("Adriatic Logistics d.o.o.", "SI", "forwarder", "healthy", 20.0, "Mat. 5123456"),
            ("TransBaltic UAB", "LT", "carrier", "warning", 55.0, "Reg. 302345678"),
            ("Iberia Trans S.L.", "ES", "carrier", "healthy", 14.0, "CIF B12345678"),
            ("DanubeLog Kft", "HU", "forwarder", "healthy", 25.0, "Cg. 01-09-654321"),
            ("PragueWheels a.s.", "CZ", "carrier", "healthy", 9.0, "IČO 12345678"),
            ("BulgarTrans EOOD", "BG", "carrier", "warning", 60.0, "EIK 123456789"),
            ("Scandia Freight ApS", "DK", "forwarder", "healthy", 7.0, "CVR 12345678"),
            ("VistulaTrans sp. z o.o.", "PL", "carrier", "healthy", 30.0, "KRS 0000678901"),
            ("MilanoFreight S.r.l.", "IT", "carrier", "healthy", 16.0, "P.IVA 01234567890"),
            ("HellasTruck A.E.", "GR", "carrier", "critical", 78.0, "AFM 123456789"),
        ]
        for name, cc, ctype, fstatus, risk, reg in company_data:
            c = Company(name=name, country_code=cc, company_type=ctype,
                        financial_status=fstatus, risk_score=risk,
                        registration_number=reg, is_active=True)
            companies.append(c)
            session.add(c)
        await session.flush()

        comp_map = {c.name: c.id for c in companies}

        # ── EVENTS ───────────────────────────────────────────────
        random.seed(42)
        event_rows = [
            # (type, severity, title, description, cc, region, city, lat, lon, source_name, company_name, trust, verified, tags, impact, lang, days_ago, hour)
            ("theft_cargo", "high", "Cargo theft on A2 near Poznan", "Electronics cargo EUR 85,000 stolen from parked truck at rest area.", "PL", "Wielkopolska", "Poznan", 52.4064, 16.9252, "Policja Wielkopolska", "TransEuropa GmbH", 0.95, True, ["nocna","autostrada","elektronika"], 85000, "pl", 5, 3),
            ("theft_fuel", "medium", "Fuel siphoning at truck stop near Duesseldorf", "400 liters diesel siphoned from 3 trucks at Raststatte Nievenheim.", "DE", "Nordrhein-Westfalen", "Duesseldorf", 51.2277, 6.7735, "Polizei NRW", None, 0.88, True, ["nocna","parking","paliwo"], 520, "de", 6, 2),
            ("bankruptcy", "high", "PolTruck sp. z o.o. files for bankruptcy", "PolTruck filed for bankruptcy. Fleet of 120 vehicles.", "PL", "Mazowieckie", "Warszawa", 52.2297, 21.0122, "KRS - Rejestr Sadowy", "PolTruck sp. z o.o.", 0.99, True, ["upadlosc"], 2500000, "pl", 8, 10),
            ("theft_cargo", "critical", "Pharmaceutical cargo hijacked on E40", "Armed hijacking of pharmaceutical shipment. Loss EUR 320,000.", "PL", "Dolnoslaskie", "Wroclaw", 51.1079, 17.0385, "KWP Wroclaw", "MedTrans International B.V.", 0.97, True, ["nocna","farmaceutyki","zorganizowana"], 320000, "pl", 4, 22),
            ("route_closure", "medium", "A1 closure near Graz due to accident", "Full A1 closure Graz-West to Graz-Ost. Duration 6 hours.", "AT", "Steiermark", "Graz", 47.0707, 15.4395, None, None, 0.90, True, ["autostrada"], None, "de", 3, 14),
            ("strike", "high", "French transport workers strike on A7", "CGT 48-hour strike affecting freight on A7 Lyon-Marseille.", "FR", "Auvergne-Rhone-Alpes", "Lyon", 45.7640, 4.8357, "France Info", None, 0.85, True, ["strajk"], None, "fr", 2, 6),
            ("payment_issue", "medium", "Balkan Express d.o.o. reported for delayed payments", "Multiple subcontractors report 90+ day payment delays.", "HR", "Grad Zagreb", "Zagreb", 45.8150, 15.9819, "Transport Forum HR", "Balkan Express d.o.o.", 0.55, False, [], None, "hr", 10, 9),
            ("theft_cargo", "high", "Textile cargo theft on A4 near Dresden", "Textile shipment EUR 45,000 stolen. Curtain slashed.", "DE", "Sachsen", "Dresden", 51.0504, 13.7373, "Polizei Sachsen", "CargoPrime s.r.o.", 0.91, True, ["nocna","tekstylia"], 45000, "de", 4, 1),
            ("license_revoked", "high", "RoTrans SRL license revoked by ISCTR", "ISCTR revoked international transport license for safety violations.", "RO", "Bucuresti", "Bucuresti", 44.4268, 26.1025, "ISCTR Romania", "RoTrans SRL", 0.98, True, [], None, "ro", 9, 11),
            ("delay", "low", "Border delays at Nadlac (RO-HU)", "Average wait time 4+ hours for freight at Nadlac crossing.", "RO", "Arad", "Nadlac", 46.1667, 20.7500, "TransportMonitor.ro", None, 0.70, False, ["granica"], None, "ro", 1, 8),
            ("restructuring", "medium", "SpedLogistics Kft restructuring announced", "Court-supervised restructuring. 85 employees affected.", "HU", "Budapest", "Budapest", 47.4979, 19.0402, "Cegjegyzek Hungary", "SpedLogistics Kft", 0.93, True, [], None, "hu", 7, 9),
            ("theft_cargo", "high", "Food cargo theft near Lodz", "Refrigerated trailer with food EUR 62,000 stolen from S8 rest area.", "PL", "Lodzkie", "Lodz", 51.7592, 19.4560, "KWP Lodz", "FreshLine sp. z o.o.", 0.90, True, ["nocna","zywnosc"], 62000, "pl", 2, 4),
            # Additional events to reach 50+
            ("theft_cargo", "high", "Container theft at Rotterdam port", "20ft container with electronics EUR 120,000 stolen overnight.", "NL", "Zuid-Holland", "Rotterdam", 51.9244, 4.4777, "Politie Nederland", None, 0.92, True, ["port","elektronika"], 120000, "nl", 3, 2),
            ("theft_fuel", "medium", "Fuel theft on A10 near Berlin", "600L diesel siphoned from parked fleet at Autohof Michendorf.", "DE", "Brandenburg", "Berlin", 52.3239, 13.0558, "Polizei Brandenburg", None, 0.89, True, ["nocna","paliwo"], 780, "de", 5, 1),
            ("theft_cargo", "critical", "High-value electronics theft near Milano", "EUR 250,000 electronics shipment hijacked on A4 near Brescia.", "IT", "Lombardia", "Milano", 45.5416, 10.2118, "Polizia di Stato", "MilanoFreight S.r.l.", 0.94, True, ["autostrada","elektronika"], 250000, "it", 1, 23),
            ("payment_issue", "medium", "TransBaltic UAB payment delays", "Lithuanian carrier 60+ day delays to Polish subcontractors.", "LT", "Vilnius", "Vilnius", 54.6872, 25.2797, "Trans.INFO", "TransBaltic UAB", 0.72, False, ["zaleglosci"], None, "pl", 12, 10),
            ("theft_cargo", "medium", "Tobacco cargo stolen on A1 near Barcelona", "EUR 35,000 tobacco shipment stolen from rest area.", "ES", "Cataluna", "Barcelona", 41.3851, 2.1734, "Policia Nacional", None, 0.87, True, ["nocna","tytoniu"], 35000, "es", 6, 3),
            ("theft_vehicle", "high", "Truck stolen at Calais terminal", "Scania R450 with trailer stolen from ferry terminal parking.", "FR", "Hauts-de-France", "Calais", 50.9513, 1.8587, "Gendarmerie Nationale", None, 0.90, True, ["port","pojazd"], 95000, "fr", 8, 4),
            ("delay", "low", "Brenner Pass congestion", "Heavy freight congestion at Brenner due to road works. 3h delays.", "AT", "Tirol", "Innsbruck", 47.2692, 11.4041, None, None, 0.75, False, ["granica","autostrada"], None, "de", 1, 12),
            ("theft_cargo", "high", "Copper wire theft on E30 near Lodz", "EUR 78,000 copper wire shipment stolen at S8/E30 junction.", "PL", "Lodzkie", "Lodz", 51.7800, 19.4900, "KWP Lodz", None, 0.91, True, ["nocna","miedz"], 78000, "pl", 3, 2),
            ("strike", "medium", "Belgian port workers slowdown at Antwerp", "Partial slowdown at Port of Antwerp affecting container handling.", "BE", "Vlaanderen", "Antwerpen", 51.2194, 4.4025, None, None, 0.78, False, ["port","strajk"], None, "nl", 4, 8),
            ("theft_fuel", "low", "Fuel siphoning at Czech truck stop", "200L diesel stolen at rest area on D1 near Brno.", "CZ", "Jihomoravsky", "Brno", 49.1951, 16.6068, None, None, 0.65, False, ["paliwo"], 260, "cs", 7, 3),
            ("damage", "medium", "Trailer damage from road debris on A2", "3 trailers damaged by road debris on A2 near Hannover.", "DE", "Niedersachsen", "Hannover", 52.3759, 9.7320, "DVZ Deutsche Verkehrs-Zeitung", "Spedition Mueller AG", 0.80, False, ["autostrada"], 15000, "de", 2, 16),
            ("theft_cargo", "high", "Alcohol shipment theft in Sofia region", "EUR 55,000 spirits shipment stolen from logistics park.", "BG", "Sofia", "Sofia", 42.6977, 23.3219, None, "BulgarTrans EOOD", 0.68, False, ["alkohol"], 55000, "bg", 5, 1),
            ("payment_issue", "high", "HellasTruck A.E. severe payment delays", "Greek carrier 120+ day delays. Multiple EU subcontractors affected.", "GR", "Attiki", "Athens", 37.9838, 23.7275, None, "HellasTruck A.E.", 0.62, False, ["zaleglosci"], None, "el", 3, 10),
            ("theft_cargo", "medium", "Automotive parts theft near Bratislava", "EUR 28,000 automotive parts stolen from D2 rest area.", "SK", "Bratislavsky", "Bratislava", 48.1486, 17.1077, None, None, 0.74, False, ["motoryzacja"], 28000, "sk", 9, 2),
            ("route_closure", "high", "Tunnel closure on E45 Brenner", "Brenner Base Tunnel emergency closure 12h. Major delays.", "AT", "Tirol", "Brenner", 47.0417, 11.5083, None, None, 0.88, True, ["tunel","autostrada"], None, "de", 6, 7),
            ("theft_cargo", "critical", "Pharmaceutical theft convoy near Wroclaw", "Second pharma theft in 10 days on A4. EUR 180,000 loss.", "PL", "Dolnoslaskie", "Wroclaw", 51.1200, 16.9800, "KWP Wroclaw", None, 0.96, True, ["farmaceutyki","zorganizowana"], 180000, "pl", 1, 1),
            ("theft_fuel", "medium", "Diesel theft ring on A6 near Mannheim", "Organized fuel theft ring targeting trucks on A6. 4 incidents.", "DE", "Baden-Wuerttemberg", "Mannheim", 49.4875, 8.4660, "Polizei NRW", None, 0.86, True, ["zorganizowana","paliwo"], 3200, "de", 8, 23),
            ("delay", "low", "Heavy traffic at Dover-Calais", "Brexit customs causing 5+ hour delays for EU freight.", "GB", "Kent", "Dover", 51.1279, 1.3134, None, None, 0.73, False, ["granica","brexit"], None, "en", 2, 9),
            ("theft_cargo", "high", "Clothing shipment theft near Lyon", "EUR 42,000 clothing stolen from A46 rest area near Lyon.", "FR", "Auvergne-Rhone-Alpes", "Lyon", 45.7800, 4.8200, "Gendarmerie Nationale", None, 0.88, True, ["nocna","tekstylia"], 42000, "fr", 3, 2),
            ("payment_issue", "low", "Minor payment delays at Adriatic Logistics", "30-day delays reported by 2 subcontractors.", "SI", "Osrednjeslovenska", "Ljubljana", 46.0569, 14.5058, None, "Adriatic Logistics d.o.o.", 0.50, False, [], None, "sl", 15, 10),
            ("theft_cargo", "medium", "Food shipment theft at Warsaw hub", "EUR 18,000 frozen food stolen from cold storage facility.", "PL", "Mazowieckie", "Warszawa", 52.2500, 20.9800, "Policja Wielkopolska", "VistulaTrans sp. z o.o.", 0.84, True, ["zywnosc"], 18000, "pl", 7, 5),
            ("theft_cargo", "high", "Copper theft on E40 near Katowice", "EUR 92,000 copper cable shipment stolen from A4 parking.", "PL", "Slaskie", "Katowice", 50.2649, 19.0238, "Policja Wielkopolska", None, 0.93, True, ["nocna","miedz"], 92000, "pl", 1, 0),
            ("damage", "low", "Minor cargo damage due to flooding near Prague", "Water damage to 2 trailers at logistics park.", "CZ", "Praha", "Praha", 50.0755, 14.4378, None, "PragueWheels a.s.", 0.60, False, [], 4500, "cs", 11, 14),
            ("theft_vehicle", "medium", "Truck stolen near Budapest logistics zone", "MAN TGX stolen overnight from guarded parking.", "HU", "Budapest", "Budapest", 47.4700, 19.0800, None, None, 0.72, False, ["pojazd"], 75000, "hu", 4, 3),
            ("theft_cargo", "high", "Electronics theft on A28 near Utrecht", "EUR 95,000 consumer electronics stolen at service area.", "NL", "Utrecht", "Utrecht", 52.0907, 5.1214, "Politie Nederland", None, 0.91, True, ["elektronika","nocna"], 95000, "nl", 2, 1),
            ("strike", "low", "Italian truck drivers protest in Rome", "One-day protest affecting deliveries in Lazio region.", "IT", "Lazio", "Roma", 41.9028, 12.4964, None, None, 0.70, False, ["strajk"], None, "it", 5, 7),
            ("theft_cargo", "medium", "Tire shipment theft near Poznan", "EUR 22,000 truck tires stolen from A2 rest area.", "PL", "Wielkopolska", "Poznan", 52.3900, 16.8800, "Policja Wielkopolska", None, 0.87, True, ["opony","nocna"], 22000, "pl", 6, 3),
            ("theft_fuel", "low", "Small-scale fuel theft near Bucharest", "150L diesel siphoned at truck stop on A1.", "RO", "Ilfov", "Bucuresti", 44.4500, 26.0800, None, None, 0.55, False, ["paliwo"], 195, "ro", 8, 2),
            ("payment_issue", "medium", "BulgarTrans EOOD payment issues worsen", "Bulgarian carrier now 75+ day delays on all invoices.", "BG", "Sofia", "Sofia", 42.7000, 23.3300, None, "BulgarTrans EOOD", 0.65, False, ["zaleglosci"], None, "bg", 2, 11),
            ("theft_cargo", "high", "Cosmetics cargo stolen near Hamburg", "EUR 67,000 cosmetics shipment stolen from A1 Autohof.", "DE", "Hamburg", "Hamburg", 53.5511, 9.9937, "Polizei NRW", None, 0.90, True, ["nocna","kosmetyki"], 67000, "de", 1, 2),
            ("delay", "medium", "Swiss transit delays due to alpine weather", "Heavy snow causing 8h delays on Gotthard route.", "CH", "Uri", "Goeschenen", 46.6647, 8.5879, None, None, 0.80, False, ["pogoda","alpy"], None, "de", 3, 6),
            ("theft_cargo", "medium", "Spare parts theft at Madrid logistics center", "EUR 31,000 auto parts stolen from warehouse.", "ES", "Madrid", "Madrid", 40.4168, -3.7038, "Policia Nacional", "Iberia Trans S.L.", 0.85, True, ["motoryzacja"], 31000, "es", 4, 22),
            ("theft_cargo", "high", "Computer equipment theft on A11 near Szczecin", "EUR 110,000 IT equipment stolen from A11 rest area.", "PL", "Zachodniopomorskie", "Szczecin", 53.4285, 14.5528, "Policja Wielkopolska", None, 0.92, True, ["elektronika","nocna"], 110000, "pl", 2, 1),
            ("route_closure", "low", "Minor road works on M1 near Budapest", "Lane closure on M1 between km 45-52. Expect 1h delays.", "HU", "Gyor-Moson-Sopron", "Gyor", 47.6875, 17.6504, None, None, 0.72, False, [], None, "hu", 1, 10),
            ("theft_cargo", "medium", "Household goods theft near Antwerp port", "EUR 19,000 household goods stolen from port storage.", "BE", "Vlaanderen", "Antwerpen", 51.2300, 4.4100, None, None, 0.76, False, ["port"], 19000, "nl", 5, 4),
            ("theft_cargo", "high", "Medical supplies theft on A4 near Krakow", "EUR 88,000 medical supplies stolen from S7 rest area.", "PL", "Malopolskie", "Krakow", 50.0647, 19.9450, "Policja Wielkopolska", None, 0.93, True, ["medyczne","nocna"], 88000, "pl", 3, 0),
            ("payment_issue", "high", "DanubeLog Kft cascading payment failures", "Hungarian forwarder affecting 12 subcontractors across 4 countries.", "HU", "Budapest", "Budapest", 47.5000, 19.0500, "Trans.INFO", "DanubeLog Kft", 0.70, False, ["zaleglosci","kaskadowe"], None, "hu", 1, 9),
            ("theft_fuel", "medium", "Organized fuel theft on A15 near Rotterdam", "Ring targeting parked trucks on A15. 5 incidents in 2 weeks.", "NL", "Zuid-Holland", "Rotterdam", 51.9100, 4.5000, "Politie Nederland", None, 0.88, True, ["zorganizowana","paliwo"], 4100, "nl", 4, 1),
        ]

        event_objs = []
        for row in event_rows:
            etype, sev, title, desc, cc, region, city, lat, lon, src_name, comp_name, trust, verified, tags, impact, lang, days_ago, hour = row
            e = Event(
                event_type=etype, severity=sev, title=title, description=desc,
                country_code=cc, region=region, city=city,
                latitude=lat, longitude=lon,
                source_id=src_map.get(src_name),
                company_id=comp_map.get(comp_name),
                trust_score=trust, is_verified=verified, tags=tags,
                financial_impact_eur=impact, language=lang,
                date_occurred=_dt(days_ago, hour),
                date_collected=_dt(days_ago - 1 if days_ago > 0 else 0, hour + 2 if hour < 22 else 8),
            )
            event_objs.append(e)
            session.add(e)
        await session.flush()

        # ── ALERTS ───────────────────────────────────────────────
        alert_data = [
            ("theft_spike", "high", "Cargo theft cluster near Poznan (A2)", "3 cargo thefts within 30km in 7 days.", ["PL"], True, 2),
            ("strike", "high", "Transport strike on A7 Lyon-Marseille", "CGT 48h strike affecting freight on A7.", ["FR"], True, 2),
            ("company_risk", "critical", "Armed hijacking on E40/A4 near Wroclaw", "Armed hijacking of pharma shipment. Police investigating.", ["PL"], True, 3),
            ("financial_distress", "medium", "PolTruck bankruptcy — subcontractor impact", "PolTruck bankruptcy. 35 subcontractors may be affected.", ["PL"], True, 8),
            ("company_risk", "high", "RoTrans SRL license revoked", "ISCTR revoked international license. Cease cooperation.", ["RO"], True, 9),
            ("theft_spike", "medium", "Fuel theft pattern A57 Duesseldorf", "Recurring fuel siphoning at Raststatte Nievenheim.", ["DE"], False, 10),
            ("route_danger", "low", "Border delays at Nadlac (RO-HU)", "4+ hour wait times. Enhanced customs through March.", ["RO", "HU"], True, 1),
            ("theft_spike", "high", "Electronics theft cluster Netherlands", "Multiple high-value electronics thefts in NL.", ["NL"], True, 2),
            ("financial_distress", "high", "HellasTruck A.E. severe financial distress", "120+ day payment delays across EU.", ["GR"], True, 3),
            ("theft_spike", "critical", "Pharma theft corridor Wroclaw-Opole", "Second pharma theft in 10 days on A4.", ["PL"], True, 1),
            ("company_risk", "medium", "BulgarTrans EOOD deteriorating payments", "Payment delays increasing to 75+ days.", ["BG"], True, 2),
        ]
        for atype, sev, title, desc, ccs, active, days_ago in alert_data:
            a = Alert(
                alert_type=atype, severity=sev, title=title, description=desc,
                country_codes=ccs, is_active=active,
                triggered_at=_dt(days_ago),
                resolved_at=_dt(days_ago - 5) if not active else None,
            )
            session.add(a)

        # ── HOTSPOTS ─────────────────────────────────────────────
        hotspot_data = [
            ("PL", "Poznan A2 corridor", 52.40, 16.93, 25.0, "theft_cargo", 8, "high", "rising"),
            ("DE", "Duesseldorf A57 area", 51.23, 6.77, 20.0, "theft_fuel", 4, "medium", "stable"),
            ("DE", "Dresden A4 corridor", 51.05, 13.74, 15.0, "theft_cargo", 3, "high", "rising"),
            ("FR", "Lyon A7 zone", 45.76, 4.84, 30.0, "mixed", 3, "medium", "stable"),
            ("PL", "Wroclaw E40/A4", 51.11, 17.04, 20.0, "theft_cargo", 5, "critical", "rising"),
            ("NL", "Rotterdam port area", 51.92, 4.48, 15.0, "theft_cargo", 4, "high", "rising"),
            ("PL", "Lodz S8 corridor", 51.76, 19.46, 20.0, "theft_cargo", 4, "high", "stable"),
            ("IT", "Milano-Brescia A4", 45.54, 10.21, 25.0, "theft_cargo", 2, "high", "rising"),
            ("FR", "Calais terminal zone", 50.95, 1.86, 10.0, "theft_vehicle", 2, "medium", "stable"),
            ("RO", "Nadlac border crossing", 46.17, 20.75, 5.0, "mixed", 3, "low", "stable"),
        ]
        for cc, region, lat, lon, radius, htype, count, sev, trend in hotspot_data:
            h = CrimeHotspot(
                country_code=cc, region=region, latitude=lat, longitude=lon,
                radius_km=radius, hotspot_type=htype, event_count=count,
                severity=sev, trend=trend,
                period_start=_d(90), period_end=_d(0),
            )
            session.add(h)

        # ── CORRELATIONS ─────────────────────────────────────────
        corr_data = [
            ("same_location", "Poznan A2 theft cluster — 3 events within 30km", 0.92, ["PL"]),
            ("same_location", "Wroclaw A4 pharma thefts — same corridor", 0.95, ["PL"]),
            ("same_company", "PolTruck financial cascade — bankruptcy + subcontractors", 0.88, ["PL", "HR"]),
            ("cross_country_route", "E40 corridor theft pattern PL-DE", 0.78, ["PL", "DE"]),
            ("same_time_pattern", "Night-time thefts 00:00-05:00 pattern", 0.85, ["PL", "DE", "FR", "NL"]),
            ("financial_operational", "HellasTruck payment defaults correlate with reduced fleet", 0.72, ["GR"]),
        ]
        for ctype, desc, conf, ccs in corr_data:
            ec = EventCorrelation(
                correlation_type=ctype, description=desc,
                confidence=conf, country_codes=ccs, is_active=True,
                pattern_description=desc,
            )
            session.add(ec)

        # ── REPORTS ──────────────────────────────────────────────
        report_data = [
            ("biweekly", "Biweekly Report 1-14 March 2026", 14, 0, ["PL","DE","CZ","SK"], "en", "published", 245760),
            ("monthly", "Monthly Report February 2026", 50, 22, ["PL","DE","CZ","SK","AT","HU"], "pl", "published", 512000),
            ("alert", "Alert Report: Pharma Hijacking Wroclaw", 4, 4, ["PL"], "en", "generated", 48000),
        ]
        for rtype, title, ps_ago, pe_ago, countries, lang, status, fsize in report_data:
            r = Report(
                report_type=rtype, title=title,
                period_start=_d(ps_ago), period_end=_d(pe_ago),
                countries=countries, language=lang, status=status,
                total_events=random.randint(20, 80),
                confirmed_events=random.randint(10, 40),
                signal_events=random.randint(5, 20),
                file_path=f"/output/reports/{rtype}_{uuid.uuid4().hex[:8]}.pdf",
            )
            session.add(r)

        # ── SUBSCRIBERS ──────────────────────────────────────────
        sub_data = [
            ("Acme Logistics GmbH", "alerts@acme-logistics.de", "premium_alerts", ["DE","PL","CZ","AT"], "de", True, 500.0),
            ("Wielton S.A.", "risk@wielton.com.pl", "enterprise_api", ["PL","DE","CZ","SK","HU","RO","BG","FR"], "pl", True, 1200.0),
            ("TIP Trailer Services", "intelligence@tipeurope.com", "enterprise_api", ["NL","DE","BE","FR","GB","ES","IT","PL"], "en", True, 1500.0),
            ("PKS Gdansk-Oliwa S.A.", "bezpieczenstwo@pksgdansk.pl", "basic_reports", ["PL","DE"], "pl", True, 200.0),
            ("Dachser SE", "risk-mgmt@dachser.com", "premium_alerts", ["DE","FR","NL","AT","CZ","PL"], "en", False, 0.0),
            ("Kuehne+Nagel Int.", "security@kuehne-nagel.com", "enterprise_api", ["DE","NL","FR","IT","ES","PL","CZ","AT","HU","RO"], "en", True, 2000.0),
        ]
        for name, email, tier, countries, lang, active, fee in sub_data:
            s = Subscriber(
                company_name=name, contact_email=email,
                subscription_tier=tier, subscribed_countries=countries,
                language_preference=lang, is_active=active,
                subscription_start=_d(180), monthly_fee_eur=fee,
            )
            session.add(s)

        # ── AGENT STATUSES ───────────────────────────────────────
        agent_countries = ["DE", "PL", "FR", "NL", "IT", "ES", "RO", "CZ", "HU", "AT", "BE", "BG", "HR", "SK", "SE", "LT", "GR", "SI", "DK", "GB"]
        agent_types = ["police", "news", "forum", "financial"]
        for cc in agent_countries:
            for at in agent_types:
                status_val = "running"
                errors = 0
                if cc in ("BG", "GR") and at == "financial":
                    status_val = "error"
                    errors = random.randint(3, 8)
                elif cc in ("DK", "SI") and at == "forum":
                    status_val = "stopped"

                ag = AgentStatus(
                    country_code=cc, agent_type=at, status=status_val,
                    last_heartbeat=_dt(0, random.randint(0, 23), random.randint(0, 59)),
                    events_collected_today=random.randint(0, 25),
                    errors_today=errors,
                    uptime_seconds=random.randint(3600, 86400),
                )
                session.add(ag)

        # ── AUDIT LOG ────────────────────────────────────────────
        for i, ev in enumerate(event_objs[:20]):
            al = AuditLog(
                event_id=ev.id,
                action="collected",
                reason="Automated collection by agent",
                processed_by=f"agent_{ev.country_code.lower()}_police",
                country_code=ev.country_code,
            )
            session.add(al)

        # ── DEFAULT ADMIN USER ─────────────────────────────────
        admin = User(
            email="admin@transport-intel.com",
            password_hash=hash_password("admin123"),
            full_name="System Administrator",
            role="admin",
            is_active=True,
        )
        session.add(admin)

        # ── COMPANY FINANCIALS ───────────────────────────────────
        fin_data = [
            ("PolTruck sp. z o.o.", "bankruptcy_filing", 8, "Filed for bankruptcy at Sad Rejonowy Warszawa.", None),
            ("PolTruck sp. z o.o.", "payment_delay", 30, "60+ day payment delays reported.", None),
            ("PolTruck sp. z o.o.", "payment_delay", 50, "First reports of delayed payments.", None),
            ("RoTrans SRL", "license_revoked", 9, "ISCTR revoked international transport license.", None),
            ("RoTrans SRL", "payment_delay", 25, "Payment delays to Romanian subcontractors.", None),
            ("SpedLogistics Kft", "restructuring", 7, "Court-supervised restructuring proceedings.", None),
            ("Balkan Express d.o.o.", "payment_delay", 10, "90+ day payment delays.", None),
            ("HellasTruck A.E.", "payment_delay", 3, "120+ day delays across EU subcontractors.", None),
            ("BulgarTrans EOOD", "payment_delay", 2, "75+ day payment delays increasing.", None),
            ("TransBaltic UAB", "payment_delay", 12, "60+ day delays to Polish subcontractors.", None),
        ]
        for comp_name, fetype, days_ago, desc, amount in fin_data:
            cf = CompanyFinancial(
                company_id=comp_map[comp_name],
                event_type=fetype,
                date_occurred=_d(days_ago),
                description=desc,
                amount_eur=amount,
                is_verified=True,
            )
            session.add(cf)

        await session.commit()
        print(f"Seed complete: {len(event_rows)} events, {len(company_data)} companies, "
              f"{len(source_data)} sources, {len(alert_data)} alerts, "
              f"{len(hotspot_data)} hotspots, {len(corr_data)} correlations.")

    await engine.dispose()


async def main():
    parser = argparse.ArgumentParser(description="Transport Intelligence DB init")
    parser.add_argument("--migrate", action="store_true", help="Run alembic upgrade head")
    parser.add_argument("--seed", action="store_true", help="Migrate + seed demo data")
    parser.add_argument("--drop", action="store_true", help="Drop all tables")
    parser.add_argument("--reset", action="store_true", help="Drop + migrate + seed")
    args = parser.parse_args()

    if args.reset:
        await drop_all_tables()
        run_alembic_upgrade()
        await seed_demo_data()
    elif args.drop:
        await drop_all_tables()
    elif args.seed:
        run_alembic_upgrade()
        await seed_demo_data()
    elif args.migrate:
        run_alembic_upgrade()
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
