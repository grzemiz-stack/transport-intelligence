"""Tests for config-driven police agents and custom subclasses.

Covers: BasePoliceAgent with configs (PL, EE, NL, HU, ES, GB),
custom subclasses (DE, AT, TR, CH), registry completeness.
"""

import asyncio

import pytest

from src.agents.police.base import BasePoliceAgent
from src.agents.police.sources import SOURCES
from src.agents.police.custom.germany import BundespolizeiAgent
from src.agents.police.custom.austria import AustrianPoliceAgent
from src.agents.police.custom.turkey import TurkishPoliceAgent
from src.agents.police.custom.switzerland import SwissPoliceAgent

# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

# -- PL: dot dates, "data" class, /pol/aktualnosci/ fallback ---------------
HTML_PL = """\
<html><body>
<article>
  <h3><a href="/pol/aktualnosci/kradziez-tira">Kradzież paliwa z ciężarówki TIR na autostradzie A2</a></h3>
  <p>Policjanci zatrzymali sprawcę kradzieży paliwa diesel z naczepy na parkingu.</p>
  <span class="data">15.03.2025</span>
</article>
<article>
  <h3><a href="/pol/aktualnosci/koncert">Koncert charytatywny w Warszawie</a></h3>
  <p>Policja zabezpieczala koncert na Stadionie Narodowym.</p>
  <span class="data">14.03.2025</span>
</article>
</body></html>
"""

# -- EE: ISO dates first, <time> element ----------------------------------
HTML_EE = """\
<html><body>
<article>
  <h3><a href="/et/uudised/veoauto-vargus">Veoauto vargus maanteel — diisel varastatud</a></h3>
  <p>Politsei otsib kahtlustatavaid seoses veoauto kütuse vargusega kiirteel.</p>
  <time datetime="2025-03-15">2025-03-15</time>
</article>
<article>
  <h3><a href="/et/uudised/kontsert">Rahvusvaheline kontsert Tallinnas</a></h3>
  <p>Politsei tagas turvalisuse suurüritusel.</p>
  <time datetime="2025-03-14">2025-03-14</time>
</article>
</body></html>
"""

# -- NL: dash dates, "datum" class, /nieuws/ fallback ----------------------
HTML_NL = """\
<html><body>
<article>
  <h3><a href="/nieuws/diefstal-vrachtwagen">Diefstal uit vrachtwagen op snelweg A12</a></h3>
  <p>De politie zoekt getuigen van diefstal van lading uit een vrachtwagen.</p>
  <span class="datum">15-03-2025</span>
</article>
<article>
  <h3><a href="/nieuws/concert">Concert in Amsterdam verloopt rustig</a></h3>
  <p>De politie was aanwezig bij het grote evenement in de RAI.</p>
  <span class="datum">14-03-2025</span>
</article>
</body></html>
"""

# -- HU: YYYY.MM.DD dates, views-row selector -----------------------------
HTML_HU = """\
<html><body>
<div class="view-content">
  <div class="views-row">
    <h3><a href="/hu/hirek/kamion-lopas">Kamion lopás az autópályán — dízel elloptak</a></h3>
    <p>A rendőrség keresi az elkövetőket egy kamionból történt dízel lopás ügyében.</p>
    <span class="datum">2025.03.15</span>
  </div>
  <div class="views-row">
    <h3><a href="/hu/hirek/koncert">Koncert Budapesten rendben zajlott</a></h3>
    <p>A rendőrség biztosította a nagy rendezvényt.</p>
    <span class="datum">2025.03.14</span>
  </div>
</div>
</body></html>
"""

# -- ES: slash dates, "fecha" class, div.noticia selector, "tr" selector ---
HTML_ES = """\
<html><body>
<div class="noticia">
  <h3><a href="/prensa/robo-camion">Robo de carga en camión en la autopista A-4</a></h3>
  <p>La policía investiga el robo de mercancía de un camión aparcado.</p>
  <span class="fecha">15/03/2025</span>
</div>
<div class="noticia">
  <h3><a href="/prensa/concierto">Concierto en Madrid sin incidentes</a></h3>
  <p>La policía garantizó la seguridad del evento.</p>
  <span class="fecha">14/03/2025</span>
</div>
</body></html>
"""

