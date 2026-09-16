"""Track A 구현 대상: 비밀번호 해싱(bcrypt) + JWT 발급/검증(python-jose).

JWT payload는 api-spec.md §1.1 기준: {"sub": <User.id>, "email": <User.email>}
"""


def hash_password(plain_password: str) -> str:
    raise NotImplementedError  # TODO: bcrypt로 해싱


def verify_password(plain_password: str, password_hash: str) -> bool:
    raise NotImplementedError  # TODO: bcrypt 비교


def create_access_token(user_id: str, email: str) -> str:
    raise NotImplementedError  # TODO: jose.jwt.encode({"sub": user_id, "email": email}, ...)


def decode_access_token(token: str) -> dict:
    raise NotImplementedError  # TODO: jose.jwt.decode, 실패 시 AppError(401, "UNAUTHORIZED", ...)
