from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import api_router
from app.services.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Adaptive Tutor API",
    version="0.1.0",
    description="Stateful adaptive tutoring backend",
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
