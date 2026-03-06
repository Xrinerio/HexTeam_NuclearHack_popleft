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
    "payload": "...",
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

## 
