import sqlite3
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.crud.users import create_user, get_user, username_exists

router: APIRouter = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class UserResponse(BaseModel):
    peer_id: str
    username: str
    created_at: str


@router.post("/register", status_code=201)
async def register(body: RegisterRequest) -> UserResponse:
    if username_exists(body.username):
        raise HTTPException(
            status_code=409,
            detail=f"Username {body.username!r} is already taken.",
        )

    peer_id = str(uuid4())
    row: sqlite3.Row = create_user(peer_id=peer_id, username=body.username)
    return UserResponse(
        peer_id=row["peer_id"],
        username=row["username"],
        created_at=str(row["created_at"]),
    )


@router.get("/users/{peer_id}")
async def get_user_info(peer_id: str) -> UserResponse:
    row = get_user(peer_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"User {peer_id!r} not found."
        )
    return UserResponse(
        peer_id=row["peer_id"],
        username=row["username"],
        created_at=str(row["created_at"]),
    )
