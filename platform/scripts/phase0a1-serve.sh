#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
  echo "usage: phase0a1-serve.sh VLLM_EXECUTABLE LOCAL_MODEL_PATH" >&2
  exit 2
fi

vllm_executable="$1"
model_path="$2"
vllm_resolved="$(realpath -e -- "$vllm_executable" 2>/dev/null || true)"
model_resolved="$(realpath -e -- "$model_path" 2>/dev/null || true)"

if [[ "$vllm_executable" != /* || ! -f "$vllm_executable" || ! -x "$vllm_executable" || -L "$vllm_executable" || "$vllm_resolved" != "$vllm_executable" ]]; then
  echo "VLLM_EXECUTABLE must be an absolute executable regular file without symlinks" >&2
  exit 2
fi
if [[ "$model_path" != /* || ! -d "$model_path" || -L "$model_path" || "$model_resolved" != "$model_path" ]]; then
  echo "LOCAL_MODEL_PATH must be an absolute regular directory without symlinks" >&2
  exit 2
fi

for variable in $(compgen -e); do
  case "$variable" in
    *[Pp][Rr][Oo][Xx][Yy]*)
      if [[ -n "${!variable-}" ]]; then
        echo "proxy variable $variable must be unset before vLLM startup" >&2
        exit 2
      fi
      ;;
  esac
done

exec "$vllm_executable" serve "$model_path" \
  --host 127.0.0.1 \
  --port 8000 \
  --revision b968826d9c46dd6066d109eabc6255188de91218 \
  --tokenizer-revision b968826d9c46dd6066d109eabc6255188de91218 \
  --dtype bfloat16 \
  --max-model-len 32768 \
  --generation-config vllm \
  --served-model-name qwen3-8b-paper1 \
  --default-chat-template-kwargs '{"enable_thinking":false}' \
  --enable-request-id-headers
