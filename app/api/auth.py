import sqlite3
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core import Settings
from app.core.utils import get_local_ip
from app.crud.users import (
    create_user,
    get_current_user,
    get_user,
    username_exists,
)
from app.database import database

router: APIRouter = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class UserResponse(BaseModel):
    peer_id: str
    username: str
    created_at: str


class NodeInfoResponse(BaseModel):
    peer_id: str
    username: str
    created_at: str
    ip: str
    port: int


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, request: Request) -> UserResponse:
    if get_current_user() is not None:
        raise HTTPException(
            status_code=409,
            detail="This node is already registered. Restart to apply.",
        )
    if username_exists(body.username):
        raise HTTPException(
            status_code=409,
            detail=f"Username {body.username!r} is already taken.",
        )

    peer_id = str(uuid4())
    row: sqlite3.Row = create_user(peer_id=peer_id, username=body.username)

    # Обновляем identity в настройках и в работающем сервере
    Settings.PEER_ID = peer_id
    Settings.USERNAME = body.username
    request.app.state.server.peer_id = peer_id

    # Удаляем невалидные ключи с пустым peer_id, если они накопились до регистрации
    database.execute("DELETE FROM keys WHERE peer_id = ''")

    return UserResponse(
        peer_id=row["peer_id"],
        username=row["username"],
        created_at=str(row["created_at"]),
    )


@router.get("/me")
async def get_current_user_info() -> NodeInfoResponse:
    """Получить информацию о текущем зарегистрированном пользователе."""
    row = get_current_user()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="User not registered. Please register first.",
        )
    return NodeInfoResponse(
        peer_id=row["peer_id"],
        username=row["username"],
        created_at=str(row["created_at"]),
        ip=get_local_ip(),
        port=Settings.PORT,
    )


@router.get("/users/{peer_id}")
async def get_user_info(peer_id: str) -> UserResponse:
    row = get_user(peer_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"User {peer_id!r} not found.",
        )
    return UserResponse(
        peer_id=row["peer_id"],
        username=row["username"],
        created_at=str(row["created_at"]),
    )
