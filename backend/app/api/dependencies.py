"""FastAPI dependencies: hand routers what create_app() built, so tests can swap it."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agents.run_case import CaseRunner
from app.agents.steps import EventSink
from app.api.errors import NotSignedIn
from app.core.config import Settings
from app.services.auth import AuthService, StaffMember
from app.services.decisions import DecisionService

SESSION_STAFF_KEY = "staff_id"  # the only thing the session cookie holds (design §4.0)


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_rw_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.rw_engine
    return engine


def get_auth_service(request: Request) -> AuthService:
    auth: AuthService = request.app.state.auth
    return auth


def get_decision_service(request: Request) -> DecisionService:
    decisions: DecisionService = request.app.state.decisions
    return decisions


def get_runner_factory(request: Request) -> Callable[[EventSink], CaseRunner]:
    """Builds the flow runner for one request; tests swap in fake models here."""
    factory: Callable[[EventSink], CaseRunner] = request.app.state.runner_factory
    return factory


AppSettings = Annotated[Settings, Depends(get_settings)]
RwEngine = Annotated[AsyncEngine, Depends(get_rw_engine)]
Auth = Annotated[AuthService, Depends(get_auth_service)]
Decisions = Annotated[DecisionService, Depends(get_decision_service)]
RunnerFactory = Annotated[Callable[[EventSink], CaseRunner], Depends(get_runner_factory)]


async def current_staff(request: Request, auth: Auth) -> StaffMember:
    """The signed-in staff member. The actor of every action comes only from here (A01)."""
    staff_id = request.session.get(SESSION_STAFF_KEY)
    staff = await auth.signed_in_staff(staff_id) if isinstance(staff_id, str) else None
    if staff is None:
        request.session.clear()
        raise NotSignedIn
    return staff


CurrentStaff = Annotated[StaffMember, Depends(current_staff)]
