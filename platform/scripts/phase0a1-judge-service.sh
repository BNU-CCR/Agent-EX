#!/usr/bin/env bash
set -euo pipefail
umask 077

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

hash_gpu_compute_process_observation() {
  local output="$1"
  nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv,noheader,nounits > "$output"
  [[ ! -s "$output" ]] || { echo "GPU compute processes remain" >&2; return 1; }
  gpu_observation_hash="$(sha256sum -- "$output" | cut -d' ' -f1)"
}

assert_gpu_compute_processes_absent() {
  local observation
  observation="$(timeout --signal=KILL 15s nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv,noheader,nounits)" || {
    echo "could not verify final GPU state" >&2
    return 1
  }
  [[ -z "$observation" ]] || { echo "GPU compute processes remain" >&2; return 1; }
}

assert_loopback_listener_absent() {
  local sockets
  sockets="$(ss -ltnH 'sport = :8000')" || {
    echo "could not verify final port 8000 listener state" >&2
    return 1
  }
  [[ -z "$sockets" ]] || {
    echo "judge port 8000 remains occupied after process exit" >&2
    return 1
  }
}

verify_evidence_directory_binding() {
  "$python_executable" - "$evidence_directory_fd" "$evidence_dir" \
    "$evidence_directory_device" "$evidence_directory_inode" <<'PY'
import os
import stat
import sys

directory_fd = int(sys.argv[1])
path = sys.argv[2]
expected = (int(sys.argv[3]), int(sys.argv[4]))

held = os.fstat(directory_fd)
if not stat.S_ISDIR(held.st_mode) or (held.st_dev, held.st_ino) != expected:
    raise SystemExit("held evidence directory identity changed")
try:
    current = os.stat(path, follow_symlinks=False)
except OSError as error:
    raise SystemExit(f"evidence directory pathname identity changed: {error}")
if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != expected:
    raise SystemExit("evidence directory pathname identity changed")
PY
}

listener_owned_by_pid() {
  ss -ltnpH 'sport = :8000' 2>/dev/null \
    | grep -F '127.0.0.1:8000' \
    | grep -Fq "pid=$1,"
}

