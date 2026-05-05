# Transport Intelligence

System analizy i monitorowania zdarzen w transporcie miedzynarodowym. Zbiera dane z wielu zrodel (strony internetowe, media spolecznosciowe, fora, zrodla oficjalne), przetwarza je przez pipeline NLP i generuje raporty ryzyka.

## Architektura

- **Agenci** - zbieranie danych z roznych zrodel (web scraping, social media, fora, zrodla oficjalne)
- **Pipeline** - parsowanie, normalizacja, klasyfikacja AI, korelacja zdarzen
- **Analiza** - NLP wielojezyczne, ekstrakcja geolokalizacji, scoring ryzyka, mapy kradziezi
- **Raporty** - automatyczne generowanie raportow 2-tygodniowych i miesiecznych
- **API** - FastAPI REST do dashboardu i integracji

## Stack technologiczny

- Python 3.11+
- PostgreSQL 16 (dane relacyjne)
- Neo4j 5 (graf powiazan)
- Apache Kafka (streaming zdarzen)
- Redis (cache, kolejki)
- FastAPI (REST API)
- spaCy + Transformers (NLP)
- Scrapy + Playwright (scraping)

## Uruchomienie

```bash
# Skopiuj zmienne srodowiskowe
cp .env.example .env

# Uruchom infrastrukture
docker-compose up -d

# Zainstaluj zaleznosci
pip install -r requirements.txt

# Uruchom migracje
alembic upgrade head

# Uruchom API
uvicorn src.api.main:app --reload
```
