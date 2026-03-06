from fastapi import APIRouter

router: APIRouter = APIRouter()


@router.get("/peers")
async def get_peers() -> str:
    return "A, B, C"
