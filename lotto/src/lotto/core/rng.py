import secrets
import hashlib
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms

NONCE = bytes(16)


@dataclass(frozen=True)
class DrawResult:
    seed_hex: str
    commitment: str
    numbers: list[int]

@dataclass(frozen=True)
class DrawCommitment:
    seed_hex: str
    commitment: str


def create_commitment() -> DrawCommitment:
    seed = secrets.token_bytes(32)

    return DrawCommitment(
        seed_hex=seed.hex(),
        commitment=hashlib.sha256(seed).hexdigest(),
    )

class DrawError(ValueError):
    pass


class ChaChaRng:
    def __init__(self, seed: bytes, nonce: bytes):
        self._encryptor = Cipher(algorithms.ChaCha20(seed, nonce), mode=None).encryptor()

    def randbytes(self, k: int) -> bytes:
        return self._encryptor.update(bytes(k))


def create_draw(k: int, max_number: int) -> DrawResult:
    seed = secrets.token_bytes(32)
    return DrawResult(
        seed_hex=seed.hex(),
        commitment=hashlib.sha256(seed).hexdigest(),
        numbers=draw(seed, k, max_number)
    )


def draw(seed: bytes, k: int, max_number: int) -> list[int]:
    if not 1 <= max_number <= 255:
        raise DrawError("max_number musi byc w zakresie 1-255")
    if not 1 <= k <= max_number:
        raise DrawError("k musi byc w zakresie 1-max_number")
    if len(seed) != 32:
        raise DrawError("seed musi miec 32 bajty")

    lotto_nums = []
    rng = ChaChaRng(seed, NONCE)
    mask = (1 << max_number.bit_length()) - 1

    while len(lotto_nums) < k:
        number = int.from_bytes(rng.randbytes(1), "big") & mask

        if 0 < number <= max_number and number not in lotto_nums:
            lotto_nums.append(number)

    return lotto_nums


def verify(commitment: str, seed_hex: str, k: int, max_number: int, result: list[int]) -> bool:
    try:
        seed = bytes.fromhex(seed_hex)
    except ValueError:
        raise DrawError("seed_hex nie jest poprawnym hexem") from None

    return hashlib.sha256(seed).hexdigest() == commitment and result == draw(seed, k, max_number)

