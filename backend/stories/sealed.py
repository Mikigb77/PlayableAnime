"""A file sealed for one reader: only the holder of the private key can open it.

The owner's own stories leave the server this way (`stories.owner_export`, T16), because the
repository is public and so is everything its Actions print. The reader makes a key pair, hands
over the public key and opens what comes back with the private one, which never leaves their
machine:

    uv run python -m stories.sealed keygen reader.key              # prints the public key
    uv run python -m stories.sealed open reader.key export.bin export.json

The file is `MAGIC`, the sender's one-time X25519 public key (32 bytes) and a nonce (12 bytes),
then the gzipped content under ChaCha20-Poly1305, keyed by HKDF-SHA256 of the X25519 shared
secret. No Django here: the reader needs only this file and `cryptography`.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import gzip
import os
import re
import sys
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from cryptography.hazmat.primitives.serialization import PublicFormat as Public

MAGIC = b"LSX1"
_KEY_BYTES = 32
_NONCE_BYTES = 12
_INFO = b"lucid-saga sealed file v1"
# 32 bytes as URL-safe base64 without padding: safe in a command line, a URL and a form field.
_KEY_TEXT = re.compile(r"^[A-Za-z0-9_-]{43}$")


class SealError(ValueError):
    """The key isn't one, or the file can't be opened with it."""


def key_text(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).rstrip(b"=").decode("ascii")


def parse_key(text: str) -> bytes:
    """The 32 bytes of a key written as `key_text` writes it."""
    text = text.strip()
    if not _KEY_TEXT.match(text):
        raise SealError("A key is 43 characters of URL-safe base64, without padding.")
    try:
        key = base64.urlsafe_b64decode(text + "=")
    except (binascii.Error, ValueError) as error:
        raise SealError("The key isn't valid base64.") from error
    if len(key) != _KEY_BYTES:
        raise SealError("A key is 32 bytes.")
    return key


def new_private_key() -> bytes:
    return X25519PrivateKey.generate().private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    )


def public_key(private_key: bytes) -> bytes:
    return (
        X25519PrivateKey.from_private_bytes(private_key)
        .public_key()
        .public_bytes(Encoding.Raw, Public.Raw)
    )


def _cipher(shared: bytes, sender: bytes, recipient: bytes) -> ChaCha20Poly1305:
    key = HKDF(
        algorithm=hashes.SHA256(), length=_KEY_BYTES, salt=sender + recipient, info=_INFO
    ).derive(shared)
    return ChaCha20Poly1305(key)


def seal(content: bytes, recipient: bytes) -> bytes:
    """`content`, gzipped and encrypted so that only `recipient`'s private key opens it."""
    if len(recipient) != _KEY_BYTES:
        raise SealError("A key is 32 bytes.")
    sender = X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(Encoding.Raw, Public.Raw)
    try:
        shared = sender.exchange(X25519PublicKey.from_public_bytes(recipient))
    except ValueError as error:
        raise SealError("The key can't be used to seal a file.") from error
    nonce = os.urandom(_NONCE_BYTES)
    sealed = _cipher(shared, sender_public, recipient).encrypt(
        nonce, gzip.compress(content, mtime=0), MAGIC
    )
    return MAGIC + sender_public + nonce + sealed


def unseal(sealed: bytes, private_key: bytes) -> bytes:
    """What `seal` was given, or `SealError` when the file is damaged or meant for another key."""
    head = len(MAGIC) + _KEY_BYTES + _NONCE_BYTES
    if len(sealed) <= head or not sealed.startswith(MAGIC):
        raise SealError("This isn't a sealed file.")
    sender_public = sealed[len(MAGIC) : len(MAGIC) + _KEY_BYTES]
    nonce = sealed[len(MAGIC) + _KEY_BYTES : head]
    try:
        reader = X25519PrivateKey.from_private_bytes(private_key)
        shared = reader.exchange(X25519PublicKey.from_public_bytes(sender_public))
        content = _cipher(shared, sender_public, public_key(private_key)).decrypt(
            nonce, sealed[head:], MAGIC
        )
    except (InvalidTag, ValueError) as error:
        raise SealError("The file can't be opened with this key.") from error
    return gzip.decompress(content)


def _keygen(path: Path) -> None:
    private_key = new_private_key()
    # Made for its owner only, and never over an existing key.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write(key_text(private_key) + "\n")
    print(key_text(public_key(private_key)))


def _open(key_path: Path, sealed_path: Path, out_path: Path) -> None:
    content = unseal(sealed_path.read_bytes(), parse_key(key_path.read_text()))
    descriptor = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        file.write(content)
    print(f"Opened {len(content)} bytes into {out_path}.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m stories.sealed", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    keygen = commands.add_parser(
        "keygen", help="Make a key pair: the private key into a new file, the public key printed."
    )
    keygen.add_argument("key_file", type=Path)
    opener = commands.add_parser("open", help="Open a sealed file with the private key.")
    opener.add_argument("key_file", type=Path)
    opener.add_argument("sealed_file", type=Path)
    opener.add_argument("out_file", type=Path)
    options = parser.parse_args(argv)
    try:
        if options.command == "keygen":
            _keygen(options.key_file)
        else:
            _open(options.key_file, options.sealed_file, options.out_file)
    except (SealError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
