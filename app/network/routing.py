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
    """IP адрес gateway (физического соседа)."""
    port: int
    """TCP-порт gateway."""
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
        port: int = 0,
        hops: int,
    ) -> None:
        """Добавить или обновить маршрут."""
        route: _Route | None = self._table.get(destination)

        if route is None or hops < route.hops:
            logger.info(f"Добавлен маршрут до {destination}")
            self._table[destination] = _Route(
                destination=destination,
                name=name,
                gateway=gateway,
                ip=ip,
                port=port,
                hops=hops,
            )

    def add_neighbor(
        self,
        *,
        destination: str,
        name: str,
        ip: str,
        port: int,
    ) -> None:
        """Добавить прямого соседа (hops=1)."""
        logger.info(f"Добавлен сосед {destination} ({ip}:{port})")
        self._table[destination] = _Route(
            destination=destination,
            name=name,
            gateway=destination,
            ip=ip,
            port=port,
            hops=1,
        )

    def get_next_hop_addr(self, destination: str, /) -> tuple[str, int] | None:
        """Вернуть (ip, port) следующего хопа для отправки пакета до destination."""
        route = self.get_route(destination)
        if route is None:
            return None
        # gateway — всегда прямой сосед
        gateway_route = self._table.get(route.gateway)
        if (
            gateway_route is None
            or not gateway_route.ip
            or not gateway_route.port
        ):
            return None
        return gateway_route.ip, gateway_route.port

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
            logger.info(f"Удалён маршрут через {gateway} до {dest}")
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
        gateway_port: int,
        routes: list[dict],
    ) -> None:
        """Обновить таблицу маршрутов по списку из PEER_INFO (Bellman-Ford)."""
        # Remove all indirect routes previously learned via this gateway.
        # This ensures that if a destination disappeared from the advertisement
        # (because it went offline), we don't keep a stale route to it.
        # The gateway's own direct route (destination == gateway) is preserved.
        stale = [
            d
            for d, r in self._table.items()
            if r.gateway == gateway and d != gateway
        ]
        for dest in stale:
            logger.info(
                f"Удалён устаревший маршрут до {dest} (через {gateway})"
            )
            del self._table[dest]

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
                logger.info(f"Обновлён маршрут до {dest}")
                self._table[dest] = _Route(
                    destination=dest,
                    name=name,
                    gateway=gateway,
                    ip=gateway_ip,
                    port=gateway_port,
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
