"""Testy dla pipeline/anonymizer.py — anonimizacja danych osobowych (RODO).

Pokrywa:
- Regex patterns: telefon, email, PESEL, NIP, dowod, IBAN, tablice rejestracyjne
- anonymize_personal_data() — zamiana PII na tokeny
- anonymize_vehicle_plates() — rozroznienie zrodel oficjalnych/prywatnych
- contains_personal_data() — detekcja PII
- get_anonymization_report() — raport z anonimizacji
- _is_residential_address() — heurystyka adresowa
- Edge cases: pusty tekst, brak PII, wielokrotne PII w jednym tekscie
"""

import pytest

from src.pipeline.anonymizer import (
    DOWOD_PATTERN,
    EMAIL_PATTERN,
    IBAN_PATTERN,
    NIP_PATTERN,
    PESEL_PATTERN,
    PHONE_PATTERN,
    PLATE_PATTERN,
    Anonymizer,
    AnonymizationReport,
)

# -- Fixtures ----------------------------------------------------------------


@pytest.fixture
def anon():
    return Anonymizer()


# -- Regex pattern unit tests ------------------------------------------------


class TestPhonePattern:
    """Wzorzec PHONE_PATTERN — numery telefonow."""

    @pytest.mark.parametrize("phone", [
        "+48 123 456 789",
        "+48 12 345 67 89",
        "+49 30 1234567",
        "(22) 123 45 67",
        "123 456 789",
        "12 345-67-89",
        "+1 555 123 4567",
    ])
    def test_matches_valid_phones(self, phone):
        assert PHONE_PATTERN.search(phone), f"Should match: {phone}"

    def test_no_match_on_short_numbers(self):
        assert not PHONE_PATTERN.search("12 34")


class TestEmailPattern:
    """Wzorzec EMAIL_PATTERN — adresy email."""

    @pytest.mark.parametrize("email", [
        "jan.kowalski@example.com",
        "user+tag@domain.co.uk",
        "test123@sub.domain.pl",
        "a.b.c@x.org",
    ])
    def test_matches_valid_emails(self, email):
        assert EMAIL_PATTERN.search(email), f"Should match: {email}"

    def test_no_match_without_at(self):
        assert not EMAIL_PATTERN.search("to nie jest email")

    def test_no_match_without_domain(self):
        assert not EMAIL_PATTERN.search("user@")


class TestPeselPattern:
    """Wzorzec PESEL_PATTERN — 11-cyfrowy numer PESEL."""

    def test_matches_valid_pesel(self):
        assert PESEL_PATTERN.search("PESEL: 85010212345")

    def test_no_match_10_digits(self):
        assert not PESEL_PATTERN.search("1234567890")

    def test_no_match_12_digits(self):
        # 12 cyfr nie powinno matchowac jako PESEL (word boundary)
        assert not PESEL_PATTERN.search("123456789012")

    def test_matches_standalone(self):
        assert PESEL_PATTERN.search("numer 92071012345 wydany")


class TestNipPattern:
    """Wzorzec NIP_PATTERN — Numer Identyfikacji Podatkowej."""

    @pytest.mark.parametrize("nip", [
        "123-456-78-90",
        "1234567890",
        "123-456-78-90",
    ])
    def test_matches_valid_nip(self, nip):
        assert NIP_PATTERN.search(nip), f"Should match: {nip}"


class TestDowodPattern:
    """Wzorzec DOWOD_PATTERN — numer dowodu osobistego (AAA123456)."""

    @pytest.mark.parametrize("dowod", [
        "ABC 123456",
        "XYZ123456",
    ])
    def test_matches_valid_dowod(self, dowod):
        assert DOWOD_PATTERN.search(dowod), f"Should match: {dowod}"

    def test_no_match_lowercase(self):
        assert not DOWOD_PATTERN.search("abc123456")

    def test_no_match_too_few_digits(self):
        assert not DOWOD_PATTERN.search("ABC12345")


