"""Real SQLite/full source tests; only the Linux lease boundary is simulated."""

import importlib
import json
import sqlite3
import os

import pytest

from test_identity_network_manipulation_requests import bound  # noqa: F401
from test_identity_network_manipulation_lock import mock_syscalls  # noqa: F401
from agent_ex.identity_network.manipulation_requests import build_manipulation_request_plan
from agent_ex.domain import _json_ready, canonical_payload_hash
from agent_ex.phase0b.vllm_event_adapter import (
    Phase0BVllmEventAdapter,
    Phase0BVllmEventResponse,
    Phase0BVllmTransportEvidence,
)


def module():
    name = "agent_ex.identity_network.manipulation_store"
    assert importlib.util.find_spec(name), "dedicated SQLite manipulation store is missing"
    return importlib.import_module(name)


@pytest.fixture
def setup(bound, tmp_path, mock_syscalls):  # noqa: F811
    lock, _ = mock_syscalls
    with lock.acquire(tmp_path) as lease:
        yield tmp_path, build_manipulation_request_plan(**bound), bound["checked_at"], lease


def response(plan, request, *, content=None, model=None):
    adapter = Phase0BVllmEventAdapter(
        plan.payload["adapter_binding"]["endpoint"],
        served_model_name=plan.payload["adapter_binding"]["served_model_name"],
    )
    raw = json.dumps(
        {
            "id": "synthetic",
            "model": model or plan.payload["adapter_binding"]["served_model_name"],
            "choices": [
                {
                    "message": {
                        "content": content
                        or json.dumps(
                            {
                                "stance": "label-5",
                                "confidence": 4,
                                "public_reason": "synthetic reason",
                            }
                        )
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        }
    ).encode()
    outcome, error, retry, usage, finish = adapter._classify(
        status=200,
        headers={"x-request-id": "synthetic"},
        raw_body=raw,
        truncated=False,
        provider_request_id="synthetic",
    )
    transport = Phase0BVllmTransportEvidence.create(
        request=request,
        http_status=200,
        response_headers={"x-request-id": "synthetic"},
        provider_request_id="synthetic",
        request_body=adapter._request_body(request),
        raw_body=raw,
        body_truncated=False,
        started_at="2026-10-01T00:06:00Z",
        ended_at="2026-10-01T00:06:01Z",
        latency_seconds=1.0,
        outcome=outcome,
        error_code=error,
    )
    return Phase0BVllmEventResponse.create(
        request=request,
        outcome=outcome,
        error_code=error,
        retry_after_seconds=retry,
        provider_request_id="synthetic",
        usage=usage,
        finish_reason=finish,
        raw_body=raw,
        transport_evidence=transport,
    )


def create(setup):
    root, plan, checked, lease = setup
    return module().ManipulationStore.create(root, plan=plan, checked_at=checked, lease=lease)


def wire(plan, request):
    return Phase0BVllmEventAdapter(
        plan.payload["adapter_binding"]["endpoint"],
        served_model_name=plan.payload["adapter_binding"]["served_model_name"],
    )._request_body(request)


def test_complete_inventory_intent_durable_and_readonly(setup):
    root, plan, checked, lease = setup
    store = create(setup)
    assert isinstance(store.requests, tuple)
    for request in store.requests:
        store.record_before_dispatch(request, wire(plan, request))
        with sqlite3.connect(root / "manipulation.sqlite3") as observer:
            assert observer.execute(
                "SELECT kind FROM transitions ORDER BY seq DESC LIMIT 1"
            ).fetchone() == ("INTENT",)
        store.store_response(response(plan, request))
        store.terminalize_saved_response()
    assert store.summary()["execution_complete"]
    assert store.summary()["valid_count"] == 4
    store.close()
    before = (root / "manipulation.sqlite3").read_bytes()
    summary = module().ManipulationStore.verify(root, plan=plan, checked_at=checked)
    assert summary["execution_complete"] and summary["formal_parameter_authority"] is False
    assert summary["inventory_contract"] == "quartet-v1-local-contract-only"
    assert summary["cloud_launch_eligible"] is False
    assert (root / "manipulation.sqlite3").read_bytes() == before
    with pytest.raises(FileExistsError):
        create(setup)
    with module().ManipulationStore.open(
        root, plan=plan, checked_at=checked, lease=lease
    ) as reopened:
        assert reopened.summary() == summary


def test_intent_and_saved_response_resume_without_resend(setup):
    root, plan, checked, lease = setup
    store = create(setup)
    request = store.requests[0]
    store.record_before_dispatch(request, wire(plan, request))
    store.close()
    store = module().ManipulationStore.open(root, plan=plan, checked_at=checked, lease=lease)
    with pytest.raises(ValueError):
        store.record_before_dispatch(request, wire(plan, request))
    store.store_response(response(plan, request))
    store.close()
    with module().ManipulationStore.open(root, plan=plan, checked_at=checked, lease=lease) as store:
        assert store.summary()["phase"] == "RESPONSE_STORED"
        store.terminalize_saved_response()
        assert store.summary()["valid_count"] == 1
        with pytest.raises(ValueError):
            store.terminalize_saved_response()


@pytest.mark.parametrize("fault", ["parse", "model"])
def test_invalid_stops_suffix(setup, fault):
    _, plan, _, _ = setup
    with create(setup) as store:
        first = store.requests[0]
        store.record_before_dispatch(first, wire(plan, first))
        store.store_response(
            response(
                plan,
                first,
                content="not-json" if fault == "parse" else None,
                model="foreign" if fault == "model" else None,
            )
        )
        store.terminalize_saved_response()
        assert store.summary()["phase"] == "INVALID"
        with pytest.raises(ValueError):
            store.record_before_dispatch(store.requests[1], wire(plan, store.requests[1]))


def test_hot_path_no_cold_derivation_and_external_change_replay(setup, monkeypatch):
    root, plan, _, _ = setup
    m = module()
    real = m.validate_manipulation_request_plan
    calls = []

    def validate(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(m, "validate_manipulation_request_plan", validate)
    with create(setup) as store:
        first = store.requests[0]
        store.record_before_dispatch(first, wire(plan, first))
        store.store_response(response(plan, first))
        store.terminalize_saved_response()
        assert len(calls) == 1
        with sqlite3.connect(root / "manipulation.sqlite3") as edit:
            edit.execute("UPDATE transitions SET record_json='{}' WHERE seq=1")
        with pytest.raises(ValueError):
            store.record_before_dispatch(store.requests[1], wire(plan, store.requests[1]))
        assert len(calls) == 2


def test_order_wire_duplicates_and_lease(setup):
    _, plan, _, lease = setup
    with create(setup) as store:
        with pytest.raises(ValueError):
            store.record_before_dispatch(store.requests[1], wire(plan, store.requests[1]))
        with pytest.raises(ValueError):
            store.record_before_dispatch(store.requests[0], b"{}")
        first = store.requests[0]
        store.record_before_dispatch(first, wire(plan, first))
        with pytest.raises(ValueError):
            store.store_response(response(plan, store.requests[1]))
        lease.close()
        with pytest.raises(RuntimeError):
            store.store_response(response(plan, first))


def test_wrong_root_missing_verify_and_hardlink(setup):
    root, plan, checked, lease = setup
    other = root / "other"
    other.mkdir()
    with pytest.raises(RuntimeError):
        module().ManipulationStore.create(other, plan=plan, checked_at=checked, lease=lease)
    with pytest.raises(FileNotFoundError):
        module().ManipulationStore.verify(root, plan=plan, checked_at=checked)
    assert not (root / "manipulation.sqlite3").exists()
    store = create(setup)
    store.close()
    os.link(root / "manipulation.sqlite3", other / "linked")
    with pytest.raises(ValueError):
        module().ManipulationStore.verify(root, plan=plan, checked_at=checked)


@pytest.mark.parametrize("target", ["intent", "response", "terminal", "metadata", "inventory"])
def test_rehashed_substitutions_fail_replay(setup, target):
    root, plan, checked, _ = setup
    with create(setup) as store:
        first = store.requests[0]
        store.record_before_dispatch(first, wire(plan, first))
        store.store_response(response(plan, first))
        store.terminalize_saved_response()
    with sqlite3.connect(root / "manipulation.sqlite3") as edit:
        if target == "metadata":
            edit.execute("UPDATE metadata SET plan_hash=?", ("a" * 64,))
        elif target == "inventory":
            entry = json.loads(
                edit.execute("SELECT entry_json FROM trials WHERE ordinal=0").fetchone()[0]
            )
            entry["request"]["model_seed"] += 1
            edit.execute("UPDATE trials SET entry_json=? WHERE ordinal=0", (json.dumps(entry),))
        else:
            rows = edit.execute("SELECT seq, record_json FROM transitions ORDER BY seq").fetchall()
            records = [json.loads(row[1]) for row in rows]
            index = {"intent": 0, "response": 1, "terminal": 2}[target]
            if target == "intent":
                records[index]["evidence"]["wire_sha256"] = "a" * 64
            elif target == "response":
                payload = records[index]["evidence"]
                payload["usage"]["total_tokens"] += 1
                payload["record_hash"] = canonical_payload_hash(
                    {k: v for k, v in payload.items() if k != "record_hash"}
                )
            else:
                payload = records[index]["evidence"]
                payload["parsed_response"]["confidence"] = 2
                payload["record_hash"] = canonical_payload_hash(
                    {k: v for k, v in payload.items() if k != "record_hash"}
                )
            tail = None
            for seq, record in enumerate(records, 1):
                record["previous_record_hash"] = tail
                record["record_hash"] = canonical_payload_hash(
                    {k: v for k, v in record.items() if k != "record_hash"}
                )
                tail = record["record_hash"]
                edit.execute(
                    "UPDATE transitions SET record_json=? WHERE seq=?", (json.dumps(record), seq)
                )
    with pytest.raises(ValueError):
        module().ManipulationStore.verify(root, plan=plan, checked_at=checked)


def test_forged_success_and_response_wire_rejected(setup):
    _, plan, _, _ = setup
    with create(setup) as store:
        first = store.requests[0]
        store.record_before_dispatch(first, wire(plan, first))
        actual = response(plan, first, model="foreign")
        values = _json_ready(actual.content_payload())
        values["outcome"], values["error_code"] = "response", None
        transport = _json_ready(actual.transport_evidence.content_payload())
        transport["outcome"], transport["error_code"] = "response", None
        typed_transport = Phase0BVllmTransportEvidence(
            **transport, record_hash=canonical_payload_hash(transport)
        )
        values["transport_evidence"] = typed_transport.to_payload()
        forged = Phase0BVllmEventResponse(
            **{**values, "transport_evidence": typed_transport},
            record_hash=canonical_payload_hash(values),
        )
        with pytest.raises(ValueError):
            store.store_response(forged)
        actual = response(plan, first)
        transport = _json_ready(actual.transport_evidence.content_payload())
        import base64
        import hashlib

        transport.update(
            request_body_base64=base64.b64encode(b"{}").decode(),
            request_body_sha256=hashlib.sha256(b"{}").hexdigest(),
            request_body_bytes=2,
        )
        changed = Phase0BVllmTransportEvidence(
            **transport, record_hash=canonical_payload_hash(transport)
        )
        values = _json_ready(actual.content_payload())
        values["transport_evidence"] = changed.to_payload()
        forged = Phase0BVllmEventResponse(
            **{**values, "transport_evidence": changed}, record_hash=canonical_payload_hash(values)
        )
        with pytest.raises(ValueError):
            store.store_response(forged)


def test_external_late_prefix_change_between_guard_and_transaction(setup, monkeypatch):
    root, plan, _, _ = setup
    with create(setup) as store:
        first = store.requests[0]
        store.record_before_dispatch(first, wire(plan, first))
        store.store_response(response(plan, first))
        store.terminalize_saved_response()
        original = store._refresh
        calls = []

        def scheduled_edit():
            original()
            calls.append(1)
            if len(calls) == 2:
                with sqlite3.connect(root / "manipulation.sqlite3") as edit:
                    edit.execute("UPDATE transitions SET record_json='{}' WHERE seq=1")

        monkeypatch.setattr(store, "_refresh", scheduled_edit)
        with pytest.raises(ValueError):
            store.record_before_dispatch(store.requests[1], wire(plan, store.requests[1]))


def test_terminal_parse_does_not_copy_complete_source_plan(setup, monkeypatch):
    from agent_ex.identity_network import manipulation_evidence

    _, plan, _, _ = setup
    with create(setup) as store:
        first = store.requests[0]
        store.record_before_dispatch(first, wire(plan, first))
        store.store_response(response(plan, first))
        original = manipulation_evidence._json_ready

        def bounded_copy(value):
            assert value is not plan.payload, "terminalization copied complete source plan"
            return original(value)

        monkeypatch.setattr(manipulation_evidence, "_json_ready", bounded_copy)
        store.terminalize_saved_response()


def test_unexpected_trigger_rejected_before_mutation(setup):
    root, plan, _, _ = setup
    with create(setup) as store:
        with sqlite3.connect(root / "manipulation.sqlite3") as edit:
            edit.execute(
                "CREATE TRIGGER corrupt AFTER INSERT ON transitions BEGIN UPDATE metadata SET plan_hash='changed'; END"
            )
        with pytest.raises(ValueError):
            store.record_before_dispatch(store.requests[0], wire(plan, store.requests[0]))


def test_non_typed_equal_request_rejected(setup):
    _, plan, _, _ = setup

    class Impostor:
        def __eq__(self, other):
            return True

    with create(setup) as store:
        with pytest.raises((ValueError, TypeError)):
            store.record_before_dispatch(Impostor(), wire(plan, store.requests[0]))


def test_provider_id_must_match_saved_http_headers(setup):
    _, plan, _, _ = setup
    with create(setup) as store:
        first = store.requests[0]
        store.record_before_dispatch(first, wire(plan, first))
        actual = response(plan, first)
        transport = _json_ready(actual.transport_evidence.content_payload())
        transport["provider_request_id"] = "forged-id"
        typed = Phase0BVllmTransportEvidence(
            **transport, record_hash=canonical_payload_hash(transport)
        )
        payload = _json_ready(actual.content_payload())
        payload["provider_request_id"] = "forged-id"
        payload["transport_evidence"] = typed.to_payload()
        forged = Phase0BVllmEventResponse(
            **{**payload, "transport_evidence": typed}, record_hash=canonical_payload_hash(payload)
        )
        with pytest.raises(ValueError):
            store.store_response(forged)


@pytest.mark.parametrize(
    "outcome,error", [("timeout", "timeout"), ("provider_error", "provider_unreachable")]
)
def test_no_http_fault_is_persisted_and_terminal_invalid(setup, outcome, error):
    root, plan, checked, _ = setup
    with create(setup) as store:
        first = store.requests[0]
        store.record_before_dispatch(first, wire(plan, first))
        transport = Phase0BVllmTransportEvidence.create(
            request=first,
            http_status=None,
            response_headers={},
            provider_request_id=None,
            request_body=wire(plan, first),
            raw_body=b"",
            body_truncated=False,
            started_at="2026-10-01T00:06:00Z",
            ended_at="2026-10-01T00:06:01Z",
            latency_seconds=1.0,
            outcome=outcome,
            error_code=error,
        )
        actual = Phase0BVllmEventResponse.create(
            request=first,
            outcome=outcome,
            error_code=error,
            retry_after_seconds=None,
            provider_request_id=None,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            finish_reason=None,
            raw_body=b"",
            transport_evidence=transport,
        )
        store.store_response(actual)
        assert store.summary()["phase"] == "RESPONSE_STORED"
        store.terminalize_saved_response()
        assert store.summary()["phase"] == "INVALID"
    assert (
        module().ManipulationStore.verify(root, plan=plan, checked_at=checked)["invalid_count"] == 1
    )


def test_cached_caller_cannot_append_evidence_to_advanced_prefix(setup, monkeypatch):
    root, plan, checked, lease = setup
    with create(setup) as store:
        original = store._append
        first = store.requests[0]

        def advance_then_append(*args, **kwargs):
            with module().ManipulationStore.open(
                root, plan=plan, checked_at=checked, lease=lease
            ) as other:
                other.record_before_dispatch(first, wire(plan, first))
                other.store_response(response(plan, first))
                other.terminalize_saved_response()
            return original(*args, **kwargs)

        monkeypatch.setattr(store, "_append", advance_then_append)
        with pytest.raises(ValueError):
            store.record_before_dispatch(first, wire(plan, first))
    assert (
        module().ManipulationStore.verify(root, plan=plan, checked_at=checked)["transition_count"]
        == 3
    )


def test_sorted_plan_roundtrip_opens_same_immutable_inventory(setup):
    from agent_ex.artifacts import ArtifactEnvelope

    root, plan, checked, lease = setup
    with create(setup):
        pass
    cold = ArtifactEnvelope.from_payload(json.loads(json.dumps(plan.to_payload(), sort_keys=True)))
    with module().ManipulationStore.open(root, plan=cold, checked_at=checked, lease=lease) as store:
        assert store.summary()["phase"] == "READY"


def test_cold_replay_cache_guard_is_captured_inside_read_snapshot(setup, monkeypatch):
    root, plan, checked, _ = setup
    m = module()
    with create(setup):
        pass
    original = m.ManipulationStore._cache_guard

    def check_protected_guard(self):
        edit = sqlite3.connect(root / "manipulation.sqlite3", timeout=0)
        try:
            edit.execute("UPDATE metadata SET plan_hash='concurrent-change'")
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                edit.commit()
        finally:
            edit.rollback()
            edit.close()
        original(self)

    monkeypatch.setattr(m.ManipulationStore, "_cache_guard", check_protected_guard)
    assert m.ManipulationStore.verify(root, plan=plan, checked_at=checked)["phase"] == "READY"


@pytest.mark.parametrize("target", ["metadata", "older_record"])
def test_external_commit_after_own_commit_cannot_poison_hot_guard(setup, target):
    root, plan, _, _ = setup
    with create(setup) as store:
        first = store.requests[0]
        store.record_before_dispatch(first, wire(plan, first))
        store.store_response(response(plan, first))
        store.terminalize_saved_response()
        real = store._conn

        class CommitInterleaving:
            pending = True

            def __getattr__(self, name):
                return getattr(real, name)

            def execute(self, sql, *args):
                result = real.execute(sql, *args)
                if sql == "COMMIT" and self.pending:
                    self.pending = False
                    edit = sqlite3.connect(root / "manipulation.sqlite3")
                    try:
                        if target == "metadata":
                            edit.execute("UPDATE metadata SET plan_hash='post-commit-edit'")
                        else:
                            edit.execute("UPDATE transitions SET record_json='{}' WHERE seq=1")
                        edit.commit()
                    finally:
                        edit.close()
                return result

        store._conn = CommitInterleaving()
        with pytest.raises(ValueError):
            second = store.requests[1]
            store.record_before_dispatch(second, wire(plan, second))
            store.summary()
