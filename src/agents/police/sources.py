"""Police source configs — one PoliceSourceConfig per country.

Each config captures the country-specific parameters needed by BasePoliceAgent:
selectors, date formats, URL patterns, etc.

Countries requiring custom subclasses (DE, AT, TR, CH) are NOT listed here —
they live in src/agents/police/custom/.
"""

from src.agents.police.base import PoliceSourceConfig

# ── Standard date pattern tuples (reused across countries) ─────────────

_DATES_DOT_ISO = (r"(\d{1,2}\.\d{1,2}\.\d{4})", r"(\d{4}-\d{2}-\d{2})")
_DATES_ISO_DOT = (r"(\d{4}-\d{2}-\d{2})", r"(\d{1,2}\.\d{1,2}\.\d{4})")
_DATES_SLASH_DOT_ISO = (
    r"(\d{1,2}/\d{1,2}/\d{4})",
    r"(\d{1,2}\.\d{1,2}\.\d{4})",
    r"(\d{4}-\d{2}-\d{2})",
)

# ── Configs (alphabetical by country code) ─────────────────────────────

BELGIUM = PoliceSourceConfig(
    country_code="BE",
    language="fr",
    source_name="Police Belge",
    source_url="https://www.police.be/5998/fr/actualites",
    url_domain="https://www.police.be",
    selectors=(
        "article", "div.view-content div.views-row",
        "div.news-item", "li.list-item",
    ),
    fallback_href_markers=("/actualites/", "/nieuws/"),
    date_class_names=("date", "datum", "news-date"),
    date_patterns=_DATES_SLASH_DOT_ISO,
)

BULGARIA = PoliceSourceConfig(
    country_code="BG",
    language="bg",
    source_name="MVR Bulgarija",
    source_url="https://www.mvr.bg/press",
    url_domain="https://www.mvr.bg",
    selectors=("article", "div.news-item", "div.list-item", "li.list-item"),
    fallback_href_markers=("/press/",),
    date_class_names=(),
    date_patterns=_DATES_DOT_ISO,
)

CROATIA = PoliceSourceConfig(
    country_code="HR",
    language="hr",
    source_name="MUP Hrvatska",
    source_url="https://mup.gov.hr/vijesti-8/8",
    url_domain="https://mup.gov.hr",
    selectors=("article", "div.news-item", "div.list-item", "li.list-item"),
    fallback_href_markers=("/vijesti",),
    date_class_names=("date", "datum"),
    date_patterns=_DATES_DOT_ISO,
)

CZECH_REPUBLIC = PoliceSourceConfig(
    country_code="CZ",
    language="cs",
    source_name="Policie \u010cR",
    source_url="https://www.policie.cz/zpravy.aspx",
    url_domain="https://www.policie.cz",
    selectors=(
        "article", "div.news-item", "div.list-item",
        "li.list-item", "div.zprava",
    ),
    fallback_href_markers=("/zprav", "/clanek"),
    date_class_names=("date", "datum", "news-date"),
    date_patterns=_DATES_DOT_ISO,
)

DENMARK = PoliceSourceConfig(
    country_code="DK",
    language="da",
    source_name="Politi Danmark",
    source_url="https://politi.dk/nyheder",
    url_domain="https://politi.dk",
    selectors=(
        "article", "div.news-item", "div.views-row", "li.list-item",
    ),
    fallback_href_markers=("/nyheder/",),
    date_class_names=("date", "dato", "news-date"),
    date_patterns=_DATES_DOT_ISO,
)

ESTONIA = PoliceSourceConfig(
    country_code="EE",
    language="et",
    source_name="Politsei Eesti",
    source_url="https://www.politsei.ee/et/uudised",
    url_domain="https://www.politsei.ee",
    selectors=("article", "div.news-item", "div.list-item", "li.list-item"),
    fallback_href_markers=("/uudised/",),
    date_class_names=(),
    date_patterns=_DATES_ISO_DOT,
)

FINLAND = PoliceSourceConfig(
    country_code="FI",
    language="fi",
    source_name="Poliisi Suomi",
    source_url="https://poliisi.fi/uutiset",
    url_domain="https://poliisi.fi",
    selectors=("article", "div.news-item", "div.list-item", "li.list-item"),
    fallback_href_markers=("/uutiset/", "/tiedotteet/"),
    date_class_names=("date", "pvm", "news-date"),
    date_patterns=_DATES_DOT_ISO,
)

FRANCE = PoliceSourceConfig(
    country_code="FR",
    language="fr",
    source_name="Gendarmerie Nationale",
    source_url="https://www.gendarmerie.interieur.gouv.fr/gendinfo/actualites",
    url_domain="https://www.gendarmerie.interieur.gouv.fr",
    selectors=(
        "article", "div.news-item", "div.views-row", "li.list-item",
    ),
    fallback_href_markers=("/nos-articles/", "/actualites/"),
    date_class_names=("date", "datum", "news-date"),
    date_patterns=_DATES_SLASH_DOT_ISO,
)

