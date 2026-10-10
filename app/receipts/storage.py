"""영수증 파일 저장 추상화.

DB에는 공개 URL이 아니라 storage key만 저장한다. 이후 S3 구현체로 교체할 때
Receipt 서비스의 계약을 바꾸지 않도록 파일 저장 책임을 별도 모듈에 둔다.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import uuid


@dataclass(frozen=True)
class StoredFile:
    key: str
    path: Path
    media_type: str


class FileStorage(Protocol):
    def save(
        self, user_id: uuid.UUID, content: bytes, media_type: str, extension: str
    ) -> StoredFile: ...

    def delete(self, key: str) -> None: ...

    def read(self, key: str) -> bytes: ...


class LocalFileStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def save(
        self, user_id: uuid.UUID, content: bytes, media_type: str, extension: str
    ) -> StoredFile:
        directory = self.root / "receipts" / str(user_id)
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4()}.{extension}"
        path = directory / filename
        with path.open("xb") as output:
            output.write(content)
        return StoredFile(
            key=path.relative_to(self.root).as_posix(),
            path=path,
            media_type=media_type,
        )

    def delete(self, key: str) -> None:
        root = self.root.resolve()
        path = (self.root / key).resolve()
        if path != root and root not in path.parents:
            raise OSError("storage key escapes storage root")
        if path.exists():
            path.unlink()

    def read(self, key: str) -> bytes:
        root = self.root.resolve()
        path = (self.root / key).resolve()
        if path != root and root not in path.parents:
            raise OSError("storage key escapes storage root")
        return path.read_bytes()


class S3FileStorage:
    def __init__(self, bucket: str, region: str):
        import boto3

        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region)

    def save(self, user_id: uuid.UUID, content: bytes, media_type: str, extension: str) -> StoredFile:
        key = f"receipts/{user_id}/{uuid.uuid4()}.{extension}"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=media_type)
        return StoredFile(key=key, path=Path(key), media_type=media_type)

    def read(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def presigned_url(self, key: str, expires_in: int = 300) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_in
        )

