"""SSE assembly preserving native reasoning, signatures, usage and incomplete streams."""
import copy
import json
import http.client
import time
from urllib.parse import urlsplit
from .archive import Stop


class Interrupted(OSError):
    def __init__(self, raw, status, headers):
        super().__init__("Stream interrupted")
        self.raw, self.status, self.headers = raw, status, headers


def send(url, body, headers, timeout):
    target = urlsplit(url)
    google_sse = target.hostname == "generativelanguage.googleapis.com" and target.path.endswith(":streamGenerateContent") and target.query == "alt=sse"
    if target.scheme != "https" or (target.query and not google_sse) or target.username or target.password:
        raise ValueError("Credential-free HTTPS stream endpoint required")
    connection = http.client.HTTPSConnection(target.hostname, port=target.port, timeout=timeout)
    deadline, pieces, status, response_headers = time.monotonic() + timeout, [], None, {}
    def remaining():
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("Stream deadline exceeded")
        return left
    try:
        connection.connect(); socket = connection.sock
        socket.settimeout(remaining())
        connection.request("POST", target.path + ("?" + target.query if target.query else ""), body=body, headers=headers)
        socket.settimeout(remaining())
        response = connection.getresponse(); status = response.status; response_headers = dict(response.getheaders())
        while True:
            socket.settimeout(remaining())
            piece = response.read1(65536)
            if not piece:
                break
            pieces.append(piece)
        return status, response_headers, b"".join(pieces)
    except (OSError, http.client.HTTPException):
        raise Interrupted(b"".join(pieces), status, response_headers) from None
    finally:
        connection.close()


def decode(raw, protocol):
    if raw.lstrip().startswith(b"{"):
        return json.loads(raw)
    events = []
    try:
        for block in raw.decode("utf-8").replace("\r\n", "\n").split("\n\n"):
            data = "\n".join(s[5:].lstrip() for s in block.splitlines() if s.startswith("data:"))
            if data and data != "[DONE]":
                events.append(json.loads(data))
    except (ValueError, UnicodeError):
        raise Stop("paused_unknown", "Incomplete or invalid SSE archive; no automatic retry") from None
    if protocol == "responses":
        terminal = [e.get("response") for e in events if e.get("type") in {"response.completed", "response.incomplete"}]
        if terminal:
            return terminal[-1]
    elif protocol == "anthropic":
        result, blocks, inputs, finished = None, {}, {}, False
        for event in events:
            kind = event.get("type")
            if kind == "message_start":
                result = copy.deepcopy(event["message"])
            elif kind == "content_block_start":
                blocks[event["index"]] = copy.deepcopy(event["content_block"])
            elif kind == "content_block_delta":
                index, delta = event["index"], event["delta"]
                if index not in blocks:
                    raise Stop("paused_unknown", "SSE block has no start")
                for field in ("text", "thinking", "signature"):
                    if field in delta:
                        blocks[index][field] = blocks[index].get(field, "") + delta[field]
                if "partial_json" in delta:
                    inputs[index] = inputs.get(index, "") + delta["partial_json"]
            elif kind == "message_delta" and result is not None:
                result.update(event.get("delta", {})); result.setdefault("usage", {}).update(event.get("usage", {}))
            elif kind == "message_stop":
                finished = True
        if finished and result is not None:
            for index, value in inputs.items():
                blocks[index]["input"] = json.loads(value)
            result["content"] = [blocks[n] for n in sorted(blocks)]
            return result
    elif protocol == "chat_completions":
        result, message, calls, finished = {}, {"role": "assistant", "content": ""}, {}, False
        for event in events:
            for key in ("id", "model", "usage"):
                if event.get(key) is not None:
                    result[key] = event[key]
            for choice in event.get("choices", []):
                if choice.get("index", 0) != 0:
                    raise Stop("failed_response", "Only one streamed candidate is supported")
                delta = choice.get("delta", {})
                for key, value in delta.items():
                    if key == "tool_calls":
                        for item in value:
                            call = calls.setdefault(item["index"], {"type": "function", "function": {"name": "", "arguments": ""}})
                            if item.get("id"):
                                call["id"] = item["id"]
                            for field, piece in item.get("function", {}).items():
                                call["function"][field] = call["function"].get(field, "") + piece
                    elif isinstance(value, str) and key != "role":
                        message[key] = message.get(key, "") + value
                    elif value is not None:
                        message[key] = value
                if choice.get("finish_reason"):
                    result["choices"] = [{"message": message, "finish_reason": choice["finish_reason"]}]; finished = True
        if finished:
            if calls:
                message["tool_calls"] = [calls[n] for n in sorted(calls)]
            return result
    elif protocol == "gemini":
        result, parts, finished = {}, [], False
        for event in events:
            result.update({k: v for k, v in event.items() if k != "candidates"})
            for candidate in event.get("candidates", []):
                parts.extend(candidate.get("content", {}).get("parts", []))
                if candidate.get("finishReason"):
                    result["candidates"] = [{**candidate, "content": {"role": "model", "parts": parts}}]; finished = True
        if finished:
            return result
    raise Stop("paused_unknown", "Stream lacks a terminal response; consumption remains unknown")
