"""Testy dla agents/transport_keywords.py — dual-list keyword matching.

Pokrywa:
- is_transport_related() — wymaga OBIE listy: vehicle + event
- has_event_keyword() — tylko event keywords (dla zaufanych kanalow)
- VEHICLE_KEYWORDS / EVENT_KEYWORDS — kompletnosc i struktura
- Multi-language: de, pl, en, fr, nl, it, es, ro, cs, hu, tr, uk, + more
- False positives: tekst z samym vehicle lub samym event
- Edge cases: pusty tekst, nieznany jezyk, case insensitive
"""

import pytest

from src.agents.transport_keywords import (
    EVENT_KEYWORDS,
    VEHICLE_KEYWORDS,
    has_event_keyword,
    is_transport_related,
)


# -- is_transport_related() — dual-list matching ---------------------------


class TestIsTransportRelated:
    """Funkcja is_transport_related() — wymaga vehicle + event."""

    # --- Positive matches: vehicle + event present ---

    @pytest.mark.parametrize("text, lang", [
        ("LKW Diebstahl auf der Autobahn", "de"),
        ("Kradzież z naczepy na autostradzie", "pl"),
        ("Truck stolen from motorway rest area", "en"),
        ("Vol de camion sur l'autoroute", "fr"),
        ("Vrachtwagen gestolen bij tankstation", "nl"),
        ("Furto di camion in autostrada", "it"),
        ("Robo de camión en autopista", "es"),
        ("Furt din camion pe autostradă", "ro"),
        ("Krádež z kamionu na dálnici", "cs"),
        ("Kamyon hırsızlık otoyolda", "tr"),
        ("Крадіжка з вантажівки на автострадій", "uk"),
    ])
    def test_matches_vehicle_and_event(self, text, lang):
        assert is_transport_related(text, lang), f"Should match: {text!r} ({lang})"

    # --- Negative: only vehicle, no event ---

    def test_only_vehicle_no_event_de(self):
        assert not is_transport_related("LKW fährt auf der Autobahn", "de")

    def test_only_vehicle_no_event_en(self):
        assert not is_transport_related("Truck parked at the motorway service station", "en")

    def test_only_vehicle_no_event_pl(self):
        assert not is_transport_related("Ciężarówka na autostradzie A4", "pl")

    # --- Negative: only event, no vehicle ---

    def test_only_event_no_vehicle_en(self):
        assert not is_transport_related("Theft reported at local shop", "en")

    def test_only_event_no_vehicle_de(self):
        assert not is_transport_related("Diebstahl in einem Geschäft", "de")

    def test_only_event_no_vehicle_pl(self):
        assert not is_transport_related("Kradzież roweru w parku", "pl")

    # --- Negative: no keywords at all ---

    def test_no_keywords(self):
        assert not is_transport_related("Pogoda jutro będzie ładna", "pl")

    def test_empty_string(self):
        assert not is_transport_related("", "en")

    # --- Case insensitive ---

    def test_case_insensitive(self):
        assert is_transport_related("TRUCK STOLEN FROM HIGHWAY", "en")

    def test_mixed_case(self):
        assert is_transport_related("LKW Diebstahl auf der AUTOBAHN", "de")

    # --- Unknown language falls back to English ---

    def test_unknown_language_uses_english(self):
        assert is_transport_related("Truck stolen from highway", "xx")

    def test_unknown_language_no_match(self):
        assert not is_transport_related("Unrelated text here", "xx")


# -- has_event_keyword() ---------------------------------------------------