verify_active_identity() {
  local identity="$1"
  [[ -f "$identity" && ! -L "$identity" ]] || { echo "judge start identity is absent or unsafe" >&2; exit 1; }
  local identity_values
  identity_values="$("$python_executable" - "$identity" "$python_executable" <<'PY'
import hashlib
import hmac
import json
import os
import re
import stat
import sys

identity, expected_python = sys.argv[1:]

def fail(message):
    raise SystemExit(message)

def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            fail(f"duplicate JSON field: {name}")
        result[name] = value
    return result

def reject_constant(value):
    fail(f"non-finite JSON value: {value}")

flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
try:
    fd = os.open(identity, flags)
except OSError as error:
    fail(f"judge start identity is absent or unsafe: {error}")
with os.fdopen(fd, "r", encoding="utf-8") as stream:
    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
        fail("judge start identity is not a regular file")
    try:
        payload = json.load(
            stream,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        fail(f"invalid judge start identity JSON: {error}")

expected_fields = {
    "schema_version", "authorization_hash", "pid", "executable",
    "cmdline_sha256", "serve_script", "control_python", "model_path",
    "proc_start_time", "process_group_id", "session_id", "calibration_only",
    "formal_parameter_authority", "metadata", "record_hash",
}
if type(payload) is not dict or set(payload) != expected_fields:
    fail("judge start identity fields are not exact")
if payload["schema_version"] != "paper1.calibration.judge-service-start-identity.v1":
    fail("judge start identity schema mismatch")
if type(payload["pid"]) is not int or payload["pid"] <= 0:
    fail("invalid judge service PID")
for name in ("proc_start_time", "process_group_id", "session_id"):
    if type(payload[name]) is not int or payload[name] <= 0:
        fail(f"invalid judge start identity {name}")
for name in (
    "authorization_hash", "executable", "cmdline_sha256", "serve_script",
    "control_python", "model_path", "record_hash",
):
    if type(payload[name]) is not str:
        fail(f"invalid judge start identity {name}")
for name in ("authorization_hash", "cmdline_sha256", "record_hash"):
    if re.fullmatch(r"[0-9a-f]{64}", payload[name]) is None:
        fail(f"invalid judge start identity {name}")
metadata = {
    "calibration_only": True,
    "formal_parameter_authority": False,
    "research_parameter_status": "not_frozen",
}
if payload["calibration_only"] is not True:
    fail("judge start identity calibration marker mismatch")
if payload["formal_parameter_authority"] is not False:
    fail("judge start identity authority marker mismatch")
if (
    type(payload["metadata"]) is not dict
    or set(payload["metadata"]) != set(metadata)
    or payload["metadata"].get("calibration_only") is not True
    or payload["metadata"].get("formal_parameter_authority") is not False
    or payload["metadata"].get("research_parameter_status") != "not_frozen"
):
    fail("judge start identity metadata mismatch")
if payload["control_python"] != expected_python:
    fail("control Python identity mismatch")
content = {name: value for name, value in payload.items() if name != "record_hash"}
encoded = json.dumps(
    content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
).encode()
if not hmac.compare_digest(payload["record_hash"], hashlib.sha256(encoded).hexdigest()):
    fail("judge start identity record hash mismatch")

pid = payload["pid"]
try:
    stat_text = open(f"/proc/{pid}/stat", encoding="utf-8").read()
    fields = stat_text[stat_text.rfind(")") + 2:].split()
    live_pgrp, live_session, live_start = int(fields[2]), int(fields[3]), int(fields[19])
    live_executable = os.path.realpath(f"/proc/{pid}/exe")
    live_cmdline = hashlib.sha256(open(f"/proc/{pid}/cmdline", "rb").read()).hexdigest()
except (FileNotFoundError, IndexError, OSError, ValueError):
    fail("stale judge service PID")
if live_start != payload["proc_start_time"]:
    fail("process start-time mismatch")
if live_pgrp != payload["process_group_id"] or live_pgrp != pid:
    fail("process-group identity mismatch")
if live_session != payload["session_id"] or live_session != pid:
    fail("session identity mismatch")
if live_executable != payload["executable"]:
    fail("judge service executable identity mismatch")
if live_cmdline != payload["cmdline_sha256"]:
    fail("judge service command identity mismatch")
print(
    pid,
    payload["record_hash"],
    payload["authorization_hash"],
    payload["process_group_id"],
)
PY
)"
  read -r pid start_hash recorded_authorization_hash process_group_id <<< "$identity_values"
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || { echo "invalid judge service PID" >&2; exit 1; }
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
    elif name in {"pid", "proc_start_time", "process_group_id", "session_id"}:
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
fd = os.open(
    output,
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
    0o600,
)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    json.dump(payload, stream, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
PY
}

terminate_process_group() {
  local group_id="$1" leader_pid="$2" exited=false
  kill -TERM -- "-$group_id" 2>/dev/null || kill -TERM -- "$leader_pid" 2>/dev/null || true
  for _ in $(seq 1 50); do
    if ! kill -0 -- "-$group_id" 2>/dev/null; then exited=true; break; fi
    sleep 0.1
  done
  if [[ "$exited" != true ]]; then
    echo "verified judge process group ignored TERM; escalating to KILL" >&2
    kill -KILL -- "-$group_id" 2>/dev/null || true
    wait "$leader_pid" 2>/dev/null || true
    for _ in $(seq 1 50); do
      if ! kill -0 -- "-$group_id" 2>/dev/null; then exited=true; break; fi
      sleep 0.1
    done
  fi
  wait "$leader_pid" 2>/dev/null || true
  [[ "$exited" == true ]] || { echo "verified judge process group did not exit" >&2; return 1; }
}

stop_verified_process() {
  terminate_process_group "$process_group_id" "$pid"
  assert_loopback_listener_absent
}

reject_proxy_environment
[[ "$#" -ge 1 ]] || usage
original_arguments=("$@")
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

if [[ -z "${AGENT_EX_JUDGE_EVIDENCE_FD-}" ]]; then
  exec "$python_executable" -c '
import os
import shutil
import sys

script, evidence_dir, *arguments = sys.argv[1:]
flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
directory_fd = os.open(evidence_dir, flags)
directory_stat = os.fstat(directory_fd)
os.set_inheritable(directory_fd, True)
environment = dict(os.environ)
environment["AGENT_EX_JUDGE_EVIDENCE_FD"] = str(directory_fd)
environment["AGENT_EX_JUDGE_EVIDENCE_DEVICE"] = str(directory_stat.st_dev)
environment["AGENT_EX_JUDGE_EVIDENCE_INODE"] = str(directory_stat.st_ino)
bash = shutil.which("bash")
if bash is None:
    raise SystemExit("bash executable is unavailable")
os.execve(bash, ["bash", os.path.realpath(script), *arguments], environment)
' "$0" "$evidence_dir" "${original_arguments[@]}"
fi
evidence_directory_fd="$AGENT_EX_JUDGE_EVIDENCE_FD"
evidence_directory_device="$AGENT_EX_JUDGE_EVIDENCE_DEVICE"
evidence_directory_inode="$AGENT_EX_JUDGE_EVIDENCE_INODE"
[[ "$evidence_directory_fd" =~ ^[0-9]+$ ]] || { echo "invalid evidence directory descriptor" >&2; exit 1; }
evidence_anchor="/proc/$$/fd/$evidence_directory_fd"
verify_evidence_directory_binding

lock_dir="$evidence_anchor/.phase0a1-judge-service.lock.d"
mkdir -- "$lock_dir" 2>/dev/null || {
  echo "judge lifecycle lock is already held or unsafe" >&2
  exit 1
}
chmod 700 -- "$lock_dir"
release_lock() {
  rmdir -- "$lock_dir" 2>/dev/null || true
}
trap release_lock EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
set -o noclobber
identity="$evidence_anchor/start-identity.json"

case "$mode" in
  start)
    [[ ! -e "$identity" && ! -e "$evidence_anchor/stop-evidence.json" && ! -e "$evidence_anchor/abort-evidence.json" ]] || {
      echo "judge lifecycle evidence already exists" >&2; exit 1;
    }
    (
      exec setsid "$serve_script" "$vllm_executable" "$model_path"
    ) > "$evidence_anchor/service.log" 2>&1 &
    pid="$!"
    process_group_id="$pid"
    committed=false
    cleanup_failed_start() {
      local cleanup_status=0
      if [[ "$committed" != true ]]; then
        terminate_process_group "$process_group_id" "$pid" || cleanup_status=1
        assert_loopback_listener_absent || cleanup_status=1
        assert_gpu_compute_processes_absent || cleanup_status=1
      fi
      return "$cleanup_status"
    }
    failed_start_exit() {
      local original_status="$1" cleanup_status=0
      trap - EXIT HUP INT TERM
      cleanup_failed_start || cleanup_status=$?
      release_lock
      [[ "$original_status" -ne 0 ]] || original_status="$cleanup_status"
      exit "$original_status"
    }
    failed_start_signal() {
      local signal_status="$1"
      trap - EXIT HUP INT TERM
      cleanup_failed_start || true
      release_lock
      exit "$signal_status"
    }
    trap 'failed_start_exit $?' EXIT
    trap 'failed_start_signal 129' HUP
    trap 'failed_start_signal 130' INT
    trap 'failed_start_signal 143' TERM
    for _ in $(seq 1 300); do
      kill -0 "$pid" 2>/dev/null || { echo "vLLM exited before judge health" >&2; exit 1; }
      if listener_owned_by_pid "$pid" && curl --fail --silent --max-time 2 --max-redirs 0 http://127.0.0.1:8000/health >/dev/null; then break; fi
      sleep 1
    done
    listener_owned_by_pid "$pid" || { echo "judge service did not become healthy" >&2; exit 1; }
    verify_evidence_directory_binding
    proc_values="$("$python_executable" - "$pid" <<'PY'
