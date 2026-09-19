#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: phase0a1-judge-service.sh start SERVE VLLM PYTHON MODEL EVIDENCE_DIR AUTHORIZATION_HASH | status PYTHON EVIDENCE_DIR | abort-pre-manifest PYTHON EVIDENCE_DIR AUTHORIZATION_HASH START_HASH [LOCK_HASH|-] | stop PYTHON EVIDENCE_DIR MANIFEST_HASH LOCK_HASH START_HASH" >&2
  exit 2
}

reject_proxy_environment() {
  local variable
  while IFS= read -r variable; do
    case "$variable" in
      *[Pp][Rr][Oo][Xx][Yy]*)
        [[ -z "${!variable-}" ]] || { echo "proxy variable $variable must be unset" >&2; exit 2; }
        ;;
    esac
  done < <(compgen -e)
}

require_sha256() {
  [[ "$1" =~ ^[0-9a-f]{64}$ ]] || { echo "$2 must be a lowercase SHA-256" >&2; exit 2; }
}

require_exact_file() {
  local resolved
  resolved="$(realpath -e -- "$1" 2>/dev/null || true)"
  [[ "$1" == /* && -f "$1" && ! -L "$1" && "$resolved" == "$1" ]] || {
    echo "$2 must be an absolute canonical regular file without symlinks" >&2
    exit 2
  }
}

require_exact_dir() {
  local resolved
  resolved="$(realpath -e -- "$1" 2>/dev/null || true)"
  [[ "$1" == /* && -d "$1" && ! -L "$1" && "$resolved" == "$1" ]] || {
    echo "$2 must be an absolute canonical directory without symlinks" >&2
    exit 2
  }
}

json_field() {
  "$python_executable" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]])' "$1" "$2"
}

hash_gpu_compute_process_observation() {
  local output="$1"
  local temporary="$output.tmp.$$"
  nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv,noheader,nounits > "$temporary"
  [[ ! -s "$temporary" ]] || { rm -f -- "$temporary"; echo "GPU compute processes remain" >&2; exit 1; }
  gpu_observation_hash="$(sha256sum -- "$temporary" | cut -d' ' -f1)"
  rm -f -- "$temporary"
}

listener_owned_by_pid() {
  ss -ltnpH 'sport = :8000' 2>/dev/null \
    | grep -F '127.0.0.1:8000' \
    | grep -Fq "pid=$1,"
}

verify_active_identity() {
  local identity="$1"
  [[ -f "$identity" && ! -L "$identity" ]] || { echo "judge start identity is absent or unsafe" >&2; exit 1; }
  pid="$(json_field "$identity" pid)"
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || { echo "invalid judge service PID" >&2; exit 1; }
  kill -0 "$pid" 2>/dev/null || { echo "stale judge service PID" >&2; exit 1; }
  [[ "$(realpath -e -- "/proc/$pid/exe")" == "$(json_field "$identity" executable)" ]] || {
    echo "judge service executable identity mismatch" >&2; exit 1;
  }
  [[ "$(sha256sum -- "/proc/$pid/cmdline" | cut -d' ' -f1)" == "$(json_field "$identity" cmdline_sha256)" ]] || {
    echo "judge service command identity mismatch" >&2; exit 1;
  }
  listener_owned_by_pid "$pid" || { echo "judge loopback listener is absent" >&2; exit 1; }
}

write_record() {
  local output="$1"
  local schema="$2"
  shift 2
  "$python_executable" - "$output" "$schema" "$@" <<'PY'
import hashlib, json, os, sys

output, schema, *pairs = sys.argv[1:]
content = {"schema_version": schema}
for pair in pairs:
    name, raw = pair.split("=", 1)
    if raw in {"true", "false"}:
        value = raw == "true"
    elif name == "pid":
        value = int(raw)
    elif raw == "null":
        value = None
    else:
        value = raw
    content[name] = value
content["calibration_only"] = True
content["formal_parameter_authority"] = False
content["metadata"] = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}
encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
payload = {**content, "record_hash": hashlib.sha256(encoded).hexdigest()}
fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    json.dump(payload, stream, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
PY
}

stop_verified_process() {
  kill -TERM -- "-$pid"
  local exited=false
  for _ in $(seq 1 60); do
    if ! kill -0 -- "-$pid" 2>/dev/null; then exited=true; break; fi
    sleep 1
  done
  [[ "$exited" == true ]] || { echo "verified judge service did not exit" >&2; exit 1; }
  ! ss -ltnH 'sport = :8000' 2>/dev/null | grep -Fq '127.0.0.1:8000' || {
    echo "judge loopback listener remains after process exit" >&2; exit 1;
  }
}

reject_proxy_environment
[[ "$#" -ge 1 ]] || usage
mode="$1"
shift

case "$mode" in
  start)
    [[ "$#" -eq 6 ]] || usage
    serve_script="$1"; vllm_executable="$2"; python_executable="$3"
    model_path="$4"; evidence_dir="$5"; authorization_hash="$6"
    require_exact_file "$serve_script" "ABSOLUTE_SERVE_SCRIPT"
    require_exact_file "$vllm_executable" "ABSOLUTE_VLLM"
    require_exact_file "$python_executable" "ABSOLUTE_PYTHON"
    require_exact_dir "$model_path" "ABSOLUTE_MODEL"
    require_exact_dir "$evidence_dir" "ABSOLUTE_EVIDENCE_DIR"
    require_sha256 "$authorization_hash" "AUTHORIZATION_HASH"
    ;;
  status)
    [[ "$#" -eq 2 ]] || usage
    python_executable="$1"; evidence_dir="$2"
    require_exact_file "$python_executable" "ABSOLUTE_PYTHON"
    require_exact_dir "$evidence_dir" "ABSOLUTE_EVIDENCE_DIR"
    ;;
  abort-pre-manifest)
    [[ "$#" -eq 4 || "$#" -eq 5 ]] || usage
    python_executable="$1"; evidence_dir="$2"; authorization_hash="$3"; expected_start_hash="$4"
    environment_lock_hash="${5--}"
    require_exact_file "$python_executable" "ABSOLUTE_PYTHON"
    require_exact_dir "$evidence_dir" "ABSOLUTE_EVIDENCE_DIR"
    require_sha256 "$authorization_hash" "AUTHORIZATION_HASH"
    require_sha256 "$expected_start_hash" "START_HASH"
    [[ "$environment_lock_hash" == "-" ]] || require_sha256 "$environment_lock_hash" "LOCK_HASH"
    ;;
  stop)
    [[ "$#" -eq 5 ]] || usage
    python_executable="$1"; evidence_dir="$2"; manifest_hash="$3"
    environment_lock_hash="$4"; expected_start_hash="$5"
    require_exact_file "$python_executable" "ABSOLUTE_PYTHON"
    require_exact_dir "$evidence_dir" "ABSOLUTE_EVIDENCE_DIR"
    require_sha256 "$manifest_hash" "MANIFEST_HASH"
    require_sha256 "$environment_lock_hash" "LOCK_HASH"
    require_sha256 "$expected_start_hash" "START_HASH"
    ;;
  *) usage ;;
esac

exec 9> "$evidence_dir/.phase0a1-judge-service.lock"
flock -x 9
identity="$evidence_dir/start-identity.json"

case "$mode" in
  start)
    [[ ! -e "$identity" && ! -e "$evidence_dir/stop-evidence.json" && ! -e "$evidence_dir/abort-evidence.json" ]] || {
      echo "judge lifecycle evidence already exists" >&2; exit 1;
    }
    (
      exec 9>&-
      exec setsid "$serve_script" "$vllm_executable" "$model_path"
    ) > "$evidence_dir/service.log" 2>&1 &
    pid="$!"
    committed=false
    cleanup_failed_start() {
      if [[ "$committed" != true ]] && kill -0 -- "-$pid" 2>/dev/null; then
        kill -TERM -- "-$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
      fi
    }
    trap cleanup_failed_start EXIT HUP INT TERM
    for _ in $(seq 1 300); do
      kill -0 "$pid" 2>/dev/null || { echo "vLLM exited before judge health" >&2; exit 1; }
      if listener_owned_by_pid "$pid" && curl --fail --silent --max-time 2 --max-redirs 0 http://127.0.0.1:8000/health >/dev/null; then break; fi
      sleep 1
    done
    listener_owned_by_pid "$pid" || { echo "judge service did not become healthy" >&2; exit 1; }
    write_record "$identity" "paper1.calibration.judge-service-start-identity.v1" \
      "authorization_hash=$authorization_hash" "pid=$pid" \
      "executable=$(realpath -e -- "/proc/$pid/exe")" \
      "cmdline_sha256=$(sha256sum -- "/proc/$pid/cmdline" | cut -d' ' -f1)" \
      "serve_script=$serve_script" "control_python=$python_executable" "model_path=$model_path"
    verify_active_identity "$identity"
    committed=true
    trap - EXIT HUP INT TERM
    printf '%s\n' "$identity"
    ;;
  status)
    verify_active_identity "$identity"
    printf '%s\n' "$identity"
    ;;
  abort-pre-manifest)
    verify_active_identity "$identity"
    [[ "$(json_field "$identity" authorization_hash)" == "$authorization_hash" ]] || { echo "authorization identity mismatch" >&2; exit 1; }
    start_hash="$(json_field "$identity" record_hash)"
    [[ "$start_hash" == "$expected_start_hash" ]] || { echo "start identity hash mismatch" >&2; exit 1; }
    stop_verified_process
    hash_gpu_compute_process_observation "$evidence_dir/gpu-abort-observation"
    lock_value="$environment_lock_hash"; [[ "$lock_value" == "-" ]] && lock_value="null"
    write_record "$evidence_dir/abort-evidence.json" "paper1.calibration.judge-pre-manifest-abort-evidence.v1" \
      "authorization_hash=$authorization_hash" "service_start_identity_hash=$start_hash" \
      "environment_lock_hash=$lock_value" "process_exit_observed=true" \
      "loopback_listener_absent=true" "gpu_idle_observation_hash=$gpu_observation_hash"
    printf '%s\n' "$evidence_dir/abort-evidence.json"
    ;;
  stop)
    verify_active_identity "$identity"
    start_hash="$(json_field "$identity" record_hash)"
    [[ "$start_hash" == "$expected_start_hash" ]] || { echo "start identity hash mismatch" >&2; exit 1; }
    stop_verified_process
    hash_gpu_compute_process_observation "$evidence_dir/gpu-stop-observation"
    write_record "$evidence_dir/stop-evidence.json" "paper1.calibration.judge-service-stop-evidence.v1" \
      "manifest_hash=$manifest_hash" "environment_lock_hash=$environment_lock_hash" \
      "service_start_identity_hash=$start_hash" "pid=$pid" "process_exit_observed=true" \
      "loopback_listener_absent=true" "gpu_compute_process_observation_hash=$gpu_observation_hash"
    printf '%s\n' "$evidence_dir/stop-evidence.json"
    ;;
esac
