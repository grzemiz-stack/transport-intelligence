"""Testy dla pipeline/normalizer.py — normalizacja zdarzen transportowych.

Pokrywa:
- normalize() — pelna normalizacja (tekst, country_code, daty, waluty, jezyk)
- _normalize_text() — NFC, whitespace, newlines
- _normalize_date_to_utc() — parsowanie dat do UTC ISO 8601
- detect_language() — wykrywanie jezyka na podstawie common words
- normalize_company_name() — usuwanie form prawnych, title case, akronimy
- Currency conversion — przeliczanie kwot na EUR
- Edge cases: brak pol, puste stringi, nieznane waluty
"""

import pytest

from src.pipeline.normalizer import EventNormalizer, _EXCHANGE_RATES_TO_EUR


@pytest.fixture
def normalizer():
    return EventNormalizer()


def _make_event(**kwargs):
    return kwargs


# -- normalize() — full pipeline -------------------------------------------


class TestNormalize:
    """Metoda normalize() — pelna normalizacja eventu."""

    def test_returns_dict(self, normalizer):
        result = normalizer.normalize({})
        assert isinstance(result, dict)

    def test_does_not_mutate_input(self, normalizer):
        ev = {"title": "Test", "country_code": "de"}
        original_keys = set(ev.keys())
        normalizer.normalize(ev)
        assert set(ev.keys()) == original_keys

    def test_text_fields_stripped(self, normalizer):
        ev = {"title": "  Wypadek na A4  ", "description": " opis zdarzenia "}
        result = normalizer.normalize(ev)
        assert result["title"] == "Wypadek na A4"
        assert result["description"] == "opis zdarzenia"

    def test_country_code_uppercased(self, normalizer):
        ev = {"country_code": "de"}
        result = normalizer.normalize(ev)
        assert result["country_code"] == "DE"

    def test_country_code_trimmed_to_two(self, normalizer):
        ev = {"country_code": "DEU"}
        result = normalizer.normalize(ev)
        assert result["country_code"] == "DE"

    def test_country_code_stripped(self, normalizer):
        ev = {"country_code": " pl "}
        result = normalizer.normalize(ev)
        assert result["country_code"] == "PL"

    def test_empty_country_code_untouched(self, normalizer):
        ev = {"country_code": ""}
        result = normalizer.normalize(ev)
        assert result["country_code"] == ""

    def test_language_detected_if_missing(self, normalizer):
        ev = {"title": "Der LKW wurde auf der Autobahn gestohlen"}
        result = normalizer.normalize(ev)
        assert result["language"] == "de"

    def test_existing_language_preserved(self, normalizer):
        ev = {"title": "Some text", "language": "fr"}
        result = normalizer.normalize(ev)
        assert result["language"] == "fr"


# -- _normalize_text() -----------------------------------------------------


class TestNormalizeText:
    """Metoda _normalize_text() — czyszczenie tekstu."""

    def test_empty_string(self, normalizer):
        assert normalizer._normalize_text("") == ""

    def test_none_returns_empty(self, normalizer):
        assert normalizer._normalize_text(None) == ""

    def test_strip_whitespace(self, normalizer):
        assert normalizer._normalize_text("  hello  ") == "hello"

    def test_collapse_multiple_spaces(self, normalizer):
        assert normalizer._normalize_text("hello    world") == "hello world"

    def test_nbsp_replaced(self, normalizer):
        text = "hello\xa0world"
        result = normalizer._normalize_text(text)
        assert "\xa0" not in result
        assert "hello world" == result

    def test_tab_replaced(self, normalizer):
        assert normalizer._normalize_text("hello\tworld") == "hello world"

    def test_multiple_newlines_collapsed(self, normalizer):
        text = "line1\n\n\n\n\nline2"
        result = normalizer._normalize_text(text)
        assert result == "line1\n\nline2"

    def test_two_newlines_preserved(self, normalizer):
        text = "line1\n\nline2"
        result = normalizer._normalize_text(text)
        assert result == "line1\n\nline2"

    def test_nfc_normalization(self, normalizer):
        """NFC: precomposed characters (e + combining accent -> é)."""
        import unicodedata
        decomposed = unicodedata.normalize("NFD", "café")
        result = normalizer._normalize_text(decomposed)
        assert result == "café"
        # Verify it's NFC
        assert result == unicodedata.normalize("NFC", result)


# -- _normalize_date_to_utc() -----------------------------------------------


