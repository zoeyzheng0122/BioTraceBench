"""Pure offline input checks. Uploads do not remove image or token limits."""
import base64
import struct
from .archive import Stop, encoded


def inventory(messages, files=None):
    images, text_bytes = [], 0
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            text_bytes += len(content.encode("utf-8")); continue
        for part in content or []:
            if part.get("type") == "text":
                text_bytes += len(part["text"].encode("utf-8"))
            elif part.get("type") == "image_url":
                url = part["image_url"]["url"]
                raw = base64.b64decode(url.split(",", 1)[1], validate=True)
                if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) < 24:
                    raise ValueError("Expected a frozen PNG image")
                w, h = struct.unpack(">II", raw[16:24])
                images.append({"width": w, "height": h, "bytes": len(raw), "inline": True,
                               "encoded_bytes": len(url.split(",", 1)[1])})
            elif part.get("type") == "file":
                meta = (files or {}).get(part["file_id"])
                if not meta or not {"width", "height", "bytes", "sha256"} <= set(meta):
                    raise ValueError("File image requires frozen dimensions, size and checksum")
                images.append({**meta, "inline": False, "encoded_bytes": 0})
    return {"images": images, "text_bytes": text_bytes}


def check(stats, limits, *, request_bytes=None):
    images = stats["images"]
    failures = []
    def bound(name, value):
        maximum = limits.get(name)
        if maximum is not None and value > maximum:
            failures.append({"limit": name, "actual": value, "maximum": maximum})
    bound("max_images", len(images))
    bound("max_total_image_bytes", sum(i["bytes"] for i in images))
    bound("max_inline_image_bytes", sum(i["bytes"] for i in images if i.get("inline", True)))
    if request_bytes is not None:
        bound("max_request_bytes", request_bytes)
    for im in images:
        bound("max_image_bytes", im["bytes"])
        bound("max_encoded_image_bytes", im.get("encoded_bytes", 0))
        bound("max_dimension", max(im["width"], im["height"]))
        if len(images) > limits.get("many_image_threshold", 10**12):
            bound("many_image_max_dimension", max(im["width"], im["height"]))
        if limits.get("min_dimension") is not None and min(im["width"], im["height"]) < limits["min_dimension"]:
            failures.append({"limit": "min_dimension", "actual": min(im["width"], im["height"]), "minimum": limits["min_dimension"]})
        bound("max_aspect_ratio", max(im["width"], im["height"]) / max(1, min(im["width"], im["height"])))
    return failures


def validate(limits):
    allowed = {"max_images", "max_total_image_bytes", "max_inline_image_bytes", "max_request_bytes",
               "max_image_bytes", "max_encoded_image_bytes", "max_dimension", "many_image_threshold",
               "many_image_max_dimension", "min_dimension", "max_aspect_ratio", "max_input_tokens",
               "provider_max_output_tokens", "output_accounting", "sources", "unknown", "retrieved_at"}
    if not isinstance(limits, dict) or set(limits) - allowed:
        raise ValueError("Unknown API limit field")
    for key, value in limits.items():
        if key.startswith(("max_", "min_", "many_", "provider_max_")) and value is not None:
            if type(value) is not int or value < 1:
                raise ValueError("API limits must be positive integers or explicitly unknown")
    return limits


def enforce(messages, config):
    limits = validate(config.get("api_limits", {}))
    stats = inventory(messages, config.get("file_metadata"))
    failures = check(stats, limits)
    if failures:
        raise Stop("paused_capacity", "Image limits exceeded: " + encoded(failures).decode())
    if config["max_output_tokens"] > limits.get("provider_max_output_tokens", config["max_output_tokens"]):
        raise Stop("paused_configuration", "Output budget exceeds the deployment's documented maximum")
    return stats
