"""
PassportTwin backend — application entrypoint.

This file wires together the FastAPI app. Route logic lives in `api/`,
configuration in `core/`, DB session handling in `database/`.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.session import Base, engine
from app.api import instruments, documents


# 1. Crea el esquema canónico en PostgreSQL si las tablas no existen
Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="PassportTwin API",
    description="Digital passport and reliability twin for measurement instrument fleets.",
    version="0.1.0",
)


# 2. Permite al frontend React/Vite acceder a la API durante desarrollo local
frontend_port = os.getenv("FRONTEND_PORT", "5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{frontend_port}",
        f"http://127.0.0.1:{frontend_port}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {
        "status": "ok",
        "service": "passporttwin-backend",
        "version": "0.1.0",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


# 3. Inyección de los routers de la API
app.include_router(instruments.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")