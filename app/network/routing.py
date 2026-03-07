from dataclasses import dataclass

from app.core import logger

_MAX_DISTANCE: int = 16


@dataclass
class _Route:
    destination: str
    """peer_id цели."""
    name: str
    """Имя пира."""
    gateway: str
    """peer_id выхода до цели."""
    ip: str | None
    """IP адрес, если это физический сосед."""
    hops: int
    """Метрика достижения цели."""


class Routing:
    def __init__(self) -> None:
        self._table: dict[str, _Route] = {}
        logger.info("Загружена таблица маршрутизации")

    def add_route(
        self,
        *,
        destination: str,
        name: str,
        gateway: str,
        ip: str | None,
        hops: int,
    ) -> None:
        """Добавить или обновить маршрут."""
        route: _Route | None = self._table.get(destination)

        if route is None or hops < route.hops:
            self._table[destination] = _Route(
                destination=destination,
                name=name,
                gateway=gateway,
                ip=ip,
                hops=hops,
            )

    def add_neighbor(self, *, destination: str, name: str, ip: str) -> None:
        """Добавить соседа."""
        self._table[destination] = _Route(
            destination=destination,
            name=name,
            gateway=destination,
            ip=ip,
            hops=1,
        )

    def get_route(self, destination: str, /) -> _Route | None:
        """Вернуть лучший маршрут до узла или None если недостижим."""
        route: _Route | None = self._table.get(destination)

        if route is not None and route.hops < _MAX_DISTANCE:
            return route

        return None

    def remove_routes_via(self, gateway: str, /) -> None:
        """Удалить все маршруты через упавший/отключившийся узел."""
        for dest in [
            d for d, route in self._table.items() if route.gateway == gateway
        ]:
            del self._table[dest]

    def get_advertisement(
        self,
        *,
        to_node_id: str,
    ) -> list[dict[str, str | int]]:
        """Сформировать список маршрутов для рассылки соседу to_node_id."""
        return [
            {"destination": r.destination, "name": r.name, "hops": r.hops}
            for r in self._table.values()
            if r.hops < _MAX_DISTANCE and r.gateway != to_node_id
        ]

    def update_from_advertisement(
        self,
        *,
        gateway: str,
        gateway_ip: str,
        routes: list[dict],
    ) -> None:
        """Обновить таблицу маршрутов по списку из PEER_INFO."""
        for entry in routes:
            dest: str | None = entry.get("destination")
            name: str = entry.get("name", "?")
            advertised_hops: int = entry.get("hops", _MAX_DISTANCE)

            if not dest or dest == gateway:
                continue

            new_hops = advertised_hops + 1
            if new_hops >= _MAX_DISTANCE:
                continue

            current = self._table.get(dest)
            if current is None or new_hops < current.hops:
                self._table[dest] = _Route(
                    destination=dest,
                    name=name,
                    gateway=gateway,
                    ip=gateway_ip,
                    hops=new_hops,
                )

    def all_routes(self) -> list[_Route]:
        return list(self._table.values())

    def __str__(self) -> str:
        if not self._table:
            return "None"

        rows = sorted(self._table.values(), key=lambda r: r.hops)

        col_dest = max(len("Destination"), *(len(r.destination) for r in rows))
        col_gateway = max(len("Gateway"), *(len(r.gateway) for r in rows))
        col_ip = max(len("IP"), *(len(r.ip or "-") for r in rows))
        col_hops = max(len("Hops"), *(len(str(r.hops)) for r in rows))

        sep = (
            f"+{'-' * (col_dest + 2)}+{'-' * (col_gateway + 2)}+"
            f"{'-' * (col_ip + 2)}+{'-' * (col_hops + 2)}+"
        )
        header = (
            f"| {'Destination':<{col_dest}} "
            f"| {'Gateway':<{col_gateway}} "
            f"| {'IP':<{col_ip}} "
            f"| {'Hops':<{col_hops}} |"
        )

        lines = [sep, header, sep]
        lines.extend(
            [
                f"| {r.destination:<{col_dest}} "
                f"| {r.gateway:<{col_gateway}} "
                f"| {(r.ip or '-'):<{col_ip}} "
                f"| {r.hops:<{col_hops}} |"
                for r in rows
            ],
        )
        lines.append(sep)

        return "\n".join(lines)


routing: Routing = Routing()