# -- GB: slash dates, "published" class, div.search-result selector --------
HTML_GB = """\
<html><body>
<div class="search-result">
  <h3><a href="/news/lorry-theft">Theft of cargo from lorry on M25 motorway</a></h3>
  <p>Police are investigating a theft of goods from a heavy goods vehicle.</p>
  <span class="published">15/03/2025</span>
</div>
<div class="search-result">
  <h3><a href="/news/concert">Concert at Wembley passes peacefully</a></h3>
  <p>Officers ensured safety at the large event.</p>
  <span class="published">14/03/2025</span>
</div>
</body></html>
"""

# -- DE: dual source (presseportal + bundespolizei) ------------------------
HTML_DE = """\
<!-- SOURCE:presseportal -->
<html><body>
<article>
  <h3><a href="/blaulicht/pm/12345">LKW-Ladung auf Autobahn A3 gestohlen</a></h3>
  <p>Diebstahl von Diesel und Fracht aus einem Sattelzug auf einem Rastplatz.</p>
  <span class="date">15.03.2025</span>
</article>
</body></html>
<!-- SEPARATOR -->
<!-- SOURCE:bundespolizei -->
<html><body>
<article>
  <h3><a href="/meldungen/unfall-lkw">Schwerer Unfall mit LKW auf der A1</a></h3>
  <p>Ein Lastwagen kollidierte mit einem Transporter auf der Autobahn.</p>
  <time datetime="2025-03-14">14.03.2025</time>
</article>
</body></html>
"""

# -- AT: dual source (presseportal AT + BMI) -------------------------------
HTML_AT = """\
<!-- SOURCE:presseportal -->
<html><body>
<article>
  <h3><a href="/blaulicht/pm/67890">LKW-Diebstahl auf Autobahn A1 bei Salzburg</a></h3>
  <p>Unbekannte stahlen Ladung aus einem abgestellten Sattelzug.</p>
  <span class="datum">15.03.2025</span>
</article>
</body></html>
<!-- SEPARATOR -->
<!-- SOURCE:bmi -->
<html><body>
<article>
  <h3><a href="/news/lkw-unfall">Schwerer Unfall mit LKW auf der A2</a></h3>
  <p>Ein Lastwagen kollidierte mit einem Transporter — Ladung beschädigt.</p>
  <time datetime="2025-03-14">14.03.2025</time>
</article>
</body></html>
"""

# -- TR: dual source (EGM + AA) with different trust scores ----------------
HTML_TR = """\
<!-- SOURCE:egm -->
<html><body>
<article>
  <h3><a href="/haberler/kamyon-hirsizlik">Otoyolda kamyon hırsızlığı — yakıt çalıntı</a></h3>
  <p>Polis kamyondan mazot hırsızlığı şüphelilerini arıyor.</p>
  <time datetime="2025-03-15">15.03.2025</time>
</article>
</body></html>
<!-- SEPARATOR -->
<!-- SOURCE:aa -->
<html><body>
<article>
  <h3><a href="/tr/gundem/tir-kaza">TIR kazası otobanda — nakliye hasarı</a></h3>
  <p>Otobanda bir tır kazası sonucu nakliye yükü hasar gördü.</p>
  <time datetime="2025-03-14">14.03.2025</time>
</article>
</body></html>
"""

# -- CH: card-based layout, DD. MONTH YYYY dates --------------------------
HTML_CH = """\
<html><body>
<div class="card">
  <div class="card__title"><a href="/de/medien/lkw-diebstahl">Diebstahl aus LKW auf Autobahn A1</a></div>
  <div class="card__description">Unbekannte entwendeten Ladung aus einem Sattelzug bei Bern.</div>
  <span>15. März 2025</span>
</div>
<div class="card">
  <div class="card__title"><a href="/de/medien/konzert">Konzert in Zürich ohne Zwischenfälle</a></div>
  <div class="card__description">Die Polizei sicherte die Veranstaltung ab.</div>
  <span>14. März 2025</span>
</div>
</body></html>
"""

