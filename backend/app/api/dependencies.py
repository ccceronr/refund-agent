"""FastAPI dependencies: hand routers what create_app() built, so tests can swap it."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_rw_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.rw_engine
    return engine


AppSettings = Annotated[Settings, Depends(get_settings)]
RwEngine = Annotated[AsyncEngine, Depends(get_rw_engine)]