class TestNormalizeDateToUtc:
    """Metoda _normalize_date_to_utc() — parsowanie dat."""

    def test_iso_with_z(self, normalizer):
        result = normalizer._normalize_date_to_utc("2024-03-15T10:30:00Z")
        assert "2024-03-15" in result
        assert "+00:00" in result

    def test_iso_with_offset(self, normalizer):
        result = normalizer._normalize_date_to_utc("2024-03-15T12:00:00+02:00")
        assert "2024-03-15" in result
        assert "+00:00" in result
        # 12:00 CET+2 -> 10:00 UTC
        assert "10:00:00" in result

    def test_iso_without_timezone(self, normalizer):
        result = normalizer._normalize_date_to_utc("2024-03-15T10:30:00")
        assert "2024-03-15" in result

    def test_empty_returns_empty(self, normalizer):
        assert normalizer._normalize_date_to_utc("") == ""

    def test_none_returns_none(self, normalizer):
        assert normalizer._normalize_date_to_utc(None) is None

    def test_unparseable_returned_as_is(self, normalizer):
        result = normalizer._normalize_date_to_utc("15. März 2025")
        assert result == "15. März 2025"

    def test_date_only_returned_as_is(self, normalizer):
        """Date without time can't be parsed as ISO datetime."""
        result = normalizer._normalize_date_to_utc("15.03.2024")
        assert result == "15.03.2024"


# -- Currency conversion ---------------------------------------------------


class TestCurrencyConversion:
    """Przeliczanie kwot na EUR."""

    def test_pln_to_eur(self, normalizer):
        ev = {"financial_impact_eur": 1000, "currency": "PLN"}
        result = normalizer.normalize(ev)
        expected = round(1000 * _EXCHANGE_RATES_TO_EUR["PLN"], 2)
        assert result["financial_impact_eur"] == expected
        assert result["original_currency"] == "PLN"
        assert result["original_amount"] == 1000

    def test_gbp_to_eur(self, normalizer):
        ev = {"financial_impact_eur": 500, "currency": "GBP"}
        result = normalizer.normalize(ev)
        expected = round(500 * _EXCHANGE_RATES_TO_EUR["GBP"], 2)
        assert result["financial_impact_eur"] == expected

    def test_eur_not_converted(self, normalizer):
        ev = {"financial_impact_eur": 1000, "currency": "EUR"}
        result = normalizer.normalize(ev)
        assert result["financial_impact_eur"] == 1000
        assert "original_currency" not in result

    def test_no_currency_no_conversion(self, normalizer):
        ev = {"financial_impact_eur": 1000}
        result = normalizer.normalize(ev)
        assert result["financial_impact_eur"] == 1000

    def test_unknown_currency_uses_rate_1(self, normalizer):
        ev = {"financial_impact_eur": 1000, "currency": "XYZ"}
        result = normalizer.normalize(ev)
        assert result["financial_impact_eur"] == 1000.0

    def test_none_amount_no_conversion(self, normalizer):
        ev = {"financial_impact_eur": None, "currency": "PLN"}
        result = normalizer.normalize(ev)
        assert result["financial_impact_eur"] is None

    def test_case_insensitive_currency(self, normalizer):
        ev = {"financial_impact_eur": 100, "currency": "pln"}
        result = normalizer.normalize(ev)
        expected = round(100 * _EXCHANGE_RATES_TO_EUR["PLN"], 2)
        assert result["financial_impact_eur"] == expected


# -- detect_language() ------------------------------------------------------


class TestDetectLanguage:
    """Wykrywanie jezyka z tekstu."""

    def test_german(self, normalizer):
        text = "Der LKW wurde auf der Autobahn von der Polizei gestoppt"
        assert normalizer.detect_language(text) == "de"

    def test_polish(self, normalizer):
        text = "Kierowca ciężarówki został zatrzymany przez policję na autostradzie"
        assert normalizer.detect_language(text) == "pl"

    def test_english(self, normalizer):
        text = "The police have reported a truck theft on the highway"
        assert normalizer.detect_language(text) == "en"

    def test_french(self, normalizer):
        text = "La police a signalé un vol de camion sur l'autoroute"
        assert normalizer.detect_language(text) == "fr"

    def test_dutch(self, normalizer):
        text = "De politie heeft een vrachtwagen diefstal gemeld op de snelweg"
        assert normalizer.detect_language(text) == "nl"

    def test_turkish(self, normalizer):
        text = "Polis otoyolda bir tır hırsızlığı bildirdi"
        assert normalizer.detect_language(text) == "tr"

    def test_empty_defaults_to_en(self, normalizer):
        assert normalizer.detect_language("") == "en"

    def test_single_word(self, normalizer):
        """Single word may not be enough for detection — defaults to best match."""
        result = normalizer.detect_language("polizei")
        assert result == "de"


# -- normalize_company_name() -----------------------------------------------


