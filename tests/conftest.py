import os
from collections.abc import Generator
from urllib.parse import parse_qs, urlparse

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import Base, get_session
from app.main import create_app
from app.orders import models as order_models  # noqa: F401


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    settings = Settings()
    url = os.getenv("TEST_DATABASE_URL", settings.test_database_url)
    database = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not database.endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL must name a database ending in '_test'")
    return settings.model_copy(update={"test_database_url": url})


@pytest.fixture(scope="session")
def test_engine(test_settings):
    engine = create_engine(test_settings.test_database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        current_db = connection.execute(text("SELECT current_database()")).scalar_one()
        if not current_db.endswith("_test"):
            raise RuntimeError("Refusing to reset a database without the '_test' suffix")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def clear_test_data(test_engine):
    with test_engine.begin() as connection:
        connection.execute(text("TRUNCATE order_items, orders, products RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    session = Session(bind=test_engine, expire_on_commit=False)
    yield session
    session.close()


def _redis_database(url: str) -> int:
    parsed = urlparse(url)
    query_database = parse_qs(parsed.query).get("db", [None])[0]
    path_database = parsed.path.strip("/") or "0"
    try:
        return int(query_database if query_database is not None else path_database)
    except ValueError as error:
        raise RuntimeError("Redis URLs must select a numeric database") from error


def _same_redis_database(runtime_url: str, test_url: str) -> bool:
    runtime_client = redis.Redis.from_url(runtime_url)
    test_client = redis.Redis.from_url(test_url)
    try:
        runtime_id = runtime_client.info("server").get("run_id")
        test_id = test_client.info("server").get("run_id")
        if not runtime_id or not test_id:
            raise RuntimeError("Redis server identity is unavailable")
        return runtime_id == test_id and _redis_database(runtime_url) == _redis_database(test_url)
    except redis.RedisError as error:
        raise RuntimeError("Cannot verify Redis server identity; refusing test cleanup") from error
    finally:
        runtime_client.close()
        test_client.close()


@pytest.fixture
def redis_client(test_settings):
    if _same_redis_database(test_settings.redis_url, test_settings.test_redis_url):
        raise RuntimeError("TEST_REDIS_URL points to the runtime Redis database")
    client = redis.Redis.from_url(test_settings.test_redis_url, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()
    client.close()


@pytest.fixture
def client(test_engine, redis_client, test_settings):
    app = create_app(test_settings, redis_client)
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seed_products(db_session):

    def seed(*products):
        db_session.add_all(products)
        db_session.flush()
        return products

    return seed
