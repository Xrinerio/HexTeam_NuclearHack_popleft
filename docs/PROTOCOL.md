# Протокол

## MESSAGE

Основной тип сообщения. Используется для передачи любых данных от клиента к
клиенту.

```json
{
    "type": "MESSAGE",
    "id": "<uuid>",
    "from": "<peer_id>",
    "to": "<peer_id>",
    "ttl": 16,
    "sent": 1741267200,
    "payload": "..."
}
```

## ACK

Подтверждение получения сообщения соседом.

```json
{
    "type": "ACK",
    "message_id": "<uuid_of_message>",
}
```

## ROUTES

Обмен маршрутами между соседями.

```json
{
    "type": "ROUTES",
    "from": "<peer_id>",
    "routes": [
        {"destination": "<peer_id>", "hops": 1},
        {"destination": "<peer_id>", "hops": 2}
    ]
}
```

## PING

Проверка доступности пира.

```json
{
    "type": "PING",
    "id": "<uuid>",
    "from": "<peer_id>",
}
```

## PONG

Ответ доступности пира.

```json
{
    "type": "PONG",
    "ping_id": "<uuid_of_ping>",
    "from": "<peer_id>"
}
```

## TRACEROUTE