class TestNormalizeCompanyName:
    """Normalizacja nazw firm."""

    def test_empty_returns_empty(self, normalizer):
        assert normalizer.normalize_company_name("") == ""

    def test_none_returns_empty(self, normalizer):
        assert normalizer.normalize_company_name(None) == ""

    # Legal forms removed

    @pytest.mark.parametrize("input_name, expected", [
        ("Trans-Pol sp. z o.o.", "Trans-Pol"),
        ("Schmidt Transport GmbH", "Schmidt Transport"),
        ("Maersk Logistics Ltd.", "Maersk Logistics"),
        ("DB Schenker AG", "DB Schenker"),
        ("Raben Group SA", "Raben Group"),
        ("Geis Transport s.r.o.", "Geis Transport"),
        ("PEKAES S.A.", "PEKAES"),
    ])
    def test_legal_form_removed(self, normalizer, input_name, expected):
        result = normalizer.normalize_company_name(input_name)
        assert result == expected, f"Input: {input_name!r}"

    # Prefix removed

    def test_firma_prefix_removed(self, normalizer):
        result = normalizer.normalize_company_name("Firma Transportowa Kowalski")
        assert result == "Transportowa Kowalski"

    def test_spolka_prefix_removed(self, normalizer):
        result = normalizer.normalize_company_name("Spółka Handlowa ABC")
        assert result == "Handlowa ABC"

    # Title case + acronyms preserved

    def test_title_case(self, normalizer):
        result = normalizer.normalize_company_name("transport kowalski")
        assert result == "Transport Kowalski"

    def test_acronym_preserved(self, normalizer):
        result = normalizer.normalize_company_name("DHL Express")
        assert result == "DHL Express"

    def test_multiple_acronyms(self, normalizer):
        """Only all-uppercase words are preserved — mixed case gets title-cased."""
        result = normalizer.normalize_company_name("TNT FAST service")
        assert result == "TNT FAST Service"

    def test_mixed_case_not_preserved(self, normalizer):
        """'FedEx' is not isupper() — gets title-cased to 'Fedex'."""
        result = normalizer.normalize_company_name("FedEx service")
        assert result == "Fedex Service"

    # Whitespace and quotes

    def test_double_spaces_collapsed(self, normalizer):
        result = normalizer.normalize_company_name("Transport   Kowalski")
        assert result == "Transport Kowalski"

    def test_quotes_stripped(self, normalizer):
        result = normalizer.normalize_company_name('"Trans-Pol"')
        assert result == "Trans-Pol"

    def test_polish_quotes_stripped(self, normalizer):
        result = normalizer.normalize_company_name("\u201eTrans-Pol\u201d")
        assert result == "Trans-Pol"


# -- Exchange rates structure -----------------------------------------------


class TestExchangeRates:
    """Struktura slownika kursow walut."""

    def test_eur_is_one(self):
        assert _EXCHANGE_RATES_TO_EUR["EUR"] == 1.0

    def test_major_currencies_present(self):
        for cur in ("PLN", "GBP", "CHF", "CZK", "USD", "TRY", "HUF", "RON"):
            assert cur in _EXCHANGE_RATES_TO_EUR

    def test_rates_positive(self):
        for cur, rate in _EXCHANGE_RATES_TO_EUR.items():
            assert rate > 0, f"Rate for {cur} should be positive"


# -- Edge cases --------------------------------------------------------------


class TestEdgeCases:
    """Przypadki brzegowe."""

    def test_normalize_preserves_unknown_fields(self, normalizer):
        ev = {"title": "Test", "custom_field": "value"}
        result = normalizer.normalize(ev)
        assert result["custom_field"] == "value"

    def test_all_text_fields_normalized(self, normalizer):
        ev = {
            "title": "  hello  world  ",
            "description": "  foo\xa0bar  ",
            "raw_text": "  baz\tqux  ",
        }
        result = normalizer.normalize(ev)
        assert result["title"] == "hello world"
        assert result["description"] == "foo bar"
        assert result["raw_text"] == "baz qux"

    def test_date_fields_normalized(self, normalizer):
        ev = {
            "date": "2024-01-01T12:00:00Z",
            "collected_at": "2024-01-01T14:00:00+02:00",
        }
        result = normalizer.normalize(ev)
        assert "+00:00" in result["date"]
        assert "+00:00" in result["collected_at"]

    def test_missing_text_fields_untouched(self, normalizer):
        ev = {"country_code": "PL"}
        result = normalizer.normalize(ev)
        assert "title" not in result

    def test_unicode_company_name(self, normalizer):
        result = normalizer.normalize_company_name("Złote Kółko sp. z o.o.")
        assert result == "Złote Kółko"
