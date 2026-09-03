"""Read-only, hash-bound mock process audits and recovery comparisons."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import threading
from types import MappingProxyType
from typing import Mapping
import weakref

from .checkpoint import build_checkpoint
from .domain import EventStatus, _freeze, _json_ready, canonical_payload_hash, derive_event_id
from .execution_evidence import EventInputEvidence, ParseNotApplicableEvidence
from .parser import ParseEvidence
from .state import PrivateState, PrivateUpdate, PublicPost
from .storage import ExecutionStatus, RunStorage
from .topic import TopicPackage


ANALYSIS_LABEL = "exploratory/process_diagnostic"
APPROVED_OUTCOME_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "private_state": "primary",
        "public_stock": "required_secondary",
        "public_flow": "required_secondary",
        "expression_gap": "required_secondary_definition_unresolved",
    }
)
APPROVED_TERMINOLOGY_MAP_ID = "paper1.phase4a1.terminology.v1"
APPROVED_TERMINOLOGY_MAP: Mapping[str, str] = MappingProxyType(
    {
        "identity": "人口身份线索可见性",
        "continuity": "历史立场一致性要求",
        "private_state": "非公开Agent立场状态",
        "public_post": "Agent可见话语分布",
    }
)
_PROVENANCE_SCHEMAS = {
    "model_provenance": {
        "required": frozenset(("provider", "model", "revision", "runtime", "mode")),
        "semantic": frozenset(("provider", "model", "revision", "runtime", "mode")),
        "excluded": frozenset(("local_path",)),
    },
    "prompt_provenance": {
        "required": frozenset(("template_id", "template_version", "prompt_limits_hash")),
        "semantic": frozenset(("template_id", "template_version", "prompt_limits_hash")),
        "excluded": frozenset(("started_at",)),
    },
    "robustness_provenance": {
        "required": frozenset(("mock_only", "research_parameter_status")),
        "semantic": frozenset(("mock_only", "research_parameter_status")),
        "excluded": frozenset(("launch_nonce",)),
    },
}
_TRUSTED_AUDIT_REGISTRY: dict[int, tuple[weakref.ReferenceType[object], str]] = {}
_TRUSTED_AUDIT_REGISTRY_LOCK = threading.Lock()


def _payload(value: object) -> object:
    return _json_ready(value)


def _require_hash(name: str, value: object) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be SHA-256 text")


def _require_mapping(name: str, value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    plain = _payload(value)
    if type(plain) is not dict or not all(type(key) is str for key in plain):
        raise TypeError(f"{name} must be a JSON object with text keys")
    canonical_payload_hash(plain)
    return _freeze(plain)  # type: ignore[return-value]


def _validate_provenance_section(
    name: str, value: object
) -> tuple[Mapping[str, object], tuple[str, ...]]:
    schema = _PROVENANCE_SCHEMAS[name]
    section = _require_mapping(name, value)
    keys = set(section)
    required = schema["required"]
    allowed = schema["semantic"] | schema["excluded"]
    if not required.issubset(keys):
        missing = ", ".join(sorted(required - keys))
        raise ValueError(f"{name} is missing required fields: {missing}")
    if not keys.issubset(allowed):
        unknown = ", ".join(sorted(keys - allowed))
        raise ValueError(f"{name} contains unknown fields: {unknown}")
    for field_name in required:
        if name == "robustness_provenance":
            continue
        field_value = section[field_name]
        if type(field_value) is not str or not field_value:
            raise ValueError(f"{name}.{field_name} must be non-empty text")
    if name == "robustness_provenance" and not (
        section["mock_only"] is True and section["research_parameter_status"] == "not_frozen"
    ):
        raise ValueError("robustness_provenance must remain mock_only with not_frozen status")
    for hash_name in ("template_hash", "prompt_limits_hash"):
        if hash_name in section:
            _require_hash(f"{name}.{hash_name}", section[hash_name])
    for field_name in schema["excluded"]:
        if field_name in section and (
            type(section[field_name]) is not str or not section[field_name]
        ):
            raise ValueError(f"{name}.{field_name} must be non-empty text")
    semantic_names = tuple(sorted(schema["semantic"] & keys))
    return section, semantic_names


def _hash_without(value: object, hash_field: str) -> str:
    plain = _payload(value)
    assert type(plain) is dict
    return canonical_payload_hash({key: item for key, item in plain.items() if key != hash_field})


@dataclass(frozen=True, slots=True)
class ExposureProcessSummary:
    analysis_label: str
    per_event_message_counts: tuple[int, ...]
    event_backed_message_ages: tuple[int, ...]
    round0_message_count: int
    unique_source_agent_ids: tuple[str, ...]
    repeated_source_message_count: int
    empty_feed_count: int
    expired_message_count: int
    sender_activity_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        if self.analysis_label != ANALYSIS_LABEL:
            raise ValueError("exposure process analysis label is fixed")
        tuple_fields = (
            self.per_event_message_counts,
            self.event_backed_message_ages,
            self.unique_source_agent_ids,
        )
        if not all(isinstance(value, tuple) for value in tuple_fields):
            raise TypeError("process repeated fields must be tuples")
        for name in (
            "round0_message_count",
            "repeated_source_message_count",
            "empty_feed_count",
            "expired_message_count",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a nonnegative strict integer")
        if any(type(value) is not int or value < 0 for value in self.per_event_message_counts):
            raise ValueError("per-event message counts must be nonnegative strict integers")
        if any(type(value) is not int or value <= 0 for value in self.event_backed_message_ages):
            raise ValueError("event-backed message ages must be positive strict integers")
        if self.unique_source_agent_ids != tuple(sorted(set(self.unique_source_agent_ids))):
            raise ValueError("unique source agent IDs must be sorted and unique")
        counts = _require_mapping("sender_activity_counts", self.sender_activity_counts)
        if any(type(value) is not int or value <= 0 for value in counts.values()):
            raise ValueError("sender activity counts must be positive strict integers")
        if tuple(sorted(counts)) != self.unique_source_agent_ids:
            raise ValueError("sender activity keys must exact-cover unique sources")
        object.__setattr__(self, "sender_activity_counts", counts)

    @property
    def selected_message_count(self) -> int:
        return sum(self.per_event_message_counts)

    def to_payload(self) -> dict[str, object]:
        return _payload({name: getattr(self, name) for name in self.__dataclass_fields__})  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class RoundZeroBaseline:
    agent_count: int
    private_state_snapshot: tuple[Mapping[str, object], ...]
    public_stock_snapshot: tuple[Mapping[str, object], ...]
    private_label_counts: Mapping[str, int]
    public_label_counts: Mapping[str, int]
    baseline_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.agent_count) is not int or self.agent_count <= 0:
            raise ValueError("round-zero agent_count must be a positive strict integer")
        if len(self.private_state_snapshot) != self.agent_count:
            raise ValueError("round-zero private snapshot must exact-cover the population")
        if len(self.public_stock_snapshot) != self.agent_count:
            raise ValueError("round-zero public stock must exact-cover the population")
        object.__setattr__(self, "private_state_snapshot", _freeze(self.private_state_snapshot))
        object.__setattr__(self, "public_stock_snapshot", _freeze(self.public_stock_snapshot))
        object.__setattr__(
            self,
            "private_label_counts",
            _require_mapping("private_label_counts", self.private_label_counts),
        )
        object.__setattr__(
            self,
            "public_label_counts",
            _require_mapping("public_label_counts", self.public_label_counts),
        )
        body = {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
            if name != "baseline_hash"
        }
        object.__setattr__(self, "baseline_hash", canonical_payload_hash(body))

    def to_payload(self) -> dict[str, object]:
        return _payload({name: getattr(self, name) for name in self.__dataclass_fields__})  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class SweepProcessAudit:
    sweep_index: int
    boundary_event_ordinal: int
    private_state_snapshot: tuple[Mapping[str, object], ...]
    public_stock_snapshot: tuple[Mapping[str, object], ...]
    public_flow_snapshot: tuple[Mapping[str, object], ...]
    process: ExposureProcessSummary
    private_label_count_delta: Mapping[str, int]
    public_stock_label_count_delta: Mapping[str, int]
    public_flow_label_count_delta: Mapping[str, int]
    label_count_delta_analysis_label: str
    sweep_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.sweep_index) is not int or self.sweep_index <= 0:
            raise ValueError("sweep_index must be a positive strict integer")
        if type(self.boundary_event_ordinal) is not int or self.boundary_event_ordinal <= 0:
            raise ValueError("sweep boundary must be a positive strict integer")
        if not isinstance(self.process, ExposureProcessSummary):
            raise TypeError("process must be an ExposureProcessSummary")
        if self.label_count_delta_analysis_label != ANALYSIS_LABEL:
            raise ValueError("label-count delta analysis label is fixed")
        for name in (
            "private_state_snapshot",
            "public_stock_snapshot",
            "public_flow_snapshot",
        ):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple")
            object.__setattr__(self, name, _freeze(value))
        for name in (
            "private_label_count_delta",
            "public_stock_label_count_delta",
            "public_flow_label_count_delta",
        ):
            value = _require_mapping(name, getattr(self, name))
            if any(type(item) is not int for item in value.values()):
                raise TypeError(f"{name} values must be strict integers")
            object.__setattr__(self, name, value)
        body = {
            name: (self.process.to_payload() if name == "process" else getattr(self, name))
            for name in self.__dataclass_fields__
            if name != "sweep_hash"
        }
        object.__setattr__(self, "sweep_hash", canonical_payload_hash(body))

    def to_payload(self) -> dict[str, object]:
        values = {
            name: (self.process.to_payload() if name == "process" else getattr(self, name))
            for name in self.__dataclass_fields__
        }
        return _payload(values)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True, weakref_slot=True)
class MockProcessAudit:
    schema_version: str
    run_id: str
    cell_id: str
    boundary_event_ordinal: int
    round_zero: RoundZeroBaseline
    sweeps: tuple[SweepProcessAudit, ...]
    outcome_labels: Mapping[str, str]
    terminology_map_id: str
    terminology_map_hash: str
    terminology_map: Mapping[str, str]
    provenance: Mapping[str, object]
    checkpoint_hash: str
    audit_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != "paper1.mock-process-audit.v1":
            raise ValueError("process audit schema version is unsupported")
        if type(self.run_id) is not str or not self.run_id:
            raise ValueError("process audit run_id must be non-empty text")
        if type(self.cell_id) is not str or not self.cell_id:
            raise ValueError("process audit cell_id must be non-empty text")
        if type(self.boundary_event_ordinal) is not int or self.boundary_event_ordinal < 0:
            raise ValueError("process audit boundary must be a nonnegative strict integer")
        if not isinstance(self.round_zero, RoundZeroBaseline):
            raise TypeError("round_zero must be a RoundZeroBaseline")
        if not isinstance(self.sweeps, tuple) or not all(
            isinstance(value, SweepProcessAudit) for value in self.sweeps
        ):
            raise TypeError("sweeps must contain SweepProcessAudit values")
        if tuple(item.sweep_index for item in self.sweeps) != tuple(range(1, len(self.sweeps) + 1)):
            raise ValueError("process audit sweeps must be continuous from one")
        if dict(self.outcome_labels) != dict(APPROVED_OUTCOME_LABELS):
            raise ValueError("outcome labels do not match the approved fixed hierarchy")
        if self.terminology_map_id != APPROVED_TERMINOLOGY_MAP_ID:
            raise ValueError("terminology map ID is not approved")
        if dict(self.terminology_map) != dict(APPROVED_TERMINOLOGY_MAP):
            raise ValueError("terminology map is incomplete or changed")
        if self.terminology_map_hash != canonical_payload_hash(APPROVED_TERMINOLOGY_MAP):
            raise ValueError("terminology map hash does not bind the approved payload")
        object.__setattr__(self, "outcome_labels", _freeze(self.outcome_labels))
        object.__setattr__(self, "terminology_map", _freeze(self.terminology_map))
        provenance = _require_mapping("provenance", self.provenance)
        if set(provenance) != {"cell_id", "topic", "model", "prompt", "robustness"}:
            raise ValueError("process audit provenance fields do not match the fixed schema")
        if provenance["cell_id"] != self.cell_id:
            raise ValueError("process audit provenance cell_id does not match the audit")
        topic = _require_mapping("topic provenance", provenance["topic"])
        if set(topic) != {"topic_id", "package_hash"}:
            raise ValueError("topic provenance fields do not match the fixed schema")
        if type(topic["topic_id"]) is not str or not topic["topic_id"]:
            raise ValueError("topic provenance topic_id must be non-empty text")
        _require_hash("topic provenance package_hash", topic["package_hash"])
        model, _ = _validate_provenance_section("model_provenance", provenance["model"])
        prompt, _ = _validate_provenance_section("prompt_provenance", provenance["prompt"])
        robustness, _ = _validate_provenance_section(
            "robustness_provenance", provenance["robustness"]
        )
        object.__setattr__(
            self,
            "provenance",
            _freeze(
                {
                    "cell_id": self.cell_id,
                    "topic": topic,
                    "model": model,
                    "prompt": prompt,
                    "robustness": robustness,
                }
            ),
        )
        _require_hash("checkpoint_hash", self.checkpoint_hash)
        body = {
            name: (
                self.round_zero.to_payload()
                if name == "round_zero"
                else [item.to_payload() for item in self.sweeps]
                if name == "sweeps"
                else getattr(self, name)
            )
            for name in self.__dataclass_fields__
            if name != "audit_hash"
        }
        object.__setattr__(self, "audit_hash", canonical_payload_hash(body))

    def to_payload(self) -> dict[str, object]:
        values = {
            name: (
                self.round_zero.to_payload()
                if name == "round_zero"
                else [item.to_payload() for item in self.sweeps]
                if name == "sweeps"
                else getattr(self, name)
            )
            for name in self.__dataclass_fields__
        }
        return _payload(values)  # type: ignore[return-value]


def _register_built_audit(audit: MockProcessAudit) -> None:
    key = id(audit)

    def cleanup(reference: weakref.ReferenceType[MockProcessAudit]) -> None:
        with _TRUSTED_AUDIT_REGISTRY_LOCK:
            current = _TRUSTED_AUDIT_REGISTRY.get(key)
            if current is not None and current[0] is reference:
                _TRUSTED_AUDIT_REGISTRY.pop(key, None)

    reference = weakref.ref(audit, cleanup)
    with _TRUSTED_AUDIT_REGISTRY_LOCK:
        _TRUSTED_AUDIT_REGISTRY[key] = (reference, audit.audit_hash)


def _is_registered_built_audit(audit: MockProcessAudit) -> bool:
    with _TRUSTED_AUDIT_REGISTRY_LOCK:
        current = _TRUSTED_AUDIT_REGISTRY.get(id(audit))
        return bool(
            current is not None and current[0]() is audit and current[1] == audit.audit_hash
        )


@dataclass(frozen=True, slots=True)
class MockComparableRunProjection:
    schema_version: str
    matched_seed: int
    cell_id: str
    schedule_hash: str
    committed_event_semantics: tuple[Mapping[str, object], ...]
    final_private_states: tuple[Mapping[str, object], ...]
    final_public_stock: tuple[Mapping[str, object], ...]
    final_feed_cursors: tuple[Mapping[str, object], ...]
    process_audit_semantics: Mapping[str, object]
    projection_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != "paper1.mock-comparable-run-projection.v1":
            raise ValueError("comparable projection schema version is unsupported")
        if type(self.matched_seed) is not int:
            raise TypeError("matched_seed must be a strict integer")
        if type(self.cell_id) is not str or not self.cell_id:
            raise ValueError("cell_id must be non-empty text")
        _require_hash("schedule_hash", self.schedule_hash)
        for name in (
            "committed_event_semantics",
            "final_private_states",
            "final_public_stock",
            "final_feed_cursors",
        ):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple")
            object.__setattr__(self, name, _freeze(value))
        object.__setattr__(
            self,
            "process_audit_semantics",
            _require_mapping("process_audit_semantics", self.process_audit_semantics),
        )
        body = {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
            if name != "projection_hash"
        }
        object.__setattr__(self, "projection_hash", canonical_payload_hash(body))

    def to_payload(self) -> dict[str, object]:
        return _payload({name: getattr(self, name) for name in self.__dataclass_fields__})  # type: ignore[return-value]


def _label_counts(
    records: tuple[Mapping[str, object], ...], labels: tuple[str, ...]
) -> dict[str, int]:
    counts = Counter(record["stance_label"] for record in records)
    if any(label not in labels for label in counts):
        raise ValueError("snapshot contains a stance outside the bound topic")
    return {label: counts[label] for label in labels}


def _delta(current: Mapping[str, int], baseline: Mapping[str, int]) -> dict[str, int]:
    if set(current) != set(baseline):
        raise ValueError("label-count delta inputs do not exact-cover the same labels")
    return {label: current[label] - baseline[label] for label in baseline}


def _process_summary(
    event_inputs: tuple[EventInputEvidence, ...],
    *,
    event_ordinal_by_id: Mapping[str, int],
    roster: set[str],
) -> ExposureProcessSummary:
    per_event: list[int] = []
    ages: list[int] = []
    round0_count = 0
    expired_count = 0
    source_counts: Counter[str] = Counter()
    for expected_ordinal, value in enumerate(
        event_inputs, start=event_inputs[0].exposure_record.event_ordinal if event_inputs else 0
    ):
        exposure = value.exposure_record
        if exposure.event_ordinal != expected_ordinal:
            raise ValueError("event evidence is missing, extra, or reordered")
        per_event.append(len(exposure.selected_post_ids))
        expired_count += len(exposure.expired_post_ids)
        for source_id, source_event_id, age in zip(
            exposure.source_agent_ids,
            exposure.source_event_ids,
            exposure.message_ages,
            strict=True,
        ):
            if source_id not in roster:
                raise ValueError("selected sender is outside the bound population")
            source_counts[source_id] += 1
            if source_event_id is None:
                round0_count += 1
                continue
            source_ordinal = event_ordinal_by_id.get(source_event_id)
            if source_ordinal is None or exposure.event_ordinal - source_ordinal != age or age <= 0:
                raise ValueError("event-backed message age or sender event identity is invalid")
            ages.append(age)
    repeated = sum(count - 1 for count in source_counts.values())
    return ExposureProcessSummary(
        analysis_label=ANALYSIS_LABEL,
        per_event_message_counts=tuple(per_event),
        event_backed_message_ages=tuple(ages),
        round0_message_count=round0_count,
        unique_source_agent_ids=tuple(sorted(source_counts)),
        repeated_source_message_count=repeated,
        empty_feed_count=sum(count == 0 for count in per_event),
        expired_message_count=expired_count,
        sender_activity_counts=dict(sorted(source_counts.items())),
    )


def build_mock_process_audit(
    storage: RunStorage,
    cell_id: str,
    topic_package: TopicPackage,
    boundary_event_ordinal: int,
    outcome_labels: Mapping[str, str],
    terminology_map_id: str,
    terminology_map: Mapping[str, str],
    model_provenance: Mapping[str, object],
    prompt_provenance: Mapping[str, object],
    robustness_provenance: Mapping[str, object],
) -> MockProcessAudit:
    """Build a process audit solely from one committed storage snapshot."""

    if not isinstance(storage, RunStorage):
        raise TypeError("storage must be a RunStorage")
    if not isinstance(topic_package, TopicPackage):
        raise TypeError("topic_package must be a TopicPackage")
    if type(cell_id) is not str or not cell_id:
        raise ValueError("cell_id must be non-empty text")
    if type(boundary_event_ordinal) is not int or boundary_event_ordinal < 0:
        raise ValueError("boundary_event_ordinal must be a nonnegative strict integer")
    if dict(outcome_labels) != dict(APPROVED_OUTCOME_LABELS):
        raise ValueError("outcome labels do not match the approved fixed hierarchy")
    if terminology_map_id != APPROVED_TERMINOLOGY_MAP_ID or dict(terminology_map) != dict(
        APPROVED_TERMINOLOGY_MAP
    ):
        raise ValueError("terminology mapping is incomplete, changed, or unapproved")
    model, _ = _validate_provenance_section("model_provenance", model_provenance)
    prompt, _ = _validate_provenance_section("prompt_provenance", prompt_provenance)
    robustness, _ = _validate_provenance_section("robustness_provenance", robustness_provenance)

    with storage.consistent_read():
        storage.verify_integrity()
        progress = storage.progress
        roster = storage.binding.expected_agent_ids
        population_size = len(roster)
        if population_size == 0:
            raise ValueError("process audit requires a non-empty bound population")
        if boundary_event_ordinal > progress.next_event_ordinal:
            raise ValueError("audit boundary is beyond the committed prefix")
        if boundary_event_ordinal % population_size:
            raise ValueError("audit boundary must be a complete population-sized sweep multiple")
        if boundary_event_ordinal != progress.next_event_ordinal:
            raise ValueError("audit boundary must equal the current committed boundary")
        execution = storage.execution_state()
        if execution.status is ExecutionStatus.FAILED:
            raise ValueError("FAILED execution cannot produce a process audit")
        if execution.status is ExecutionStatus.COMPLETE:
            if boundary_event_ordinal != progress.expected_event_count:
                raise ValueError("COMPLETE audit must exact-cover the full frozen schedule")
            storage.assert_complete()
        elif execution.status is ExecutionStatus.RUNNING:
            journal = storage.current_event_journal()
            if journal.latest_transition is not None or journal.resume_state != "new_attempt":
                raise ValueError("RUNNING audit boundary contains a nonterminal attempt")
        else:
            raise ValueError("process audit requires RUNNING or COMPLETE execution state")
        if boundary_event_ordinal == 0:
            raise ValueError("process audit requires at least one committed complete sweep")
        if (
            storage.binding.artifact_hashes.get(topic_package.topic_id)
            != topic_package.package_hash
        ):
            raise ValueError("topic package is not bound by the storage artifact set")

        histories = {agent_id: storage.private_updates_for_agent(agent_id) for agent_id in roster}
        posts_by_agent = {agent_id: storage.public_posts_for_agent(agent_id) for agent_id in roster}
        initial_states: dict[str, PrivateState] = {}
        current_states: dict[str, PrivateState] = {}
        updates_by_ordinal: dict[int, PrivateUpdate] = {}
        latest_posts: dict[str, PublicPost] = {}
        posts_by_ordinal: dict[int, PublicPost] = {}
        for agent_id in roster:
            history = histories[agent_id]
            initial = PrivateState.from_update(history[0], previous=None, mock_only=True)
            initial_states[agent_id] = initial
            current_states[agent_id] = initial
            for update in history[1:]:
                if update.event_ordinal is None or update.event_ordinal in updates_by_ordinal:
                    raise ValueError("private update evidence is missing, duplicate, or unordered")
                updates_by_ordinal[update.event_ordinal] = update
            agent_posts = posts_by_agent[agent_id]
            if not agent_posts or agent_posts[0].published_event_ordinal is not None:
                raise ValueError("public history must begin with exactly one round-zero post")
            latest_posts[agent_id] = agent_posts[0]
            for post in agent_posts[1:]:
                ordinal = post.published_event_ordinal
                if ordinal is None or ordinal in posts_by_ordinal:
                    raise ValueError("public post evidence is missing, duplicate, or unordered")
                posts_by_ordinal[ordinal] = post

        if set(updates_by_ordinal) != set(range(boundary_event_ordinal)):
            raise ValueError("committed private updates do not exact-cover the audit boundary")
        events = []
        inputs = []
        for ordinal in range(boundary_event_ordinal):
            event = storage.event_at(ordinal)
            if event is None or event.status is not EventStatus.SUCCEEDED:
                raise ValueError("committed event evidence is missing or nonterminal")
            if event.event_id != derive_event_id(storage.binding.run_id, ordinal):
                raise ValueError("committed event identity is not canonical")
            if event.agent_id != updates_by_ordinal[ordinal].agent_id:
                raise ValueError("committed event and private update agents disagree")
            if event.publish_flag != (ordinal in posts_by_ordinal):
                raise ValueError("public flow does not exactly follow frozen publish flags")
            event_input = storage.event_input_evidence(event.event_id)
            if not isinstance(event_input, EventInputEvidence):
                raise ValueError("committed event input evidence is missing")
            # Strict typed replay catches in-memory corruption from a substituted reader.
            if EventInputEvidence.from_payload(event_input.to_payload()) != event_input:
                raise ValueError("event input evidence changed during typed replay")
            if event_input.publish_flag is not event.publish_flag:
                raise ValueError("event input publish flag differs from committed event")
            if event_input.prompt_view.cell_id != cell_id:
                raise ValueError("audit cell_id differs from committed prompt evidence")
            if not (
                event_input.prompt_view.topic_package_id == topic_package.topic_id
                and event_input.prompt_view.topic_hash == topic_package.package_hash
                and event_input.exposure_record.topic_package_id == topic_package.topic_id
                and event_input.exposure_record.topic_package_hash == topic_package.package_hash
                and event_input.prompt_view.stance_labels == topic_package.stance_labels
            ):
                raise ValueError("audit topic package differs from committed event evidence")
            events.append(event)
            inputs.append(event_input)

        first_attempts = storage.attempts_for_event(events[0].event_id)
        if not first_attempts:
            raise ValueError("committed model provenance requires attempt evidence")
        committed_attempt = first_attempts[-1]
        request = storage.adapter_request_evidence(committed_attempt.attempt_id)
        invocation = storage.invocation_evidence(committed_attempt.attempt_id)
        if request is None or invocation is None:
            raise ValueError("committed model provenance evidence is incomplete")
        runtime_identity = invocation.response.runtime_identity
        expected_model_provenance = {
            "provider": runtime_identity["provider"],
            "model": request.model_identity["model"],
            "revision": request.model_identity["revision"],
            "runtime": runtime_identity["runtime_version"],
            "mode": request.model_identity["mode"],
        }
        if any(model[name] != value for name, value in expected_model_provenance.items()):
            raise ValueError("model provenance differs from committed request evidence")
        first_prompt = inputs[0].prompt_view
        expected_prompt_provenance = {
            "template_id": first_prompt.template_id,
            "template_version": first_prompt.template_version,
            "prompt_limits_hash": first_prompt.limits_hash,
        }
        if any(prompt[name] != value for name, value in expected_prompt_provenance.items()):
            raise ValueError("prompt provenance differs from committed prompt evidence")

        labels = topic_package.stance_labels
        round_private = tuple(initial_states[agent_id].to_payload() for agent_id in roster)
        round_public = tuple(latest_posts[agent_id].to_payload() for agent_id in roster)
        round_zero = RoundZeroBaseline(
            agent_count=population_size,
            private_state_snapshot=round_private,
            public_stock_snapshot=round_public,
            private_label_counts=_label_counts(round_private, labels),
            public_label_counts=_label_counts(round_public, labels),
        )
        event_ordinal_by_id = {event.event_id: event.event_ordinal for event in events}
        sweeps = []
        flow: list[PublicPost] = []
        for ordinal, event in enumerate(events):
            update = updates_by_ordinal[ordinal]
            current_states[event.agent_id] = PrivateState.from_update(
                update, previous=current_states[event.agent_id], mock_only=True
            )
            if event.publish_flag:
                post = posts_by_ordinal[ordinal]
                if post != PublicPost.from_private_update(update, mock_only=True):
                    raise ValueError(
                        "public post does not replay from its published private update"
                    )
                latest_posts[event.agent_id] = post
                flow.append(post)
            if (ordinal + 1) % population_size:
                continue
            sweep_index = (ordinal + 1) // population_size
            private_snapshot = tuple(current_states[agent_id].to_payload() for agent_id in roster)
            public_stock = tuple(latest_posts[agent_id].to_payload() for agent_id in roster)
            public_flow = tuple(post.to_payload() for post in flow)
            private_counts = _label_counts(private_snapshot, labels)
            stock_counts = _label_counts(public_stock, labels)
            flow_counts = _label_counts(public_flow, labels)
            start = ordinal + 1 - population_size
            sweeps.append(
                SweepProcessAudit(
                    sweep_index=sweep_index,
                    boundary_event_ordinal=ordinal + 1,
                    private_state_snapshot=private_snapshot,
                    public_stock_snapshot=public_stock,
                    public_flow_snapshot=public_flow,
                    process=_process_summary(
                        tuple(inputs[start : ordinal + 1]),
                        event_ordinal_by_id=event_ordinal_by_id,
                        roster=set(roster),
                    ),
                    private_label_count_delta=_delta(
                        private_counts, round_zero.private_label_counts
                    ),
                    public_stock_label_count_delta=_delta(
                        stock_counts, round_zero.public_label_counts
                    ),
                    public_flow_label_count_delta=_delta(
                        flow_counts, round_zero.public_label_counts
                    ),
                    label_count_delta_analysis_label=ANALYSIS_LABEL,
                )
            )
            flow = []

        checkpoint = build_checkpoint(storage)
        audit = MockProcessAudit(
            schema_version="paper1.mock-process-audit.v1",
            run_id=storage.binding.run_id,
            cell_id=cell_id,
            boundary_event_ordinal=boundary_event_ordinal,
            round_zero=round_zero,
            sweeps=tuple(sweeps),
            outcome_labels=outcome_labels,
            terminology_map_id=terminology_map_id,
            terminology_map_hash=canonical_payload_hash(terminology_map),
            terminology_map=terminology_map,
            provenance={
                "cell_id": cell_id,
                "topic": {
                    "topic_id": topic_package.topic_id,
                    "package_hash": topic_package.package_hash,
                },
                "model": model,
                "prompt": prompt,
                "robustness": robustness,
            },
            checkpoint_hash=checkpoint.checkpoint_hash,
        )
        _register_built_audit(audit)
        return audit


def _private_semantics(value: Mapping[str, object]) -> dict[str, object]:
    return {
        name: value[name]
        for name in (
            "matched_seed",
            "agent_id",
            "successful_update_count",
            "event_ordinal",
            "stance_label",
            "reason",
            "confidence",
        )
    }


def _post_semantics(value: Mapping[str, object]) -> dict[str, object]:
    return {
        name: value[name]
        for name in (
            "matched_seed",
            "author_agent_id",
            "published_event_ordinal",
            "stance_label",
            "public_reason",
        )
    }


def _cursor_semantics(value: Mapping[str, object]) -> dict[str, object]:
    return {
        name: value[name]
        for name in (
            "matched_seed",
            "receiver_agent_id",
            "exposure_mode",
            "exposure_graph_hash",
            "last_scanned_event_ordinal",
        )
    }


def _parse_semantics(
    value: ParseEvidence | ParseNotApplicableEvidence,
    *,
    event_parser_limits_hash: str,
) -> dict[str, object]:
    if value.parser_limits_hash != event_parser_limits_hash:
        raise ValueError("parse limits differ from committed event input evidence")
    if isinstance(value, ParseEvidence):
        payload = value.to_payload()
        semantics = {
            "parse_kind": "parsed",
            "parser_id": value.parser_id,
            "parser_version": value.parser_version,
            "parser_limits_hash": value.parser_limits_hash,
            **{
                name: payload.get(name)
                for name in ("success", "parsed", "error", "reason")
                if name in payload
            },
        }
    elif isinstance(value, ParseNotApplicableEvidence):
        semantics = {
            "parse_kind": "not_applicable",
            "parser_id": None,
            "parser_version": None,
            "parser_limits_hash": value.parser_limits_hash,
            "outcome": value.outcome,
            "error": value.error,
            "reason": value.reason,
        }
    else:
        raise TypeError("parse evidence has an unsupported typed variant")
    return {**semantics, "parse_semantic_hash": canonical_payload_hash(semantics)}


def _audit_semantics(audit: MockProcessAudit) -> dict[str, object]:
    provenance = audit.provenance
    model, model_fields = _validate_provenance_section("model_provenance", provenance["model"])
    prompt, prompt_fields = _validate_provenance_section("prompt_provenance", provenance["prompt"])
    robustness, robustness_fields = _validate_provenance_section(
        "robustness_provenance", provenance["robustness"]
    )

    return {
        "schema_version": audit.schema_version,
        "cell_id": audit.cell_id,
        "boundary_event_ordinal": audit.boundary_event_ordinal,
        "round_zero": {
            "agent_count": audit.round_zero.agent_count,
            "private_state_snapshot": tuple(
                _private_semantics(value) for value in audit.round_zero.private_state_snapshot
            ),
            "public_stock_snapshot": tuple(
                _post_semantics(value) for value in audit.round_zero.public_stock_snapshot
            ),
            "private_label_counts": audit.round_zero.private_label_counts,
            "public_label_counts": audit.round_zero.public_label_counts,
        },
        "sweeps": tuple(
            {
                "sweep_index": sweep.sweep_index,
                "boundary_event_ordinal": sweep.boundary_event_ordinal,
                "private_state_snapshot": tuple(
                    _private_semantics(value) for value in sweep.private_state_snapshot
                ),
                "public_stock_snapshot": tuple(
                    _post_semantics(value) for value in sweep.public_stock_snapshot
                ),
                "public_flow_snapshot": tuple(
                    _post_semantics(value) for value in sweep.public_flow_snapshot
                ),
                "process": sweep.process.to_payload(),
                "private_label_count_delta": sweep.private_label_count_delta,
                "public_stock_label_count_delta": sweep.public_stock_label_count_delta,
                "public_flow_label_count_delta": sweep.public_flow_label_count_delta,
                "label_count_delta_analysis_label": sweep.label_count_delta_analysis_label,
            }
            for sweep in audit.sweeps
        ),
        "outcome_labels": audit.outcome_labels,
        "terminology_map_id": audit.terminology_map_id,
        "terminology_map_hash": audit.terminology_map_hash,
        "terminology_map": audit.terminology_map,
        "provenance": {
            "cell_id": provenance["cell_id"],
            "topic": provenance["topic"],
            "model": {name: model[name] for name in model_fields},
            "prompt": {name: prompt[name] for name in prompt_fields},
            "robustness": {name: robustness[name] for name in robustness_fields},
        },
    }


def _verify_audit_hash_integrity(audit: MockProcessAudit) -> None:
    if audit.round_zero.baseline_hash != _hash_without(
        audit.round_zero.to_payload(), "baseline_hash"
    ):
        raise ValueError("process audit baseline hash integrity check failed")
    if any(
        sweep.sweep_hash != _hash_without(sweep.to_payload(), "sweep_hash")
        for sweep in audit.sweeps
    ):
        raise ValueError("process audit sweep hash integrity check failed")
    if audit.audit_hash != _hash_without(audit.to_payload(), "audit_hash"):
        raise ValueError("process audit hash integrity check failed")


def build_mock_comparable_run_projection(
    storage: RunStorage, audit: MockProcessAudit
) -> MockComparableRunProjection:
    """Project only run-comparable semantics, excluding launch-local identity."""

    if not isinstance(storage, RunStorage):
        raise TypeError("storage must be a RunStorage")
    if not isinstance(audit, MockProcessAudit):
        raise TypeError("audit must be a MockProcessAudit")
    _verify_audit_hash_integrity(audit)
    if not _is_registered_built_audit(audit):
        raise ValueError("audit is not a trusted builder-issued process audit")
    if audit.run_id != storage.binding.run_id:
        raise ValueError("audit and storage must belong to the same run")
    with storage.consistent_read():
        storage.verify_integrity()
        if audit.boundary_event_ordinal != storage.progress.next_event_ordinal:
            raise ValueError("audit boundary differs from committed storage progress")
        if audit.checkpoint_hash != build_checkpoint(storage).checkpoint_hash:
            raise ValueError("audit checkpoint differs from current storage evidence")
        recovery = storage.recovery_evidence(audit.boundary_event_ordinal)
        private_values = tuple(recovery["private_states"])
        public_values = tuple(recovery["public_stock"])
        cursor_values = tuple(recovery["feed_cursors"])
        if not private_values:
            raise ValueError("comparable projection requires a non-empty population")
        matched_seed = private_values[0]["matched_seed"]
        if type(matched_seed) is not int:
            raise ValueError("committed matched seed is invalid")
        event_semantics = []
        event_ordinal_by_id = {
            derive_event_id(storage.binding.run_id, ordinal): ordinal
            for ordinal in range(audit.boundary_event_ordinal)
        }
        for ordinal in range(audit.boundary_event_ordinal):
            event = storage.event_at(ordinal)
            if event is None or event.status is not EventStatus.SUCCEEDED:
                raise ValueError("comparable projection requires committed successful events")
            event_input = storage.event_input_evidence(event.event_id)
            if event_input is None:
                raise ValueError("comparable projection is missing event input evidence")
            exposure = event_input.exposure_record
            attempts = []
            for attempt in storage.attempts_for_event(event.event_id):
                request = storage.adapter_request_evidence(attempt.attempt_id)
                invocation = storage.invocation_evidence(attempt.attempt_id)
                parsed = storage.parse_evidence(attempt.attempt_id)
                if request is None or invocation is None or parsed is None:
                    raise ValueError("comparable projection requires exact attempt evidence")
                prompt_view = event_input.prompt_view
                if request.prompt_limits_hash != prompt_view.limits_hash:
                    raise ValueError("request prompt limits differ from committed prompt evidence")
                parse_semantics = _parse_semantics(
                    parsed,
                    event_parser_limits_hash=event_input.parser_limits.record_hash,
                )
                attempts.append(
                    {
                        "attempt_index": attempt.attempt_index,
                        "status": attempt.status.value,
                        "prompt_template_id": prompt_view.template_id,
                        "prompt_template_version": prompt_view.template_version,
                        "prompt_limits_hash": request.prompt_limits_hash,
                        "rendered_prompt_semantic_hash": canonical_payload_hash(
                            {
                                "template_id": prompt_view.template_id,
                                "template_version": prompt_view.template_version,
                                "prompt_limits_hash": request.prompt_limits_hash,
                                "rendered_messages": request.request.rendered_messages,
                            }
                        ),
                        "request_parameters": request.request_parameters,
                        "request_parameters_semantic_hash": canonical_payload_hash(
                            request.request_parameters
                        ),
                        "model_identity": request.model_identity,
                        "model_identity_semantic_hash": canonical_payload_hash(
                            request.model_identity
                        ),
                        "model_seed": request.model_seed,
                        "response_outcome": invocation.response.outcome,
                        "response_semantic_hash": canonical_payload_hash(
                            {
                                "raw_response": invocation.response.raw_response,
                                "error": invocation.response.error,
                                "runtime_identity": invocation.response.runtime_identity,
                                "model_identity": invocation.response.model_identity,
                                "mock_seed": invocation.response.mock_seed,
                            }
                        ),
                        **parse_semantics,
                    }
                )
            event_semantics.append(
                {
                    "event_ordinal": ordinal,
                    "sweep_index": event.sweep_index,
                    "draw_index": event.draw_index,
                    "agent_id": event.agent_id,
                    "status": event.status.value,
                    "publish_flag": event.publish_flag,
                    "exposure": {
                        "mode": exposure.exposure_mode,
                        "graph_hash": exposure.exposure_graph_hash,
                        "capacity": exposure.capacity,
                        "source_agent_ids": exposure.source_agent_ids,
                        "source_event_ordinals": tuple(
                            None if source is None else event_ordinal_by_id.get(source)
                            for source in exposure.source_event_ids
                        ),
                        "message_ages": exposure.message_ages,
                        "round0_message_count": sum(
                            source is None for source in exposure.source_event_ids
                        ),
                        "expired_message_count": len(exposure.expired_post_ids),
                    },
                    "attempts": tuple(attempts),
                }
            )
        latest_stock: dict[str, Mapping[str, object]] = {}
        for value in public_values:
            latest_stock[value["author_agent_id"]] = value
        roster = storage.binding.expected_agent_ids
        if set(latest_stock) != set(roster):
            raise ValueError("public stock does not exact-cover the population")
        return MockComparableRunProjection(
            schema_version="paper1.mock-comparable-run-projection.v1",
            matched_seed=matched_seed,
            cell_id=audit.cell_id,
            schedule_hash=storage.binding.schedule_hash,
            committed_event_semantics=tuple(event_semantics),
            final_private_states=tuple(_private_semantics(value) for value in private_values),
            final_public_stock=tuple(_post_semantics(latest_stock[agent]) for agent in roster),
            final_feed_cursors=tuple(_cursor_semantics(value) for value in cursor_values),
            process_audit_semantics=_audit_semantics(audit),
        )
