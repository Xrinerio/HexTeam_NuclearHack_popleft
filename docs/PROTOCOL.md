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

## PEER_INFO

Обмен маршрутами между соседями.

```json
{
    "type": "PEER_INFO",
    "from": "<peer_id>",
    "tcp_port": "<port>",
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

## KEY_EXCHANGE

Обмен публичными ключами перед первой отправкой зашифрованного сообщения.
Инициируется автоматически при обнаружении нового соседа (после PEER_INFO).
Пакет маршрутизируется как MESSAGE (через TTL).

```json
{
    "type": "KEY_EXCHANGE",
    "from": "<peer_id>",
    "to": "<peer_id>",
    "public_key": "<base64_encoded_curve25519_public_key>",
    "ttl": 16
}
```

Получатель сохраняет публичный ключ отправителя и, если это первый контакт,
отвечает симметричным KEY_EXCHANGE со своим ключом.

Шифрование `payload` в MESSAGE выполняется алгоритмом NaCl Box
(Curve25519 + XSalsa20-Poly1305). Зашифрованный payload передаётся
в виде base64-строки.
