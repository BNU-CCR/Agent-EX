"""Synthetic model-directory metadata only; never load a model."""

import json

import pytest

from agent_ex.identity_network.benchmark_snapshot import snapshot_runtime


def test_snapshot_binds_files_tokenizer_template_and_revision(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "model_type": "qwen3",
                "architectures": ["Qwen3ForCausalLM"],
                "hidden_size": 4096,
                "intermediate_size": 12288,
                "num_hidden_layers": 36,
                "num_attention_heads": 32,
                "num_key_value_heads": 8,
                "head_dim": 128,
                "vocab_size": 151936,
                "tie_word_embeddings": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "tokenizer_config.json").write_text(
        json.dumps({"chat_template": "synthetic template"}), encoding="utf-8"
    )
    (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    (tmp_path / "model.safetensors").write_bytes(b"synthetic weights, not a model")
    first = snapshot_runtime(
        tmp_path,
        model_revision="a" * 40,
        served_model_name="Qwen3-8B",
        vllm_version="synthetic-test",
    )
    (tmp_path / "tokenizer.json").write_text('{"changed":true}', encoding="utf-8")
    second = snapshot_runtime(
        tmp_path,
        model_revision="a" * 40,
        served_model_name="Qwen3-8B",
        vllm_version="synthetic-test",
    )
    assert first["tokenizer_hash"] != second["tokenizer_hash"]
    assert first["model_files_hash"] != second["model_files_hash"]
    assert first["chat_template_hash"] == second["chat_template_hash"]
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    config["hidden_size"] = 1024
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="8B architecture"):
        snapshot_runtime(
            tmp_path,
            model_revision="a" * 40,
            served_model_name="Qwen3-8B",
            vllm_version="synthetic-test",
        )


def test_missing_template_or_weights_fails_closed(tmp_path):
    with pytest.raises(ValueError):
        snapshot_runtime(
            tmp_path,
            model_revision="a" * 40,
            served_model_name="Qwen3-8B",
            vllm_version="synthetic-test",
        )
