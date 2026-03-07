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

## HELLO

UDP-broadcast для обнаружения соседей в локальной сети. Отправляется
периодически на широковещательный адрес. При получении инициируется
TCP-соединение и обмен PEER_INFO.

```json
{
    "type": "HELLO",
    "peer_id": "<peer_id>",
    "name": "Alice",
    "port": 8001
}
```

## FILE_CHUNK

Передача фрагмента файла. Файл разбивается на чанки фиксированного размера
(по умолчанию 32 КБ). Каждый чанк шифруется NaCl Box и передаётся отдельным
пакетом. Маршрутизируется через TTL как MESSAGE.

```json
{
    "type": "FILE_CHUNK",
    "from": "<peer_id>",
    "to": "<peer_id>",
    "file_id": "<uuid>",
    "filename": "photo.jpg",
    "chunk_index": 0,
    "total_chunks": 5,
    "file_size": 163840,
    "sha256": "<hex_digest>",
    "payload": "<base64_encrypted_chunk>",
    "encrypted": true,
    "ttl": 16
}
```

После получения всех чанков получатель собирает файл и проверяет SHA-256
контрольную сумму.

## FILE_ACK

Подтверждение получения отдельного чанка файла. Отправляется получателем
обратно отправителю для каждого принятого FILE_CHUNK.

```json
{
    "type": "FILE_ACK",
    "from": "<peer_id>",
    "to": "<peer_id>",
    "file_id": "<uuid>",
    "chunk_index": 0,
    "ttl": 16
}
```

## CALL_OFFER

Инициация голосового звонка. Отправляется вызывающей стороной.
Маршрутизируется через TTL.

```json
{
    "type": "CALL_OFFER",
    "from": "<peer_id>",
    "to": "<peer_id>",
    "call_id": "<uuid>",
    "ttl": 16
}
```

## CALL_ANSWER

Ответ на входящий звонок. Поле `accepted` определяет, принят звонок или
отклонён.

```json
{
    "type": "CALL_ANSWER",
    "from": "<peer_id>",
    "to": "<peer_id>",
    "call_id": "<uuid>",
    "accepted": true,
    "ttl": 16
}
```

## CALL_END

Завершение активного звонка. Может быть отправлен любой из сторон.

```json
{
    "type": "CALL_END",
    "from": "<peer_id>",
    "to": "<peer_id>",
    "call_id": "<uuid>",
    "ttl": 16
}
```

## CALL_AUDIO

Фрагмент аудиоданных голосового звонка. Payload содержит PCM Int16 mono 16 kHz,
зашифрованный NaCl Box и закодированный в base64. Поле `seq` — порядковый номер
фрейма для упорядочивания на принимающей стороне. Маршрутизируется через TTL;
при смене маршрута звонок продолжается без разрыва.

```json
{
    "type": "CALL_AUDIO",
    "from": "<peer_id>",
    "to": "<peer_id>",
    "call_id": "<uuid>",
    "seq": 42,
    "payload": "<base64_encrypted_pcm>",
    "encrypted": true,
    "ttl": 16
}
```