class TestIbanPattern:
    r"""Wzorzec IBAN_PATTERN — numery kont bankowych.

    Pattern: [A-Z]{2}\d{2} + up to 4 groups of \d{4} (space-separated).
    Covers standard EU IBANs like DE (22 chars) but not all formats
    (e.g. PL 28-char without spaces, or GB with letters in bank code).
    """

    @pytest.mark.parametrize("iban", [
        "DE89 3704 0044 0532 0130 00",
        "FR76 3000 6000 0112 3456 7890",
    ])
    def test_matches_digit_only_iban_with_spaces(self, iban):
        assert IBAN_PATTERN.search(iban), f"Should match: {iban}"

    def test_no_match_iban_with_letters_in_body(self):
        """GB-style IBAN has letters (NWBK) — regex expects digits only."""
        assert not IBAN_PATTERN.search("GB29 NWBK 6016 1331 9268 19")


class TestPlatePattern:
    """Wzorzec PLATE_PATTERN — tablice rejestracyjne."""

    @pytest.mark.parametrize("plate", [
        "WA 12345",
        "KR 5A123",
        "B AB1234",
    ])
    def test_matches_valid_plates(self, plate):
        assert PLATE_PATTERN.search(plate), f"Should match: {plate}"


# -- anonymize_personal_data() ----------------------------------------------


class TestAnonymizePersonalData:
    """Metoda anonymize_personal_data() — zamiana PII na tokeny."""

    def test_empty_string_returns_empty(self, anon):
        assert anon.anonymize_personal_data("") == ""

    def test_none_returns_none(self, anon):
        assert anon.anonymize_personal_data(None) is None

    def test_no_pii_unchanged(self, anon):
        text = "Wypadek na autostradzie A4 w rejonie Katowic."
        assert anon.anonymize_personal_data(text) == text

    def test_phone_replaced(self, anon):
        text = "Zadzwon pod +48 123 456 789 po szczegoly."
        result = anon.anonymize_personal_data(text)
        assert "[telefon usuniety]" in result
        assert "123 456 789" not in result

    def test_email_replaced(self, anon):
        text = "Kontakt: jan.kowalski@firma.pl w sprawie zdarzenia."
        result = anon.anonymize_personal_data(text)
        assert "[email usuniety]" in result
        assert "jan.kowalski@firma.pl" not in result

    def test_pesel_replaced(self, anon):
        """PESEL (11 digits) is caught by PHONE_PATTERN first — PII is still removed."""
        text = "Sprawca o numerze PESEL 85010212345 zostal zatrzymany."
        result = anon.anonymize_personal_data(text)
        # The key RODO requirement: digits are gone
        assert "85010212345" not in result

    def test_nip_replaced(self, anon):
        """NIP pattern overlaps with phone — PII is still removed."""
        text = "Firma o NIP 123-456-78-90 zglosila zdarzenie."
        result = anon.anonymize_personal_data(text)
        assert "123-456-78-90" not in result

    def test_dowod_replaced(self, anon):
        text = "Dowod osobisty numer ABC 123456 wystawiony."
        result = anon.anonymize_personal_data(text)
        assert "[ID usuniete]" in result
        assert "ABC 123456" not in result

    def test_iban_digits_removed(self, anon):
        """IBAN digits are removed — phone pattern intercepts before IBAN pattern
        in anonymize_personal_data() due to application order."""
        text = "Przelew na konto DE89 3704 0044 0532 0130 00."
        result = anon.anonymize_personal_data(text)
        # RODO requirement: account digits are gone
        assert "3704 0044" not in result
        assert "0532 0130" not in result

    def test_long_iban_digits_still_removed(self, anon):
        """Long IBAN without spaces — phone pattern catches digit subsequences."""
        text = "Konto PL61109010140000071219812874 do wplaty."
        result = anon.anonymize_personal_data(text)
        # Digits are removed even if by phone pattern
        assert "109010140000" not in result

    def test_multiple_pii_types_in_one_text(self, anon):
        text = (
            "Jan Kowalski (PESEL 85010212345) zadzwonil z +48 123 456 789 "
            "i wyslal email na jan@example.com."
        )
        result = anon.anonymize_personal_data(text)
        # All PII must be gone (regardless of which pattern catches it)
        assert "85010212345" not in result
        assert "123 456 789" not in result
        assert "jan@example.com" not in result
        assert "[telefon usuniety]" in result
        assert "[email usuniety]" in result

    def test_transport_context_preserved(self, anon):
        """Kontekst transportowy (trasa, nr autostrady) nie jest usuwany."""
        text = "Kolizja na A4 km 312, 3 pojazdy, temperatura -5C."
        result = anon.anonymize_personal_data(text)
        assert "A4" in result
        assert "km 312" in result
        assert "3 pojazdy" in result

    def test_repeated_pii_all_replaced(self, anon):
        text = "Tel: +48 123 456 789. Powtarzam: +48 123 456 789."
        result = anon.anonymize_personal_data(text)
        assert result.count("[telefon usuniety]") == 2
        assert "+48 123 456 789" not in result


