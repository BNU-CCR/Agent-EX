"""Explicit SIS binding over the shared SQLite v6 initial-state transactions.

Event writes are gated off until SIS causal-prefix and commit integration exists.
"""

from dataclasses import dataclass
import re
from typing import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import (
    FrozenSchedule,
    _freeze,
    _json_ready,
    _require_int,
    _require_sha256,
    canonical_payload_hash,
)
from ..network import validate_ws_artifact
from ..storage import RunStorage, _load_canonical_json
from ..topic import TopicPackage
from .contracts import STUDY_ID, StudyCell, study_cells
from .groups import GroupContext
from .networks import validate_randomized_counterpart


BINDING_SCHEMA = "paper1.identity-network.storage-binding.v1"


@dataclass(frozen=True, slots=True, init=False)
class StudyRunBinding:
    cell: StudyCell
    matched_seed: int
    groups: GroupContext
    aliases: Mapping[str, str]
    node_agent_ids: tuple[str, ...]
    topic_package: TopicPackage
    schedule: FrozenSchedule
    ws: ArtifactEnvelope
    randomized: ArtifactEnvelope
    common_inputs_hash: str
    _payload: Mapping[str, object]

    @classmethod
    def create(
        cls,
        *,
        cell,
        matched_seed,
        groups,
        aliases,
        node_agent_ids,
        topic_package,
        schedule,
        ws,
        randomized,
        common_inputs_hash,
    ):
        if cell not in study_cells() or not isinstance(cell, StudyCell):
            raise ValueError("canonical SIS cell required")
        _require_int("matched_seed", matched_seed)
        _require_sha256("common_inputs_hash", common_inputs_hash)
        if not isinstance(topic_package, TopicPackage) or not isinstance(schedule, FrozenSchedule):
            raise TypeError("typed topic and schedule required")
        context = GroupContext.from_artifact(groups)
        agents = tuple(node_agent_ids)
        if (
            not agents
            or len(set(agents)) != len(agents)
            or set(agents) != set(context.memberships)
            or len(agents) != schedule.population_size
            or any(slot.agent_id not in context.memberships for slot in schedule.slots)
        ):
            raise ValueError("schedule/roster/group exact cover mismatch")
        if groups.payload["matched_seed"] != matched_seed:
            raise ValueError("group matched seed mismatch")
        if any(
            s not in topic_package.stance_labels for s in groups.payload["initial_stances"].values()
        ):
            raise ValueError("group initial stances must use topic labels")
        if not isinstance(aliases, Mapping) or set(aliases) != set(agents):
            raise ValueError("alias roster mismatch")
        if any(
            type(a) is not str or re.fullmatch(r"member-[0-9]+", a, flags=re.ASCII) is None
            for a in aliases.values()
        ):
            raise ValueError("neutral member aliases required")
        if len(set(aliases.values())) != len(agents):
            raise ValueError("aliases must be bijective")
        validate_ws_artifact(ws)
        validate_randomized_counterpart(randomized, ws)
        if (
            ws.payload["matched_seed"] != matched_seed
            or tuple(ws.payload["nodes"]) != tuple(range(len(agents)))
            or not ws.payload["structure_report"]["connected"]
        ):
            raise ValueError("graph seed/node roster/connectivity mismatch")
        # Reopen keeps full artifacts; no fabricated protocol freeze or runtime receipt.
        payload = _json_ready(
            {
                "schema_version": BINDING_SCHEMA,
                "study_id": STUDY_ID,
                "cell_id": cell.cell_id,
                "matched_seed": matched_seed,
                "groups": groups.to_payload(),
                "aliases": dict(aliases),
                "node_agent_ids": agents,
                "topic_package": topic_package.to_payload(),
                "schedule": schedule.to_payload(),
                "ws": ws.to_payload(),
                "randomized": randomized.to_payload(),
                "common_inputs_hash": common_inputs_hash,
                "metadata": {
                    "status": "preliminary",
                    "research_parameter_status": "not_frozen",
                    "formal_parameter_authority": False,
                },
            }
        )
        result = object.__new__(cls)
        values = dict(
            cell=cell,
            matched_seed=matched_seed,
            groups=context,
            aliases=_freeze(dict(aliases)),
            node_agent_ids=agents,
            topic_package=topic_package,
            schedule=schedule,
            ws=ws,
            randomized=randomized,
            common_inputs_hash=common_inputs_hash,
            _payload=_freeze(payload),
        )
        for name, value in values.items():
            object.__setattr__(result, name, value)
        return result

    @property
    def record_hash(self):
        return canonical_payload_hash(self._payload)

    def to_payload(self):
        return _json_ready({**self._payload, "record_hash": self.record_hash})

    @classmethod
    def from_payload(cls, payload):
        fields = {
            "schema_version",
            "study_id",
            "cell_id",
            "matched_seed",
            "groups",
            "aliases",
            "node_agent_ids",
            "topic_package",
            "schedule",
            "ws",
            "randomized",
            "common_inputs_hash",
            "metadata",
            "record_hash",
        }
        if not isinstance(payload, Mapping) or set(payload) != fields:
            raise ValueError("SIS binding fields mismatch")
        payload = _json_ready(payload)
        if payload["schema_version"] != BINDING_SCHEMA or payload["study_id"] != STUDY_ID:
            raise ValueError("SIS binding schema/study mismatch")
        cell = next((c for c in study_cells() if c.cell_id == payload["cell_id"]), None)
        result = cls.create(
            cell=cell,
            matched_seed=payload["matched_seed"],
            groups=ArtifactEnvelope.from_payload(payload["groups"]),
            aliases=payload["aliases"],
            node_agent_ids=payload["node_agent_ids"],
            topic_package=TopicPackage.from_payload(payload["topic_package"]),
            schedule=FrozenSchedule.from_payload(payload["schedule"]),
            ws=ArtifactEnvelope.from_payload(payload["ws"]),
            randomized=ArtifactEnvelope.from_payload(payload["randomized"]),
            common_inputs_hash=payload["common_inputs_hash"],
        )
        if canonical_payload_hash(payload) != canonical_payload_hash(result.to_payload()):
            raise ValueError("SIS binding hash/metadata mismatch")
        return result

    @property
    def cursor_mode(self):
        # This shared cursor mode means fixed graph-neighbor traversal, not a SIS factor ID.
        return "self_history_only" if self.cell.network == "no_social" else "ws_neighbors"

    @property
    def exposure_graph(self):
        if self.cell.network == "no_social":
            return None
        return self.randomized if self.cell.network == "randomized" else self.ws

    @property
    def exposure_graph_hash(self):
        return None if self.exposure_graph is None else self.exposure_graph.output_hash

    def storage_arguments(self):
        artifacts = {a.artifact_id: a.output_hash for a in (self.ws, self.randomized)}
        artifacts["sis-binding"] = self.record_hash
        return dict(
            artifact_hashes=artifacts,
            expected_agent_ids=self.node_agent_ids,
            expected_exposure_mode=self.cursor_mode,
            expected_exposure_graph_hash=self.exposure_graph_hash,
            expected_exposure_graph_artifact=self.exposure_graph,
            expected_source_ws_artifact=None if self.exposure_graph is None else self.ws,
        )


