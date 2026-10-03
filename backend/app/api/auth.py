"""Sign in, sign out and "who am I" (design §4.0)."""

from http import HTTPStatus
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import SESSION_STAFF_KEY, Auth, CurrentStaff
from app.services.auth import StaffMember

router = APIRouter(prefix="/auth")


class SignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class StaffResponse(BaseModel):
    name: str
    role: Literal["staff", "supervisor"]

    @classmethod
    def of(cls, staff: StaffMember) -> "StaffResponse":
        return cls(name=staff.first_name, role=staff.role.value)  # type: ignore[arg-type]  # system can't sign in


@router.post("/login")
async def sign_in(body: SignInRequest, request: Request, auth: Auth) -> StaffResponse:
    staff = await auth.sign_in(body.username, body.password)
    # A fresh session on every sign-in: nothing from before it survives (OWASP A07).
    request.session.clear()
    request.session[SESSION_STAFF_KEY] = staff.staff_id
    return StaffResponse.of(staff)


@router.post("/logout", status_code=HTTPStatus.NO_CONTENT)
async def sign_out(request: Request, staff: CurrentStaff, auth: Auth) -> Response:
    request.session.clear()
    await auth.sign_out(staff)
    return Response(status_code=HTTPStatus.NO_CONTENT)


@router.get("/me")
async def me(staff: CurrentStaff) -> StaffResponse:
    return StaffResponse.of(staff)
