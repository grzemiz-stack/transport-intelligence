"""Testy dla pipeline/classifier.py — klasyfikacja zdarzen transportowych.

Pokrywa:
- EventClassifier.classify() — pelna klasyfikacja (event_type + severity + tags)
- _classify_type() — keyword matching per jezyk, scoring, fallback na en
- _determine_severity() — reguly severity na podstawie typu/tekstu/kwoty
- _extract_tags() — wyciaganie tagow z tekstu
- Negacja: "nie doszlo do kradziezy" — znane ograniczenie (substring matching)
- False positives: slowa w kontekscie nie-transportowym
- Edge cases: brak tekstu, nieznany jezyk, wiele typow, EventType/Severity enum
"""

import pytest

from src.pipeline.classifier import (
    KEYWORDS,
    EventClassifier,
    EventType,
    Severity,
    _determine_severity,
)

# -- Fixtures ----------------------------------------------------------------


@pytest.fixture
def classifier():
    return EventClassifier()


def _make_event(title="", description="", language="en", raw_text="",
                financial_impact_eur=None):
    ev = {
        "title": title,
        "description": description,
        "language": language,
        "raw_text": raw_text,
    }
    if financial_impact_eur is not None:
        ev["financial_impact_eur"] = financial_impact_eur
    return ev


# -- Enums -------------------------------------------------------------------


class TestEnums:
    """Wartosci EventType i Severity enum."""

    def test_event_type_values(self):
        assert EventType.THEFT_CARGO == "theft_cargo"
        assert EventType.DAMAGE == "damage"
        assert EventType.BANKRUPTCY == "bankruptcy"
        assert EventType.OTHER == "other"

    def test_severity_values(self):
        assert Severity.CRITICAL == "critical"
        assert Severity.HIGH == "high"
        assert Severity.MEDIUM == "medium"
        assert Severity.LOW == "low"
        assert Severity.INFO == "info"

    def test_event_type_is_str(self):
        """EventType inherits from str — can be used as dict key."""
        assert isinstance(EventType.THEFT_CARGO, str)

    def test_all_event_types_have_keywords(self):
        """Every EventType (except OTHER) should have keywords defined."""
        for et in EventType:
            if et == EventType.OTHER:
                continue
            assert et.value in KEYWORDS, f"Missing keywords for {et.value}"


# -- classify() — event_type detection per language --------------------------


