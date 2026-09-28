import logging
import signal
import threading

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import make_session_factory
from app.products.cache import ProductCache
from app.worker.expiry import expire_pending_orders

logger = logging.getLogger(__name__)
POLL_SECONDS = 30
RETRY_SECONDS = 5


def wait_for_migrations(factory: sessionmaker[Session], stop: threading.Event) -> bool:
    while not stop.is_set():
        try:
            with factory() as session:
                session.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                ).scalar_one()
            return True
        except SQLAlchemyError:
            logger.exception("Database migrations are not ready; retrying")
            stop.wait(RETRY_SECONDS)
    return False


def run_worker(factory: sessionmaker[Session], cache: ProductCache, stop: threading.Event) -> None:
    if not wait_for_migrations(factory, stop):
        return
    while not stop.is_set():
        try:
            with factory() as session:
                count = expire_pending_orders(session, cache)
            if count:
                logger.info("Expired %s pending orders", count)
        except SQLAlchemyError:
            logger.exception("Expiry batch failed; retrying")
            stop.wait(RETRY_SECONDS)
            continue
        stop.wait(POLL_SECONDS)


def main() -> None:
    settings = get_settings()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    factory = make_session_factory(settings.database_url)
    import redis

    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        run_worker(factory, ProductCache(client), stop)
    finally:
        client.close()
        factory.kw["bind"].dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
