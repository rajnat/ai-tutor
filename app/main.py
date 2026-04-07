import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.core.config import get_settings
from app.services.bootstrap import ensure_starter_curriculum
from app.services.database import SessionLocal
from app.services.dependencies import get_curriculum_repository


app = FastAPI(
    title="Adaptive Tutor API",
    version="0.1.0",
    description="Stateful adaptive tutoring backend",
)

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.on_event("startup")
def seed_starter_curriculum() -> None:
    db = SessionLocal()
    try:
        ensure_starter_curriculum(get_curriculum_repository(db))
    finally:
        db.close()


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
