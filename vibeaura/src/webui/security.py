import jwt, requests
from datetime import datetime, timedelta, timezone
import logging
import generate_keys

logger = logging.getLogger("my_app")

VERIFY_ALLOWED_ALGOS = ["RS256"]


def generate_jwt_token(payload_data: dict, expiration_minutes: int = 30) -> str:

    private_pem = generate_keys.get_private_pem()
    payload = dict(payload_data)
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=expiration_minutes)

    token = jwt.encode(payload, private_pem, algorithm="RS256")
    logger.debug("Generated RS256 token")
    return token


def verify_token(token: str):
    try:
        logger.debug(f"Token to validate: {token}")
        unverified_header = jwt.get_unverified_header(token)

        alg = unverified_header.get("alg", "").upper()
        jku_url = unverified_header.get("jku")
        logger.debug(f"Token header alg: {alg}, jku: {jku_url}")

        public_pem = generate_keys.get_public_pem()

        decoded = jwt.decode(token, key=public_pem, algorithms=VERIFY_ALLOWED_ALGOS)
        logger.debug(f"Decoded payload: {decoded}")

        uid = decoded.get("user_id")
        if uid is None:
            logger.error("Token payload missing user_id")
            return False, "Invalid token payload"
        
        username = decoded.get("username")
        if username is None:
            logger.error("Token payload missing username")
            return False, "Invalid token payload"

        return True, username

    except jwt.ExpiredSignatureError as e:
        logger.error(f"Token expired: {e}")
        return False, "Token has expired"
    except jwt.InvalidKeyError as e:
        logger.error(f"Invalid Key: {e}")
        return False, "Invalid Key"
    except jwt.InvalidTokenError as e:
        logger.error(f"Invalid token: {e}")
        return False, "Invalid token"
    except Exception as e:
        logger.error(f"Unexpected token error: {e}")
        return False, f"Token verification failed: {str(e)}"