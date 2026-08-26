from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine

from api import router as api_router
from config.settings import Settings, get_settings
from db.session import build_session_factory, init_db, make_engine
from services.bootstrap import seed_reference_data
from services.recovery import RecoveryService
from web import router as web_router


def create_app(settings: Optional[Settings] = None, engine: Optional[Engine] = None) -> FastAPI:
    app_settings = settings or get_settings()
    app_settings.validate()
    app_engine = engine or make_engine(app_settings.database_url)
    session_factory = build_session_factory(app_engine)
    init_db(app_engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = session_factory()
        try:
            RecoveryService(db).reconcile()
            seed_reference_data(db, app_settings)
        finally:
            db.close()
        yield
        app_engine.dispose()

    app = FastAPI(
        title=app_settings.app_name,
        description="主管 Agent + 专业 Agent/Tool 的企业售后、知识咨询、行为分析与预约统一服务",
        version=app_settings.version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.settings = app_settings
    app.state.engine = app_engine
    app.state.session_factory = session_factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Actor-Id", "X-Role", "X-Confirm-Token"],
    )
    app.include_router(api_router)
    app.include_router(web_router)
    static_dir = Path(__file__).parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("app:app", host=settings.host, port=settings.port, reload=settings.app_env == "local")

