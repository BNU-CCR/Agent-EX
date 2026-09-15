#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: phase0a1-install.sh ABSOLUTE_PYTHON ABSOLUTE_WHEELHOUSE ABSOLUTE_WHEEL_MANIFEST WHEEL_MANIFEST_SHA256 ABSOLUTE_NEW_ENV" >&2
  exit 2
}

[[ "$#" -eq 5 ]] || usage
ABSOLUTE_PYTHON="$1"
ABSOLUTE_WHEELHOUSE="$2"
ABSOLUTE_WHEEL_MANIFEST="$3"
WHEEL_MANIFEST_SHA256="$4"
ABSOLUTE_NEW_ENV="$5"

require_exact_path() {
  local path="$1"
  local kind="$2"
  local resolved
  resolved="$(realpath -e -- "$path" 2>/dev/null || true)"
  if [[ "$path" != /* || -L "$path" || "$resolved" != "$path" ]]; then
    echo "$kind must be absolute, existing, canonical, and not a symlink" >&2
    exit 2
  fi
}

require_no_proxy() {
  local variable
  while IFS= read -r variable; do
    case "$variable" in
      *[Pp][Rr][Oo][Xx][Yy]*)
        if [[ -n "${!variable-}" ]]; then
          echo "proxy variable $variable must be unset before offline installation" >&2
          exit 2
        fi
        ;;
    esac
  done < <(compgen -e)
}

require_exact_path "$ABSOLUTE_PYTHON" "ABSOLUTE_PYTHON"
require_exact_path "$ABSOLUTE_WHEELHOUSE" "ABSOLUTE_WHEELHOUSE"
require_exact_path "$ABSOLUTE_WHEEL_MANIFEST" "ABSOLUTE_WHEEL_MANIFEST"
[[ -f "$ABSOLUTE_PYTHON" && -x "$ABSOLUTE_PYTHON" ]] || usage
[[ -d "$ABSOLUTE_WHEELHOUSE" && -f "$ABSOLUTE_WHEEL_MANIFEST" ]] || usage
if [[ "$ABSOLUTE_WHEEL_MANIFEST" != "$ABSOLUTE_WHEELHOUSE/"* ]]; then
  echo "wheel manifest must be inside the wheelhouse" >&2
  exit 2
fi
if [[ "$ABSOLUTE_NEW_ENV" != /* || -e "$ABSOLUTE_NEW_ENV" || -L "$ABSOLUTE_NEW_ENV" ]]; then
  echo "ABSOLUTE_NEW_ENV must be an absent absolute path" >&2
  exit 2
fi
env_parent="$(dirname -- "$ABSOLUTE_NEW_ENV")"
env_parent_resolved="$(realpath -e -- "$env_parent" 2>/dev/null || true)"
if [[ ! -d "$env_parent" || -L "$env_parent" || "$env_parent_resolved" != "$env_parent" ]]; then
  echo "ABSOLUTE_NEW_ENV parent must be an existing canonical directory without symlinks" >&2
  exit 2
fi
[[ "$WHEEL_MANIFEST_SHA256" =~ ^[0-9a-f]{64}$ ]] || usage
require_no_proxy

"$ABSOLUTE_PYTHON" - "$ABSOLUTE_WHEELHOUSE" "$ABSOLUTE_WHEEL_MANIFEST" "$WHEEL_MANIFEST_SHA256" <<'PY'
import hashlib, json, pathlib, re, sys

wheelhouse = pathlib.Path(sys.argv[1])
manifest_path = pathlib.Path(sys.argv[2])
affirmative_hash = sys.argv[3]
payload = json.loads(manifest_path.read_text(encoding="utf-8"))
if type(payload) is not dict or set(payload) != {"schema_version", "wheel_entries", "record_hash"}:
    raise SystemExit("wheel manifest fields are not exact")
if payload["schema_version"] != "paper1.calibration.wheel-manifest.v1":
    raise SystemExit("wheel manifest schema is not supported")
entries = payload["wheel_entries"]
if type(entries) is not list or not entries:
    raise SystemExit("wheel manifest requires entries")
if entries != sorted(entries, key=lambda item: item["name"].casefold()):
    raise SystemExit("wheel manifest entries are not sorted")
content = {"schema_version": payload["schema_version"], "wheel_entries": entries}
encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
record_hash = hashlib.sha256(encoded).hexdigest()
if payload["record_hash"] != record_hash or affirmative_hash != record_hash:
    raise SystemExit("wheel manifest record hash mismatch")
seen = set()
seen_files = set()
vllm = []
for entry in entries:
    if type(entry) is not dict or set(entry) != {"name", "version", "sha256", "source"}:
        raise SystemExit("wheel entry fields are not exact")
    name = entry["name"]
    if type(name) is not str or re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name) is None:
        raise SystemExit("wheel entry name is unsafe")
    if name in seen:
        raise SystemExit("wheel entry names are not unique")
    seen.add(name)
    if type(entry["version"]) is not str or not entry["version"]:
        raise SystemExit("wheel version is invalid")
    if type(entry["source"]) is not str or not entry["source"]:
        raise SystemExit("wheel source is invalid")
    if type(entry["sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None:
        raise SystemExit("wheel hash is invalid")
    matching = [
        path
        for path in wheelhouse.glob("*.whl")
        if path.name.split("-", 1)[0].replace("_", "-").casefold() == name.casefold()
    ]
    if len(matching) != 1:
        raise SystemExit("manifest wheel is absent or unsafe")
    wheel = matching[0]
    if wheel.is_symlink():
        raise SystemExit("manifest wheel is absent or unsafe")
    seen_files.add(wheel.name)
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != entry["sha256"]:
        raise SystemExit("wheel content hash mismatch")
    if name.casefold() == "vllm":
        vllm.append(entry)
actual_names = {path.name for path in wheelhouse.glob("*.whl") if path.is_file()}
if actual_names != seen_files:
    raise SystemExit("wheelhouse content differs from the affirmative manifest")
if len(vllm) != 1 or vllm[0]["version"] != "0.23.0" or vllm[0]["source"] != "official-cuda-12.9":
    raise SystemExit("wheel manifest requires official CUDA 12.9 vLLM 0.23.0")
PY

"$ABSOLUTE_PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 12)'
"$ABSOLUTE_PYTHON" -m venv "$ABSOLUTE_NEW_ENV"
env_python="$ABSOLUTE_NEW_ENV/bin/python"
"$env_python" -m pip install \
  --no-index \
  --find-links "$ABSOLUTE_WHEELHOUSE" \
  "vllm==0.23.0"
"$env_python" -c \
  'import pathlib, sys, torch, vllm; root=pathlib.Path(sys.argv[1]).resolve(); torch_path=pathlib.Path(torch.__file__).resolve(); assert root in torch_path.parents; assert vllm.__version__ == "0.23.0"' \
  "$ABSOLUTE_NEW_ENV"
"$env_python" -m pip check
