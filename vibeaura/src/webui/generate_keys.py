from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import base64
import json
import logging

logger = logging.getLogger("jwks_logs")

KID = "main-key"

PRIVATE_KEY_OBJ = None
PUBLIC_KEY_OBJ = None
JWKS = None


def to_base64url(num):
    return base64.urlsafe_b64encode(num.to_bytes((num.bit_length() + 7) // 8, "big")) \
        .rstrip(b"=").decode("utf-8")


def generate_keys_in_memory():
    global PRIVATE_KEY_OBJ, PUBLIC_KEY_OBJ, JWKS

    logger.debug("[*] Generating new RSA key pair in memory...")

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    public_key = private_key.public_key()

    PRIVATE_KEY_OBJ = private_key
    PUBLIC_KEY_OBJ = public_key

    public_numbers = public_key.public_numbers()

    JWKS = {
        "keys": [
            {
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "kid": KID,
                "n": to_base64url(public_numbers.n),
                "e": to_base64url(public_numbers.e)
            }
        ]
    }

    logger.debug("[+] In-memory JWKS generated")
    logger.debug(f"[+] JWKS content: {json.dumps(JWKS, indent=2)}")


def get_private_pem() -> str:
    global PRIVATE_KEY_OBJ
    if PRIVATE_KEY_OBJ is None:
        generate_keys_in_memory()
    return PRIVATE_KEY_OBJ.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ).decode("utf-8")

def get_public_pem() -> str:
    global PUBLIC_KEY_OBJ
    if PUBLIC_KEY_OBJ is None:
        generate_keys_in_memory()
    return PUBLIC_KEY_OBJ.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("utf-8")


def get_jwks() -> dict:
    global JWKS
    if JWKS is None:
        generate_keys_in_memory()
    return JWKS