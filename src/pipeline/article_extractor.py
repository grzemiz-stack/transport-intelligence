"""Article text extraction and structured detail extraction from news articles.

Fetches full article text from source URLs and extracts structured intelligence:
- Cargo type (electronics, fuel, textiles, etc.)
- Modus operandi (curtain slashed, cab break-in, etc.)
- Location detail (highway + km marker + city/parking)
- Vehicle country (from plate pattern or text mentions)
- Financial value (delegated to EventParser)
"""

import base64
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# --- SSRF protection & fetch limits -----------------------------------------
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB
_MAX_REDIRECTS = 3
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
]

_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(15.0, connect=10.0),
    follow_redirects=False,
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)


def _validate_url(url: str) -> None:
    """Block non-HTTP schemes and private/reserved IPs (SSRF protection).

    Resolves DNS to check actual IP addresses, not just hostname strings.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Blocked URL scheme: {parsed.scheme!r}")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("No hostname in URL")
    addrinfos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    for _family, _type, _proto, _canonname, sockaddr in addrinfos:
        ip = ipaddress.ip_address(sockaddr[0])
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                raise ValueError(f"Blocked private/reserved IP {ip} for host {hostname}")


async def _safe_get(url: str, headers: dict[str, str] | None = None) -> httpx.Response:
    """HTTP GET with SSRF validation on every redirect hop and 2 MB body limit."""
    _headers = dict(headers) if headers else {}
    for _ in range(_MAX_REDIRECTS + 1):
        _validate_url(url)
        req = _http_client.build_request("GET", url, headers=_headers)
        resp = await _http_client.send(req, stream=True)
        if resp.is_redirect:
            await resp.aclose()
            location = resp.headers.get("location")
            if not location:
                raise ValueError("Redirect without Location header")
            url = str(resp.url.join(location))
            continue
        # Stream body with size limit
        chunks: list[bytes] = []
        size = 0
        async for chunk in resp.aiter_bytes():
            size += len(chunk)
            if size > _MAX_RESPONSE_BYTES:
                await resp.aclose()
                raise ValueError(f"Response exceeds {_MAX_RESPONSE_BYTES} byte limit")
            chunks.append(chunk)
        await resp.aclose()
        resp._content = b"".join(chunks)  # noqa: SLF001
        return resp
    raise httpx.TooManyRedirects(
        f"Exceeded {_MAX_REDIRECTS} redirects",
        request=httpx.Request("GET", url),
    )


# Noise element selectors to remove before extracting text
_NOISE_TAGS = {"nav", "footer", "aside", "header", "script", "style", "noscript", "iframe"}
_NOISE_CLASS_RE = re.compile(
    r"nav|footer|sidebar|cookie|ad-|social|comment|share|menu|newsletter|popup|banner|promo",
    re.IGNORECASE,
)

# --- Cargo type keywords per language ---

CARGO_KEYWORDS: dict[str, list[tuple[str, str]]] = {
    "electronics": [
        "elektronika", "elektronik", "electronics", "laptopy", "tvs", "telefony",
        "computers", "smartphones", "tablets", "monitory", "komputery", "phones",
        "elettronica", "electrónica", "elektronica", "electronice",
    ],
    "fuel": [
        "paliwo", "diesel", "kraftstoff", "fuel", "benzyna", "olej napędowy",
        "carburant", "combustible", "brandstof", "carburante", "combustibil",
    ],
    "textiles": [
        "tekstylia", "textilien", "textiles", "odzież", "clothing", "ubrania",
        "tessuti", "textiel", "vêtements", "ropa", "textile",
    ],
    "food": [
        "żywność", "lebensmittel", "food", "mięso", "nabiał", "nourriture",
        "alimentos", "voedsel", "cibo", "alimente", "meat", "dairy",
    ],
    "alcohol": [
        "alkohol", "spirituosen", "spirits", "wódka", "wino", "piwo",
        "vodka", "wine", "beer", "alcool", "alcohol", "alcolici",
    ],
    "tobacco": [
        "tytoń", "tabak", "tobacco", "papierosy", "cigarettes", "zigaretten",
        "tabac", "tabaco", "sigarette", "tutun",
    ],
    "pharmaceuticals": [
        "farmaceutyki", "medikamente", "pharmaceuticals", "leki", "medicines",
        "médicaments", "medicamentos", "farmaci", "medicamente",
    ],
    "metals": [
        "metale", "metalle", "metals", "miedź", "copper", "aluminium",
        "aluminum", "stal", "steel", "stahl", "métaux", "metales", "metalli",
    ],
    "cosmetics": [
        "kosmetyki", "kosmetik", "cosmetics", "perfumy", "perfume",
        "cosmétiques", "cosméticos", "cosmetici",
    ],
    "automotive_parts": [
        "części samochodowe", "autoteile", "auto parts", "car parts",
        "opony", "tires", "reifen", "pièces auto", "recambios",
    ],
}

# --- Modus operandi patterns per language ---

MO_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "curtain_slashed": [
        (r"rozcięci[ea]\s+plandek", "pl"),
        (r"przecięci[ea]\s+plandek", "pl"),
        (r"rozci[eę]t[aey]\s+plandek", "pl"),
        (r"plane\s+aufgeschlitzt", "de"),
        (r"plane\s+aufgeschnitten", "de"),
        (r"curtain\s+(?:slashed|cut|slit)", "en"),
        (r"tarpaulin\s+(?:slashed|cut|slit)", "en"),
        (r"bâche\s+(?:découpée|lacérée)", "fr"),
        (r"telone\s+(?:tagliato|squarciato)", "it"),
        (r"zeil\s+(?:opengesneden|doorgesneden)", "nl"),
        (r"prelată\s+(?:tăiată|spartă)", "ro"),
        (r"lona\s+(?:cortada|rajada)", "es"),
    ],
    "cab_break_in": [
        (r"włamani[ea]\s+do\s+kabiny", "pl"),
        (r"einbruch.*kabine", "de"),
        (r"cab\s+break[\s-]?in", "en"),
        (r"break[\s-]?in.*cab", "en"),
        (r"effraction.*cabine", "fr"),
        (r"intrusione.*cabina", "it"),
        (r"inbraak.*cabine", "nl"),
    ],
    "fuel_theft": [
        (r"kradzież\s+paliwa", "pl"),
        (r"spuszcz\w+\s+paliw", "pl"),
        (r"diesel.*abgezapft", "de"),
        (r"tank.*angebohrt", "de"),
        (r"kraftstoff.*gestohlen", "de"),
        (r"fuel\s+(?:siphon|theft|stolen)", "en"),
        (r"siphon\w*\s+(?:fuel|diesel)", "en"),
        (r"vol\s+de\s+(?:carburant|diesel)", "fr"),
        (r"furto\s+di\s+(?:carburante|diesel|gasolio)", "it"),
    ],
    "driver_attack": [
        (r"napad\s+na\s+kierowc", "pl"),
        (r"zaatakow\w+\s+kierowc", "pl"),
        (r"fahrer.*angegriffen", "de"),
        (r"überfall.*fahrer", "de"),
        (r"driver\s+(?:attack|assault|robbed)", "en"),
        (r"attack\w*\s+(?:on\s+)?(?:the\s+)?driver", "en"),
        (r"agression.*chauffeur", "fr"),
        (r"aggressione.*autista", "it"),
    ],
    "trailer_stolen": [
        (r"skradzion\w*\s+naczep", "pl"),
        (r"kradzież\s+naczep", "pl"),
        (r"auflieger.*gestohlen", "de"),
        (r"trailer\s+(?:stolen|theft|detached)", "en"),
        (r"stole\w*\s+(?:the\s+)?trailer", "en"),
        (r"vol\s+de\s+remorque", "fr"),
        (r"furto\s+(?:del\s+)?rimorchio", "it"),
    ],
    "vehicle_stolen": [
        (r"skradzion\w*\s+(?:ciężarówk|samochód|pojazd|tir)", "pl"),
        (r"lkw.*gestohlen", "de"),
        (r"(?:truck|lorry|vehicle)\s+stolen", "en"),
        (r"stole\w*\s+(?:the\s+)?(?:truck|lorry|vehicle)", "en"),
    ],
    "hijacking": [
        (r"porwani[ea]\s+(?:pojazdu|ciężarówk|tir)", "pl"),
        (r"(?:truck|lorry|vehicle)\s+hijack", "en"),
        (r"hijack\w*\s+(?:the\s+)?(?:truck|lorry)", "en"),
        (r"carjack", "en"),
        (r"détournement", "fr"),
    ],
    "parking_theft": [
        (r"kradzież\s+(?:na|z)\s+parking", "pl"),
        (r"diebstahl.*parkplatz", "de"),
        (r"(?:theft|stolen)\s+(?:at|from)\s+(?:the\s+)?(?:parking|rest\s+area|truck\s+stop)", "en"),
    ],
}

# --- Vehicle country text patterns ---

_VEHICLE_COUNTRY_TEXT: list[tuple[str, str]] = [
    (r"polsk\w+\s+tablic", "PL"),
    (r"na\s+polskich\s+rejestracj", "PL"),
    (r"polsk\w+\s+rejestracj", "PL"),
    (r"deutsch\w+\s+kennzeichen", "DE"),
    (r"mit\s+deutschen\s+kennzeichen", "DE"),
    (r"german[\s-]registered", "DE"),
    (r"uk[\s-]registered", "GB"),
    (r"british\s+(?:registered|plates?)", "GB"),
    (r"french[\s-]registered", "FR"),
    (r"immatricul\w+\s+(?:en\s+)?fran[cç]", "FR"),
    (r"plaques?\s+fran[cç]aises?", "FR"),
    (r"dutch[\s-]registered", "NL"),
    (r"romanian[\s-]registered", "RO"),
    (r"czech[\s-]registered", "CZ"),
    (r"italian[\s-]registered", "IT"),
    (r"spanish[\s-]registered", "ES"),
    (r"targa\s+italian", "IT"),
    (r"targhe\s+italian", "IT"),
    (r"numer\w+\s+di\s+targa\s+italian", "IT"),
    (r"lithu?anian[\s-]registered", "LT"),
    (r"bulgarian[\s-]registered", "BG"),
    (r"hungarian[\s-]registered", "HU"),
    (r"ukrain\w+\s+(?:registered|plates?|rejestracj)", "UA"),
    (r"turk\w+\s+(?:registered|plates?)", "TR"),
    (r"belarusian[\s-]registered", "BY"),
]

# Plate prefix -> ISO code mapping (first 1-3 uppercase letter groups)
_PLATE_PREFIX_MAP = {
    "PL": "PL", "D": "DE", "DE": "DE", "F": "FR", "FR": "FR",
    "NL": "NL", "B": "BE", "BE": "BE", "I": "IT", "IT": "IT",
    "E": "ES", "ES": "ES", "A": "AT", "AT": "AT", "CZ": "CZ",
    "SK": "SK", "H": "HU", "HU": "HU", "RO": "RO", "BG": "BG",
    "HR": "HR", "SLO": "SI", "SI": "SI", "GB": "GB", "UK": "GB",
    "S": "SE", "SE": "SE", "N": "NO", "NO": "NO", "DK": "DK",
    "FIN": "FI", "FI": "FI", "CH": "CH", "GR": "GR", "TR": "TR",
    "UA": "UA", "LT": "LT", "LV": "LV", "EST": "EE", "EE": "EE",
    "SRB": "RS", "RS": "RS", "P": "PT", "PT": "PT", "IRL": "IE",
    "IE": "IE", "L": "LU", "LU": "LU", "MD": "MD", "BY": "BY",
    "RUS": "RU", "RU": "RU",
}

# KM marker regex
_KM_MARKER_RE = re.compile(
    r"(?:km|kilometer|kilometre|kilometr)\s*(\d+[\.,]?\d*)",
    re.IGNORECASE,
)
_MILE_MARKER_RE = re.compile(r"mile\s*(\d+[\.,]?\d*)", re.IGNORECASE)


async def resolve_google_news_url(google_url: str) -> str | None:
    """Resolve Google News redirect URL to actual article URL.

    Google News RSS entries use encoded redirect URLs like:
    https://news.google.com/rss/articles/CBMi...

    The base64-encoded part after 'CBMi' contains the real URL.
    Falls back to following redirects with a browser UA.
    """
    # Method 1: Decode from the base64 payload in the URL path
    try:
        if "/rss/articles/" in google_url:
            encoded_part = google_url.split("/rss/articles/")[1].split("?")[0]
            padded = encoded_part + "=" * (4 - len(encoded_part) % 4)
            decoded = base64.urlsafe_b64decode(padded)
            # The actual URL is embedded in the decoded bytes after some protobuf framing
            decoded_str = decoded.decode("latin-1")
            http_idx = decoded_str.find("http")
            if http_idx >= 0:
                url_candidate = decoded_str[http_idx:]
                clean_url = ""
                for ch in url_candidate:
                    if ord(ch) >= 32 and ch not in ('\x7f',):
                        clean_url += ch
                    else:
                        break
                if clean_url.startswith("http") and len(clean_url) > 20:
                    return clean_url
    except Exception:
        pass

    # Method 2: Follow redirects with a real browser-like request
    try:
        headers = {
            "User-Agent": BROWSER_UA,
            "Accept": "text/html",
            "Cookie": "CONSENT=YES+cb.20210720-07-p0.en+FX+410",
        }
        resp = await _safe_get(google_url, headers=headers)
        final_url = str(resp.url)
        if "consent.google.com" not in final_url and "news.google.com" not in final_url:
            return final_url
    except Exception:
        pass

    return None


async def fetch_article_text(url: str, language: str = "en") -> str | None:
    """Fetch and extract article text from a URL.

    Returns the full article text or None on any error.
    Never raises exceptions.
    """
    # Resolve Google News redirect URLs to actual article URLs
    if "news.google.com" in url:
        resolved = await resolve_google_news_url(url)
        if resolved:
            url = resolved
        else:
            logger.debug("Could not resolve Google News URL: %s", url[:80])
            return None

    try:
        headers = {
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": f"{language},en;q=0.5",
        }
        response = await _safe_get(url, headers=headers)
        response.raise_for_status()
        html = response.text
    except Exception as e:
        logger.debug("Article fetch failed for %s: %s", url[:80], e)
        return None

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return None

    # Remove noise elements
    for tag_name in _NOISE_TAGS:
        for el in soup.find_all(tag_name):
            el.decompose()

    for el in soup.find_all(attrs={"class": _NOISE_CLASS_RE}):
        el.decompose()
    for el in soup.find_all(attrs={"id": _NOISE_CLASS_RE}):
        el.decompose()

    # Article content selector cascade
    content = None
    selectors = [
        lambda s: s.find("article"),
        lambda s: s.find("div", class_=re.compile(r"article[-_]?body")),
        lambda s: s.find("div", class_=re.compile(r"article[-_]?content")),
        lambda s: s.find("div", class_=re.compile(r"post[-_]?content")),
        lambda s: s.find("div", class_=re.compile(r"entry[-_]?content")),
        lambda s: s.find("div", attrs={"itemprop": "articleBody"}),
        lambda s: s.find("main"),
    ]

    for selector in selectors:
        content = selector(soup)
        if content:
            break

    # Fallback: largest div by paragraph count
    if not content:
        divs = soup.find_all("div")
        if divs:
            content = max(divs, key=lambda d: len(d.find_all("p")))

    if not content:
        return None

    paragraphs = content.find_all("p")
    text = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

    if len(text) < 50:
        return None

    return text


class ArticleExtractor:
    """Extracts structured details from full article text."""

    def __init__(self):
        from src.analysis.geo_extractor import GeoExtractor
        from src.pipeline.parser import EventParser

        self._geo = GeoExtractor()
        self._parser = EventParser()

    def extract_details(self, full_text: str, language: str = "en") -> dict:
        """Extract structured details from article text.

        Returns dict with keys: cargo_type, modus_operandi, location_detail,
        vehicle_country, financial_value_eur. Each value may be None.
        """
        result = {
            "cargo_type": None,
            "modus_operandi": None,
            "location_detail": None,
            "vehicle_country": None,
            "financial_value_eur": None,
        }

        text_lower = full_text.lower()

        # --- Cargo type ---
        try:
            result["cargo_type"] = self._extract_cargo_type(text_lower)
        except Exception:
            pass

        # --- Modus operandi ---
        try:
            result["modus_operandi"] = self._extract_modus_operandi(text_lower)
        except Exception:
            pass

        # --- Location detail ---
        try:
            result["location_detail"] = self._extract_location_detail(full_text, language)
        except Exception:
            pass

        # --- Vehicle country ---
        try:
            result["vehicle_country"] = self._extract_vehicle_country(full_text)
        except Exception:
            pass

        # --- Financial value ---
        try:
            result["financial_value_eur"] = self._parser.extract_financial_impact(full_text)
        except Exception:
            pass

        return result

    def _extract_cargo_type(self, text_lower: str) -> str | None:
        """Match cargo type keywords (case-insensitive)."""
        for cargo_type, keywords in CARGO_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return cargo_type
        return None

    def _extract_modus_operandi(self, text_lower: str) -> str | None:
        """Match modus operandi patterns."""
        for mo_key, patterns in MO_PATTERNS.items():
            for pattern, _lang in patterns:
                if re.search(pattern, text_lower):
                    return mo_key
        return None

    def _extract_location_detail(self, text: str, language: str) -> str | None:
        """Extract location detail using GeoExtractor + km markers."""
        geo_result = self._geo.extract_location(text, language, country_code=None)

        parts = []

        if geo_result.highway:
            parts.append(geo_result.highway)

        # Extract km marker
        km_match = _KM_MARKER_RE.search(text)
        if km_match:
            km_val = km_match.group(1).replace(",", ".")
            parts.append(f"km {km_val}")
        else:
            mile_match = _MILE_MARKER_RE.search(text)
            if mile_match:
                parts.append(f"mile {mile_match.group(1)}")

        if geo_result.city:
            parts.append(geo_result.city)

        if geo_result.parking:
            parts.append(f"parking: {geo_result.parking}")

        if geo_result.border_crossing:
            parts.append(f"border: {geo_result.border_crossing}")

        if not parts:
            if geo_result.region:
                return geo_result.region
            return None

        return ", ".join(parts)

    def _extract_vehicle_country(self, text: str) -> str | None:
        """Extract vehicle registration country from text mentions or plate patterns.

        Never stores full plate numbers (GDPR compliance).
        """
        # Method 1: Text mentions
        text_lower = text.lower()
        for pattern, country_code in _VEHICLE_COUNTRY_TEXT:
            if re.search(pattern, text_lower):
                return country_code

        # Method 2: Plate pattern detection — extract country prefix only
        from src.pipeline.anonymizer import PLATE_PATTERN

        plates = PLATE_PATTERN.findall(text)
        for plate in plates:
            # Extract first 1-3 uppercase letters as potential country prefix
            prefix_match = re.match(r"^([A-Z]{1,3})", plate.strip())
            if prefix_match:
                prefix = prefix_match.group(1)
                if prefix in _PLATE_PREFIX_MAP:
                    return _PLATE_PREFIX_MAP[prefix]

        return None