# Fields with datetime.utcnow() — skip in comparison
DYNAMIC_FIELDS = {"timestamp", "collected_at"}


def _strip_dynamic(events: list[dict]) -> list[dict]:
    return [{k: v for k, v in ev.items() if k not in DYNAMIC_FIELDS} for ev in events]


# ---------------------------------------------------------------------------
# Standard configs (BasePoliceAgent)
# ---------------------------------------------------------------------------


class TestPolishPolice:
    def test_transport_filter(self):
        agent = BasePoliceAgent(SOURCES["PL"])
        events = asyncio.run(agent.parse(HTML_PL))
        assert len(events) == 1
        assert "tir" in events[0]["title"].lower() or "kradzież" in events[0]["title"].lower()

    def test_date_extraction(self):
        agent = BasePoliceAgent(SOURCES["PL"])
        events = asyncio.run(agent.parse(HTML_PL))
        assert events[0]["date"] == "15.03.2025"

    def test_link_resolution(self):
        agent = BasePoliceAgent(SOURCES["PL"])
        events = asyncio.run(agent.parse(HTML_PL))
        assert events[0]["source_url"] == "https://policja.pl/pol/aktualnosci/kradziez-tira"

    def test_metadata(self):
        agent = BasePoliceAgent(SOURCES["PL"])
        events = asyncio.run(agent.parse(HTML_PL))
        ev = events[0]
        assert ev["country_code"] == "PL"
        assert ev["language"] == "pl"
        assert ev["source_name"] == "Policja Polska"
        assert ev["trust_score"] == 1.0
        assert ev["is_official"] is True


class TestEstonianPolice:
    def test_transport_filter(self):
        agent = BasePoliceAgent(SOURCES["EE"])
        events = asyncio.run(agent.parse(HTML_EE))
        assert len(events) == 1

    def test_date_from_time_element(self):
        agent = BasePoliceAgent(SOURCES["EE"])
        events = asyncio.run(agent.parse(HTML_EE))
        assert events[0]["date"] == "2025-03-15"

    def test_link_resolution(self):
        agent = BasePoliceAgent(SOURCES["EE"])
        events = asyncio.run(agent.parse(HTML_EE))
        assert events[0]["source_url"] == "https://www.politsei.ee/et/uudised/veoauto-vargus"


class TestDutchPolice:
    def test_transport_filter(self):
        agent = BasePoliceAgent(SOURCES["NL"])
        events = asyncio.run(agent.parse(HTML_NL))
        assert len(events) == 1

    def test_dash_date(self):
        agent = BasePoliceAgent(SOURCES["NL"])
        events = asyncio.run(agent.parse(HTML_NL))
        assert events[0]["date"] == "15-03-2025"

    def test_link_resolution(self):
        agent = BasePoliceAgent(SOURCES["NL"])
        events = asyncio.run(agent.parse(HTML_NL))
        assert events[0]["source_url"] == "https://www.politie.nl/nieuws/diefstal-vrachtwagen"


class TestHungarianPolice:
    def test_transport_filter(self):
        agent = BasePoliceAgent(SOURCES["HU"])
        events = asyncio.run(agent.parse(HTML_HU))
        assert len(events) == 1

    def test_yyyy_dot_date(self):
        """HU uses YYYY.MM.DD format (unique)."""
        agent = BasePoliceAgent(SOURCES["HU"])
        events = asyncio.run(agent.parse(HTML_HU))
        assert events[0]["date"] == "2025.03.15"

    def test_views_row_selector(self):
        """HU uses div.view-content div.views-row selector."""
        agent = BasePoliceAgent(SOURCES["HU"])
        events = asyncio.run(agent.parse(HTML_HU))
        assert len(events) == 1
        assert events[0]["country_code"] == "HU"


