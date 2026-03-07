import time


def now() -> int:
    return int(time.time())


def now_ms() -> float:
    return time.time() * 1000


async def handle_message(message: str) -> None:
    pass