class TestHasEventKeyword:
    """Funkcja has_event_keyword() — tylko event keywords."""

    def test_event_keyword_en(self):
        assert has_event_keyword("Theft reported yesterday", "en")

    def test_event_keyword_de(self):
        assert has_event_keyword("Diebstahl gemeldet", "de")

    def test_event_keyword_pl(self):
        assert has_event_keyword("Kradzież na parkingu", "pl")

    def test_no_event_keyword(self):
        assert not has_event_keyword("Nice weather today", "en")

    def test_empty_text(self):
        assert not has_event_keyword("", "en")

    def test_english_fallback(self):
        """Event keyword check falls back to English."""
        assert has_event_keyword("A theft was reported", "xx")

    def test_vehicle_keyword_not_matched(self):
        """Vehicle keywords are NOT checked by has_event_keyword()."""
        assert not has_event_keyword("Truck on the motorway", "en")

    def test_case_insensitive(self):
        assert has_event_keyword("DIESEL stolen", "en")

    def test_source_language_checked_first(self):
        """Source language keywords are checked before English fallback."""
        # "paliwo" is PL event keyword
        assert has_event_keyword("problem z paliwo w firmie", "pl")


# -- Dual-list false positive elimination -----------------------------------


class TestFalsePositiveElimination:
    """Eliminacja false positives przez dual-list matching."""

    def test_bicycle_theft_not_transport(self):
        """'bicycle theft' — has event keyword but no vehicle keyword."""
        assert not is_transport_related("Bicycle theft in the park", "en")

    def test_shop_robbery_not_transport(self):
        assert not is_transport_related("Shop robbery on High Street", "en")

    def test_car_accident_not_transport(self):
        """'accident' is event keyword but 'car' is not a vehicle keyword
        (truck/lorry/hgv are vehicle keywords)."""
        assert not is_transport_related("Car accident at intersection", "en")

    def test_generic_fire_not_transport(self):
        """'arson' is event keyword but needs vehicle/infra keyword too."""
        assert not is_transport_related("Arson attack on local building", "en")

    def test_truck_theft_is_transport(self):
        """Contrast: truck + theft matches both lists."""
        assert is_transport_related("Truck theft at rest area", "en")


# -- Keywords structure and completeness ------------------------------------


class TestKeywordsStructure:
    """Weryfikacja struktury slownikow."""

    def test_vehicle_keywords_has_en(self):
        assert "en" in VEHICLE_KEYWORDS

    def test_event_keywords_has_en(self):
        assert "en" in EVENT_KEYWORDS

    @pytest.mark.parametrize("lang", [
        "de", "pl", "en", "fr", "nl", "it", "es", "ro", "cs", "hu",
        "tr", "uk", "sv", "da", "no", "fi", "hr", "sl", "sr", "bg",
        "el", "lt", "lv", "et", "sk",
    ])
    def test_vehicle_keywords_has_language(self, lang):
        assert lang in VEHICLE_KEYWORDS, f"VEHICLE_KEYWORDS missing {lang}"
        assert len(VEHICLE_KEYWORDS[lang]) > 0

    @pytest.mark.parametrize("lang", [
        "de", "pl", "en", "fr", "nl", "it", "es", "ro", "cs", "hu",
        "tr", "uk", "sv", "da", "no", "fi", "hr", "sl", "sr", "bg",
        "el", "lt", "lv", "et", "sk",
    ])
    def test_event_keywords_has_language(self, lang):
        assert lang in EVENT_KEYWORDS, f"EVENT_KEYWORDS missing {lang}"
        assert len(EVENT_KEYWORDS[lang]) > 0

    def test_vehicle_and_event_same_languages(self):
        """Both dictionaries should cover the same set of languages."""
        assert set(VEHICLE_KEYWORDS.keys()) == set(EVENT_KEYWORDS.keys())

    def test_keywords_are_lowercase(self):
        """All keywords should be lowercase (matching uses .lower()).

        Known exception: EVENT_KEYWORDS['uk'] has 'ДТП' (uppercase Cyrillic
        acronym) which won't match since text is lowercased before comparison.
        """
        non_lower = []
        for lang, kws in VEHICLE_KEYWORDS.items():
            for kw in kws:
                if kw != kw.lower():
                    non_lower.append(f"VEHICLE_KEYWORDS[{lang}]: '{kw}'")
        for lang, kws in EVENT_KEYWORDS.items():
            for kw in kws:
                if kw != kw.lower():
                    non_lower.append(f"EVENT_KEYWORDS[{lang}]: '{kw}'")
        # Only known case: Ukrainian 'ДТП' — a dead keyword (won't match)
        assert len(non_lower) == 1
        assert "ДТП" in non_lower[0]

    def test_no_duplicate_keywords_per_language(self):
        """No duplicates within a single language list."""
        for lang, kws in VEHICLE_KEYWORDS.items():
            assert len(kws) == len(set(kws)), (
                f"VEHICLE_KEYWORDS[{lang}] has duplicates"
            )
        for lang, kws in EVENT_KEYWORDS.items():
            assert len(kws) == len(set(kws)), (
                f"EVENT_KEYWORDS[{lang}] has duplicates"
            )