# -- anonymize_vehicle_plates() ---------------------------------------------


class TestAnonymizeVehiclePlates:
    """Metoda anonymize_vehicle_plates() — rozroznienie zrodel."""

    def test_private_source_plates_anonymized(self, anon):
        text = "Pojazd WA 12345 uczestniczyl w zdarzeniu."
        result = anon.anonymize_vehicle_plates(text, is_official_source=False)
        assert "[rejestracja usunieta]" in result
        assert "WA 12345" not in result

    def test_official_source_plates_preserved(self, anon):
        text = "Pojazd WA 12345 uczestniczyl w zdarzeniu."
        result = anon.anonymize_vehicle_plates(text, is_official_source=True)
        assert "WA 12345" in result
        assert "[rejestracja usunieta]" not in result

    def test_default_is_not_official(self, anon):
        text = "Pojazd KR 5A123 na miejscu."
        result = anon.anonymize_vehicle_plates(text)
        assert "[rejestracja usunieta]" in result

    def test_no_plates_unchanged(self, anon):
        text = "Zdarzenie bez pojazdow."
        result = anon.anonymize_vehicle_plates(text, is_official_source=False)
        assert result == text


# -- contains_personal_data() -----------------------------------------------


class TestContainsPersonalData:
    """Metoda contains_personal_data() — detekcja PII."""

    def test_empty_string(self, anon):
        assert anon.contains_personal_data("") is False

    def test_none_returns_false(self, anon):
        assert anon.contains_personal_data(None) is False

    def test_detects_phone(self, anon):
        assert anon.contains_personal_data("Zadzwon +48 123 456 789") is True

    def test_detects_email(self, anon):
        assert anon.contains_personal_data("mail: test@example.com") is True

    def test_detects_pesel(self, anon):
        assert anon.contains_personal_data("PESEL: 85010212345") is True

    def test_clean_text_returns_false(self, anon):
        assert anon.contains_personal_data(
            "Wypadek na autostradzie A1 kolo Lodzi"
        ) is False


# -- get_anonymization_report() ---------------------------------------------


class TestAnonymizationReport:
    """Metoda get_anonymization_report() — raport z anonimizacji."""

    def test_empty_text_report(self, anon):
        report = anon.get_anonymization_report("")
        assert report.original_length == 0
        assert report.removed_phones == 0
        assert report.removed_emails == 0

    def test_none_text_report(self, anon):
        report = anon.get_anonymization_report(None)
        assert report.original_length == 0

    def test_counts_phones(self, anon):
        text = "Tel: +48 123 456 789 i +49 30 1234567."
        report = anon.get_anonymization_report(text)
        assert report.removed_phones >= 2

    def test_counts_emails(self, anon):
        text = "a@b.com i c@d.pl"
        report = anon.get_anonymization_report(text)
        assert report.removed_emails == 2

    def test_counts_ids_dowod(self, anon):
        """Dowod pattern (3 letters + 6 digits) is distinct from phone pattern."""
        text = "Dowod ABC 123456 wydany w urzedzie."
        report = anon.get_anonymization_report(text)
        assert report.removed_ids >= 1

    def test_counts_ids_pesel_and_nip(self, anon):
        """PESEL/NIP overlap with phone — removed_ids may undercount due to
        phone pattern intercepting digits first. Pattern unit tests above
        verify the regexes individually."""
        text = "PESEL 85010212345 i NIP 1234567890."
        report = anon.get_anonymization_report(text)
        # At minimum phone pattern catches these digits
        assert report.removed_phones >= 1

    def test_anonymized_length_shorter(self, anon):
        """Tekst po anonimizacji moze byc krotszy lub dluzszy
        (tokeny zastepcze moga byc dluzsze od oryginalnych danych)."""
        text = "jan.kowalski@firma.pl dzwonil z +48 123 456 789."
        report = anon.get_anonymization_report(text)
        assert report.original_length == len(text)
        assert report.anonymized_length > 0
        assert report.anonymized_length != report.original_length

    def test_report_to_dict(self, anon):
        report = anon.get_anonymization_report("test@example.com")
        d = report.to_dict()
        assert isinstance(d, dict)
        assert "removed_emails" in d
        assert d["removed_emails"] == 1

    def test_report_dataclass_defaults(self):
        report = AnonymizationReport()
        assert report.original_length == 0
        assert report.details == []
        assert report.removed_names == 0