GREECE = PoliceSourceConfig(
    country_code="GR",
    language="el",
    source_name="\u0395\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ae \u0391\u03c3\u03c4\u03c5\u03bd\u03bf\u03bc\u03af\u03b1",
    source_url="https://www.astynomia.gr/deltia-typou/",
    url_domain="https://www.astynomia.gr",
    selectors=("article", "div.news-item", "div.list-item", "li.list-item"),
    fallback_href_markers=("/deltia-typou/",),
    date_class_names=(),
    date_patterns=_DATES_SLASH_DOT_ISO,
)

HUNGARY = PoliceSourceConfig(
    country_code="HU",
    language="hu",
    source_name="Rend\u0151rs\u00e9g Magyarorsz\u00e1g",
    source_url="https://www.police.hu/hu/hirek-es-informaciok/legfrissebb-hireink",
    url_domain="https://www.police.hu",
    selectors=(
        "article", "div.news-item",
        "div.view-content div.views-row", "li.list-item",
    ),
    fallback_href_markers=("/hirek/",),
    date_class_names=("date", "datum", "news-date"),
    date_patterns=(r"(\d{4}\.\d{2}\.\d{2})", r"(\d{4}-\d{2}-\d{2})"),
)

ITALY = PoliceSourceConfig(
    country_code="IT",
    language="it",
    source_name="Polizia di Stato",
    source_url="https://www.poliziadistato.it/articolo/welcome",
    url_domain="https://www.poliziadistato.it",
    selectors=(
        "article", "div.news-item", "div.comunicato", "li.list-item",
    ),
    fallback_href_markers=("/comunicat", "/press"),
    date_class_names=("date", "data", "news-date"),
    date_patterns=_DATES_SLASH_DOT_ISO,
)

LATVIA = PoliceSourceConfig(
    country_code="LV",
    language="lv",
    source_name="Valsts Policija Latvija",
    source_url="https://www.vp.gov.lv/lv/jaunumi",
    url_domain="https://www.vp.gov.lv",
    selectors=("article", "div.news-item", "div.list-item", "li.list-item"),
    fallback_href_markers=("/jaunumi/",),
    date_class_names=(),
    date_patterns=_DATES_ISO_DOT,
)

LITHUANIA = PoliceSourceConfig(
    country_code="LT",
    language="lt",
    source_name="Policija Lietuva",
    source_url="https://policija.lrv.lt/lt/naujienos",
    url_domain="https://policija.lrv.lt",
    selectors=("article", "div.news-item", "div.list-item", "li.list-item"),
    fallback_href_markers=("/naujienos/",),
    date_class_names=(),
    date_patterns=_DATES_ISO_DOT,
)

MOLDOVA = PoliceSourceConfig(
    country_code="MD",
    language="ro",
    source_name="Poli\u021bia Moldova",
    source_url="https://www.politia.md/ro/noutati",
    url_domain="https://www.politia.md",
    selectors=(
        "article", "div.news-item", "div.views-row", "div.list-item",
    ),
    fallback_href_markers=("/noutati/", "/noutate/"),
    date_class_names=(),
    date_patterns=_DATES_DOT_ISO,
)

NETHERLANDS = PoliceSourceConfig(
    country_code="NL",
    language="nl",
    source_name="Politie Nederland",
    source_url="https://www.politie.nl/nieuws",
    url_domain="https://www.politie.nl",
    selectors=("article", "div.news-item", "div.search-result", "li.list-item"),
    fallback_href_markers=("/nieuws/", "/berichten/"),
    date_class_names=("date", "datum", "news-date"),
    date_patterns=(r"(\d{1,2}-\d{1,2}-\d{4})", r"(\d{4}-\d{2}-\d{2})"),
)

NORWAY = PoliceSourceConfig(
    country_code="NO",
    language="no",
    source_name="Politiet Norge",
    source_url="https://www.politiet.no/nyheter-og-presse",
    url_domain="https://www.politiet.no",
    selectors=("article", "div.news-item", "div.list-item", "li.list-item"),
    fallback_href_markers=("/nyheter-og-presse/", "/nyhet/"),
    date_class_names=("date", "dato", "news-date"),
    date_patterns=_DATES_DOT_ISO,
)

POLAND = PoliceSourceConfig(
    country_code="PL",
    language="pl",
    source_name="Policja Polska",
    source_url="https://policja.pl/pol/aktualnosci",
    url_domain="https://policja.pl",
    selectors=("article", "div.news-item", "div.list-item", "li.news-item"),
    fallback_href_markers=("/pol/aktualnosci/", "/aktualnosci/"),
    date_class_names=("date", "data", "news-date", "item-date"),
    date_patterns=_DATES_DOT_ISO,
)

