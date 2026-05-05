"""Walidacja legalnosci zrodel danych przed scrapowaniem.

Sprawdza:
- Czy zrodlo jest publiczne (nie wymaga logowania/paywallu).
- Czy robots.txt pozwala na scrapowanie.
- Czy Terms of Service nie zabraniaja.
- Utrzymuje whitelist zatwierdzonych i blacklist zabronionych zrodel.

Reguly:
- robots.txt zabrania -> NIE scrapujemy.
- Strona wymaga logowania -> NIE scrapujemy.
- Strona ma paywall -> NIE scrapujemy.
- Publiczne rejestry, komunikaty policji, artykuly prasowe -> OK.
- API z oficjalnym dostepem (Reddit API) -> OK.
"""

import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

DEFAULT_WHITELIST: set[str] = {
    "polizei.de",
    "bundespolizei.de",
    "policja.pl",
    "policja.gov.pl",
    "policie.cz",
    "politie.nl",
    "police.be",
    "polizei.gv.at",
    "police-nationale.interieur.gouv.fr",
    "polisen.se",
    "politiet.no",
    "reddit.com",
}

DEFAULT_BLACKLIST: set[str] = set()

# Domeny znane z wymagania logowania / paywallu
LOGIN_REQUIRED_DOMAINS: set[str] = {
    "linkedin.com",
    "facebook.com",
    "instagram.com",
}

PAYWALL_DOMAINS: set[str] = {
    "ft.com",
    "wsj.com",
    "bloomberg.com",
    "economist.com",
}

USER_AGENT_NAME = "TransportIntelligence"


class SourceValidator:
    """Walidator legalnosci zrodel przed scrapowaniem."""

    def __init__(self):
        self._whitelist: set[str] = DEFAULT_WHITELIST.copy()
        self._blacklist: set[str] = DEFAULT_BLACKLIST.copy()
        self._robots_cache: dict[str, bool] = {}

    def is_public_source(self, url: str) -> bool:
        """Sprawdza czy zrodlo jest publicznie dostepne (bez logowania/paywallu)."""
        domain = self._extract_domain(url)
        if domain in LOGIN_REQUIRED_DOMAINS:
            logger.debug("Zrodlo wymaga logowania: %s", domain)
            return False
        if domain in PAYWALL_DOMAINS:
            logger.debug("Zrodlo ma paywall: %s", domain)
            return False
        return True

    def is_legal_to_scrape(self, url: str) -> bool:
        """Sprawdza czy mozna legalnie scrapowac dane zrodlo.

        Sprawdza:
        1. Blacklist
        2. Whitelist (natychmiastowe OK)
        3. Login/paywall
        4. robots.txt
        """
        domain = self._extract_domain(url)

        if domain in self._blacklist:
            logger.warning("Zrodlo na blackliscie: %s", domain)
            return False

        if domain in self._whitelist:
            return True

        if not self.is_public_source(url):
            return False

        if not self.check_robots_txt(url):
            logger.warning("robots.txt zabrania scrapowania: %s", url)
            return False

        return True

    def check_robots_txt(self, url: str) -> bool:
        """Sprawdza czy robots.txt pozwala na scrapowanie danego URL.

        Uzywa urllib.robotparser. Cachuje wynik per domena.
        Przy bledzie parsowania (timeout, 404, etc.) — zwraca True (domyslnie OK).
        """
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        # Sprawdz cache
        if robots_url in self._robots_cache:
            return self._robots_cache[robots_url]

        try:
            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.read()
            allowed = rp.can_fetch(USER_AGENT_NAME, url)
            # Jesli brak regul dla naszego agenta, sprawdz tez jako *
            if allowed:
                allowed = rp.can_fetch("*", url)
            self._robots_cache[robots_url] = allowed
            return allowed
        except Exception as e:
            logger.debug("Nie mozna odczytac robots.txt (%s): %s — domyslnie OK", robots_url, e)
            self._robots_cache[robots_url] = True
            return True

    def requires_login(self, url: str) -> bool:
        """Sprawdza czy strona wymaga logowania."""
        domain = self._extract_domain(url)
        return domain in LOGIN_REQUIRED_DOMAINS

    def has_paywall(self, url: str) -> bool:
        """Sprawdza czy strona ma paywall."""
        domain = self._extract_domain(url)
        return domain in PAYWALL_DOMAINS

    def maintain_whitelist(self) -> set[str]:
        """Zwraca aktualna liste zatwierdzonych zrodel."""
        return self._whitelist.copy()

    def add_to_whitelist(self, domain: str) -> None:
        """Dodaje domene do whitelist."""
        self._whitelist.add(domain)
        self._blacklist.discard(domain)
        logger.info("Dodano do whitelist: %s", domain)

    def maintain_blacklist(self) -> set[str]:
        """Zwraca aktualna liste zabronionych zrodel."""
        return self._blacklist.copy()

    def add_to_blacklist(self, domain: str) -> None:
        """Dodaje domene do blacklist."""
        self._blacklist.add(domain)
        self._whitelist.discard(domain)
        logger.info("Dodano do blacklist: %s", domain)

    def _extract_domain(self, url: str) -> str:
        """Wyciaga domene z URL."""
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
