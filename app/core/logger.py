import logging
from logging import Formatter, StreamHandler
from typing import TextIO

logger: logging.Logger = logging.getLogger("uvicorn.error")

handler: StreamHandler[TextIO] = logging.StreamHandler()
logger.addHandler(handler)

formatter: Formatter = logging.Formatter(
    "[%(asctime)s] [%(module)s] [%(levelname)s] %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
)
handler.setFormatter(formatter)