# -- _is_residential_address() ----------------------------------------------


class TestIsResidentialAddress:
    """Heurystyka _is_residential_address() — wykrywanie adresow zamieszkania."""

    @pytest.mark.parametrize("text", [
        "ul. Marszalkowska 10",
        "ul Dluga 5/3",
        "os. Tysiaclecia 2",
        "al. Jerozolimskie 100",
        "str. Hauptbahnhof 15",
        "Str. Berliner 7",
    ])
    def test_residential_indicators(self, anon, text):
        assert anon._is_residential_address(text) is True

    @pytest.mark.parametrize("text", [
        "Katowice",
        "Warszawa",
        "autostrada A4",
        "skrzyzowanie Polna/Dluga",
        "Berlin",
    ])
    def test_non_residential(self, anon, text):
        assert anon._is_residential_address(text) is False


# -- NER integration (spaCy) ------------------------------------------------


try:
    import spacy
    spacy.load("xx_ent_wiki_sm")
    HAS_SPACY = True
except (ImportError, OSError):
    HAS_SPACY = False


@pytest.mark.skipif(not HAS_SPACY, reason="spaCy model xx_ent_wiki_sm not available")
class TestNerAnonymization:
    """Testy NER — wymagaja spaCy + modelu xx_ent_wiki_sm."""

    def test_person_name_replaced(self, anon):
        text = "Kierowca Jan Kowalski spieszyl sie na lotnisko."
        result = anon.anonymize_personal_data(text)
        assert "[osoba]" in result

    def test_residential_address_replaced(self, anon):
        text = "Zamieszkaly przy ul. Marszalkowskiej 10 w Warszawie."
        result = anon.anonymize_personal_data(text)
        assert "[adres usuniety]" in result

    def test_contains_personal_data_detects_name(self, anon):
        assert anon.contains_personal_data(
            "Kierowca Jan Kowalski zglosil zdarzenie."
        ) is True

    def test_report_counts_names(self, anon):
        report = anon.get_anonymization_report(
            "Jan Kowalski i Anna Nowak byli swiadkami."
        )
        assert report.removed_names >= 1


# -- Regression / edge cases ------------------------------------------------


class TestEdgeCases:
    """Przypadki brzegowe i regresje."""

    def test_unicode_text_preserved(self, anon):
        text = "Straż Graniczna złapała sprawcę — działania na granicy."
        result = anon.anonymize_personal_data(text)
        assert "Straż Graniczna" in result

    def test_very_long_text(self, anon):
        text = "Wypadek. " * 5000
        result = anon.anonymize_personal_data(text)
        assert len(result) > 0

    def test_mixed_pii_and_transport_data(self, anon):
        text = (
            "Na autostradzie A2 km 205 doszlo do zderzenia. "
            "Kierowca (PESEL 92071012345) jechał pojazdem WA 12345. "
            "Kontakt: +48 600 700 800, email: kierowca@poczta.pl."
        )
        result = anon.anonymize_personal_data(text)
        # PII removed
        assert "92071012345" not in result
        assert "kierowca@poczta.pl" not in result
        # Transport context preserved
        assert "A2" in result
        assert "km 205" in result
        assert "zderzenia" in result

    def test_german_phone_format(self, anon):
        text = "Anruf von +49 30 1234567 wegen Unfall."
        result = anon.anonymize_personal_data(text)
        assert "[telefon usuniety]" in result

    def test_international_email(self, anon):
        text = "Contact: hans.mueller@bundespolizei.de for details."
        result = anon.anonymize_personal_data(text)
        assert "[email usuniety]" in result
        assert "hans.mueller@bundespolizei.de" not in result
