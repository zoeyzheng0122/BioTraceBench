"""Wire protocols for the task conversation contract; no network or task logic.

Internal turns use role/content/tool_calls and an opaque `_native` continuation.
Only the adapter that created a continuation may replay it. No reasoning block,
thought signature or response output item is reconstructed from final text.
"""
import copy
import json
from urllib.parse import urlsplit

from .archive import Stop, encoded
from .structured import format_schema

PROTOCOLS = {"chat_completions", "responses", "anthropic", "gemini"}
PROVIDERS = {"kimi": "MOONSHOT_API_KEY", "openai": "OPENAI_API_KEY",
             "anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY",
             "qwen": "DASHSCOPE_API_KEY", "zhipu": "ZHIPU_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "xai": "XAI_API_KEY", "doubao": "ARK_API_KEY"}


def validate_generation(config):
    """Validate supported wire parameters without coercion or model defaults.

    Deployment-specific capability checks still belong to model acceptance.
    In particular, Gemini's -1 and 0 budgets are distinct documented controls.
    """
    protocol = config.get("protocol", "chat_completions")
    allowed = {"chat_completions": {"reasoning_effort", "thinking", "enable_thinking", "temperature", "top_p"},
               "responses": {"reasoning", "temperature", "top_p"}, "anthropic": {"thinking", "output_config"},
               "gemini": {"thinkingConfig"}}
    generation = config.get("generation", {})
    if protocol not in allowed or not isinstance(generation, dict):
        raise ValueError("generation: expected an object for a supported protocol")
    unknown = set(generation) - allowed[protocol]
    if unknown:
        raise ValueError("generation." + sorted(unknown)[0] + ": unsupported parameter for " + protocol)

    def object_value(name, keys):
        value = generation[name]
        if not isinstance(value, dict):
            raise ValueError("generation." + name + ": expected an object")
        extra = set(value) - keys
        if extra:
            raise ValueError("generation." + name + "." + sorted(extra)[0] + ": unsupported field")
        return value

    def choice(path, value, choices):
        if not isinstance(value, str) or value not in choices:
            raise ValueError(path + ": expected one of " + ", ".join(sorted(choices)))

    efforts = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
    if "reasoning_effort" in generation:
        choice("generation.reasoning_effort", generation["reasoning_effort"], efforts)
    for name in ("temperature", "top_p"):
        if name in generation and (type(generation[name]) not in {int, float} or not 0 <= generation[name] <= (2 if name == "temperature" else 1)):
            raise ValueError("Invalid sampling parameter: " + name)
    if "enable_thinking" in generation and type(generation["enable_thinking"]) is not bool:
        raise ValueError("generation.enable_thinking: expected a boolean")
    if "reasoning" in generation:
        value = object_value("reasoning", {"effort"})
        if "effort" in value:
            choice("generation.reasoning.effort", value["effort"], efforts)
    if "thinking" in generation:
        anthropic = protocol == "anthropic"
        value = object_value("thinking", {"type", "budget_tokens"} if anthropic else {"type", "clear_thinking"})
        modes = {"enabled", "disabled", "adaptive"}
        if config.get("provider") == "zhipu":
            modes = {"enabled", "disabled"}
        choice("generation.thinking.type", value.get("type"), modes)
        if "clear_thinking" in value and type(value["clear_thinking"]) is not bool:
            raise ValueError("generation.thinking.clear_thinking must be boolean")
        if anthropic and value["type"] == "enabled":
            budget = value.get("budget_tokens")
            if type(budget) is not int or budget < 1024:
                raise ValueError("generation.thinking.budget_tokens: expected an integer >= 1024")
            maximum = config.get("max_output_tokens")
            if type(maximum) is int and budget >= maximum:
                raise ValueError("generation.thinking.budget_tokens: must be less than max_output_tokens")
        elif "budget_tokens" in value:
            raise ValueError("generation.thinking.budget_tokens: only valid with thinking.type=enabled")
    if "output_config" in generation:
        value = object_value("output_config", {"effort"})
        if "effort" in value:
            choice("generation.output_config.effort", value["effort"], {"low", "medium", "high", "xhigh", "max"})
    if "thinkingConfig" in generation:
        value = object_value("thinkingConfig", {"includeThoughts", "thinkingBudget", "thinkingLevel"})
        if "includeThoughts" in value and type(value["includeThoughts"]) is not bool:
            raise ValueError("generation.thinkingConfig.includeThoughts: expected a boolean")
        if "thinkingBudget" in value and (type(value["thinkingBudget"]) is not int or value["thinkingBudget"] < -1):
            raise ValueError("generation.thinkingConfig.thinkingBudget: expected an integer >= -1")
        if "thinkingLevel" in value:
            levels = {"minimal", "low", "medium", "high", "MINIMAL", "LOW", "MEDIUM", "HIGH", "THINKING_LEVEL_UNSPECIFIED"}
            choice("generation.thinkingConfig.thinkingLevel", value["thinkingLevel"], levels)
        if "thinkingBudget" in value and "thinkingLevel" in value:
            raise ValueError("generation.thinkingConfig: thinkingBudget and thinkingLevel are mutually exclusive")


def profile(config):
    """Retain the original Kimi draft shape; new profiles are fully explicit."""
    c = copy.deepcopy(config)
    legacy = "protocol" not in c
    if legacy:
        if c.get("endpoint") != "https://api.moonshot.cn/v1/chat/completions" or c.get("model") != "kimi-k3" or c.get("reasoning_effort") != "high":
            raise ValueError("Legacy profile is only valid for the original Kimi K3 configuration")
        c.update(provider="kimi", protocol="chat_completions", key_env="MOONSHOT_API_KEY",
                 generation={"reasoning_effort": "high"}, output_token_field="max_completion_tokens",
                 capabilities={"vision": True, "tools": True, "json_object": True},
                 estimator={"kind": "kimi", "endpoint": "https://api.moonshot.cn/v1/tokenizers/estimate-token-count"},
                 accepted_response_models=["kimi-k3"])
    allowed = {"api_limits", "deployment", "stream", "file_metadata", "billable_output_token_upper", "provider", "protocol", "key_env", "endpoint", "model", "timeout", "retries",
               "context_tokens", "max_output_tokens", "max_request_bytes", "generation", "capabilities",
               "estimator", "accepted_response_models", "output_token_field", "api_version", "reasoning_effort", "tool_choice", "response_format", "execution_mode", "output_schema", "file_expiries"}
    if set(c) - allowed:
        raise ValueError("Unknown model profile fields")
    if c.get("provider") not in PROVIDERS or c.get("protocol") not in PROTOCOLS:
        raise ValueError("Explicit supported provider and wire protocol required")
    if c.get("provider") == "deepseek" and (c.get("protocol") != "chat_completions" or c.get("endpoint") != "https://api.deepseek.com/chat/completions"):
        raise ValueError("DeepSeek requires its explicit Chat Completions endpoint")
    if "file_expiries" in c and (c["provider"] not in {"deepseek", "openai", "anthropic", "gemini"} or not isinstance(c["file_expiries"], dict)
            or any(type(v) is not int for v in c["file_expiries"].values())):
        raise ValueError("File references require DeepSeek expiration records")
    if c.get("key_env") != PROVIDERS[c["provider"]]:
        raise ValueError("Use the provider's environment variable; never embed credentials")
    endpoint = urlsplit(c.get("endpoint") or "")
    if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
        raise ValueError("An HTTPS endpoint without embedded credentials/query is required")
    identities = c.get("accepted_response_models")
    if not isinstance(c.get("model"), str) or not c["model"] or not isinstance(identities, list) or not identities or any(not isinstance(x, str) or not x or "*" in x for x in identities):
        raise ValueError("Select a concrete model and explicit accepted response identities")
    for bound in ("context_tokens", "max_output_tokens", "max_request_bytes"):
        if type(c.get(bound)) is not int or c[bound] < 1:
            raise ValueError("Complete positive model bounds required: " + bound)
    if c["max_output_tokens"] >= c["context_tokens"]:
        raise ValueError("Output reserve must fit context")
    if "billable_output_token_upper" in c and (type(c["billable_output_token_upper"]) is not int or c["billable_output_token_upper"] < c["max_output_tokens"]):
        raise ValueError("Billable output upper bound must include the answer and separately billed reasoning")
    if (type(c.get("timeout")) is not int or not 1 <= c["timeout"] <= 3600 or c.get("retries") != 0):
        raise ValueError("Explicit timeout of 1-3600 seconds and zero retries required")
    caps = c.get("capabilities", {})
    if not {"vision", "tools", "json_object"} <= set(caps) or set(caps) - {"vision", "tools", "json_object", "json_schema"} or any(type(v) is not bool for v in caps.values()):
        raise ValueError("Explicit boolean vision/tools/JSON capabilities required")
    if "output_schema" in c:
        if not caps.get("json_schema") or c.get("execution_mode") != "final":
            raise ValueError("Output schema requires declared capability and final mode")
        format_schema(c["output_schema"])
    if "generation" not in c:
        raise ValueError("generation: an explicit object is required")
    validate_generation(c)
    if c["model"] == "gemini-3.8-flash" and c["generation"].get("thinkingConfig", {}).get("thinkingLevel", "").lower() == "minimal":
        raise ValueError("Gemini 3.8 Flash does not support minimal thinking")
    if c["model"] == "glm-5.3-flash" and c["generation"].get("thinking", {}).get("type") != "enabled":
        raise ValueError("GLM 5.3 Flash requires thinking enabled")
    if c["provider"] == "kimi":
        if c["protocol"] != "chat_completions" or c["endpoint"] != "https://api.moonshot.cn/v1/chat/completions" or c["model"] not in {"kimi-k3", "kimi-k3.1-pro"}:
            raise ValueError("Select an explicitly supported China Kimi deployment")
        if c["model"] == "kimi-k3.1-pro" and c["generation"].get("reasoning_effort") not in {"low", "high", "max"}:
            raise ValueError("Kimi K3.1 Pro requires an explicit supported reasoning effort")
        if c["model"] == "kimi-k3.1-pro" and c["generation"].get("thinking", {}).get("type", "enabled") != "enabled":
            raise ValueError("Kimi K3.1 Pro always enables thinking")
    if "file_metadata" in c:
        if c["provider"] not in {"deepseek", "openai", "anthropic", "gemini"} or not isinstance(c["file_metadata"], dict):
            raise ValueError("No verified native image file transport for this provider")
        for identifier, meta in c["file_metadata"].items():
            if (not isinstance(identifier, str) or not identifier or meta.get("provider") != c["provider"]
                    or any(type(meta.get(k)) is not int or meta[k] < 1 for k in ("width", "height", "bytes"))
                    or not isinstance(meta.get("sha256"), str) or len(meta["sha256"]) != 64):
                raise ValueError("File metadata requires matching provider, dimensions, bytes and SHA-256")
            if meta.get("expiry_policy") == "provider_persistent" and c["provider"] != "anthropic":
                raise ValueError("Only the verified Anthropic transport uses persistent files")
    if "api_limits" in c:
        from .input_limits import validate
        validate(c["api_limits"])
    if "stream" in c and type(c["stream"]) is not bool:
        raise ValueError("stream must be boolean")
    if c["protocol"] == "chat_completions" and c.get("output_token_field") not in {"max_tokens", "max_completion_tokens"}:
        raise ValueError("Explicit output token field required")
    if c["protocol"] == "anthropic" and not c.get("api_version"):
        raise ValueError("Anthropic API version required")
    if c["protocol"] == "gemini" and not c["endpoint"].endswith("/" + c["model"] + ":generateContent"):
        raise ValueError("Gemini endpoint and selected model disagree")
    if "tool_choice" in c or "response_format" in c:
        if c["protocol"] != "chat_completions":
            raise ValueError("Explicit acceptance controls currently require Chat Completions")
        if c.get("tool_choice", "auto") not in {"auto", "required", "none"}:
            raise ValueError("Invalid tool choice")
        if c.get("response_format", "json_object") not in {"text", "json_object"}:
            raise ValueError("Invalid response format")
        if c.get("response_format") == "json_object" and not c["capabilities"]["json_object"]:
            raise ValueError("JSON mode is not supported by selected profile")
    if c.get("execution_mode") not in {None, "reading", "tool_query", "final", "continuation"}:
        raise ValueError("Invalid execution mode")
    est = c.get("estimator", {})
    if est.get("kind") == "kimi":
        if c["provider"] != "kimi" or est.get("endpoint") != "https://api.moonshot.cn/v1/tokenizers/estimate-token-count":
            raise ValueError("Kimi estimator cannot be reused for another provider")
    elif est.get("kind") == "native_count":
        if c["protocol"] not in {"responses", "anthropic", "gemini"} or type(est.get("reserve_tokens")) is not int or est["reserve_tokens"] < 0 or not est.get("basis"):
            raise ValueError("Native count requires a supported protocol and documented extra reserve")
    elif est.get("kind") == "local_tokenizer":
        if (c["provider"] != "deepseek" or not isinstance(est.get("path"), str) or not est.get("sha256")
                or est.get("image_token_upper") != 1024 or type(est.get("reserve_tokens")) is not int
                or est["reserve_tokens"] < 4096 or not est.get("basis")):
            raise ValueError("Local DeepSeek counting requires a frozen tokenizer and explicit conservative reserves")
    elif est.get("kind") == "fixed_upper_bound":
        if type(est.get("input_tokens")) is not int or est["input_tokens"] < 1 or not est.get("basis"):
            raise ValueError("A documented, validated whole-request token bound is required")
    elif est.get("kind") == "offline_only":
        if not est.get("basis"):
            raise ValueError("Offline-only profiles require an explicit missing-counter basis")
    else:
        raise ValueError("Select an estimator; no silent tokenizer fallback")
    return c


def _call(identifier, name, args):
    return {"id": identifier, "type": "function", "function": {"name": name, "arguments": args if isinstance(args, str) else encoded(args).decode()}}


def validate_turns(messages, allow_files=False):
    pending, seen = set(), set()
    for m in messages:
        role = m.get("role")
        if role == "assistant":
            if pending:
                raise ValueError("Unanswered tool calls")
            for call in m.get("tool_calls", []):
                if not call.get("id") or call["id"] in seen:
                    raise ValueError("Missing or duplicate tool call ID")
                seen.add(call["id"]); pending.add(call["id"])
        elif role == "tool":
            if m.get("tool_call_id") not in pending:
                raise ValueError("Unmatched tool result")
            pending.remove(m["tool_call_id"])
        elif role not in {"user", "system"} or pending:
            raise ValueError("Invalid role or interrupted tool-result sequence")
        content = m.get("content")
        if isinstance(content, list) and role != "assistant":
            for p in content:
                if p.get("type") == "image_url":
                    if not p.get("image_url", {}).get("url", "").startswith("data:image/png;base64,"):
                        raise ValueError("Only frozen inline PNG images are allowed")
                elif p.get("type") == "file":
                    if not allow_files or set(p) != {"type", "file_id"} or (p.get("file_id") not in allow_files if isinstance(allow_files, dict) else not p.get("file_id", "").startswith("file-api-")):
                        raise ValueError("Only declared DeepSeek image file references are allowed")
                elif p.get("type") != "text":
                    raise ValueError("Unsupported content block")
    if pending:
        raise ValueError("Unanswered tool calls")


class Adapter:
    def __init__(self, config):
        self.c = profile(config)
        self.protocol = self.c["protocol"]

    def headers(self, key):
        h = {"Content-Type": "application/json"}
        if self.protocol == "anthropic":
            h.update({"x-api-key": key, "anthropic-version": self.c["api_version"]})
        elif self.protocol == "gemini":
            h["x-goog-api-key"] = key
        else:
            h["Authorization"] = "Bearer " + key
        if self.c.get("file_metadata") and self.protocol == "anthropic":
            h["anthropic-beta"] = "files-api-2025-04-14"
        return h

    def parts(self, content):
        parts = [{"type": "text", "text": content}] if isinstance(content, str) else content or []
        result = []
        for p in parts:
            if p["type"] == "text":
                result.append({"type": "input_text", "text": p["text"]} if self.protocol == "responses" else {"text": p["text"]} if self.protocol == "gemini" else p)
            elif p["type"] == "file":
                if not self.c["capabilities"]["vision"]:
                    raise Stop("unsupported_capability", "Selected model does not support images")
                meta = self.c.get("file_metadata", {}).get(p["file_id"])
                if not meta or meta.get("provider") != self.c["provider"]:
                    raise ValueError("Native file reference lacks matching provider metadata")
                if self.protocol == "responses":
                    result.append({"type": "input_image", "file_id": p["file_id"]})
                elif self.protocol == "anthropic":
                    result.append({"type": "image", "source": {"type": "file", "file_id": p["file_id"]}})
                elif self.protocol == "gemini":
                    result.append({"fileData": {"mimeType": "image/png", "fileUri": p["file_id"]}})
                else:
                    raise ValueError("Unsupported native file transport")
            else:
                if not self.c["capabilities"]["vision"]:
                    raise Stop("unsupported_capability", "Selected model does not support images")
                url = p["image_url"]["url"]
                data = url.split(",", 1)[1]
                result.append({"type": "input_image", "image_url": url} if self.protocol == "responses" else
                              {"inlineData": {"mimeType": "image/png", "data": data}} if self.protocol == "gemini" else
                              {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}})
        return result

    def build(self, messages, tools):
        validate_turns(messages, allow_files=self.c.get("file_metadata") or self.c["provider"] == "deepseek")
        p, c = self.protocol, self.c
        if tools and not c["capabilities"]["tools"]:
            raise Stop("unsupported_capability", "Selected model does not support tools")
        defs = [t["function"] for t in tools]
        if p == "chat_completions":
            turns = []
            for m in messages:
                if isinstance(m.get("content"), list) and not c["capabilities"]["vision"] and any(x.get("type") in {"image_url", "file"} for x in m["content"]):
                    raise Stop("unsupported_capability", "Selected model does not support images")
                if isinstance(m.get("content"), list) and any(x.get("type") == "file" and x["file_id"] not in c.get("file_expiries", {}) for x in m["content"]):
                    raise ValueError("File reference lacks a frozen expiration record")
                turns.append(copy.deepcopy(m.get("_native", {}).get("value", m)))
                turns[-1].pop("_native", None)
            body = {"model": c["model"], "messages": turns, "stream": False, c["output_token_field"]: c["max_output_tokens"], **c["generation"]}
            if tools: body.update(tools=tools, tool_choice=c.get("tool_choice", "auto"))
            elif c.get("tool_choice") == "required" and c.get("execution_mode") not in {"final", "continuation"}:
                raise ValueError("Required tool choice needs a nonempty tool list")
            if c["capabilities"]["json_object"] and c.get("response_format", "json_object") == "json_object": body["response_format"] = {"type": "json_object"}
        else:
            turns, system, call_names = [], [], {}
            for m in messages:
                role = m["role"]
                if role == "system":
                    system.append(m["content"]); continue
                if role == "assistant":
                    native = m.get("_native")
                    if not native or native.get("protocol") != p:
                        raise ValueError("Native assistant continuation required for this protocol")
                    for call in m.get("tool_calls", []): call_names[call["id"]] = call["function"]["name"]
                    if p == "responses": turns.extend(copy.deepcopy(native["value"]))
                    else: turns.append(copy.deepcopy(native["value"]))
                elif role == "tool":
                    if p == "responses":
                        turns.append({"type": "function_call_output", "call_id": m["tool_call_id"], "output": m["content"]})
                    elif p == "anthropic":
                        self.merge(turns, "user", [{"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}], "content")
                    else:
                        response = {"name": call_names[m["tool_call_id"]], "response": json.loads(m["content"])}
                        # Native function call IDs are optional on older Gemini models.
                        if not m["tool_call_id"].startswith("gemini-local-"): response["id"] = m["tool_call_id"]
                        self.merge(turns, "user", [{"functionResponse": response}], "parts")
                elif p == "responses": turns.append({"role": role, "content": self.parts(m["content"])})
                else: self.merge(turns, role, self.parts(m["content"]), "parts" if p == "gemini" else "content")
            if p == "responses":
                body = {"model": c["model"], "instructions": "\n\n".join(system), "input": turns,
                        "store": False, "include": ["reasoning.encrypted_content"], "stream": False,
                        "max_output_tokens": c["max_output_tokens"], **c["generation"]}
                if tools: body["tools"] = [{"type": "function", **d, "strict": False} for d in defs]
                if c["capabilities"]["json_object"]: body["text"] = {"format": {"type": "json_object"}}
            elif p == "anthropic":
                body = {"model": c["model"], "system": "\n\n".join(system), "messages": turns,
                        "max_tokens": c["max_output_tokens"], "stream": False, **c["generation"]}
                if tools: body["tools"] = [{"name": d["name"], "description": d.get("description", ""), "input_schema": d["parameters"]} for d in defs]
            else:
                body = {"contents": turns, "systemInstruction": {"parts": [{"text": "\n\n".join(system)}]},
                        "generationConfig": {"maxOutputTokens": c["max_output_tokens"], **c["generation"]}}
                if tools: body["tools"] = [{"functionDeclarations": [{"name": d["name"], "description": d.get("description", ""), "parametersJsonSchema": d["parameters"]} for d in defs]}]
                if c["capabilities"]["json_object"]: body["generationConfig"]["responseMimeType"] = "application/json"
        mode = c.get("execution_mode")
        if mode == "tool_query":
            if not tools:
                raise ValueError("Tool query mode requires tools")
            # Query selection remains autonomous. Do not constrain an assistant
            # tool decision with the final answer's JSON response format.
            if p == "chat_completions":
                body["tool_choice"] = "auto"
                body.pop("response_format", None)
            elif p == "responses":
                body["tool_choice"] = "auto"
                body.pop("text", None)
            elif p == "anthropic":
                body["tool_choice"] = {"type": "auto"}
            else:
                body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
                body["generationConfig"].pop("responseMimeType", None)
        elif mode == "reading":
            if not tools:
                raise ValueError("Reading mode requires task tools")
            if p == "chat_completions":
                body["tool_choice"] = "required"
                body.pop("response_format", None)
            elif p == "responses":
                body["tool_choice"] = "required"
                body.pop("text", None)
            elif p == "anthropic":
                # Extended thinking only supports auto/none; the host still
                # enforces the explicit finish_reading gate for every provider.
                thinking = c["generation"].get("thinking", {}).get("type")
                body["tool_choice"] = {"type": "auto" if thinking in {"enabled", "adaptive"} else "any"}
            else:
                body["toolConfig"] = {"functionCallingConfig": {"mode": "ANY"}}
                body["generationConfig"].pop("responseMimeType", None)
        elif mode == "continuation":
            if tools:
                raise ValueError("Continuation cannot expose tools")
            # A suffix of a truncated JSON document is not itself a JSON object.
            if p == "chat_completions": body.pop("response_format", None)
            elif p == "responses": body.pop("text", None)
            elif p == "gemini": body["generationConfig"].pop("responseMimeType", None)
        elif mode == "final":
            if tools:
                raise ValueError("Final mode cannot expose tools")
            if p == "chat_completions" and c["capabilities"]["json_object"]:
                body["response_format"] = {"type": "json_object"}
            if c.get("output_schema"):
                native = format_schema(c["output_schema"])
                definition = native["json_schema"]
                if p == "chat_completions":
                    body["response_format"] = native
                elif p == "responses":
                    body["text"] = {"format": {"type": "json_schema", **definition}}
                elif p == "anthropic":
                    body["output_config"] = {**body.get("output_config", {}),
                                             "format": {"type": "json_schema", "schema": definition["schema"]}}
                else:
                    body["generationConfig"].update(responseMimeType="application/json", responseJsonSchema=definition["schema"])
        for m in messages:
            if m.get("_native", {}).get("protocol", p) != p:
                raise ValueError("Cross-protocol history is forbidden")
        if c.get("stream") and p != "gemini":
            body["stream"] = True
            if p == "chat_completions" and c["provider"] in {"qwen", "doubao"}:
                body["stream_options"] = {"include_usage": True}
        return body

    @staticmethod
    def merge(turns, role, parts, field):
        if turns and turns[-1].get("role") == role:
            turns[-1][field].extend(parts)
        else: turns.append({"role": role, field: parts})

    def count_request(self, messages, tools):
        body = self.build(messages, tools)
        endpoint = self.c["endpoint"]
        if self.protocol == "anthropic":
            body = {k: v for k, v in body.items() if k not in {"max_tokens", "stream"}}
            return endpoint + "/count_tokens", body, "input_tokens"
        if self.protocol == "responses":
            body = {k: v for k, v in body.items() if k not in {"max_output_tokens", "stream", "store", "include"}}
            return endpoint + "/input_tokens", body, "input_tokens"
        if self.protocol == "gemini":
            return endpoint.removesuffix(":generateContent") + ":countTokens", {"generateContentRequest": {"model": "models/" + self.c["model"], **body}}, "totalTokens"
        raise ValueError("No native token counter for this protocol")

    def usage(self, raw):
        return raw.get("usageMetadata") if self.protocol == "gemini" else raw.get("usage")

    def parse(self, raw):
        p = self.protocol
        calls, text, blocked = [], "", False
        model = raw.get("modelVersion") if p == "gemini" else raw.get("model")
        try:
            if p == "chat_completions":
                if len(raw["choices"]) != 1: raise ValueError()
                choice = raw["choices"][0]; native = choice["message"]; finish = choice["finish_reason"]
                if native.get("role") != "assistant": raise ValueError()
                calls, text = native.get("tool_calls", []), native.get("content") or ""
                normal = finish == ("tool_calls" if calls else "stop")
                truncated = finish == "length"
                message = copy.deepcopy(native)
            elif p == "responses":
                native = raw["output"]; finish = raw["status"]
                for item in native:
                    if item["type"] == "function_call": calls.append(_call(item["call_id"], item["name"], item["arguments"]))
                    elif item["type"] == "message":
                        for block in item["content"]:
                            if block["type"] == "output_text": text += block["text"]
                            elif block["type"] == "refusal": blocked = True
                    elif item["type"] != "reasoning": blocked = True
                normal = finish == "completed"; truncated = finish == "incomplete" and raw.get("incomplete_details", {}).get("reason") == "max_output_tokens"
            elif p == "anthropic":
                native = {"role": raw["role"], "content": raw["content"]}; finish = raw["stop_reason"]
                if native["role"] != "assistant": raise ValueError()
                for block in native["content"]:
                    if block["type"] == "text": text += block["text"]
                    elif block["type"] == "tool_use": calls.append(_call(block["id"], block["name"], block["input"]))
                    elif block["type"] not in {"thinking", "redacted_thinking"}: blocked = True
                normal = finish == ("tool_use" if calls else "end_turn"); truncated = finish == "max_tokens"
            else:
                if len(raw["candidates"]) != 1: raise ValueError()
                candidate = raw["candidates"][0]; native = candidate["content"]; finish = candidate.get("finishReason")
                if native.get("role") != "model": raise ValueError()
                for i, part in enumerate(native["parts"]):
                    if "functionCall" in part:
                        call = part["functionCall"]
                        # Stable per response, including when the provider omits IDs.
                        from .archive import digest
                        calls.append(_call(call.get("id") or "gemini-local-" + digest(raw)[:20] + "-" + str(i), call["name"], call.get("args", {})))
                    elif "text" in part and not part.get("thought"): text += part["text"]
                normal = finish == "STOP"; truncated = finish == "MAX_TOKENS"
            if p != "chat_completions":
                message = {"role": "assistant", "content": text, "_native": {"protocol": p, "value": native}}
                if calls: message["tool_calls"] = calls
            if not isinstance(text, str) or not isinstance(calls, list): raise ValueError()
            for call in calls:
                if not isinstance(call["id"], str) or not isinstance(call["function"]["arguments"], str): raise ValueError()
            status = "paused_truncated" if truncated else "ok" if normal and not blocked and (text or calls) else "failed_response"
            if model not in self.c["accepted_response_models"]: status = "failed_model_identity"
            return {"status": status, "message": message, "finish_reason": finish, "model": model,
                    "request_id": raw.get("id", raw.get("responseId")), "raw_usage": self.usage(raw)}
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            raise Stop("failed_response", "Malformed provider response; original response archived") from None
