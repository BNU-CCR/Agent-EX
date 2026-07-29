---
status: provisional
authority: Phase0B official API discovery
supersedes: none
last-verified: 2026-07-29
---

# Allowed APIs v1

This document is the provisional Phase 0B allow-list for the Paper 1 model interfaces. It separates properties supported by official documentation from values frozen for execution. Documentation support alone is not an execution guarantee; credentialed/runtime smoke tests and an environment lock are required before a value moves into the frozen runtime configuration. A run manifest records what actually occurred and cannot override that configuration.

## Local Qwen3-8B model identity

The user-approved local model route is [Qwen/Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B), BF16 and non-thinking. The following full commit is a documentation/repository-verified Phase 0B candidate:

`b968826d9c46dd6066d109eabc6255188de91218`

Documentation-supported properties:

- License: Apache 2.0.
- Inference dtype: BF16.
- Generation mode: non-thinking.
- Native context length: 32,768 tokens.
- YaRN: disabled; no YaRN configuration is allowed for this native-context target.

The executable model revision remains `UNRESOLVED[P1_MODEL_REVISION]` until the candidate commit passes artifact access, tokenizer/chat-template, non-thinking, response-contract and runtime smoke tests and is written into the environment lock. The candidate hash above must not be treated as execution-frozen before that gate.

## vLLM serving contract

Documentation was verified against the Phase 0B candidate `vllm==0.23.0`. The executable version remains `UNRESOLVED[P1_VLLM_VERSION]` until an image/runtime smoke test passes and the version plus image digest are frozen. The official references are the [vLLM serve CLI](https://docs.vllm.ai/en/v0.23.0/cli/serve/) and the [chat-completion protocol](https://docs.vllm.ai/en/v0.23.0/api/vllm/entrypoints/openai/chat_completion/protocol/).

If both candidates pass and are frozen, the server launch contract must include these values:

```text
--revision b968826d9c46dd6066d109eabc6255188de91218
--tokenizer-revision b968826d9c46dd6066d109eabc6255188de91218
--dtype bfloat16
--max-model-len 32768
--generation-config vllm
--served-model-name qwen3-8b-paper1
--default-chat-template-kwargs enable_thinking false
--enable-request-id-headers
```

`--generation-config vllm` is required so repository generation defaults do not silently override the frozen experiment parameters. Both model and tokenizer revisions are pinned to the same commit.

## OpenAI-compatible chat-completion allow-list

Only the following request fields are allowed:

| Field | Constraint |
|---|---|
| `model` | Must be `qwen3-8b-paper1` for the local server. |
| `messages` | Required chat input. |
| `temperature` | Must come from the frozen protocol/runtime configuration. |
| `top_p` | Must come from the frozen protocol/runtime configuration. |
| `max_tokens` | Allowed for compatibility but deprecated; its use must be recorded. |
| `seed` | Official protocol support is documented; it must be explicit and recorded, but determinism and actual propagation remain subject to the `UNRESOLVED[P1_REQUEST_SEED]` smoke gate. |
| `top_k` | vLLM extension; must be explicit if used. |
| `min_p` | vLLM extension; must be explicit if used. |
| `chat_template_kwargs` | Must set `enable_thinking` to `false` when supplied. |

No unlisted request field is part of the v1 contract.

For every successful response, the adapter must parse and persist the contract fields below and must preserve the raw response body, HTTP status and all response headers available from the client:

- `id`;
- `choices[].index`;
- `choices[].message.content`;
- `choices[].finish_reason`;
- `usage`;
- the `X-Request-Id` response header when returned.

For non-success responses, the adapter must preserve the raw error body, HTTP status and all response headers available from the client. The exact structured error fields and header behavior are not yet execution-frozen and require credentialed/runtime smoke verification. In particular, support and semantics for `Retry-After` remain `UNRESOLVED[P1_TIMEOUT_RETRY]`; retry scheduling must not depend on it before that gate is frozen.

## DashScope external robustness candidate

Provider remains `UNRESOLVED[P1_API_PROVIDER]`. The documentation-identified DashScope candidate snapshot is `qwen3.7-plus-2026-05-26`, but the executable snapshot remains `UNRESOLVED[P1_API_SNAPSHOT]` until credentialed endpoint verification and robustness preregistration.

Official discovery references:

- [Model Studio text-generation models](https://help.aliyun.com/en/model-studio/text-generation-model/)
- [Qwen API via OpenAI Chat Completions](https://help.aliyun.com/en/model-studio/qwen-api-via-openai-chat-completions)

Before the provider and snapshot can be frozen, a credentialed smoke test must verify all of the following against the actual endpoint:

- sending `temperature` and `top_p` together;
- custom request-ID submission and response propagation;
- success response fields and raw body/status/header capture;
- structured error-body fields, throttling/error behavior and the presence and semantics of `Retry-After` under `UNRESOLVED[P1_TIMEOUT_RETRY]`.

Until that test passes, these behaviors are not execution guarantees and must not be assumed by the provider adapter.

## Interpretation boundary

The DashScope/API subset is an external **model-system robustness** comparison. Differences between it and the pinned local Qwen3-8B system must not be interpreted as an "API deployment effect": model weights, serving stack, templates, and other system components are not isolated by this comparison.
