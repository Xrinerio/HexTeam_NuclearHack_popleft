import logging
from logging import Formatter, Logger, StreamHandler
from typing import TextIO

logger: Logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler: StreamHandler[TextIO] = logging.StreamHandler()
logger.addHandler(handler)

formatter: Formatter = logging.Formatter(
    "[%(asctime)s] [%(module)s] [%(levelname)s] %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
)
handler.setFormatter(formatter)
