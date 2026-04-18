from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import Settings, get_settings
from app.core.database import check_database_connection, close_database_connection

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await check_database_connection()
    yield
    await close_database_connection()


def create_app(app_settings: Settings = settings) -> FastAPI:
    api = FastAPI(
        title=app_settings.app_name,
        debug=app_settings.debug,
        version=app_settings.app_version,
        lifespan=lifespan,
    )

    api.state.settings = app_settings
    api.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api.include_router(api_router, prefix=app_settings.api_v1_prefix)

    @api.get("/", tags=["system"])
    async def root() -> dict[str, str]:
        return {
            "name": app_settings.app_name,
            "status": "running",
            "docs": "/docs",
        }

    @api.get("/health", tags=["system"])
    async def health() -> dict[str, object]:
        return {
            "ok": True,
            "app": app_settings.app_name,
            "version": app_settings.app_version,
            "environment": app_settings.app_env,
            "database_configured": app_settings.is_database_configured,
        }

    @api.get("/db/health", tags=["system"])
    async def database_health() -> dict[str, object]:
        return await check_database_connection()

    return api


app = create_app()
