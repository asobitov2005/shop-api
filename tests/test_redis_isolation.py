import pytest
import redis

from app.core.config import Settings
from tests.conftest import redis_client as redis_client_fixture


class FakeRedis:
    def __init__(self, run_id):
        self.run_id = run_id
        self.flushes = 0

    def info(self, section):
        return {"run_id": self.run_id}

    def flushdb(self):
        self.flushes += 1

    def close(self):
        pass


def test_fixture_refuses_runtime_database_when_hosts_are_aliases(monkeypatch):
    fake = FakeRedis(run_id="same-server")
    monkeypatch.setattr(redis.Redis, "from_url", lambda *args, **kwargs: fake)
    settings = Settings(
        redis_url="redis://localhost:56380/1",
        test_redis_url="redis://127.0.0.1:56380/1",
    )
    fixture = redis_client_fixture.__wrapped__(settings)

    with pytest.raises(RuntimeError, match="runtime Redis database"):
        next(fixture)

    assert fake.flushes == 0


def test_fixture_allows_a_different_database_on_same_server(monkeypatch):
    fake = FakeRedis(run_id="same-server")
    monkeypatch.setattr(redis.Redis, "from_url", lambda *args, **kwargs: fake)
    settings = Settings(
        redis_url="redis://localhost:56380/0",
        test_redis_url="redis://127.0.0.1:56380/1",
    )
    fixture = redis_client_fixture.__wrapped__(settings)

    assert next(fixture) is fake
    assert fake.flushes == 1
    fixture.close()
