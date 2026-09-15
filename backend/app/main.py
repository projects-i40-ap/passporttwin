"""
PassportTwin backend — application entrypoint.

This file wires together the FastAPI app. Route logic lives in `api/`,
configuration in `core/`, DB session handling in `database/`.
"""
from fastapi import FastAPI
from app.api import instruments
from app.database.session import Base, engine
from app.api import instruments, documents

# 1. Crea el esquema canónico en PostgreSQL si las tablas no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PassportTwin API",
    description="Digital passport and reliability twin for measurement instrument fleets.",
    version="0.1.0",
)

@app.get("/")
def read_root():
    return {"status": "ok", "service": "passporttwin-backend", "version": "0.1.0"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

# 2. Inyección del enrutador de la Capa 3
app.include_router(instruments.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")