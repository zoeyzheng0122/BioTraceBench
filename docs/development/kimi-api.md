# Kimi Client Acceptance

The acceptance helper supports `preflight`, `invoke` and `recover`. Preflight is offline. Explicit invocation requires a provider credential supplied through the environment and writes a new immutable attempt directory. Recovery reuses an existing complete response. Synthetic unit tests inject a local sender and perform no paid calls.
