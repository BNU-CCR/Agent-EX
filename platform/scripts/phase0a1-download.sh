#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: phase0a1-download.sh packages ABSOLUTE_PYTHON ABSOLUTE_WHEELHOUSE | model ABSOLUTE_PYTHON ABSOLUTE_MODEL_DIR" >&2
  exit 2
}

[[ "$#" -eq 3 ]] || usage
mode="$1"
python_executable="$2"
output_path="$3"

python_resolved="$(realpath -e -- "$python_executable" 2>/dev/null || true)"
if [[ "$python_executable" != /* || ! -f "$python_executable" || ! -x "$python_executable" || -L "$python_executable" || "$python_resolved" != "$python_executable" ]]; then
  echo "ABSOLUTE_PYTHON must be an absolute executable regular file without symlinks" >&2
  exit 2
fi
if [[ "$output_path" != /* || -e "$output_path" || -L "$output_path" ]]; then
  echo "download output must be an absent absolute path" >&2
  exit 2
fi
output_parent="$(dirname -- "$output_path")"
parent_resolved="$(realpath -e -- "$output_parent" 2>/dev/null || true)"
if [[ ! -d "$output_parent" || -L "$output_parent" || "$parent_resolved" != "$output_parent" ]]; then
  echo "download output parent must be an existing canonical directory without symlinks" >&2
  exit 2
fi

case "$mode" in
  packages|model) ;;
  *) usage ;;
esac

(
  cleanup() {
    local variable
    while IFS= read -r variable; do
      case "$variable" in
        *[Pp][Rr][Oo][Xx][Yy]*) unset "$variable" ;;
      esac
    done < <(compgen -e)
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
  }
  signal_exit() {
    local code="$1"
    cleanup
    exit "$code"
  }
  trap cleanup EXIT
  trap 'signal_exit 129' HUP
  trap 'signal_exit 130' INT
  trap 'signal_exit 143' TERM

  # AutoDL acceleration is deliberately scoped to this child process only.
  source /etc/network_turbo

  case "$mode" in
    packages)
      mkdir -- "$output_path"
      "$python_executable" -m pip download \
        --only-binary=:all: \
        --dest "$output_path" \
        "vllm==0.23.0"
      "$python_executable" - "$output_path" <<'PY'
import hashlib, json, os, pathlib, sys
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename

wheelhouse = pathlib.Path(sys.argv[1])
entries = []
for wheel in sorted(wheelhouse.glob("*.whl"), key=lambda path: path.name.casefold()):
    distribution, version, _, _ = parse_wheel_filename(wheel.name)
    name = canonicalize_name(distribution)
    source = "official-cuda-12.9" if name == "vllm" else "resolved-vllm-0.23.0-cuda-12.9"
    entries.append(
        {
            "name": name,
            "version": version.public if name == "vllm" else str(version),
            "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "source": source,
        }
    )
if not entries:
    raise SystemExit("package download produced no wheels")
entries.sort(key=lambda entry: entry["name"].casefold())
vllm = [entry for entry in entries if entry["name"] == "vllm"]
if len(vllm) != 1 or vllm[0]["version"] != "0.23.0":
    raise SystemExit("download did not resolve exactly one vLLM 0.23.0 wheel")
content = {
    "schema_version": "paper1.calibration.wheel-manifest.v1",
    "wheel_entries": entries,
}
encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
payload = {**content, "record_hash": hashlib.sha256(encoded).hexdigest()}
output = wheelhouse / "wheel-manifest.json"
fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    json.dump(payload, stream, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
PY
      ;;
    model)
      "$python_executable" -c \
        'from huggingface_hub import snapshot_download; import sys; snapshot_download(repo_id="Qwen/Qwen3-8B", revision="b968826d9c46dd6066d109eabc6255188de91218", local_dir=sys.argv[1], token=False)' \
        "$output_path"
      ;;
  esac
)
