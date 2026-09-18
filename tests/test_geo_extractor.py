"""Testy dla analysis/geo_extractor.py — regresja po naprawie duplikatow kluczy autostrad.

Pokrywa:
- _HIGHWAYS dict — brak duplikatow kluczy, wszystkie kraje obecne
- find_highway() — lookup zwraca dane dla wszystkich krajow
- extract_location() — country_code rozroznia A2 DE vs A2 CH
"""

from src.analysis.geo_extractor import GeoExtractor, _HIGHWAYS


# -- _HIGHWAYS dict integrity --------------------------------------------------


class TestHighwayDictIntegrity:
    """Slownik _HIGHWAYS nie ma duplikatow i zawiera wszystkie kraje."""

    def test_a1_includes_pl(self):
        assert "PL" in _HIGHWAYS["A1"]["countries"]

    def test_a1_includes_fr(self):
        assert "FR" in _HIGHWAYS["A1"]["countries"]

    def test_a1_includes_at(self):
        assert "AT" in _HIGHWAYS["A1"]["countries"]

    def test_a1_includes_ro(self):
        assert "RO" in _HIGHWAYS["A1"]["countries"]

    def test_a1_includes_it(self):
        assert "IT" in _HIGHWAYS["A1"]["countries"]

    def test_a2_includes_pl(self):
        assert "PL" in _HIGHWAYS["A2"]["countries"]

    def test_a2_includes_de(self):
        assert "DE" in _HIGHWAYS["A2"]["countries"]

    def test_a2_includes_ch(self):
        assert "CH" in _HIGHWAYS["A2"]["countries"]

    def test_a2_includes_at(self):
        assert "AT" in _HIGHWAYS["A2"]["countries"]

    def test_a2_includes_es(self):
        assert "ES" in _HIGHWAYS["A2"]["countries"]

    def test_a3_includes_de(self):
        assert "DE" in _HIGHWAYS["A3"]["countries"]

    def test_a3_includes_ro(self):
        assert "RO" in _HIGHWAYS["A3"]["countries"]

    def test_a4_includes_pl(self):
        assert "PL" in _HIGHWAYS["A4"]["countries"]

    def test_a4_includes_it(self):
        assert "IT" in _HIGHWAYS["A4"]["countries"]

    def test_a7_includes_de(self):
        assert "DE" in _HIGHWAYS["A7"]["countries"]

    def test_a7_includes_fr(self):
        assert "FR" in _HIGHWAYS["A7"]["countries"]

    def test_a9_includes_de(self):
        assert "DE" in _HIGHWAYS["A9"]["countries"]

    def test_a9_includes_fr(self):
        assert "FR" in _HIGHWAYS["A9"]["countries"]

    def test_a10_includes_de(self):
        assert "DE" in _HIGHWAYS["A10"]["countries"]

    def test_a10_includes_fr(self):
        assert "FR" in _HIGHWAYS["A10"]["countries"]

    def test_m1_includes_hu(self):
        assert "HU" in _HIGHWAYS["M1"]["countries"]

    def test_m1_includes_gb(self):
        assert "GB" in _HIGHWAYS["M1"]["countries"]

    def test_all_entries_have_countries(self):
        for code, hw in _HIGHWAYS.items():
            assert "countries" in hw, f"{code} missing 'countries'"
            assert len(hw["countries"]) > 0, f"{code} has empty countries list"

    def test_all_entries_have_desc(self):
        for code, hw in _HIGHWAYS.items():
            assert "desc" in hw, f"{code} missing 'desc'"
            assert len(hw["desc"]) > 0, f"{code} has empty desc"


# -- find_highway() -----------------------------------------------------------


class TestFindHighway:
    """find_highway() — regex + lookup w highways_db."""

    def setup_method(self):
        self.geo = GeoExtractor()

    def test_a2_returns_all_countries(self):
        """A2 exists in PL, DE, NL, AT, ES, CH — all must be present."""
        results = self.geo.find_highway("Accident on A2")
        assert len(results) == 1
        hw = results[0]
        assert hw["code"] == "A2"
        assert "DE" in hw["countries"]
        assert "CH" in hw["countries"]
        assert "PL" in hw["countries"]

    def test_a1_returns_all_countries(self):
        results = self.geo.find_highway("Traffic jam on A1 near Gdansk")
        assert len(results) == 1
        assert "PL" in results[0]["countries"]
        assert "FR" in results[0]["countries"]
        assert "AT" in results[0]["countries"]

    def test_m1_returns_hu_and_gb(self):
        results = self.geo.find_highway("M1 motorway closure")
        assert len(results) == 1
        assert "HU" in results[0]["countries"]
        assert "GB" in results[0]["countries"]

    def test_unknown_highway_returns_empty_countries(self):
        results = self.geo.find_highway("A99 does not exist in DB")
        assert len(results) == 1
        assert results[0]["countries"] == []

    def test_no_match(self):
        results = self.geo.find_highway("no highway here")
        assert results == []


# -- extract_location() — country_code disambiguates --------------------------


class TestExtractLocationHighway:
    """extract_location() z country_code rozroznia autostrady miedzy krajami."""

    def setup_method(self):
        self.geo = GeoExtractor()

    def test_a2_with_country_de(self):
        result = self.geo.extract_location("Stau auf A2 bei Hannover", country_code="DE")
        assert result.highway == "A2"
        assert result.country == "DE"

    def test_a2_with_country_ch(self):
        result = self.geo.extract_location("Unfall auf A2 bei Basel", country_code="CH")
        assert result.highway == "A2"
        assert result.country == "CH"

    def test_a2_with_country_pl(self):
        result = self.geo.extract_location("Wypadek na A2 kolo Poznania", country_code="PL")
        assert result.highway == "A2"
        assert result.country == "PL"

    def test_a1_with_country_fr(self):
        result = self.geo.extract_location("Accident sur A1 pres de Lille", country_code="FR")
        assert result.highway == "A1"
        assert result.country == "FR"

    def test_a1_with_country_at(self):
        result = self.geo.extract_location("Stau auf A1 bei Salzburg", country_code="AT")
        assert result.highway == "A1"
        assert result.country == "AT"

    def test_m1_with_country_hu(self):
        result = self.geo.extract_location("Baleset az M1 autopalyan", country_code="HU")
        assert result.highway == "M1"
        assert result.country == "HU"

    def test_m1_with_country_gb(self):
        result = self.geo.extract_location("Crash on M1 near Leeds", country_code="GB")
        assert result.highway == "M1"
        assert result.country == "GB"
