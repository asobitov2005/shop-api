from contextlib import asynccontextmanager
from pathlib import Path

import redis
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings, get_settings
from app.orders.router import router as orders_router
from app.payments.click.router import router as click_router
from app.payments.router import router as payments_router
from app.products.router import router as products_router

SHOP_STATIC = Path(__file__).parent / "shop" / "static"


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
    app.state.settings = configured
    app.mount("/static", StaticFiles(directory=SHOP_STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def shop_home() -> FileResponse:
        return FileResponse(SHOP_STATIC / "index.html")

    app.include_router(products_router)
    app.include_router(orders_router)
    app.include_router(payments_router)
    app.include_router(click_router)
    return app


app = create_app()
