"""
Модуль криптографии и хеширования паролей (PBKDF2-HMAC-SHA256).
"""
import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    """
    Хеширование пароля через PBKDF2-HMAC-SHA256 (100,000 итераций)
    с генерацией уникальной криптографической соли (16 байт).
    Возвращает строку в модульном формате crypt: pbkdf2_sha256$<iterations>$<salt>$<hash>.
    """
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    return f"pbkdf2_sha256$100000${salt}${derived.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """
    Проверка пароля через PBKDF2-HMAC-SHA256 по модульному формату crypt.
    Использует hmac.compare_digest для защиты от атак по времени (timing attacks).
    """
    if not hashed or not hashed.startswith("pbkdf2_sha256$"):
        return False
    parts = hashed.split("$")

    # Стандартный формат: pbkdf2_sha256$<iterations>$<salt>$<hash>
    if len(parts) == 4 and parts[0] == "pbkdf2_sha256":
        try:
            iterations = int(parts[1])
        except ValueError:
            return False
        salt = parts[2]
        expected_hash = parts[3]
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        return hmac.compare_digest(derived, expected_hash)

    return False
