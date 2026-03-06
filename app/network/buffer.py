from app.protocol.message import Message


class Buffer:
    def __init__(self) -> None:
        self._buffer: list[Message] = []

    def add_message(self, message: Message) -> None:
        self._buffer.append(message)

    def get_messages(self, destination: str) -> list[Message]:
        return [msg for msg in self._buffer if msg.to == destination]

    def has_messages(self, destination: str) -> bool:
        return any(msg.to == destination for msg in self._buffer)

    def clear_messages(self, destination: str) -> None:
        self._buffer = [msg for msg in self._buffer if msg.to != destination]

    def remove_message(self, message: Message) -> None:
        if message in self._buffer:
            self._buffer.remove(message)

    def get_pending_destinations(self) -> list[str]:
        return list({msg.to for msg in self._buffer})

    def clear_all(self) -> None:
        self._buffer.clear()


buffer: Buffer = Buffer()