class StudyRunStorage(RunStorage):
    """SIS initial-state store; shared tables/leases/transactions, distinct validation."""

    @staticmethod
    def _validate_run_exposure(
        manifest, artifacts, population_size, mode, graph_hash, graph, source_ws
    ):
        if manifest.run_spec.get("study_id") != STUDY_ID or manifest.protocol_id != STUDY_ID:
            raise ValueError("explicit SIS manifest required")
        binding = StudyRunBinding.from_payload(manifest.run_spec.get("identity_network_binding"))
        if (
            manifest.run_spec.get("cell_id") != binding.cell.cell_id
            or manifest.matched_seed != binding.matched_seed
            or manifest.schedule != binding.schedule
            or population_size != len(binding.node_agent_ids)
            or artifacts != binding.storage_arguments()["artifact_hashes"]
            or mode != binding.cursor_mode
            or graph_hash != binding.exposure_graph_hash
            or graph != binding.exposure_graph
            or source_ws != (None if graph is None else binding.ws)
        ):
            raise ValueError("SIS manifest/schedule/artifact exposure binding mismatch")
        if graph is None:
            return mode, None, None, None, None, None, None
        return (
            mode,
            graph_hash,
            graph.artifact_id,
            graph.artifact_type,
            binding.ws.output_hash,
            binding.ws.artifact_id,
            binding.ws.artifact_type,
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        payload = _load_canonical_json(
            self._connection.execute(
                "SELECT manifest_payload_json FROM binding WHERE singleton=1"
            ).fetchone()[0],
            "SIS manifest",
        )
        self.study_binding = StudyRunBinding.from_payload(
            payload["run_spec"]["identity_network_binding"]
        )
        if set(self.binding.expected_agent_ids) != set(self.study_binding.node_agent_ids):
            raise ValueError("SIS stored roster mismatch")

    def _validate_initial_update(self, update):
        binding = self.study_binding
        if (
            update.agent_id not in binding.groups.memberships
            or update.matched_seed != binding.matched_seed
            or update.topic_package_id != binding.topic_package.topic_id
            or update.topic_package_hash != binding.topic_package.package_hash
            or update.stance_label
            != binding._payload["groups"]["payload"]["initial_stances"][update.agent_id]
        ):
            raise ValueError("SIS initial state does not bind groups/topic/seed")

    def initialize_agent(self, **kwargs):
        self._validate_initial_update(kwargs["private_update"])
        return super().initialize_agent(**kwargs)

    def verify_integrity(self):
        super().verify_integrity()
        self._round0_entries(require_exact=self.binding.round0_root is not None)

    def _round0_entries(self, *, require_exact):
        from ..state import PrivateUpdate

        entries = super()._round0_entries(require_exact=require_exact)
        for entry in entries:
            self._validate_initial_update(PrivateUpdate.from_payload(entry["private_update"]))
        return entries

    def record_prepared_attempt(self, *args, **kwargs):
        raise ValueError("SIS event writes require the SIS causal-prefix integration")

    def record_diagnostic_prepared_attempt(self, *args, **kwargs):
        raise ValueError("SIS event writes require the SIS causal-prefix integration")

    def append_attempt(self, *args, **kwargs):
        raise ValueError("SIS event writes require the SIS causal-prefix integration")

    def commit_success(self, *args, **kwargs):
        raise ValueError("SIS event writes require the SIS atomic event integration")