ROMANIA = PoliceSourceConfig(
    country_code="RO",
    language="ro",
    source_name="Poli\u021bia Rom\u00e2n\u0103",
    source_url="https://www.politiaromana.ro/ro/stiri",
    url_domain="https://www.politiaromana.ro",
    selectors=(
        "article", "div.news-item", "div.stire", "li.list-item",
    ),
    fallback_href_markers=("/stiri/", "/stire/"),
    date_class_names=("date", "data", "news-date"),
    date_patterns=_DATES_DOT_ISO,
)

SERBIA = PoliceSourceConfig(
    country_code="RS",
    language="sr",
    source_name="MUP Srbije",
    source_url="https://www.mup.gov.rs/wps/portal/sr/vesti",
    url_domain="https://www.mup.gov.rs",
    selectors=("article", "div.news-item", "div.list-item", "li.list-item"),
    fallback_href_markers=("/vesti/",),
    date_class_names=(),
    date_patterns=_DATES_DOT_ISO,
)

SLOVAKIA = PoliceSourceConfig(
    country_code="SK",
    language="sk",
    source_name="MV SR",
    source_url="https://www.minv.sk/?tlacove-spravy",
    url_domain="https://www.minv.sk",
    selectors=("article", "div.news-item", "div.list-item", "li.list-item"),
    fallback_href_markers=("tlacove-spravy", "/sprava/"),
    date_class_names=(),
    date_patterns=_DATES_DOT_ISO,
)

SLOVENIA = PoliceSourceConfig(
    country_code="SI",
    language="sl",
    source_name="Policija Slovenije",
    source_url="https://www.policija.si/medijsko-sredisce/sporocila-za-javnost",
    url_domain="https://www.policija.si",
    selectors=("article", "div.news-item", "div.list-item", "li.list-item"),
    fallback_href_markers=("/sporocila",),
    date_class_names=(),
    date_patterns=_DATES_DOT_ISO,
)

SPAIN = PoliceSourceConfig(
    country_code="ES",
    language="es",
    source_name="Polic\u00eda Nacional",
    source_url="https://www.policia.es/_es/comunicacion_salaprensa.php",
    url_domain="https://www.policia.es",
    selectors=(
        "article", "div.news-item", "div.noticia",
        "li.list-item", "tr",
    ),
    fallback_href_markers=("/prensa/", "/noticia"),
    date_class_names=("date", "fecha", "news-date"),
    date_patterns=_DATES_SLASH_DOT_ISO,
)

SWEDEN = PoliceSourceConfig(
    country_code="SE",
    language="sv",
    source_name="Polisen Sverige",
    source_url="https://polisen.se/aktuellt/polisens-nyheter/",
    url_domain="https://polisen.se",
    selectors=("article", "div.news-item", "div.list-item", "li.list-item"),
    fallback_href_markers=("/nyheter/", "/polisens-nyheter/"),
    date_class_names=("date", "datum", "news-date"),
    date_patterns=_DATES_DOT_ISO,
)

UKRAINE = PoliceSourceConfig(
    country_code="UA",
    language="uk",
    source_name="MVS Ukrajiny",
    source_url="https://mvs.gov.ua/uk/press-center/news",
    url_domain="https://mvs.gov.ua",
    selectors=(
        "article", "div.news-item", "div.card",
        "div.item", "div.list-item", "li.list-item",
    ),
    fallback_href_markers=("/news/", "/press-center/"),
    date_class_names=(),
    date_patterns=_DATES_DOT_ISO,
)

UNITED_KINGDOM = PoliceSourceConfig(
    country_code="GB",
    language="en",
    source_name="Metropolitan Police",
    source_url="https://news.met.police.uk/latest_news",
    url_domain="https://news.met.police.uk",
    selectors=("article", "div.news-item", "div.search-result", "li.list-item"),
    fallback_href_markers=("/news/",),
    date_class_names=("date", "news-date", "published"),
    date_patterns=(r"(\d{1,2}/\d{1,2}/\d{4})", r"(\d{4}-\d{2}-\d{2})"),
)

# ── Registry: country_code -> config (25 standard countries) ───────────

SOURCES: dict[str, PoliceSourceConfig] = {
    cfg.country_code: cfg
    for cfg in [
        BELGIUM, BULGARIA, CROATIA, CZECH_REPUBLIC, DENMARK, ESTONIA,
        FINLAND, FRANCE, GREECE, HUNGARY, ITALY, LATVIA, LITHUANIA,
        MOLDOVA, NETHERLANDS, NORWAY, POLAND, ROMANIA, SERBIA,
        SLOVAKIA, SLOVENIA, SPAIN, SWEDEN, UKRAINE, UNITED_KINGDOM,
    ]
}
