"""Polaczenie z baza grafowa Neo4j do analizy powiazan miedzy zdarzeniami."""

from neo4j import AsyncGraphDatabase

from src.config import settings

driver = AsyncGraphDatabase.driver(
    settings.neo4j_uri,
    auth=(settings.neo4j_user, settings.neo4j_password),
)


async def get_neo4j_session():
    """Zwraca sesje Neo4j."""
    async with driver.session() as session:
        yield session


async def close_neo4j():
    """Zamyka polaczenie z Neo4j."""
    await driver.close()
