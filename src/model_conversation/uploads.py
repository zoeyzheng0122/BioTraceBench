"""Explicit native PNG uploads; reusable receipts bind provider and content."""
import hashlib
import datetime
import os
import struct
import time
from pathlib import Path
from .archive import Stop, encoded, digest, sha, read, write, seal, verify
from model_api.http import send
from model_api.backend import safe_response


def upload_image(provider, image, folder, *, sender=None):
    if provider not in {"deepseek", "openai", "anthropic", "gemini"}:
        raise ValueError("No verified native image upload for this provider")
    image, folder = Path(image), Path(folder)
    raw = image.read_bytes()
    if len(raw) < 24 or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Frozen PNG required")
    width, height = struct.unpack(">II", raw[16:24]); identity = sha(image)
    if provider == "deepseek":
        from .files import upload
        receipt = upload(image, folder, sender=sender)
        return {**receipt, "provider": provider, "width": width, "height": height}
    endpoint, env = {"openai": ("https://api.openai.com/v1/files", "OPENAI_API_KEY"),
                     "anthropic": ("https://api.anthropic.com/v1/files", "ANTHROPIC_API_KEY"),
                     "gemini": ("https://generativelanguage.googleapis.com/upload/v1beta/files", "GEMINI_API_KEY")}[provider]
    request = {"provider": provider, "endpoint": endpoint, "source_sha256": identity,
               "bytes": len(raw), "width": width, "height": height, "mime": "image/png"}
    if folder.exists():
        verify(folder)
        if read(folder / "request.json") != request:
            raise Stop("tampered", "Upload content/provider identity changed")
        if not (folder / "response.bin").exists() or read(folder / "http.json")["status"] not in {200, 201}:
            raise Stop("paused_files", "Unresolved upload; no automatic resubmission")
        response = read(folder / "response.bin")
    else:
        key = os.environ.get(env)
        if not key or any(ord(c) < 32 for c in key):
            raise Stop("paused_account", env + " is absent or invalid")
        boundary = "biotracebench-" + identity[:24]
        headers = {"Content-Type": "multipart/form-data; boundary=" + boundary}
        pieces = []
        if provider == "openai":
            headers["Authorization"] = "Bearer " + key
            for name, value in (("purpose", "user_data"), ("expires_after[anchor]", "created_at"), ("expires_after[seconds]", "86400")):
                pieces.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        elif provider == "anthropic":
            headers.update({"x-api-key": key, "anthropic-version": "2023-06-01", "anthropic-beta": "files-api-2025-04-14"})
        else:
            headers.update({"x-goog-api-key": key, "X-Goog-Upload-Protocol": "multipart",
                            "Content-Type": "multipart/related; boundary=" + boundary})
            pieces.append(f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode() + encoded({"file": {"display_name": identity + ".png"}}) + b"\r\n")
        disposition = "" if provider == "gemini" else f'Content-Disposition: form-data; name="file"; filename="{identity}.png"\r\n'
        pieces.extend([f'--{boundary}\r\n{disposition}Content-Type: image/png\r\n\r\n'.encode(), raw, f'\r\n--{boundary}--\r\n'.encode()])
        folder.mkdir(parents=True); write(folder / "request.json", request)
        try:
            status, _, data = (sender or send)(endpoint, b"".join(pieces), headers, 900)
        except (OSError, TimeoutError):
            write(folder / "failure.json", {"status": "paused_unknown"}); seal(folder)
            raise Stop("paused_files", "Upload interrupted; no automatic retry") from None
        (folder / "response.bin").write_bytes(safe_response(data, key))
        write(folder / "http.json", {"status": status, "body_sha256": hashlib.sha256(b"".join(pieces)).hexdigest()})
        seal(folder)
        if status not in {200, 201}:
            raise Stop("paused_files", "Upload HTTP " + str(status))
        response = read(folder / "response.bin")
    file = response.get("file", response)
    size = file.get("sizeBytes") if provider == "gemini" else file.get("size_bytes", file.get("bytes"))
    if str(size) != str(len(raw)) or file.get("mimeType", file.get("mime_type", "image/png")) != "image/png":
        raise Stop("paused_files", "Upload receipt size or type mismatch")
    file_id = file.get("uri") if provider == "gemini" else file.get("id")
    if not isinstance(file_id, str) or not file_id:
        raise Stop("paused_files", "Upload receipt has no native file identity")
    expiry = file.get("expires_at")
    if provider == "gemini" and file.get("expirationTime"):
        expiry = int(datetime.datetime.fromisoformat(file["expirationTime"].replace("Z", "+00:00")).timestamp())
    if provider != "anthropic" and (type(expiry) is not int or expiry <= time.time()):
        raise Stop("paused_files", "Upload expiration is absent or expired")
    return {"provider": provider, "file_id": file_id, "sha256": identity, "bytes": len(raw),
            "width": width, "height": height, "expires_at": expiry,
            "expiry_policy": "provider_persistent" if provider == "anthropic" else "provider_expiry"}
