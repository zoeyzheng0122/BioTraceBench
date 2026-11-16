"""Provider-declared billing semantics; missing usage remains unknown."""
from decimal import Decimal, InvalidOperation

BUCKETS = ("input", "cache_hit", "cache_write", "output")


def at(value, path):
    if isinstance(path, dict):
        # Only explicit tariff metadata can declare a category inapplicable.
        return 0 if path.get("not_applicable") is True and path.get("basis") else None
    if isinstance(path, list):
        parts = [at(value, p) for p in path]
        return sum(parts) if parts and all(p is not None for p in parts) else None
    if not isinstance(path, str) or not path:
        return None
    for key in path.split("."):
        if not isinstance(value, dict): return None
        value = value.get(key)
    return value if type(value) is int and value >= 0 else None


def validate_tariff(tariff):
    if tariff.get("input_accounting", "includes_cache") not in {"includes_cache", "excludes_cache"}:
        raise ValueError("Explicit input accounting must include or exclude cache")
    for key in BUCKETS:
        try:
            rate = Decimal(str(tariff["per_million"][key]))
            if not rate.is_finite() or rate < 0: raise ValueError()
        except (KeyError, InvalidOperation, ValueError):
            raise ValueError("Finite nonnegative tariff rates required") from None
        spec = tariff["usage_paths"].get(key)
        if isinstance(spec, dict):
            if key in {"input", "output"} or spec.get("not_applicable") is not True or not spec.get("basis") or rate != 0:
                raise ValueError("Inapplicable cache categories require a source basis and zero rate")
        elif isinstance(spec, list):
            if not spec or any(not isinstance(x, str) or not x for x in spec): raise ValueError("Invalid summed usage paths")
        elif not isinstance(spec, str) or not spec:
            raise ValueError("Explicit usage mapping required; missing is not zero")


def calculate(usage, tariff):
    paths = tariff["usage_paths"]
    values = {key: at(usage, paths.get(key)) for key in BUCKETS}
    base = {"currency": tariff["currency"], "raw_usage": usage, "tokens": values,
            "not_applicable": [k for k, v in paths.items() if isinstance(v, dict) and v.get("not_applicable")]}
    if any(v is None for v in values.values()):
        return {**base, "amount": None, "kind": "unknown"}
    total, cached, created, output = (values[k] for k in BUCKETS)
    exclusive = tariff.get("input_accounting", "includes_cache") == "excludes_cache"
    uncached = total if exclusive else total - cached - created
    if uncached < 0:
        return {**base, "amount": None, "kind": "unknown", "reason": "inconsistent_usage"}
    buckets = {"input": uncached, "cache_hit": cached, "cache_write": created, "output": output}
    # Runner token budgets always count all input, regardless of wire convention.
    base["tokens"] = {**values, "input": total + cached + created if exclusive else total}
    amount = sum(Decimal(n) * Decimal(str(tariff["per_million"][k])) / Decimal(1000000) for k, n in buckets.items())
    return {**base, "amount": str(amount), "billing_buckets": buckets,
            "kind": "tariff_estimate_not_invoice", "source_url": tariff["source_url"]}


def upper(input_tokens, output_tokens, tariff):
    rates = tariff["per_million"]
    return (Decimal(input_tokens) * max(Decimal(str(rates[k])) for k in ("input", "cache_hit", "cache_write"))
            + Decimal(output_tokens) * Decimal(str(rates["output"]))) / Decimal(1000000)


def budget_cost(usage, tariff, policy="require_exact"):
    """Keep exact cost separate from an explicitly authorized budget bound."""
    if policy not in {"require_exact", "known_totals_upper_bound"}:
        raise ValueError("Unknown cost policy")
    result = calculate(usage, tariff)
    result["budget_upper"] = result["amount"]
    result["budget_basis"] = "tariff_estimate" if result["amount"] is not None else "unknown"
    if policy == "require_exact":
        return result
    validate_tariff(tariff)
    values = result["tokens"]
    # Cache-exclusive totals cannot bound missing cache input.
    if tariff.get("input_accounting", "includes_cache") != "includes_cache":
        return result
    inp, out = values["input"], values["output"]
    if inp is None or out is None:
        return result
    if "total_tokens" in usage and (type(usage["total_tokens"]) is not int or usage["total_tokens"] != inp + out):
        return {**result, "amount": None, "budget_upper": None, "budget_basis": "inconsistent_totals"}
    known = []
    for key in ("cache_hit", "cache_write"):
        path = tariff["usage_paths"][key]
        if not isinstance(path, str):
            if values[key] is None:
                return result
        else:
            node = usage
            for part in path.split("."):
                if not isinstance(node, dict):
                    return {**result, "budget_upper": None, "budget_basis": "malformed_cache"}
                if part not in node:
                    break
                node = node[part]
            else:
                if type(node) is not int or node < 0:
                    return {**result, "budget_upper": None, "budget_basis": "malformed_cache"}
        if values[key] is not None:
            known.append(values[key])
    if sum(known) > inp:
        return {**result, "amount": None, "budget_upper": None, "budget_basis": "inconsistent_cache"}
    if result["amount"] is None:
        result["budget_upper"] = str(upper(inp, out, tariff))
        result["budget_basis"] = "known_totals_highest_applicable_rate"
    return result
