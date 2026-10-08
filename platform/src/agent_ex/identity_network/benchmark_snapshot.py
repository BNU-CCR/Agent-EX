"""Read-only model-file snapshot; no model loading or network interaction.

Revision is an operator-supplied repository commit, cross-checked when the model
directory itself is an HF snapshot hash. Content hashes bind actual local bytes.
This does not prove an already-running service loaded that snapshot; service
ownership/launch-command inspection remains part of cloud acceptance.
"""

import hashlib
from pathlib import Path
import re

from ..domain import canonical_payload_hash
from .dispatch import _strict_json
from .benchmark_run import validate_runtime

# Architecture fingerprint, not a proof of authentic weights or live service identity.
# Source: https://huggingface.co/Qwen/Qwen3-8B/raw/main/config.json
QWEN3_8B_ARCHITECTURE = {
    "architectures": ["Qwen3ForCausalLM"],
    "model_type": "qwen3",
    "hidden_size": 4096,
    "intermediate_size": 12288,
    "num_hidden_layers": 36,
    "num_attention_heads": 32,
    "num_key_value_heads": 8,
    "head_dim": 128,
    "vocab_size": 151936,
    "tie_word_embeddings": False,
}


def snapshot_runtime(model_dir, *, model_revision, served_model_name, vllm_version):
    root = Path(model_dir).resolve(strict=True)
    if not root.is_dir() or re.fullmatch(r"[0-9a-f]{40}", str(model_revision)) is None:
        raise ValueError("existing model directory and exact revision required")
    if re.fullmatch(r"[0-9a-f]{40}", root.name) and root.name != model_revision:
        raise ValueError("snapshot directory/revision differs")
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(root).parts)
    )
    names = {path.relative_to(root).as_posix(): path for path in paths}
    if not {"config.json", "tokenizer_config.json", "tokenizer.json"} <= set(names) or not any(
        name.endswith(".safetensors") for name in names
    ):
        raise ValueError("complete Qwen model/tokenizer files required")
    config = _strict_json(names["config.json"].read_text(encoding="utf-8"))
    if any(
        type(config.get(key)) is not type(value) or config.get(key) != value
        for key, value in QWEN3_8B_ARCHITECTURE.items()
    ):
        raise ValueError("Qwen3-8B architecture configuration required")
    identities = {
        name: (path.stat().st_size, path.stat().st_mtime_ns) for name, path in names.items()
    }
    hashes = {}
    for name, path in names.items():
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        hashes[name] = digest.hexdigest()
    tokenizer = {
        name: value
        for name, value in hashes.items()
        if Path(name).name.startswith("tokenizer")
        or Path(name).name
        in {"special_tokens_map.json", "added_tokens.json", "vocab.json", "merges.txt"}
    }
    if "chat_template.jinja" in names:
        template = names["chat_template.jinja"].read_bytes()
    else:
        value = _strict_json(names["tokenizer_config.json"].read_text(encoding="utf-8")).get(
            "chat_template"
        )
        if type(value) is not str or not value:
            raise ValueError("exact active chat template required")
        template = value.encode("utf-8")
    if any(
        (path.stat().st_size, path.stat().st_mtime_ns) != identities[name]
        for name, path in names.items()
    ):
        raise ValueError("model files changed during snapshot")
    result = {
        "model_id": "Qwen/Qwen3-8B",
        "model_revision": model_revision,
        "model_files_hash": canonical_payload_hash(hashes),
        "tokenizer_hash": canonical_payload_hash(tokenizer),
        "chat_template_hash": hashlib.sha256(template).hexdigest(),
        "vllm_version": vllm_version,
        "dtype": "bfloat16",
        "enable_thinking": False,
        "served_model_name": served_model_name,
        "endpoint": "http://127.0.0.1:8000/v1/chat/completions",
    }
    validate_runtime(result)
    return result