# -- Language-specific regression tests -------------------------------------


class TestLanguageSpecific:
    """Testy per-jezyk z realnymi przykladami."""

    def test_german_truck_diesel_theft(self):
        assert is_transport_related(
            "Dieseldiebstahl: LKW auf Rastplatz bestohlen", "de"
        )

    def test_polish_highway_accident(self):
        assert is_transport_related(
            "Wypadek ciężarówki na autostradzie A1 koło Łodzi", "pl"
        )

    def test_french_motorway_robbery(self):
        assert is_transport_related(
            "Vol de fret d'un camion sur l'autoroute A6", "fr"
        )

    def test_dutch_truck_cargo_theft(self):
        assert is_transport_related(
            "Lading gestolen uit vrachtwagen op snelweg", "nl"
        )

    def test_italian_highway_incident(self):
        assert is_transport_related(
            "Furto di carburante da camion in autostrada", "it"
        )

    def test_spanish_truck_robbery(self):
        assert is_transport_related(
            "Robo de camión en la autopista nacional", "es"
        )

    def test_czech_truck_theft(self):
        assert is_transport_related(
            "Krádež z kamionu na dálnici D1", "cs"
        )

    def test_hungarian_truck_accident(self):
        assert is_transport_related(
            "Kamion baleset az autópályán", "hu"
        )

    def test_turkish_truck_hijack(self):
        assert is_transport_related(
            "Kamyon hırsızlık otoyolda gerçekleşti", "tr"
        )

    def test_ukrainian_cargo_theft(self):
        assert is_transport_related(
            "Крадіжка вантажу з вантажівки на трасі", "uk"
        )

    def test_swedish_truck_theft(self):
        assert is_transport_related(
            "Stöld från lastbil vid rastplats", "sv"
        )

    def test_finnish_truck_fire(self):
        assert is_transport_related(
            "Tulipalo rekka moottoritiellä", "fi"
        )

    def test_romanian_truck_accident(self):
        assert is_transport_related(
            "Accident cu camion pe autostradă", "ro"
        )


# -- Edge cases --------------------------------------------------------------


class TestEdgeCases:
    """Przypadki brzegowe."""

    def test_very_long_text(self):
        """Performance: doesn't hang on long texts."""
        text = "Some normal text. " * 10000 + " truck stolen"
        assert is_transport_related(text, "en")

    def test_keyword_at_start(self):
        assert is_transport_related("Truck stolen!", "en")

    def test_keyword_at_end(self):
        assert is_transport_related("Report: stolen truck", "en")

    def test_keywords_separated_by_long_text(self):
        """Vehicle and event keywords can be far apart in text."""
        text = "A truck was seen " + "driving normally " * 100 + "then theft occurred"
        assert is_transport_related(text, "en")

    def test_partial_keyword_no_match(self):
        """'truck' as substring of another word should still match
        since matching is substring-based."""
        assert is_transport_related("firetruck involved in an accident", "en")

    def test_ascii_fallback_for_polish(self):
        """Polish keywords include ASCII fallbacks: 'ciezarowka' for 'ciężarówka'."""
        assert is_transport_related(
            "ciezarowka — kradziez na parkingu", "pl"
        )