class TestSpanishPolice:
    def test_transport_filter(self):
        agent = BasePoliceAgent(SOURCES["ES"])
        events = asyncio.run(agent.parse(HTML_ES))
        assert len(events) == 1

    def test_slash_date(self):
        agent = BasePoliceAgent(SOURCES["ES"])
        events = asyncio.run(agent.parse(HTML_ES))
        assert events[0]["date"] == "15/03/2025"

    def test_noticia_selector(self):
        """ES uses div.noticia as 3rd selector."""
        agent = BasePoliceAgent(SOURCES["ES"])
        events = asyncio.run(agent.parse(HTML_ES))
        assert events[0]["source_url"] == "https://www.policia.es/prensa/robo-camion"


class TestUKPolice:
    def test_transport_filter(self):
        agent = BasePoliceAgent(SOURCES["GB"])
        events = asyncio.run(agent.parse(HTML_GB))
        assert len(events) == 1

    def test_published_class_date(self):
        """GB uses 'published' CSS class for dates."""
        agent = BasePoliceAgent(SOURCES["GB"])
        events = asyncio.run(agent.parse(HTML_GB))
        assert events[0]["date"] == "15/03/2025"

    def test_search_result_selector(self):
        agent = BasePoliceAgent(SOURCES["GB"])
        events = asyncio.run(agent.parse(HTML_GB))
        assert events[0]["source_url"] == "https://news.met.police.uk/news/lorry-theft"


# ---------------------------------------------------------------------------
# Fallback href discovery
# ---------------------------------------------------------------------------


class TestFallbackHrefDiscovery:
    def test_pl_fallback(self):
        html = """\
<html><body><div>
  <a href="/pol/aktualnosci/wypadek-tira">Wypadek ciężarówki na A4 — kradzież ładunku</a>
  <p>Doszlo do wypadku z udzialem TIR-a.</p>
  <span>01.04.2025</span>
</div></body></html>
"""
        agent = BasePoliceAgent(SOURCES["PL"])
        events = asyncio.run(agent.parse(html))
        assert len(events) == 1
        assert events[0]["source_url"] == "https://policja.pl/pol/aktualnosci/wypadek-tira"

    def test_nl_fallback(self):
        html = """\
<html><body><div>
  <a href="/nieuws/aanhouding-chauffeur">Aanhouding vrachtwagen chauffeur na diefstal</a>
  <p>De politie heeft een chauffeur aangehouden op de snelweg.</p>
</div></body></html>
"""
        agent = BasePoliceAgent(SOURCES["NL"])
        events = asyncio.run(agent.parse(html))
        assert len(events) == 1


# ---------------------------------------------------------------------------
# Custom subclasses
# ---------------------------------------------------------------------------


class TestGermanPolice:
    def test_dual_source_parse(self):
        agent = BundespolizeiAgent()
        events = asyncio.run(agent.parse(HTML_DE))
        assert len(events) == 2
        sources = {ev["source_name"] for ev in events}
        assert "Presseportal/Bundespolizei" in sources
        assert "Bundespolizei" in sources

    def test_presseportal_link(self):
        agent = BundespolizeiAgent()
        events = asyncio.run(agent.parse(HTML_DE))
        pp_events = [e for e in events if e["source_name"] == "Presseportal/Bundespolizei"]
        assert pp_events[0]["source_url"] == "https://www.presseportal.de/blaulicht/pm/12345"

    def test_bundespolizei_date(self):
        agent = BundespolizeiAgent()
        events = asyncio.run(agent.parse(HTML_DE))
        bp_events = [e for e in events if e["source_name"] == "Bundespolizei"]
        assert bp_events[0]["date"] == "2025-03-14"

    def test_metadata(self):
        agent = BundespolizeiAgent()
        assert agent.country_code == "DE"
        assert agent.language == "de"


