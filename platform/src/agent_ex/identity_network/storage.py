"""Explicit SIS binding, causal prefixes and derived commits over SQLite v6.

No HTTP dispatch, real-run authorization or automatic retry is provided here.
"""

from dataclasses import dataclass, replace
import json
import re
from typing import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import (
    FrozenSchedule,
    EventStatus,
    _freeze,
    _json_ready,
    _require_int,
    _require_sha256,
    canonical_payload_hash,
    derive_event_id,
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
        self._execution_inputs_cache = None
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
        self._sis_run_spec = _freeze(payload["run_spec"])
        common_payload = payload["run_spec"].get("identity_network_execution_inputs")
        self._stored_common_inputs = None
        self._stored_common_initial_root = None
        self._historical_input_contexts = {}
        if common_payload is not None:
            from .execution_inputs import validate_execution_inputs

            self._stored_common_inputs = ArtifactEnvelope.from_payload(common_payload)
            validate_execution_inputs(self._stored_common_inputs, self.study_binding)

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
        # A sealed cold replay already calls our typed _round0_entries override;
        # the parent's connection-signature cache then protects trusted writes.
        # Partial initialization still needs SIS checks even without a root.
        if self.binding.round0_root is None:
            self._round0_entries(require_exact=False)

    def _round0_entries(self, *, require_exact):
        from ..state import PrivateUpdate

        entries = super()._round0_entries(require_exact=require_exact)
        for entry in entries:
            self._validate_initial_update(PrivateUpdate.from_payload(entry["private_update"]))
        return entries

    def snapshot_next_input(self, *, persona_text, feed_capacity, memory_window):
        """Read the next causal input under a lease; neither dispatch nor commit.

        Capacity/window are explicit candidate values accepted by the shared
        preliminary feed/memory primitives, not a formal protocol freeze.
        """
        from ..feed import select_unread_feed
        from ..memory import build_memory_view
        from .prompts import ShownPost, render_study_prompt

        self.assert_run_lease_owned()
        if self._connection.in_transaction:
            raise RuntimeError("input snapshot cannot nest a storage transaction")
        self._connection.execute("BEGIN")
        try:
            self.verify_integrity()
            if self.binding.round0_root is None:
                raise ValueError("input snapshot requires sealed round-0")
            binding = self.study_binding
            progress = self.progress
            ordinal = progress.next_event_ordinal
            if ordinal >= len(binding.schedule.slots):
                raise ValueError("input snapshot has no next scheduled event")
            slot = binding.schedule.slots[ordinal]
            receiver = slot.agent_id
            neighbors = []
            if binding.exposure_graph is not None:
                node = binding.node_agent_ids.index(receiver)
                for left, right in binding.exposure_graph.payload["edges"]:
                    if left == node:
                        neighbors.append(binding.node_agent_ids[right])
                    elif right == node:
                        neighbors.append(binding.node_agent_ids[left])
            neighbors = tuple(sorted(neighbors))
            state = self.private_state(receiver)
            cursor = self.feed_cursor(receiver)
            unread = self.unread_public_posts_for_agents(
                neighbors, cursor.last_scanned_event_ordinal
            )
            history = self.private_updates_for_agent(receiver)
            selection = select_unread_feed(
                unread_public_posts=unread,
                topic_package=binding.topic_package,
                neighbor_agent_ids=neighbors,
                cursor=cursor,
                receiver_event_id=derive_event_id(self.binding.run_id, ordinal),
                receiver_event_ordinal=ordinal,
                matched_seed=binding.matched_seed,
                exposure_mode=binding.cursor_mode,
                exposure_graph_hash=binding.exposure_graph_hash,
                capacity=feed_capacity,
                mock_only=True,
            )
            memory = build_memory_view(
                private_updates=history,
                topic_package=binding.topic_package,
                matched_seed=binding.matched_seed,
                agent_id=receiver,
                window=memory_window,
                mock_only=True,
            )
            posts = tuple(
                ShownPost(
                    p.post_id,
                    p.source_agent_id,
                    binding.aliases[p.source_agent_id],
                    p.stance_label,
                    p.public_reason,
                )
                for p in sorted(selection.selected, key=lambda p: p.display_slot)
            )
            prompt = render_study_prompt(
                cell=binding.cell,
                groups=binding.groups,
                receiver_id=receiver,
                persona_text=persona_text,
                topic_package=binding.topic_package,
                pre_state={"stance": state.stance_label, "reason": state.reason},
                self_history=tuple(
                    {"stance": i.stance_label, "reason": i.private_reason, "published": i.published}
                    for i in memory.items
                ),
                posts=posts,
            )
            return ArtifactEnvelope.create(
                artifact_type="sis-input-snapshot",
                schema_version="paper1.identity-network.input-snapshot.v1",
                algorithm_id="sis-sqlite-input-snapshot",
                algorithm_version="1.0.0",
                input_hashes={"study-binding": binding.record_hash},
                rng_provenance=(),
                payload={
                    "run_id": self.binding.run_id,
                    "study_binding_hash": binding.record_hash,
                    "round0_root": self.binding.round0_root,
                    "event_id": derive_event_id(self.binding.run_id, ordinal),
                    "event_ordinal": ordinal,
                    "receiver_agent_id": receiver,
                    "previous_event_hash": progress.event_chain_head,
                    "publish_flag": slot.publish_flag,
                    "pre_state": state.to_payload(),
                    "potential_neighbor_ids": neighbors,
                    "unread_public_posts": tuple(p.to_payload() for p in unread),
                    "private_history": tuple(u.to_payload() for u in history),
                    "selection": selection.to_payload(),
                    "memory": memory.to_payload(),
                    "prompt": {
                        "messages": prompt.messages,
                        "prompt_hash": prompt.prompt_hash,
                        "evidence": prompt.evidence,
                        "evidence_hash": prompt.evidence_hash,
                    },
                    "metadata": {
                        "status": "preliminary",
                        "research_parameter_status": "not_frozen",
                        "formal_parameter_authority": False,
                        "committed": False,
                    },
                },
            )
        finally:
            self._connection.rollback()

    def prepare_snapshot_event(
        self,
        snapshot,
        *,
        persona_text,
        feed_capacity,
        memory_window,
        attempt_index,
        parser_limits,
        model_seed,
        generation_settings,
        adapter_binding_hash,
    ):
        """Build a prospective request only after replaying the whole input snapshot.

        Not a dispatch authorization: no intent/policy/response has been persisted.
        The caller must retain the lease through later durable-prefix integration.
        Model settings and candidate policies still need a common-input artifact.
        """
        from ..state import PrivateState
        from .execution import prepare_study_event
        from .prompts import StudyPrompt

        if not isinstance(snapshot, ArtifactEnvelope):
            raise TypeError("typed SIS input snapshot required")
        current = self.snapshot_next_input(
            persona_text=persona_text, feed_capacity=feed_capacity, memory_window=memory_window
        )
        if snapshot != current:
            raise ValueError("snapshot does not match current SIS database input")
        payload = current.payload
        prompt_payload = payload["prompt"]
        prompt = StudyPrompt(
            messages=prompt_payload["messages"],
            prompt_hash=prompt_payload["prompt_hash"],
            evidence=prompt_payload["evidence"],
            evidence_hash=prompt_payload["evidence_hash"],
        )
        return prepare_study_event(
            run_id=payload["run_id"],
            event_ordinal=payload["event_ordinal"],
            attempt_index=attempt_index,
            previous_event_hash=payload["previous_event_hash"],
            publish_flag=payload["publish_flag"],
            prompt=prompt,
            private_state=PrivateState.from_payload(_json_ready(payload["pre_state"])),
            topic_package=self.study_binding.topic_package,
            parser_limits=parser_limits,
            model_seed=model_seed,
            generation_settings=generation_settings,
            adapter_binding_hash=adapter_binding_hash,
        )

    def prepare_bound_snapshot_event(self, snapshot, common_inputs, *, attempt_index):
        """Candidate request with all settings resolved from one bound artifact.

        Does not authorize dispatch, a retry or a formal run. In particular, no
        durable policy/input/intent has been written by this read-side method.
        """
        from ..parser import ParserLimits
        from ..phase0b.contracts import DiagnosticAdapterBinding
        from .execution_inputs import validate_execution_inputs

        self.assert_run_lease_owned()
        # Verify database mutations before consulting the immutable-object cache.
        self.verify_integrity()
        cached = self._execution_inputs_cache
        if cached is None or cached[0] is not common_inputs or cached[4] is not self.study_binding:
            validate_execution_inputs(common_inputs, self.study_binding)
            payload = common_inputs.payload
            actual = {
                e["agent_id"]: e["private_update"] for e in self._round0_entries(require_exact=True)
            }
            expected = {u["agent_id"]: _json_ready(u) for u in payload["initial_updates"]}
            if actual != expected:
                raise ValueError("execution-input initial updates differ from actual round-0")
            limits = ParserLimits.from_payload(_json_ready(payload["parser_limits"]))
            adapter = DiagnosticAdapterBinding.from_payload(_json_ready(payload["adapter_binding"]))
            cached = (common_inputs, payload, limits, adapter, self.study_binding)
            self._execution_inputs_cache = cached
        _, payload, limits, adapter, _ = cached
        ordinal = self.progress.next_event_ordinal
        slot = self.schedule_slot(ordinal)
        return self.prepare_snapshot_event(
            snapshot,
            persona_text=payload["persona_by_agent"][slot.agent_id],
            feed_capacity=payload["feed_capacity"],
            memory_window=payload["memory_window"],
            attempt_index=attempt_index,
            parser_limits=limits,
            model_seed=payload["model_seeds"][ordinal],
            generation_settings=payload["generation_settings"],
            adapter_binding_hash=adapter.record_hash,
        )

    def record_prepared_attempt(self, *args, **kwargs):
        raise ValueError("SIS event writes require the SIS causal-prefix integration")

    def record_diagnostic_prepared_attempt(self, *args, **kwargs):
        return RunStorage.record_diagnostic_prepared_attempt(self, *args, **kwargs)

    def event_input_evidence(self, event_id):
        from .stored_input import StoredStudyInput

        row = self._read_evidence_payload(
            "event_input_evidence", "event_id", event_id, payload_key="event_id"
        )
        if row is None:
            return None
        return StoredStudyInput.from_payload(row[0])

    def _diagnostic_input_projection(self, event_input):
        from ..feed import ExposureSelection
        from ..memory import MemoryView
        from ..parser import ParserLimits
        from .prompts import ShownPost, render_study_prompt
        from .stored_input import StoredStudyInput

        if not isinstance(event_input, StoredStudyInput):
            raise TypeError("SIS prefix requires typed StoredStudyInput, never legacy input")
        if self._stored_common_inputs is None:
            raise ValueError("SIS prefix requires complete execution inputs in manifest")
        if self.binding.round0_root is None:
            raise ValueError("SIS prefix requires sealed round-0")
        binding = self.study_binding
        common = self._stored_common_inputs.payload
        if self._stored_common_initial_root != self.binding.round0_root:
            actual = {
                e["agent_id"]: e["private_update"] for e in self._round0_entries(require_exact=True)
            }
            expected = {u["agent_id"]: _json_ready(u) for u in common["initial_updates"]}
            if actual != expected:
                raise ValueError("SIS prefix common initial state differs from actual round-0")
            self._stored_common_initial_root = self.binding.round0_root
        i = event_input.input
        s = event_input.snapshot.payload
        ordinal = i.event_ordinal
        if i.run_id != self.binding.run_id or ordinal > self.progress.next_event_ordinal:
            raise ValueError("SIS input lies outside the actual event prefix")
        slot = self.schedule_slot(ordinal)
        if ordinal == self.progress.next_event_ordinal:
            cursor = self.feed_cursor(slot.agent_id)
            pre_state = self.private_state(slot.agent_id)
            previous_hash = self.progress.event_chain_head
        else:
            context = self._historical_input_contexts.get(ordinal)
            if context is None:
                raise ValueError("SIS historical input lacks independently replayed context")
            pre_state, cursor, previous_hash = context
        selection = ExposureSelection.from_payload(_json_ready(s["selection"]))
        memory = MemoryView.from_payload(_json_ready(s["memory"]))
        neighbors = []
        if binding.exposure_graph is not None:
            node = binding.node_agent_ids.index(slot.agent_id)
            for a, b in binding.exposure_graph.payload["edges"]:
                if a == node:
                    neighbors.append(binding.node_agent_ids[b])
                elif b == node:
                    neighbors.append(binding.node_agent_ids[a])
        neighbors = tuple(sorted(neighbors))
        actual_posts = tuple(
            p
            for p in self.unread_public_posts_for_agents(
                neighbors, cursor.last_scanned_event_ordinal
            )
            if p.published_event_ordinal is None or p.published_event_ordinal < ordinal
        )
        actual_history = tuple(
            u
            for u in self.private_updates_for_agent(slot.agent_id)
            if u.event_ordinal is None or u.event_ordinal < ordinal
        )
        if (
            i.receiver_agent_id != slot.agent_id
            or i.publish_flag != slot.publish_flag
            or i.private_state != pre_state
            or i.previous_event_hash != previous_hash
            or i.topic_package != binding.topic_package
            or i.parser_limits != ParserLimits.from_payload(_json_ready(common["parser_limits"]))
            or s["study_binding_hash"] != binding.record_hash
            or s["round0_root"] != self.binding.round0_root
            or tuple(s["potential_neighbor_ids"]) != neighbors
            or selection.cursor_before != cursor
            or selection.exposure_mode != binding.cursor_mode
            or selection.exposure_graph_hash != binding.exposure_graph_hash
            or selection.capacity != common["feed_capacity"]
            or memory.window != common["memory_window"]
            or canonical_payload_hash(s["unread_public_posts"])
            != canonical_payload_hash(tuple(p.to_payload() for p in actual_posts))
            or canonical_payload_hash(s["private_history"])
            != canonical_payload_hash(tuple(u.to_payload() for u in actual_history))
        ):
            raise ValueError("SIS prefix input differs from current database/common contract")
        expected_prompt = render_study_prompt(
            cell=binding.cell,
            groups=binding.groups,
            receiver_id=slot.agent_id,
            persona_text=common["persona_by_agent"][slot.agent_id],
            topic_package=binding.topic_package,
            pre_state={"stance": i.private_state.stance_label, "reason": i.private_state.reason},
            self_history=tuple(
                {"stance": m.stance_label, "reason": m.private_reason, "published": m.published}
                for m in memory.items
            ),
            posts=tuple(
                ShownPost(
                    p.post_id,
                    p.source_agent_id,
                    binding.aliases[p.source_agent_id],
                    p.stance_label,
                    p.public_reason,
                )
                for p in sorted(selection.selected, key=lambda p: p.display_slot)
            ),
        )
        if i.prompt != expected_prompt:
            raise ValueError("SIS prefix exact prompt differs from bound group/alias/common inputs")
        return dict(
            event_ordinal=i.event_ordinal,
            prompt_hash=i.prompt.prompt_hash,
            exposure_id=event_input.exposure_id,
            exposure_mode=binding.cursor_mode,
            exposure_graph_hash=binding.exposure_graph_hash,
            topic_package_id=i.topic_package.topic_id,
            topic_hash=i.topic_package.package_hash,
        )

    def _validate_diagnostic_request_contract(self, event_input, request, policy, adapter):
        from ..execution_evidence import DiagnosticAdapterRequestEvidence
        from ..phase0b.contracts import DiagnosticAdapterBinding, DiagnosticAttemptPolicy

        if not isinstance(request, DiagnosticAdapterRequestEvidence):
            raise TypeError("SIS prefix requires diagnostic request evidence")
        common = self._stored_common_inputs.payload
        authorization = self._sis_run_spec.get("sis_diagnostic_authorization_hash")
        _require_sha256("SIS candidate authorization hash", authorization)
        if request.run_authorization_hash != authorization:
            raise ValueError("SIS prefix authorization does not match manifest reference")
        if (
            policy != DiagnosticAttemptPolicy.from_payload(_json_ready(common["attempt_policy"]))
            or adapter
            != DiagnosticAdapterBinding.from_payload(_json_ready(common["adapter_binding"]))
            or request.request.generation_settings != common["generation_settings"]
            or request.model_seed != common["model_seeds"][event_input.input.event_ordinal]
            or request.request.rendered_messages != event_input.input.prompt.messages
        ):
            raise ValueError("SIS prefix request/policy/adapter differs from common inputs")

    def append_attempt(self, *args, **kwargs):
        raise ValueError("SIS event writes require the SIS causal-prefix integration")

    def start_diagnostic_attempt(self, pending, *, started_at):
        """Persist IN_PROGRESS without sending or authorizing any HTTP request."""
        self.assert_run_lease_owned()
        self.verify_integrity()
        if (
            self.current_event_journal().latest_transition != pending
            or pending.status is not EventStatus.PENDING
        ):
            raise ValueError("SIS start requires the exact durable PENDING attempt")
        self._prepared_for_attempt(pending.attempt_id)
        in_progress = replace(pending, status=EventStatus.IN_PROGRESS, started_at=started_at)
        RunStorage.append_attempt(self, in_progress)
        return in_progress

    def _prepared_for_attempt(self, attempt_id):
        from ..execution_evidence import DiagnosticAdapterRequestEvidence
        from .execution import prepare_study_event

        request = self.adapter_request_evidence(attempt_id)
        if not isinstance(request, DiagnosticAdapterRequestEvidence):
            raise ValueError("SIS response requires its diagnostic request prefix")
        stored = self.event_input_evidence(request.event_id)
        if stored is None:
            raise ValueError("SIS response requires its stored causal input")
        self._diagnostic_input_projection(stored)
        self._validate_diagnostic_request_contract(
            stored,
            request,
            self.attempt_policy_evidence(request.event_id),
            self.adapter_execution_binding(attempt_id),
        )
        i, r = stored.input, request.request
        prepared = prepare_study_event(
            run_id=i.run_id,
            event_ordinal=i.event_ordinal,
            attempt_index=r.attempt_index,
            previous_event_hash=i.previous_event_hash,
            publish_flag=i.publish_flag,
            prompt=i.prompt,
            private_state=i.private_state,
            topic_package=i.topic_package,
            parser_limits=i.parser_limits,
            model_seed=r.model_seed,
            generation_settings=dict(r.generation_settings),
            adapter_binding_hash=r.adapter_binding_hash,
        )
        if prepared.request != r:
            raise ValueError("SIS reconstructed request differs from durable request")
        return prepared

    def _validate_study_invocation(self, evidence):
        from ..execution_evidence import DiagnosticPersistedInvocationEvidence
        from .execution import finalize_study_response

        if not isinstance(evidence, DiagnosticPersistedInvocationEvidence):
            raise TypeError("SIS response requires typed diagnostic invocation")
        request = self.adapter_request_evidence(evidence.attempt_id)
        if request is None or evidence.run_authorization_hash != request.run_authorization_hash:
            raise ValueError("SIS invocation authorization differs from durable request")
        result = finalize_study_response(
            prepared=self._prepared_for_attempt(evidence.attempt_id), response=evidence.response
        )
        adapter = self.adapter_execution_binding(evidence.attempt_id)
        wire = json.loads(evidence.response.transport_evidence.request_body)
        if wire["model"] != adapter.served_model_name:
            raise ValueError("SIS wire model differs from bound served model")
        # Invalid provider JSON is retained as a failed parse, not discarded.
        # When a provider declares a model, it must agree with the bound name.
        try:
            provider = json.loads(evidence.response.raw_body)
        except (ValueError, UnicodeError, RecursionError):
            provider = None
        if result.parse.success and (
            not isinstance(provider, dict) or provider.get("model") != adapter.served_model_name
        ):
            raise ValueError("SIS successful response lacks the bound provider model")
        if (
            isinstance(provider, dict)
            and "model" in provider
            and provider["model"] != adapter.served_model_name
        ):
            raise ValueError("SIS response model differs from bound served model")
        return result

    def record_diagnostic_invocation_evidence(self, evidence):
        self.assert_run_lease_owned()
        self.verify_integrity()
        self._validate_study_invocation(evidence)
        return RunStorage.record_diagnostic_invocation_evidence(self, evidence)

    def record_diagnostic_finalized_attempt(self, terminal, parsed):
        from ..domain import GenerationAttempt
        from ..execution_evidence import DiagnosticParseEvidence

        self.assert_run_lease_owned()
        self.verify_integrity()
        if not isinstance(terminal, GenerationAttempt) or not isinstance(
            parsed, DiagnosticParseEvidence
        ):
            raise TypeError("SIS finalization requires typed diagnostic terminal and parse")
        result = self._validate_study_invocation(self.invocation_evidence(terminal.attempt_id))
        if result.parse != parsed:
            raise ValueError("SIS parse differs from bounded response replay")
        return RunStorage.record_diagnostic_finalized_attempt(self, terminal, parsed)

    def _verify_v6_evidence_exact_cover(self):
        self._rebuild_historical_input_contexts()
        super()._verify_v6_evidence_exact_cover()
        for (attempt_id,) in self._connection.execute(
            "SELECT attempt_id FROM invocation_evidence"
        ).fetchall():
            result = self._validate_study_invocation(self.invocation_evidence(attempt_id))
            parsed = self.parse_evidence(attempt_id)
            if parsed is not None and parsed != result.parse:
                raise ValueError("SIS stored parse differs from bounded response replay")

    def commit_success(self, *args, **kwargs):
        raise ValueError("SIS event writes require the SIS atomic event integration")

    def _rebuild_historical_input_contexts(self):
        """One forward pass on cold replay; no per-input prefix re-scans."""
        from ..state import PrivateUpdate, PrivateState, PublicPost
        from ..feed import FeedCursor

        self._historical_input_contexts = {}
        if self.progress.next_event_ordinal == 0:
            return
        entries = self._round0_entries(require_exact=True)
        states = {
            e["agent_id"]: PrivateState.from_update(
                PrivateUpdate.from_payload(e["private_update"]), previous=None, mock_only=True
            )
            for e in entries
        }
        cursors = {
            agent: self._read_typed_current("initial_feed_cursors", agent, FeedCursor)
            for agent in states
        }
        chain = self._event_chain_genesis(self.binding.round0_root)
        for ordinal in range(self.progress.next_event_ordinal):
            event = self.event_at(ordinal)
            if event is None:
                raise ValueError("SIS historical event prefix is incomplete")
            agent = self.schedule_slot(ordinal).agent_id
            self._historical_input_contexts[ordinal] = (states[agent], cursors[agent], chain)
            row = self._connection.execute(
                "SELECT payload_json, payload_hash FROM private_updates WHERE event_ordinal=?",
                (ordinal,),
            ).fetchall()
            if len(row) != 1:
                raise ValueError("SIS historical update is not exact-cover")
            payload = _load_canonical_json(row[0][0], "SIS historical update")
            if canonical_payload_hash(payload) != row[0][1]:
                raise ValueError("SIS historical update hash mismatch")
            update = PrivateUpdate.from_payload(payload)
            state = PrivateState.from_update(update, previous=states[agent], mock_only=True)
            cursor = cursors[agent].advance(ordinal)
            post = (
                PublicPost.from_private_update(update, mock_only=True)
                if event.publish_flag
                else None
            )
            chain = canonical_payload_hash(
                {
                    "previous": chain,
                    "event": event.to_payload(),
                    "attempts": self._attempt_chain_entries(
                        event.event_id, self.attempts_for_event(event.event_id)
                    ),
                    "private_update_hash": update.record_hash,
                    "private_state_hash": state.record_hash,
                    "public_post_hash": None if post is None else post.record_hash,
                    "cursor_hash": cursor.record_hash,
                }
            )
            states[agent], cursors[agent] = state, cursor

    def commit_study_success(self, attempt_id):
        """Derive all state changes from durable SIS evidence, then commit atomically."""
        from ..domain import GenerationEvent
        from ..feed import ExposureSelection
        from ..state import LatestPublicPointer

        self.assert_run_lease_owned()
        self.verify_integrity()
        journal = self.current_event_journal()
        terminal = journal.latest_transition
        if (
            terminal is None
            or terminal.attempt_id != attempt_id
            or terminal.status is not EventStatus.SUCCEEDED
        ):
            raise ValueError("SIS commit requires current durable terminal success")
        invocation = self.invocation_evidence(attempt_id)
        result = self._validate_study_invocation(invocation)
        if not result.parse.success or result.parse != self.parse_evidence(attempt_id):
            raise ValueError("SIS success parse differs from bounded durable response")
        stored = self.event_input_evidence(terminal.event_id)
        slot = self.schedule_slot(self.progress.next_event_ordinal)
        selection = ExposureSelection.from_payload(
            _json_ready(stored.snapshot.payload["selection"])
        )
        event = GenerationEvent(
            run_id=self.binding.run_id,
            event_id=terminal.event_id,
            event_ordinal=slot.event_ordinal,
            sweep_index=slot.sweep_index,
            draw_index=slot.draw_index,
            agent_id=slot.agent_id,
            publish_flag=slot.publish_flag,
            exposure_id=stored.exposure_id,
            status=EventStatus.SUCCEEDED,
            attempt_ids=tuple(a.attempt_id for a in self.attempts_for_event(terminal.event_id)),
            failure_reason=None,
        )
        pointer = (
            None
            if result.public_post is None
            else LatestPublicPointer.from_post(
                result.public_post,
                previous=self.latest_public_pointer(slot.agent_id),
                mock_only=True,
            )
        )
        RunStorage.commit_success(
            self,
            event,
            final_attempt=terminal,
            private_update=result.private_update,
            private_state=result.private_state,
            feed_cursor=selection.cursor_after,
            public_post=result.public_post,
            latest_public_pointer=pointer,
        )
