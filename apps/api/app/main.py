import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import companies

log = logging.getLogger("financial-overview")
logging.basicConfig(level=logging.INFO)

settings = get_settings()
app = FastAPI(
    title="Financial Overview API",
    version="0.1.0",
    description="Companies House filing retrieval and Claude-assisted review of UK accounts.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
