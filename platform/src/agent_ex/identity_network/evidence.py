"""Reconstructable SIS inputs; independent of provider attempt identity."""

from dataclasses import dataclass
from typing import Mapping

from ..domain import (
    _json_ready,
    _require_id,
    _require_int,
    _require_sha256,
    canonical_payload_hash,
    derive_event_id,
)
from ..parser import ParserLimits
from ..state import PrivateState
from ..topic import TopicPackage
from .contracts import STUDY_ID, study_cells
from .prompts import RENDERER_VERSION, StudyPrompt, validate_study_prompt_projection


INPUT_SCHEMA = "paper1.identity-network.event-input.v1"


def _metadata():
    return {
        "status": "preliminary",
        "research_parameter_status": "not_frozen",
        "formal_parameter_authority": False,
        "committed": False,
    }


@dataclass(frozen=True, slots=True)
class StudyEventInputEvidence:
    run_id: str
    event_ordinal: int
    previous_event_hash: str
    publish_flag: bool
    prompt: StudyPrompt
    private_state: PrivateState
    topic_package: TopicPackage
    parser_limits: ParserLimits

    def __post_init__(self):
        _require_id("run_id", self.run_id)
        _require_int("event_ordinal", self.event_ordinal)
        _require_sha256("previous_event_hash", self.previous_event_hash)
        if type(self.publish_flag) is not bool:
            raise TypeError("publish_flag must be boolean")
        for value, expected in (
            (self.prompt, StudyPrompt),
            (self.private_state, PrivateState),
            (self.topic_package, TopicPackage),
            (self.parser_limits, ParserLimits),
        ):
            if not isinstance(value, expected):
                raise TypeError("typed SIS input components required")
        evidence = self.prompt.evidence
        if evidence["renderer_version"] != RENDERER_VERSION:
            raise ValueError("unsupported renderer")
        if evidence["cell_id"] not in {c.cell_id for c in study_cells()}:
            raise ValueError("unknown SIS cell")
        if evidence["receiver_id"] != self.private_state.agent_id:
            raise ValueError("receiver identity drift")
        if evidence["pre_state"] != {
            "stance": self.private_state.stance_label,
            "reason": self.private_state.reason,
        }:
            raise ValueError("pre-state drift")
        if (
            self.private_state.event_ordinal is not None
            and self.private_state.event_ordinal >= self.event_ordinal
        ):
            raise ValueError("event ordinal must advance receiver state")
        if (
            evidence["topic_package_hash"] != self.topic_package.package_hash
            or self.private_state.topic_package_hash != self.topic_package.package_hash
            or evidence["topic_package_id"] != self.topic_package.topic_id
            or self.private_state.topic_package_id != self.topic_package.topic_id
        ):
            raise ValueError("topic identity drift")
        if evidence["exact_messages_shown"] != self.prompt.messages:
            raise ValueError("exact messages drift")
        validate_study_prompt_projection(self.prompt, self.topic_package)

    @property
    def event_id(self):
        return derive_event_id(self.run_id, self.event_ordinal)

    @property
    def receiver_agent_id(self):
        return self.private_state.agent_id

    @property
    def record_hash(self):
        return canonical_payload_hash(self.content_payload())

    def content_payload(self):
        return _json_ready(
            {
                "schema_version": INPUT_SCHEMA,
                "study_id": STUDY_ID,
                "run_id": self.run_id,
                "event_id": self.event_id,
                "event_ordinal": self.event_ordinal,
                "receiver_agent_id": self.receiver_agent_id,
                "previous_event_hash": self.previous_event_hash,
                "publish_flag": self.publish_flag,
                "prompt": {
                    "messages": self.prompt.messages,
                    "prompt_hash": self.prompt.prompt_hash,
                    "evidence": self.prompt.evidence,
                    "evidence_hash": self.prompt.evidence_hash,
                },
                "pre_state": self.private_state.to_payload(),
                "topic_package": self.topic_package.to_payload(),
                "parser_limits": self.parser_limits.to_payload(),
                "metadata": _metadata(),
            }
        )

    def to_payload(self):
        return {**self.content_payload(), "record_hash": self.record_hash}

    @classmethod
    def from_prepared(cls, prepared):
        from .execution import PreparedStudyEvent

        if not isinstance(prepared, PreparedStudyEvent):
            raise TypeError("typed PreparedStudyEvent required")
        return cls(*(getattr(prepared, name) for name in cls.__dataclass_fields__))

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]):
        fields = {
            "schema_version",
            "study_id",
            "run_id",
            "event_id",
            "event_ordinal",
            "receiver_agent_id",
            "previous_event_hash",
            "publish_flag",
            "prompt",
            "pre_state",
            "topic_package",
            "parser_limits",
            "metadata",
            "record_hash",
        }
        if not isinstance(payload, Mapping) or set(payload) != fields:
            raise ValueError("SIS input fields mismatch")
        if payload["schema_version"] != INPUT_SCHEMA or payload["study_id"] != STUDY_ID:
            raise ValueError("SIS input schema/study mismatch")
        if canonical_payload_hash(payload["metadata"]) != canonical_payload_hash(_metadata()):
            raise ValueError("SIS input metadata mismatch")
        if (
            canonical_payload_hash({k: v for k, v in payload.items() if k != "record_hash"})
            != payload["record_hash"]
        ):
            raise ValueError("SIS input hash mismatch")
        prompt = payload["prompt"]
        if not isinstance(prompt, Mapping) or set(prompt) != {
            "messages",
            "prompt_hash",
            "evidence",
            "evidence_hash",
        }:
            raise ValueError("SIS prompt fields mismatch")
        messages = prompt["messages"]
        if not isinstance(messages, (tuple, list)):
            raise TypeError("SIS messages must be ordered")
        result = cls(
            payload["run_id"],
            payload["event_ordinal"],
            payload["previous_event_hash"],
            payload["publish_flag"],
            StudyPrompt(
                tuple(messages), prompt["prompt_hash"], prompt["evidence"], prompt["evidence_hash"]
            ),
            PrivateState.from_payload(payload["pre_state"]),
            TopicPackage.from_payload(payload["topic_package"]),
            ParserLimits.from_payload(payload["parser_limits"]),
        )
        if (
            result.event_id != payload["event_id"]
            or result.receiver_agent_id != payload["receiver_agent_id"]
        ):
            raise ValueError("SIS input event/receiver identity mismatch")
        if result.record_hash != payload["record_hash"]:
            raise ValueError("SIS input canonical reconstruction hash mismatch")
        return result
