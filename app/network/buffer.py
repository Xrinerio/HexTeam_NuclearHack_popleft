from dataclasses import dataclass


@dataclass
class _Pending:
    destination: str
    data: bytes


class Buffer:
    """Буфер для ретрансляции пакетов, когда маршрут до получателя недоступен.

    Хранит сырые байты (JSON-пакеты любого типа) с привязкой к destination.
    Когда маршрут появляется — буфер сбрасывается через _flush_buffer в server.py.
    """

    def __init__(self, max_per_destination: int = 64) -> None:
        self._buffer: list[_Pending] = []
        self._max = max_per_destination

    def add(self, destination: str, data: bytes) -> None:
        count = sum(1 for p in self._buffer if p.destination == destination)
        if count >= self._max:
            return
        self._buffer.append(_Pending(destination=destination, data=data))

    def pop_all(self, destination: str) -> list[bytes]:
        pending = [p.data for p in self._buffer if p.destination == destination]
        self._buffer = [p for p in self._buffer if p.destination != destination]
        return pending

    def get_pending_destinations(self) -> list[str]:
        return list({p.destination for p in self._buffer})

    def __len__(self) -> int:
        return len(self._buffer)


buffer: Buffer = Buffer()
