#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: phase0a1-service.sh start-first SERVE VLLM MODEL EVIDENCE_DIR MANIFEST_HASH PRELIMINARY_HASH | start-recovery SERVE VLLM MODEL EVIDENCE_DIR MANIFEST_HASH LOCK_HASH | status EVIDENCE_DIR | stop EVIDENCE_DIR MANIFEST_HASH LOCK_HASH" >&2
  exit 2
}

reject_proxy_environment() {
  local variable
  while IFS= read -r variable; do
    case "$variable" in
      *[Pp][Rr][Oo][Xx][Yy]*)
        if [[ -n "${!variable-}" ]]; then
          echo "proxy variable $variable must be unset before service lifecycle actions" >&2
          exit 2
        fi
        ;;
    esac
  done < <(compgen -e)
}

require_sha256() {
  [[ "$1" =~ ^[0-9a-f]{64}$ ]] || {
    echo "$2 must be a lowercase SHA-256" >&2
    exit 2
  }
}

require_exact_file() {
  local path="$1"
  local resolved
  resolved="$(realpath -e -- "$path" 2>/dev/null || true)"
  [[ "$path" == /* && -f "$path" && ! -L "$path" && "$resolved" == "$path" ]] || {
    echo "$2 must be an absolute canonical regular file without symlinks" >&2
    exit 2
  }
}

require_exact_dir() {
  local path="$1"
  local resolved
  resolved="$(realpath -e -- "$path" 2>/dev/null || true)"
  [[ "$path" == /* && -d "$path" && ! -L "$path" && "$resolved" == "$path" ]] || {
    echo "$2 must be an absolute canonical directory without symlinks" >&2
    exit 2
  }
}

json_field() {
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]]; print(str(value).lower() if isinstance(value,bool) else value)' "$1" "$2"
}

verify_service_record() {
  python3 - "$1" "$2" <<'PY'
import hashlib, json, sys

path, expected_schema = sys.argv[1:]
payload = json.load(open(path, encoding="utf-8"))
fields = {
    "paper1.calibration.service-start-identity.v1": {
        "schema_version", "generation", "mode", "manifest_hash", "binding_kind",
        "binding_hash", "pid", "executable", "cmdline_sha256", "proc_start_time",
        "serve_script", "model_path", "started_at", "calibration_only",
        "formal_parameter_authority", "record_hash",
    },
    "paper1.calibration.service-stop-evidence.v1": {
        "schema_version", "manifest_hash", "environment_lock_hash",
        "service_start_identity_hash", "pid", "process_exit_observed",
        "loopback_listener_absent", "stopped_at", "calibration_only",
        "formal_parameter_authority", "record_hash",
    },
}
if type(payload) is not dict or set(payload) != fields[expected_schema]:
    raise SystemExit("service evidence fields are not exact")
if payload["schema_version"] != expected_schema:
    raise SystemExit("service evidence schema mismatch")
record_hash = payload.pop("record_hash")
encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
if record_hash != hashlib.sha256(encoded).hexdigest():
    raise SystemExit("service evidence record hash mismatch")
PY
}

proc_cmdline_sha256() {
  sha256sum -- "/proc/$1/cmdline" | cut -d' ' -f1
}

proc_start_time() {
  awk '{print $22}' "/proc/$1/stat"
}

listener_owned_by_pid() {
  ss -ltnpH 'sport = :8000' 2>/dev/null \
    | grep -F '127.0.0.1:8000' \
    | grep -Fq "pid=$1,"
}

verify_active_identity() {
  local identity="$1"
  verify_service_record "$identity" "paper1.calibration.service-start-identity.v1"
  pid="$(json_field "$identity" pid)"
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || {
    echo "invalid recorded PID" >&2
    exit 1
  }
  pid_evidence="$(dirname -- "$identity")/pid"
  [[ -f "$pid_evidence" && ! -L "$pid_evidence" ]] || {
    echo "create-only PID evidence is absent or unsafe" >&2
    exit 1
  }
  [[ "$(< "$pid_evidence")" == "$pid" ]] || {
    echo "PID evidence and service identity mismatch" >&2
    exit 1
  }
  kill -0 "$pid" 2>/dev/null || {
    echo "stale PID: recorded process is not running" >&2
    exit 1
  }
  expected_start="$(json_field "$identity" proc_start_time)"
  [[ "$(proc_start_time "$pid")" == "$expected_start" ]] || {
    echo "process start-time mismatch" >&2
    exit 1
  }
  expected_executable="$(json_field "$identity" executable)"
  [[ "$(realpath -e -- "/proc/$pid/exe")" == "$expected_executable" ]] || {
    echo "process executable identity mismatch" >&2
    exit 1
  }
  expected_command_hash="$(json_field "$identity" cmdline_sha256)"
  [[ "$(proc_cmdline_sha256 "$pid")" == "$expected_command_hash" ]] || {
    echo "command-line identity mismatch" >&2
    exit 1
  }
  listener_owned_by_pid "$pid" || {
    echo "expected loopback listener is absent or owned by another process" >&2
    exit 1
  }
}

find_active_generation() {
  local generations="$1"
  local candidate
  local -a active=()
  shopt -s nullglob
  for candidate in "$generations"/*; do
    case "$(basename -- "$candidate")" in
      0001|0002) ;;
      *) echo "unexpected service generation" >&2; exit 1 ;;
    esac
    if [[ -f "$candidate/start-identity.json" && ! -e "$candidate/stop-evidence.json" ]]; then
      active+=("$candidate")
    fi
  done
  shopt -u nullglob
  [[ "${#active[@]}" -eq 1 ]] || {
    echo "exactly one active generation is required" >&2
    exit 1
  }
  active_generation="${active[0]}"
}

write_start_identity() {
  local output="$1"
  shift
  python3 - "$output" "$@" <<'PY'
import hashlib, json, os, sys
from datetime import datetime, timezone

output, generation, mode, manifest_hash, binding_kind, binding_hash, pid, executable, command_hash, start_time, serve_script, model_path = sys.argv[1:]
content = {
    "schema_version": "paper1.calibration.service-start-identity.v1",
    "generation": generation,
    "mode": mode,
    "manifest_hash": manifest_hash,
    "binding_kind": binding_kind,
    "binding_hash": binding_hash,
    "pid": int(pid),
    "executable": executable,
    "cmdline_sha256": command_hash,
    "proc_start_time": start_time,
    "serve_script": serve_script,
    "model_path": model_path,
    "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "calibration_only": True,
    "formal_parameter_authority": False,
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

write_stop_evidence() {
  local output="$1"
  shift
  python3 - "$output" "$@" <<'PY'
import hashlib, json, os, sys
from datetime import datetime, timezone

output, manifest_hash, lock_hash, identity_hash, pid = sys.argv[1:]
content = {
    "schema_version": "paper1.calibration.service-stop-evidence.v1",
    "manifest_hash": manifest_hash,
    "environment_lock_hash": lock_hash,
    "service_start_identity_hash": identity_hash,
    "pid": int(pid),
    "process_exit_observed": True,
    "loopback_listener_absent": True,
    "stopped_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "calibration_only": True,
    "formal_parameter_authority": False,
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

reject_proxy_environment
[[ "$#" -ge 1 ]] || usage
mode="$1"
shift

case "$mode" in
  start-first|start-recovery)
    [[ "$#" -eq 6 ]] || usage
    serve_script="$1"
    vllm_executable="$2"
    model_path="$3"
    evidence_dir="$4"
    manifest_hash="$5"
    binding_hash="$6"
    require_exact_file "$serve_script" "ABSOLUTE_SERVE_SCRIPT"
    require_exact_file "$vllm_executable" "ABSOLUTE_VLLM"
    [[ -x "$serve_script" && -x "$vllm_executable" ]] || usage
    require_exact_dir "$model_path" "ABSOLUTE_MODEL"
    require_exact_dir "$evidence_dir" "ABSOLUTE_EVIDENCE_DIR"
    require_sha256 "$manifest_hash" "MANIFEST_HASH"
    require_sha256 "$binding_hash" "binding hash"
    ;;
  status)
    [[ "$#" -eq 1 ]] || usage
    evidence_dir="$1"
    require_exact_dir "$evidence_dir" "ABSOLUTE_EVIDENCE_DIR"
    ;;
  stop)
    [[ "$#" -eq 3 ]] || usage
    evidence_dir="$1"
    manifest_hash="$2"
    lock_hash="$3"
    require_exact_dir "$evidence_dir" "ABSOLUTE_EVIDENCE_DIR"
    require_sha256 "$manifest_hash" "MANIFEST_HASH"
    require_sha256 "$lock_hash" "LOCK_HASH"
    ;;
  *) usage ;;
esac

lock_file="$evidence_dir/.phase0a1-service.lock"
exec 9> "$lock_file"
flock -x 9
generations="$evidence_dir/service-generations"

case "$mode" in
  start-first|start-recovery)
    mkdir -p -- "$generations"
    generations_resolved="$(realpath -e -- "$generations" 2>/dev/null || true)"
    [[ -d "$generations" && ! -L "$generations" && "$generations_resolved" == "$generations" ]] || {
      echo "service generation root is unsafe" >&2
      exit 1
    }
    if [[ "$mode" == "start-first" ]]; then
      generation="0001"
      binding_kind="preliminary-inspection"
      [[ ! -e "$generations/0001" && ! -e "$generations/0002" ]] || {
        echo "start-first requires no existing service generation" >&2
        exit 1
      }
    else
      generation="0002"
      binding_kind="environment-lock"
      [[ -f "$generations/0001/start-identity.json" && -f "$generations/0001/stop-evidence.json" && ! -e "$generations/0002" ]] || {
        echo "start-recovery requires one completely stopped first generation" >&2
        exit 1
      }
      verify_service_record "$generations/0001/stop-evidence.json" "paper1.calibration.service-stop-evidence.v1"
      [[ "$(json_field "$generations/0001/stop-evidence.json" manifest_hash)" == "$manifest_hash" ]] || exit 1
      [[ "$(json_field "$generations/0001/stop-evidence.json" environment_lock_hash)" == "$binding_hash" ]] || exit 1
    fi
    generation_dir="$generations/$generation"
    mkdir -- "$generation_dir"
    (
      exec 9>&-
      exec "$serve_script" "$vllm_executable" "$model_path"
    ) > "$generation_dir/service.log" 2>&1 &
    pid="$!"
    start_committed=false
    cleanup_failed_start() {
      if [[ "$start_committed" != true ]] && kill -0 "$pid" 2>/dev/null; then
        kill -TERM "$pid" 2>/dev/null || true
        for _ in $(seq 1 10); do
          kill -0 "$pid" 2>/dev/null || break
          sleep 1
        done
        kill -KILL "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
      fi
    }
    trap cleanup_failed_start EXIT
    trap 'cleanup_failed_start; exit 129' HUP
    trap 'cleanup_failed_start; exit 130' INT
    trap 'cleanup_failed_start; exit 143' TERM
    set -o noclobber
    printf '%s\n' "$pid" > "$generation_dir/pid"
    set +o noclobber
    for _ in $(seq 1 120); do
      kill -0 "$pid" 2>/dev/null || {
        echo "vLLM exited before health" >&2
        exit 1
      }
      if listener_owned_by_pid "$pid" && curl --fail --silent --show-error --max-time 2 --max-redirs 0 http://127.0.0.1:8000/health >/dev/null; then
        break
      fi
      sleep 1
    done
    listener_owned_by_pid "$pid" || {
      echo "vLLM did not establish the required loopback listener" >&2
      exit 1
    }
    curl --fail --silent --show-error --max-time 2 --max-redirs 0 http://127.0.0.1:8000/health >/dev/null
    executable="$(realpath -e -- "/proc/$pid/exe")"
    command_hash="$(proc_cmdline_sha256 "$pid")"
    start_time="$(proc_start_time "$pid")"
    identity="$generation_dir/start-identity.json"
    write_start_identity "$identity" "$generation" "$mode" "$manifest_hash" "$binding_kind" "$binding_hash" "$pid" "$executable" "$command_hash" "$start_time" "$serve_script" "$model_path"
    verify_active_identity "$identity"
    start_committed=true
    trap - EXIT HUP INT TERM
    printf '%s\n' "$identity"
    ;;
  status)
    [[ -d "$generations" && ! -L "$generations" ]] || {
      echo "no active generation" >&2
      exit 1
    }
    find_active_generation "$generations"
    identity="$active_generation/start-identity.json"
    verify_active_identity "$identity"
    printf '%s\n' "$identity"
    ;;
  stop)
    [[ -d "$generations" && ! -L "$generations" ]] || {
      echo "no active generation" >&2
      exit 1
    }
    find_active_generation "$generations"
    identity="$active_generation/start-identity.json"
    [[ "$(json_field "$identity" manifest_hash)" == "$manifest_hash" ]] || {
      echo "manifest identity mismatch" >&2
      exit 1
    }
    if [[ "$(json_field "$identity" binding_kind)" == "environment-lock" && "$(json_field "$identity" binding_hash)" != "$lock_hash" ]]; then
      echo "environment-lock identity mismatch" >&2
      exit 1
    fi
    verify_active_identity "$identity"
    identity_hash="$(json_field "$identity" record_hash)"
    kill -TERM "$pid"
    exited=false
    for _ in $(seq 1 60); do
      if ! kill -0 "$pid" 2>/dev/null; then
        exited=true
        break
      fi
      sleep 1
    done
    [[ "$exited" == true ]] || {
      echo "verified service did not exit after TERM" >&2
      exit 1
    }
    ! ss -ltnH 'sport = :8000' 2>/dev/null | grep -Fq '127.0.0.1:8000' || {
      echo "loopback listener remains after process exit" >&2
      exit 1
    }
    stop_evidence="$active_generation/stop-evidence.json"
    write_stop_evidence "$stop_evidence" "$manifest_hash" "$lock_hash" "$identity_hash" "$pid"
    verify_service_record "$stop_evidence" "paper1.calibration.service-stop-evidence.v1"
    printf '%s\n' "$stop_evidence"
    ;;
esac