class TestAustrianPolice:
    def test_dual_source_parse(self):
        agent = AustrianPoliceAgent()
        events = asyncio.run(agent.parse(HTML_AT))
        assert len(events) == 2
        sources = {ev["source_name"] for ev in events}
        assert "Presseportal/Polizei \u00d6sterreich" in sources
        assert "BMI \u00d6sterreich" in sources

    def test_presseportal_link(self):
        agent = AustrianPoliceAgent()
        events = asyncio.run(agent.parse(HTML_AT))
        pp = [e for e in events if "Presseportal" in e["source_name"]]
        assert pp[0]["source_url"] == "https://www.presseportal.de/blaulicht/pm/67890"

    def test_bmi_date(self):
        agent = AustrianPoliceAgent()
        events = asyncio.run(agent.parse(HTML_AT))
        bmi = [e for e in events if "BMI" in e["source_name"]]
        assert bmi[0]["date"] == "2025-03-14"

    def test_metadata(self):
        agent = AustrianPoliceAgent()
        assert agent.country_code == "AT"
        assert agent.language == "de"


class TestTurkishPolice:
    def test_dual_source_parse(self):
        agent = TurkishPoliceAgent()
        events = asyncio.run(agent.parse(HTML_TR))
        assert len(events) == 2

    def test_trust_score_varies(self):
        """EGM gets trust 1.0, AA gets 0.85."""
        agent = TurkishPoliceAgent()
        events = asyncio.run(agent.parse(HTML_TR))
        egm = [e for e in events if e["source_name"] == "EGM T\u00fcrkiye"]
        aa = [e for e in events if e["source_name"] == "Anadolu Ajans\u0131"]
        assert egm[0]["trust_score"] == 1.0
        assert egm[0]["is_official"] is True
        assert aa[0]["trust_score"] == 0.85
        assert aa[0]["is_official"] is False

    def test_egm_date(self):
        agent = TurkishPoliceAgent()
        events = asyncio.run(agent.parse(HTML_TR))
        egm = [e for e in events if e["source_name"] == "EGM T\u00fcrkiye"]
        assert egm[0]["date"] == "2025-03-15"

    def test_metadata(self):
        agent = TurkishPoliceAgent()
        assert agent.country_code == "TR"
        assert agent.language == "tr"


class TestSwissPolice:
    def test_card_selector(self):
        agent = SwissPoliceAgent()
        events = asyncio.run(agent.parse(HTML_CH))
        assert len(events) == 1

    def test_card_title_extraction(self):
        """CH uses div.card__title for title."""
        agent = SwissPoliceAgent()
        events = asyncio.run(agent.parse(HTML_CH))
        assert "Diebstahl" in events[0]["title"]

    def test_word_date_format(self):
        """CH uses DD. MONTH YYYY format."""
        agent = SwissPoliceAgent()
        events = asyncio.run(agent.parse(HTML_CH))
        assert "März" in events[0]["date"] or "15." in events[0]["date"]

    def test_link_resolution(self):
        agent = SwissPoliceAgent()
        events = asyncio.run(agent.parse(HTML_CH))
        assert events[0]["source_url"] == "https://www.fedpol.admin.ch/de/medien/lkw-diebstahl"

    def test_metadata(self):
        agent = SwissPoliceAgent()
        assert agent.country_code == "CH"
        assert agent.language == "de"


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_29_police_agents(self):
        from src.agents.runner import _register_agents, AGENT_REGISTRY
        AGENT_REGISTRY.clear()
        _register_agents()

        police = {k for k, v in AGENT_REGISTRY.items() if "police" in v}
        assert len(police) == 29

    def test_all_instantiate(self):
        from src.agents.runner import _register_agents, AGENT_REGISTRY
        AGENT_REGISTRY.clear()
        _register_agents()

        for code, agents in AGENT_REGISTRY.items():
            if "police" in agents:
                agent = agents["police"]()
                assert agent.country_code == code, f"{code}: got {agent.country_code}"
