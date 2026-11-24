"""Local content-addressed evidence storage for synthetic fixtures.

Clients never supply paths. Objects are stored under <root>/<mission_id>/<sha256> and resolved
with a containment check. A future object store would implement the same two methods.
"""

import hashlib
from pathlib import Path
from uuid import UUID

from backend.core.errors import NotFound, Unprocessable


class LocalEvidenceStore:
    def __init__(self, root: Path, max_bytes: int, media_types: tuple[str, ...]) -> None:
        self.root = root.resolve()
        self.max_bytes = max_bytes
        self.media_types = frozenset(media_types)

    def _path(self, storage_key: str) -> Path:
        parts = storage_key.split("/")
        if len(parts) != 2:
            raise NotFound("evidence object not found")
        mission, digest = parts
        try:
            UUID(mission)
        except ValueError as exc:
            raise NotFound("evidence object not found") from exc
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise NotFound("evidence object not found")
        path = (self.root / mission / digest).resolve()
        if not path.is_relative_to(self.root):
            raise NotFound("evidence object not found")
        return path

    def put(self, mission_id: UUID, data: bytes, media_type: str) -> tuple[str, str, int]:
        if media_type not in self.media_types:
            raise Unprocessable("unsupported media type", code="unsupported_media_type")
        if not data:
            raise Unprocessable("empty evidence object", code="empty_object")
        if len(data) > self.max_bytes:
            raise Unprocessable("evidence object too large", code="object_too_large")
        digest = hashlib.sha256(data).hexdigest()
        key = f"{mission_id}/{digest}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return key, digest, len(data)

    def read(self, storage_key: str) -> bytes:
        path = self._path(storage_key)
        if not path.is_file():
            raise NotFound("evidence object not found")
        return path.read_bytes()
