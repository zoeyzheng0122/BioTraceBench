"""Offline text token counts and explicit conservative image/framing reserves."""
from functools import lru_cache
from pathlib import Path
import importlib.metadata
from .archive import Stop, sha, digest, read, write, seal, verify, encoded


@lru_cache(maxsize=2)
def tokenizer(path, identity):
    if sha(path) != identity:
        raise Stop("tampered", "Local tokenizer checksum changed")
    try:
        from tokenizers import Tokenizer
    except ImportError:
        raise Stop("blocked_dependency", "Local counting requires tokenizers==0.22.1") from None
    if importlib.metadata.version("tokenizers") != "0.22.1":
        raise Stop("changed_runtime", "Local counting requires tokenizers==0.22.1")
    result = Tokenizer.from_file(path)
    result.no_truncation()
    result.no_padding()
    return result


def count(body, policy):
    path = str(Path(policy["path"]).resolve())
    # Verify on every physical estimate, including when the tokenizer is cached.
    if sha(path) != policy["sha256"]:
        raise Stop("tampered", "Local tokenizer checksum changed")
    encoder = tokenizer(path, policy["sha256"])
    texts, images = [], 0
    for message in body["messages"]:
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for part in content:
                if part["type"] == "text":
                    texts.append(part["text"])
                elif part["type"] in {"image_url", "file"}:
                    images += 1
        if message.get("reasoning_content"):
            texts.append(message["reasoning_content"])
        if message.get("tool_calls"):
            texts.append(encoded(message["tool_calls"]).decode())
    for key in ("tools", "response_format"):
        if key in body:
            texts.append(encoded(body[key]).decode())
    text_tokens = sum(len(encoder.encode(text, add_special_tokens=False).ids) for text in texts)
    image_tokens = images * policy["image_token_upper"]
    return {"total_tokens": text_tokens + image_tokens, "text_tokens": text_tokens,
            "image_count": images, "image_token_upper": policy["image_token_upper"],
            "reserved_input_tokens": text_tokens + image_tokens + policy["reserve_tokens"],
            "reserve_tokens": policy["reserve_tokens"], "kind": "local_tokenizer_upper_bound",
            "tokenizer_sha256": policy["sha256"], "tokenizers_version": "0.22.1"}


def estimate(body, policy, folder, offline=False):
    folder = Path(folder)
    request = {"request_identity": digest(body), "policy": policy}
    if folder.exists():
        verify(folder)
        if read(folder / "request.json") != request:
            raise Stop("tampered", "Local token estimate identity changed")
        return read(folder / "result.json")
    if offline:
        raise Stop("offline_missing", "No archived local token count")
    result = count(body, policy)
    folder.mkdir(parents=True)
    write(folder / "request.json", request)
    write(folder / "result.json", result)
    seal(folder)
    return result