import sys

pid = int(sys.argv[1])
text = open(f"/proc/{pid}/stat", encoding="utf-8").read()
fields = text[text.rfind(")") + 2:].split()
print(int(fields[19]), int(fields[2]), int(fields[3]))
PY
)"
    read -r proc_start_time process_group_id session_id <<< "$proc_values"
    [[ "$process_group_id" == "$pid" && "$session_id" == "$pid" ]] || {
      echo "judge service did not establish the expected session" >&2
      exit 1
    }
    write_record "$identity" "paper1.calibration.judge-service-start-identity.v1" \
      "authorization_hash=$authorization_hash" "pid=$pid" \
      "executable=$(realpath -e -- "/proc/$pid/exe")" \
      "cmdline_sha256=$(sha256sum -- "/proc/$pid/cmdline" | cut -d' ' -f1)" \
      "serve_script=$serve_script" "control_python=$python_executable" "model_path=$model_path" \
      "proc_start_time=$proc_start_time" "process_group_id=$process_group_id" "session_id=$session_id"
    verify_active_identity "$identity"
    committed=true
    trap release_lock EXIT
    trap - HUP INT TERM
    printf '%s\n' "$identity"
    ;;
  status)
    verify_evidence_directory_binding
    verify_active_identity "$identity"
    printf '%s\n' "$identity"
    ;;
  abort-pre-manifest)
    verify_active_identity "$identity"
    [[ "$recorded_authorization_hash" == "$authorization_hash" ]] || { echo "authorization identity mismatch" >&2; exit 1; }
    [[ "$start_hash" == "$expected_start_hash" ]] || { echo "start identity hash mismatch" >&2; exit 1; }
    stop_verified_process
    verify_evidence_directory_binding
    hash_gpu_compute_process_observation "$evidence_anchor/gpu-abort-observation"
    lock_value="$environment_lock_hash"; [[ "$lock_value" == "-" ]] && lock_value="null"
    write_record "$evidence_anchor/abort-evidence.json" "paper1.calibration.judge-pre-manifest-abort-evidence.v1" \
      "authorization_hash=$authorization_hash" "service_start_identity_hash=$start_hash" \
      "environment_lock_hash=$lock_value" "process_exit_observed=true" \
      "loopback_listener_absent=true" "gpu_idle_observation_hash=$gpu_observation_hash"
    printf '%s\n' "$evidence_dir/abort-evidence.json"
    ;;
  stop)
    verify_active_identity "$identity"
    [[ "$start_hash" == "$expected_start_hash" ]] || { echo "start identity hash mismatch" >&2; exit 1; }
    stop_verified_process
    verify_evidence_directory_binding
    hash_gpu_compute_process_observation "$evidence_anchor/gpu-stop-observation"
    write_record "$evidence_anchor/stop-evidence.json" "paper1.calibration.judge-service-stop-evidence.v1" \
      "manifest_hash=$manifest_hash" "environment_lock_hash=$environment_lock_hash" \
      "service_start_identity_hash=$start_hash" "pid=$pid" "process_exit_observed=true" \
      "loopback_listener_absent=true" "gpu_compute_process_observation_hash=$gpu_observation_hash"
    printf '%s\n' "$evidence_dir/stop-evidence.json"
    ;;
esac
