from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.orders.router import router as orders_router
from app.products.router import router as products_router


def create_app(settings: Settings | None = None, redis_client=None) -> FastAPI:
    configured = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if redis_client is None:
            app.state.redis = redis.Redis.from_url(configured.redis_url, decode_responses=True)
        else:
            app.state.redis = redis_client
        yield
        if redis_client is None:
            app.state.redis.close()

    app = FastAPI(title="Shop API", lifespan=lifespan, root_path=configured.app_root_path)
    app.include_router(products_router)
    app.include_router(orders_router)
    return app


app = create_app()
