import base64
from pathlib import Path
from typing import cast

from nacl.public import Box, PrivateKey, PublicKey

from app.crud.keys import add_all_keys, get_all_keys


class Crypto:
    def __init__(self) -> None:
        self.keys_dir = Path("keys")

        self.private_key: PrivateKey | None = None
        self.public_key: PublicKey | None = None
        self.peers: dict[str, PublicKey] = {}

    async def initialize(self) -> None:
        self.keys_dir.mkdir(exist_ok=True)

        private_key_path = self.keys_dir / "private.key"
        public_key_path = self.keys_dir / "public.key"

        if private_key_path.exists() and public_key_path.exists():
            self.private_key = PrivateKey(
                self._b64d(private_key_path.read_text()),
            )
            self.public_key = PublicKey(self._b64d(public_key_path.read_text()))
        else:
            self.private_key = PrivateKey.generate()
            self.public_key = self.private_key.public_key

            private_key_path.write_text(self._b64e(bytes(self.private_key)))
            public_key_path.write_text(self._b64e(bytes(self.public_key)))
        await self.read_peers()

    async def read_peers(self) -> None:
        raw = get_all_keys()
        self.peers = {
            peer_id: PublicKey(self._b64d(pub_key))
            for peer_id, pub_key in raw.items()
        }

    async def write_peers(self) -> None:
        add_all_keys(
            {
                peer_id: self._b64e(bytes(pub_key))
                for peer_id, pub_key in self.peers.items()
            },
        )

    async def add_peer(self, peer_id: str, public_key: str) -> None:
        self.peers[peer_id] = PublicKey(self._b64d(public_key))
        add_all_keys({peer_id: public_key})

    @staticmethod
    def _b64e(data: bytes) -> str:
        return base64.b64encode(data).decode("utf-8")

    @staticmethod
    def _b64d(data: str) -> bytes:
        return base64.b64decode(data.encode("utf-8"))

    async def encrypt_message_to(self, message: bytes, peer_id: str) -> bytes:
        box = Box(self.private_key, self.peers[peer_id])
        return cast("bytes", box.encrypt(message))

    async def decrypt_message_from(self, message: bytes, peer_id: str) -> bytes:
        box = Box(self.private_key, self.peers[peer_id])
        return cast("bytes", box.decrypt(message))


crypto = Crypto()