class TestClassifyEventType:
    """Klasyfikacja event_type na podstawie slow kluczowych."""

    # --- English ---

    def test_cargo_theft_en(self, classifier):
        ev = _make_event(title="Cargo theft on M1 motorway", language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "theft_cargo"

    def test_fuel_theft_en(self, classifier):
        ev = _make_event(title="Diesel theft at truck stop", language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "theft_fuel"

    def test_vehicle_theft_en(self, classifier):
        ev = _make_event(title="Stolen truck found abandoned", language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "theft_vehicle"

    def test_damage_en(self, classifier):
        ev = _make_event(title="Truck accident on highway A2", language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "damage"

    def test_delay_en(self, classifier):
        ev = _make_event(title="Major traffic jam on border crossing", language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "delay"

    def test_strike_en(self, classifier):
        ev = _make_event(title="Trucker strike blocks main routes", language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "strike"

    def test_bankruptcy_en(self, classifier):
        ev = _make_event(title="Haulage company filed for bankruptcy", language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "bankruptcy"

    def test_payment_issue_en(self, classifier):
        ev = _make_event(title="Unpaid invoices from freight company", language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "payment_issue"

    def test_restructuring_en(self, classifier):
        ev = _make_event(title="Major restructuring at logistics group", language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "restructuring"

    def test_license_revoked_en(self, classifier):
        ev = _make_event(title="Transport license revoked for safety violations", language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "license_revoked"

    def test_route_closure_en(self, classifier):
        ev = _make_event(title="Highway closed due to road works", language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "route_closure"

    def test_other_en(self, classifier):
        ev = _make_event(title="New warehouse opened in Rotterdam", language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "other"

    # --- German ---

    def test_cargo_theft_de(self, classifier):
        ev = _make_event(title="Ladungsdiebstahl auf der A7", language="de")
        result = classifier.classify(ev)
        assert result["event_type"] == "theft_cargo"

    def test_damage_de(self, classifier):
        ev = _make_event(title="Schwerer Unfall auf der Autobahn", language="de")
        result = classifier.classify(ev)
        assert result["event_type"] == "damage"

    def test_bankruptcy_de(self, classifier):
        ev = _make_event(title="Spedition meldet Insolvenz an", language="de")
        result = classifier.classify(ev)
        assert result["event_type"] == "bankruptcy"

    def test_route_closure_de(self, classifier):
        ev = _make_event(title="Autobahn gesperrt wegen Baustelle", language="de")
        result = classifier.classify(ev)
        assert result["event_type"] == "route_closure"

    # --- Polish ---

    def test_cargo_theft_pl(self, classifier):
        ev = _make_event(title="Kradzież ładunku z naczepy na parkingu", language="pl")
        result = classifier.classify(ev)
        assert result["event_type"] == "theft_cargo"

    def test_damage_pl(self, classifier):
        ev = _make_event(title="Wypadek ciężarówki na autostradzie A4", language="pl")
        result = classifier.classify(ev)
        assert result["event_type"] == "damage"

    def test_delay_pl(self, classifier):
        ev = _make_event(title="Opóźnienie na granicy z Niemcami", language="pl")
        result = classifier.classify(ev)
        assert result["event_type"] == "delay"

    def test_strike_pl(self, classifier):
        ev = _make_event(title="Strajk kierowców na trasie Warszawa-Gdańsk", language="pl")
        result = classifier.classify(ev)
        assert result["event_type"] == "strike"

    def test_bankruptcy_pl(self, classifier):
        ev = _make_event(
            title="Ogłoszenie upadłości firmy transportowej z Łodzi", language="pl"
        )
        result = classifier.classify(ev)
        assert result["event_type"] == "bankruptcy"

    # --- French ---

    def test_cargo_theft_fr(self, classifier):
        ev = _make_event(title="Vol de marchandises sur l'autoroute A1", language="fr")
        result = classifier.classify(ev)
        assert result["event_type"] == "theft_cargo"

    def test_strike_fr(self, classifier):
        ev = _make_event(title="Grève des routiers bloque le port", language="fr")
        result = classifier.classify(ev)
        assert result["event_type"] == "strike"

    # --- Turkish ---

    def test_damage_tr(self, classifier):
        ev = _make_event(title="Tır kazası İstanbul'da", language="tr")
        result = classifier.classify(ev)
        assert result["event_type"] == "damage"

    # --- Ukrainian ---

    def test_cargo_theft_uk(self, classifier):
        ev = _make_event(title="Крадіжка вантажу на трасі Київ-Одеса", language="uk")
        result = classifier.classify(ev)
        assert result["event_type"] == "theft_cargo"


# -- Source language scoring (2x) vs English fallback (1x) ------------------


class TestScoringPriority:
    """Weryfikacja systemu scoringu: jezyk zrodlowy 2x, EN fallback 1x."""

    def test_source_lang_beats_en_fallback(self, classifier):
        """When source-language keywords match one type and English keywords
        match another, source language wins (2 pts vs 1 pt)."""
        # "Stau" = German "delay" (2 pts), "accident" = English "damage" (1 pt)
        ev = _make_event(
            title="Stau nach accident", language="de"
        )
        result = classifier.classify(ev)
        assert result["event_type"] == "delay"

    def test_english_fallback_used_for_unknown_lang(self, classifier):
        """Unknown language uses English keywords as primary (1 pt each)."""
        ev = _make_event(title="Cargo theft reported", language="xx")
        result = classifier.classify(ev)
        assert result["event_type"] == "theft_cargo"

    def test_multiple_keywords_accumulate(self, classifier):
        """More matching keywords = higher score for that type."""
        ev = _make_event(
            title="Cargo theft and stolen goods from hijacked truck",
            language="en",
        )
        result = classifier.classify(ev)
        assert result["event_type"] == "theft_cargo"

    def test_description_and_raw_text_also_matched(self, classifier):
        """classify() combines title + description + raw_text."""
        ev = _make_event(
            title="Incident report",
            description="cargo theft",
            raw_text="stolen goods from lorry",
            language="en",
        )
        result = classifier.classify(ev)
        assert result["event_type"] == "theft_cargo"


# -- _determine_severity() --------------------------------------------------


class TestSeverity:
    """Reguly severity."""

    def test_cargo_theft_critical_above_50k(self):
        sev = _determine_severity("theft_cargo", "stolen", 60000)
        assert sev == "critical"

    def test_cargo_theft_high_below_50k(self):
        sev = _determine_severity("theft_cargo", "stolen", 30000)
        assert sev == "high"

    def test_cargo_theft_high_no_impact(self):
        sev = _determine_severity("theft_cargo", "stolen", None)
        assert sev == "high"

    def test_vehicle_theft_critical_above_50k(self):
        sev = _determine_severity("theft_vehicle", "truck", 100000)
        assert sev == "critical"

    def test_vehicle_theft_high(self):
        sev = _determine_severity("theft_vehicle", "truck", None)
        assert sev == "high"

    def test_bankruptcy_critical_above_1m(self):
        sev = _determine_severity("bankruptcy", "firma", 2000000)
        assert sev == "critical"

    def test_bankruptcy_high_below_1m(self):
        sev = _determine_severity("bankruptcy", "firma", 500000)
        assert sev == "high"

    def test_license_revoked_high(self):
        sev = _determine_severity("license_revoked", "license", None)
        assert sev == "high"

    def test_strike_high_if_general(self):
        sev = _determine_severity("strike", "Generalstreik im Land", None)
        assert sev == "high"

    def test_strike_high_if_blockade(self):
        sev = _determine_severity("strike", "blokada granicy", None)
        assert sev == "high"

    def test_strike_medium_normal(self):
        sev = _determine_severity("strike", "local protest", None)
        assert sev == "medium"

    def test_fuel_theft_medium(self):
        sev = _determine_severity("theft_fuel", "diesel", None)
        assert sev == "medium"

    def test_damage_medium(self):
        sev = _determine_severity("damage", "accident", None)
        assert sev == "medium"

    def test_payment_issue_medium(self):
        sev = _determine_severity("payment_issue", "unpaid", None)
        assert sev == "medium"

    def test_restructuring_medium(self):
        sev = _determine_severity("restructuring", "plan", None)
        assert sev == "medium"

    def test_route_closure_medium(self):
        sev = _determine_severity("route_closure", "closed", None)
        assert sev == "medium"

    def test_delay_low(self):
        sev = _determine_severity("delay", "queue", None)
        assert sev == "low"

    def test_other_info(self):
        sev = _determine_severity("other", "something", None)
        assert sev == "info"

    def test_empty_text(self):
        sev = _determine_severity("other", "", None)
        assert sev == "info"

    def test_none_text_handled(self):
        sev = _determine_severity("other", None, None)
        assert sev == "info"


# -- Tags -------------------------------------------------------------------


class TestTagExtraction:
    """Tag extraction z tekstu."""

    def test_autostrada_tag(self, classifier):
        """Tag matching is exact substring — 'autostrada' matches but
        inflected form 'autostradzie' does not."""
        ev = _make_event(title="Wypadek na autostrada A4", language="pl")
        result = classifier.classify(ev)
        assert "autostrada" in result["tags"]

    def test_autostrada_inflected_no_tag(self, classifier):
        """Polish inflection: 'autostradzie' does not contain 'autostrada'."""
        ev = _make_event(title="Wypadek na autostradzie A4", language="pl")
        result = classifier.classify(ev)
        assert "autostrada" not in result["tags"]

    def test_parking_tag(self, classifier):
        ev = _make_event(title="Theft at parking lot near highway", language="en")
        result = classifier.classify(ev)
        assert "parking" in result["tags"]

    def test_nocna_tag(self, classifier):
        ev = _make_event(title="Nocna kradzież na MOP", language="pl")
        result = classifier.classify(ev)
        assert "nocna" in result["tags"]

    def test_paliwo_tag(self, classifier):
        ev = _make_event(title="Diesel theft from parked truck", language="en")
        result = classifier.classify(ev)
        assert "paliwo" in result["tags"]

    def test_granica_tag(self, classifier):
        ev = _make_event(title="Customs delay at border crossing", language="en")
        result = classifier.classify(ev)
        assert "granica" in result["tags"]

    def test_multiple_tags(self, classifier):
        ev = _make_event(
            title="Nocna kradzież elektroniki z parkingu na autostrada",
            language="pl",
        )
        result = classifier.classify(ev)
        tags = result["tags"]
        assert "nocna" in tags
        assert "autostrada" in tags
        assert "parking" in tags
        assert "elektronika" in tags

    def test_no_tags_for_generic_text(self, classifier):
        ev = _make_event(title="Company report published", language="en")
        result = classifier.classify(ev)
        assert result["tags"] == []

    def test_zorganizowana_tag(self, classifier):
        ev = _make_event(
            title="Gang of thieves targeted transport vehicles", language="en"
        )
        result = classifier.classify(ev)
        assert "zorganizowana" in result["tags"]


# -- Negation (known limitation) -------------------------------------------


class TestNegation:
    """Negacja — znane ograniczenie keyword matching.

    Classifier uzywa substring matching (kw in text), wiec NIE wykrywa negacji.
    Te testy dokumentuja to zachowanie jako known limitation.
    """

    def test_negated_theft_with_inflection_misses(self, classifier):
        """Polish inflection accidentally prevents false positive:
        'kradzieży ładunku' (genitive) != 'kradzież ładunku' (nominative)."""
        ev = _make_event(
            title="Policja informuje: nie doszło do kradzieży ładunku",
            language="pl",
        )
        result = classifier.classify(ev)
        # Inflected form doesn't match keyword — classifies as OTHER
        assert result["event_type"] == "other"

    def test_negated_theft_nominative_still_matches(self, classifier):
        """Without inflection, negation is NOT detected (known limitation)."""
        ev = _make_event(
            title="To nie była kradzież ładunku lecz pomyłka",
            language="pl",
        )
        result = classifier.classify(ev)
        # Exact keyword "kradzież ładunku" IS a substring — classified as theft
        assert result["event_type"] == "theft_cargo"

    def test_negated_accident_still_classified_as_damage(self, classifier):
        """'no accident occurred' still matches 'accident'."""
        ev = _make_event(
            title="Fortunately no accident occurred on the highway",
            language="en",
        )
        result = classifier.classify(ev)
        assert result["event_type"] == "damage"

    def test_negated_bankruptcy_still_classified(self, classifier):
        """'firm is not bankrupt' still matches 'bankrupt'."""
        ev = _make_event(
            title="Despite rumours, the firm is not bankrupt",
            language="en",
        )
        result = classifier.classify(ev)
        assert result["event_type"] == "bankruptcy"


# -- False positives (contextual ambiguity) --------------------------------


class TestFalsePositives:
    """Potencjalne false positives — slowa w kontekscie nie-transportowym."""

    def test_accident_insurance_classified_as_damage(self, classifier):
        """'accident insurance' contains 'accident' — classified as damage."""
        ev = _make_event(
            title="New accident insurance policy for fleet operators",
            language="en",
        )
        result = classifier.classify(ev)
        # Known limitation: insurance context not distinguished
        assert result["event_type"] == "damage"

    def test_fuel_price_classified_as_fuel_theft(self, classifier):
        """'fuel' alone can trigger fuel_theft if combined with other words."""
        ev = _make_event(
            title="Fuel prices rising sharply across Europe", language="en"
        )
        result = classifier.classify(ev)
        # "fuel" alone does not match — keyword is "fuel theft" (multi-word)
        assert result["event_type"] != "theft_fuel"

    def test_strike_bowling_not_transport_strike(self, classifier):
        """'strike' in bowling context — single word 'strike' IS a keyword."""
        ev = _make_event(
            title="Strike at the bowling championship", language="en"
        )
        result = classifier.classify(ev)
        # "strike" is indeed a keyword
        assert result["event_type"] == "strike"

    def test_delay_in_software_context(self, classifier):
        """'delay' is a common word — matches transport 'delay' type."""
        ev = _make_event(
            title="Software release delay announced", language="en"
        )
        result = classifier.classify(ev)
        assert result["event_type"] == "delay"


# -- classify() full output structure ---------------------------------------


class TestClassifyOutput:
    """Struktura wyjscia z classify()."""

    def test_returns_dict_with_all_fields(self, classifier):
        ev = _make_event(title="Truck accident", language="en")
        result = classifier.classify(ev)
        assert "event_type" in result
        assert "severity" in result
        assert "tags" in result
        # Original fields preserved
        assert result["title"] == "Truck accident"
        assert result["language"] == "en"

    def test_does_not_mutate_input(self, classifier):
        ev = _make_event(title="Crash on A2", language="en")
        original_keys = set(ev.keys())
        classifier.classify(ev)
        assert set(ev.keys()) == original_keys

    def test_empty_event(self, classifier):
        result = classifier.classify({})
        assert result["event_type"] == "other"
        assert result["severity"] == "info"
        assert result["tags"] == []

    def test_classify_with_financial_impact(self, classifier):
        ev = _make_event(
            title="Cargo theft worth millions",
            language="en",
            financial_impact_eur=100000,
        )
        result = classifier.classify(ev)
        assert result["event_type"] == "theft_cargo"
        assert result["severity"] == "critical"


# -- KEYWORDS structure tests -----------------------------------------------


class TestKeywordsStructure:
    """Weryfikacja struktury slownika KEYWORDS."""

    def test_all_event_types_have_en(self):
        """Kazdy event_type powinien miec co najmniej EN keywords."""
        for etype, langs in KEYWORDS.items():
            assert "en" in langs, f"{etype} missing English keywords"

    def test_all_event_types_have_pl(self):
        """Kazdy event_type powinien miec PL keywords."""
        for etype, langs in KEYWORDS.items():
            assert "pl" in langs, f"{etype} missing Polish keywords"

    def test_all_event_types_have_de(self):
        """Kazdy event_type powinien miec DE keywords."""
        for etype, langs in KEYWORDS.items():
            assert "de" in langs, f"{etype} missing German keywords"

    def test_keywords_are_lowercase(self):
        """Sprawdza ze keywords sa lowercase (matching uzywa .lower())."""
        for etype, langs in KEYWORDS.items():
            for lang, kws in langs.items():
                for kw in kws:
                    assert kw == kw.lower(), (
                        f"Keyword '{kw}' in {etype}/{lang} is not lowercase"
                    )

    def test_no_empty_keyword_lists(self):
        for etype, langs in KEYWORDS.items():
            for lang, kws in langs.items():
                assert len(kws) > 0, f"Empty keywords for {etype}/{lang}"


# -- Edge cases --------------------------------------------------------------


class TestEdgeCases:
    """Przypadki brzegowe."""

    def test_very_long_text(self, classifier):
        ev = _make_event(title="Accident " * 5000, language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "damage"

    def test_unicode_keywords_matched(self, classifier):
        ev = _make_event(
            title="Opóźnienia na granicy z powodu kontroli celnej", language="pl"
        )
        result = classifier.classify(ev)
        # "opóźnienia" matches pl delay keywords
        assert result["event_type"] == "delay"

    def test_mixed_case_text_matched(self, classifier):
        ev = _make_event(title="CARGO THEFT ON MOTORWAY", language="en")
        result = classifier.classify(ev)
        assert result["event_type"] == "theft_cargo"

    def test_financial_impact_zero_not_critical(self):
        sev = _determine_severity("theft_cargo", "stolen", 0)
        assert sev == "high"  # 0 is falsy, so not > 50k

    def test_financial_impact_exactly_50k(self):
        sev = _determine_severity("theft_cargo", "stolen", 50000)
        assert sev == "high"  # > 50000 required, not >=

    def test_financial_impact_exactly_1m_bankruptcy(self):
        sev = _determine_severity("bankruptcy", "firma", 1000000)
        assert sev == "high"  # > 1000000 required, not >=

    def test_get_keywords_returns_dict(self, classifier):
        kw = classifier._get_keywords()
        assert isinstance(kw, dict)
        assert "theft_cargo" in kw
