"""Discriminated SIS causal input for an uncommitted SQLite PENDING prefix."""

from dataclasses import dataclass

from ..artifacts import ArtifactEnvelope
from ..domain import _json_ready, canonical_payload_hash
from ..feed import ExposureSelection, validate_exposure_selection
from ..memory import MemoryView, validate_memory_view
from ..state import PrivateUpdate, PublicPost
from .evidence import StudyEventInputEvidence


STORED_INPUT_SCHEMA = "paper1.identity-network.stored-event-input.v2"


@dataclass(frozen=True, slots=True)
class StoredStudyInput:
    input: StudyEventInputEvidence
    snapshot: ArtifactEnvelope

    def __post_init__(self):
        if not isinstance(self.input, StudyEventInputEvidence) or not isinstance(
            self.snapshot, ArtifactEnvelope
        ):
            raise TypeError("typed SIS input and snapshot required")
        s = _json_ready(self.snapshot.payload)
        fields = {
            "run_id",
            "study_binding_hash",
            "round0_root",
            "event_id",
            "event_ordinal",
            "receiver_agent_id",
            "previous_event_hash",
            "publish_flag",
            "pre_state",
            "potential_neighbor_ids",
            "unread_public_posts",
            "private_history",
            "selection",
            "memory",
            "prompt",
            "metadata",
        }
        if not isinstance(s, dict) or set(s) != fields:
            raise ValueError("stored SIS snapshot fields mismatch")
        expected_envelope = ArtifactEnvelope.create(
            artifact_type="sis-input-snapshot",
            schema_version="paper1.identity-network.input-snapshot.v1",
            algorithm_id="sis-sqlite-input-snapshot",
            algorithm_version="1.0.0",
            input_hashes={"study-binding": s["study_binding_hash"]},
            rng_provenance=(),
            payload=s,
        )
        if self.snapshot != expected_envelope:
            raise ValueError("stored SIS snapshot envelope mismatch")
        base = self.input.to_payload()
        for field in (
            "run_id",
            "event_id",
            "event_ordinal",
            "receiver_agent_id",
            "previous_event_hash",
            "publish_flag",
            "pre_state",
            "prompt",
            "metadata",
        ):
            if canonical_payload_hash(s[field]) != canonical_payload_hash(base[field]):
                raise ValueError("stored SIS input and snapshot drifted")
        selection = ExposureSelection.from_payload(s["selection"])
        validate_exposure_selection(
            selection,
            unread_public_posts=tuple(PublicPost.from_payload(p) for p in s["unread_public_posts"]),
            topic_package=self.input.topic_package,
            neighbor_agent_ids=tuple(s["potential_neighbor_ids"]),
            cursor=selection.cursor_before,
            receiver_event_id=self.event_id,
            receiver_event_ordinal=self.input.event_ordinal,
            matched_seed=self.input.private_state.matched_seed,
            exposure_mode=selection.exposure_mode,
            exposure_graph_hash=selection.exposure_graph_hash,
            capacity=selection.capacity,
        )
        memory = MemoryView.from_payload(s["memory"])
        validate_memory_view(
            memory,
            tuple(PrivateUpdate.from_payload(u) for u in s["private_history"]),
            self.input.topic_package,
        )
        if (
            memory.agent_id != self.receiver_agent_id
            or memory.matched_seed != self.input.private_state.matched_seed
        ):
            raise ValueError("stored SIS memory identity mismatch")
        shown = self.input.prompt.evidence["shown_posts"]
        selected = sorted(selection.selected, key=lambda p: p.display_slot)
        actual = tuple(
            (p["post_id"], p["source_agent_id"], p["stance"], p["reason"]) for p in shown
        )
        expected = tuple(
            (p.post_id, p.source_agent_id, p.stance_label, p.public_reason) for p in selected
        )
        if actual != expected:
            raise ValueError("stored SIS prompt differs from selected public posts")
        expected_memory = tuple(
            {"stance": i.stance_label, "reason": i.private_reason, "published": i.published}
            for i in memory.items
        )
        if canonical_payload_hash(
            self.input.prompt.evidence["self_history"]
        ) != canonical_payload_hash(expected_memory):
            raise ValueError("stored SIS prompt differs from selected private memory")

    @property
    def event_id(self):
        return self.input.event_id

    @property
    def evidence_id(self):
        return "sis-stored-event-input-" + self.record_hash

    @property
    def receiver_agent_id(self):
        return self.input.receiver_agent_id

    @property
    def publish_flag(self):
        return self.input.publish_flag

    @property
    def parser_limits(self):
        return self.input.parser_limits

    @property
    def exposure_id(self):
        return self.snapshot.payload["selection"]["selection_id"]

    def content_payload(self):
        return {
            "schema_version": STORED_INPUT_SCHEMA,
            "event_id": self.event_id,
            "sis_input": self.input.to_payload(),
            "causal_snapshot": self.snapshot.to_payload(),
        }

    @property
    def record_hash(self):
        return canonical_payload_hash(self.content_payload())

    def to_payload(self):
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def from_payload(cls, payload):
        if (
            not isinstance(payload, dict)
            or set(payload)
            != {"schema_version", "event_id", "sis_input", "causal_snapshot", "record_hash"}
            or payload["schema_version"] != STORED_INPUT_SCHEMA
        ):
            raise ValueError("stored SIS input schema/fields mismatch")
        result = cls(
            StudyEventInputEvidence.from_payload(payload["sis_input"]),
            ArtifactEnvelope.from_payload(payload["causal_snapshot"]),
        )
        if result.event_id != payload["event_id"] or result.record_hash != payload["record_hash"]:
            raise ValueError("stored SIS input hash/event mismatch")
        return result
