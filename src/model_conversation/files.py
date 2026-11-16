"""One archived image upload, with explicit expiration and no automatic retries."""
import hashlib
import os
import re
import time
from pathlib import Path
from model_api.http import send
from model_api.backend import safe_response
from .archive import Stop, read, write, seal, verify, digest

ENDPOINT = "https://api.deepseek.com/files"


def upload(image, folder, *, expires_seconds=86400, sender=None):
    image, folder = Path(image), Path(folder)
    if expires_seconds != 86400:
        raise ValueError("DeepSeek test uploads require a 24-hour expiration")
    raw = image.read_bytes()
    if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) > 64 * 1024 * 1024:
        raise ValueError("Upload requires a frozen PNG no larger than 64 MiB")
    identity = hashlib.sha256(raw).hexdigest()
    request = {"endpoint": ENDPOINT, "source_sha256": identity, "bytes": len(raw),
               "filename": "image-" + identity + ".png", "purpose": "user_data",
               "expires_after": {"anchor": "created_at", "seconds": expires_seconds}}
    if folder.exists():
        verify(folder)
        if read(folder / "request.json") != request:
            raise Stop("tampered", "File upload identity changed")
        if not (folder / "response.bin").exists() or read(folder / "http.json")["status"] not in {200, 201}:
            raise Stop("paused_files", "Prior file upload is unresolved; no automatic retry")
        result = read(folder / "response.bin")
    else:
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise Stop("paused_account", "DEEPSEEK_API_KEY is required")
        boundary = "biotracebench-" + identity[:24]
        chunks = []
        for name, value in (("purpose", "user_data"), ("expires_after[anchor]", "created_at"),
                            ("expires_after[seconds]", str(expires_seconds))):
            chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode())
        chunks.extend([(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{request["filename"]}"\r\nContent-Type: image/png\r\n\r\n').encode(),
                       raw, (f"\r\n--{boundary}--\r\n").encode()])
        body = b"".join(chunks)
        folder.mkdir(parents=True)
        write(folder / "request.json", request)
        try:
            status, headers, response = (sender or send)(ENDPOINT, body,
                {"Authorization": "Bearer " + key, "Content-Type": "multipart/form-data; boundary=" + boundary}, 600)
        except Exception as exc:
            write(folder / "failure.json", {"status": "paused_unknown", "execution": "unknown", "error_type": type(exc).__name__})
            seal(folder)
            raise Stop("paused_files", "Upload interrupted; no automatic retry") from None
        (folder / "response.bin").write_bytes(safe_response(response, key))
        write(folder / "http.json", {"status": status, "body_sha256": hashlib.sha256(body).hexdigest()})
        seal(folder)
        if status not in {200, 201}:
            raise Stop("paused_files", "Upload HTTP " + str(status) + "; archived without retry")
        result = read(folder / "response.bin")
    if (not re.fullmatch(r"file-api-[A-Za-z0-9_-]+", result.get("id", ""))
            or result.get("bytes") != len(raw) or result.get("purpose") != "user_data"
            or type(result.get("expires_at")) is not int or type(result.get("created_at")) is not int
            or result["expires_at"] > result["created_at"] + expires_seconds + 60):
        raise Stop("paused_files", "Upload receipt has invalid identity, size or expiration")
    if result["expires_at"] <= time.time():
        raise Stop("paused_files", "Uploaded file expired; no automatic replacement")
    return {"file_id": result["id"], "expires_at": result["expires_at"],
            "sha256": identity, "bytes": len(raw), "upload_identity": digest(request)}
