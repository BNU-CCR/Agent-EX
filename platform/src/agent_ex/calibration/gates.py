"""Evidence-bound, deterministic calibration gates; no formal selection authority."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, fields
from fractions import Fraction
from itertools import combinations
from statistics import mean, stdev
from types import MappingProxyType
from typing import Mapping

from ..artifacts import ArtifactEnvelope
from ..domain import _freeze, _require_id, _require_sha256, canonical_payload_hash
from .contracts import ProbeCase, ProbeParseEvidence, ProbeRunProjection, ProbeTopicCandidate


TOPIC_ORDER = ("retirement-delay", "gm-soybean-oil", "ai-net-employment")
SCALES = {"stance-1-7": tuple(range(1, 8)), "stance-0-10": tuple(range(11))}


class GateFailure(ValueError):
    """A prespecified numerical gate cannot be satisfied or calculated."""


def paired_dz(deltas: tuple[int, ...]) -> float:
    """Paired integer-scale mean difference divided by unbiased sample SD."""
    if type(deltas) is not tuple or any(type(x) is not int for x in deltas):
        raise TypeError("deltas must be a tuple of integer-scale differences")
    if len(deltas) < 2:
        raise GateFailure("at least two valid pairs are required")
    deviation = stdev(deltas)
    average = mean(deltas)
    if deviation == 0:
        if average != 0:
            raise GateFailure("nonzero difference with zero variance")
        return 0.0
    return average / deviation


def _dz_passes(deltas: tuple[int, ...], threshold: Fraction) -> bool:
    # Compare the squared rational statistic exactly; stdev is for reporting only.
    paired_dz(deltas)
    n = len(deltas)
    average = Fraction(sum(deltas), n)
    variance = sum((Fraction(x) - average) ** 2 for x in deltas) / (n - 1)
    return average == 0 or average**2 <= threshold**2 * variance


def total_variation(a: tuple[int, ...], b: tuple[int, ...], scale: tuple[int, ...]) -> Fraction:
    """Exact empirical TV over every legal integer-scale category."""
    if any(type(v) is not tuple for v in (a, b, scale)):
        raise TypeError("samples and scale must be tuples")
    if not scale or len(set(scale)) != len(scale) or any(type(x) is not int for x in scale):
        raise ValueError("scale must enumerate unique legal integers")
    if any(type(x) is not int or x not in scale for x in a + b):
        raise ValueError("sample contains illegal scale value")
    if not a or not b:
        raise GateFailure("TV requires both distribution universes")
    ca, cb = Counter(a), Counter(b)
    return (
        sum((abs(Fraction(ca[x], len(a)) - Fraction(cb[x], len(b))) for x in scale), Fraction()) / 2
    )


@dataclass(frozen=True, slots=True)
class PairChallenge:
    challenge_id: str
    case_family: str
    scale_id: str
    axis: str
    left: int | str
    right: int | str

    def __post_init__(self):
        _require_id("challenge_id", self.challenge_id)
        _require_id("case_family", self.case_family)
        if self.scale_id not in SCALES or self.axis not in {"variant_index", "field_order_id"}:
            raise ValueError("unsupported challenge scale or axis")
        expected_type = int if self.axis == "variant_index" else str
        if type(self.left) is not expected_type or type(self.right) is not expected_type:
            raise TypeError("challenge levels do not match axis")
        if self.left == self.right:
            raise ValueError("challenge levels must differ")

    def to_payload(self):
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True, slots=True)
class GateAlgorithm:
    algorithm_id: str
    algorithm_version: str
    min_parse: Fraction
    max_refusal: Fraction
    min_main_categories: int
    max_main_endpoint: Fraction
    max_abs_dz: Fraction
    max_contradiction: Fraction
    tv_threshold: Fraction | None
    minimum_distribution_n: int
    classifier_id: str
    classifier_version: str
    classifier_hash: str
    challenges: tuple[PairChallenge, ...]

    def __post_init__(self):
        for name in ("algorithm_id", "algorithm_version", "classifier_id", "classifier_version"):
            _require_id(name, getattr(self, name))
        _require_sha256("classifier_hash", self.classifier_hash)
        for name in (
            "min_parse",
            "max_refusal",
            "max_main_endpoint",
            "max_abs_dz",
            "max_contradiction",
        ):
            value = getattr(self, name)
            if type(value) is not Fraction or not 0 <= value <= 1:
                raise ValueError(f"{name} requires an exact registered fraction in [0,1]")
        if self.tv_threshold is not None and (
            type(self.tv_threshold) is not Fraction or not 0 <= self.tv_threshold <= 1
        ):
            raise ValueError("TV threshold must be an explicit fraction or None")
        for name in ("min_main_categories", "minimum_distribution_n"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.min_main_categories > 7:
            raise ValueError("main categories exceed scale")
        if type(self.challenges) is not tuple or any(
            type(c) is not PairChallenge for c in self.challenges
        ):
            raise TypeError("challenges must be explicit PairChallenge tuples")
        if len({c.challenge_id for c in self.challenges}) != len(self.challenges):
            raise ValueError("duplicate challenge identities")

    def to_payload(self):
        payload = {f.name: getattr(self, f.name) for f in fields(self)}
        for name, value in tuple(payload.items()):
            if isinstance(value, Fraction):
                payload[name] = {"numerator": value.numerator, "denominator": value.denominator}
        payload["challenges"] = [c.to_payload() for c in self.challenges]
        payload["implementation"] = "paper1.calibration.gates.v3"
        payload["inventory_policy"] = "exact-specification-expansion-before-scoring"
        payload["challenge_coverage"] = "all-topic-wording-and-field-order-pairs-on-each-scale"
        payload["aggregation"] = "all-family-and-challenge-hard-gates; incomplete-suppresses-all"
        payload["pair_strata"] = [
            "case_family",
            "scenario_id",
            "scale_id",
            "persona_view_id",
            "replicate_id",
            "requested_seed",
            "nonchallenged-axis",
        ]
        payload["contradiction_labels"] = ["consistent", "contradiction", "indeterminate"]
        return payload

    @property
    def record_hash(self):
        return canonical_payload_hash(self.to_payload())


@dataclass(frozen=True, slots=True)
class SemanticGateEvidence:
    """Explicit synthetic/offline bridge for the independent semantic-review layer."""

    case_id: str
    case_hash: str
    parse_hash: str
    classifier_id: str
    classifier_version: str
    classifier_hash: str
    review_policy_hash: str
    dimension_labels: Mapping[str, str]
    dimension_passes: Mapping[str, bool]
    semantic_passed: bool
    refusal: bool
    contradiction: str
    review_complete: bool
    review_evidence_hash: str

    def __post_init__(self):
        for name in ("case_id", "classifier_id", "classifier_version"):
            _require_id(name, getattr(self, name))
        for name in (
            "case_hash",
            "parse_hash",
            "classifier_hash",
            "review_policy_hash",
            "review_evidence_hash",
        ):
            _require_sha256(name, getattr(self, name))
        if (
            type(self.refusal) is not bool
            or type(self.review_complete) is not bool
            or type(self.semantic_passed) is not bool
        ):
            raise TypeError("review flags must be bool")
        if not isinstance(self.dimension_labels, Mapping) or not isinstance(
            self.dimension_passes, Mapping
        ):
            raise TypeError("semantic dimensions must use exact mappings")
        labels = dict(self.dimension_labels)
        passes = dict(self.dimension_passes)
        if any(type(key) is not str or type(value) is not str for key, value in labels.items()):
            raise TypeError("semantic dimension labels must be strings")
        if any(type(key) is not str or type(value) is not bool for key, value in passes.items()):
            raise TypeError("semantic dimension pass values must be booleans")
        if self.review_complete:
            if not labels or set(labels) != set(passes):
                raise ValueError("complete semantic evidence requires every dimension verdict")
            if self.semantic_passed is not all(passes.values()):
                raise ValueError("semantic aggregate must equal all dimension verdicts")
        elif labels or passes or self.semantic_passed:
            raise ValueError("incomplete semantic evidence cannot contain favorable verdicts")
        if self.contradiction not in {"consistent", "contradiction", "indeterminate"}:
            raise ValueError("invalid direct contradiction code")
        object.__setattr__(self, "dimension_labels", _freeze(dict(sorted(labels.items()))))
        object.__setattr__(self, "dimension_passes", _freeze(dict(sorted(passes.items()))))

    def to_payload(self):
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @property
    def record_hash(self):
        return canonical_payload_hash(self.to_payload())


@dataclass(frozen=True, slots=True)
class FoldedCase:
    case: ProbeCase
    first_parse: ProbeParseEvidence | None
    final_parse: ProbeParseEvidence | None
    attempt_hashes: tuple[str, ...]
    seed_guaranteed: bool


def fold_case_attempts(
    cases: tuple[ProbeCase, ...], projection: ProbeRunProjection
) -> Mapping[str, FoldedCase]:
    if type(cases) is not tuple or not cases or any(type(c) is not ProbeCase for c in cases):
        raise TypeError("cases must be a nonempty tuple of ProbeCase")
    if type(projection) is not ProbeRunProjection:
        raise TypeError("projection must be reviewed ProbeRunProjection")
    # Round-trip validation replays terminal/repair/transport ordering and every nested hash.
    ProbeRunProjection.from_payload(projection.to_payload())
    if len({c.probe_case_id for c in cases}) != len(cases):
        raise ValueError("duplicate case inventory")
    expected = canonical_payload_hash(
        [c.to_payload() for c in sorted(cases, key=lambda c: c.probe_case_id)]
    )
    if expected != projection.case_inventory_hash or set(projection.case_statuses) != {
        c.probe_case_id for c in cases
    }:
        raise ValueError("scheduled case inventory mismatch")
    result = {}
    for case in cases:
        if case.specification_hash != projection.specification_hash:
            raise ValueError("case specification mismatch")
        attempts = tuple(a for a in projection.attempts if a.probe_case_id == case.probe_case_id)
        if any(a.probe_case_hash != case.record_hash for a in attempts):
            raise ValueError("attempt case hash mismatch")
        parses = tuple(a.parse_evidence for a in attempts if a.parse_evidence is not None)
        result[case.probe_case_id] = FoldedCase(
            case,
            parses[0] if parses else None,
            parses[-1] if parses else None,
            tuple(a.record_hash for a in attempts),
            bool(attempts)
            and all(
                a.response.provider_seed_supported and case.requested_seed is not None
                for a in attempts
            ),
        )
    return MappingProxyType(result)


def _rate(n: int, ids: tuple[str, ...], threshold: Fraction | None, *, minimum=False):
    fraction = Fraction(n, len(ids)) if ids else None
    passed = (
        None
        if threshold is None
        else fraction is not None and (fraction >= threshold if minimum else fraction <= threshold)
    )
    return {"numerator": n, "denominator": len(ids), "universe_case_ids": ids, "passed": passed}


def _validate_required_challenges(
    algorithm: GateAlgorithm, authoritative: tuple[ProbeCase, ...]
) -> None:
    """All topic wording and field-order pairs, on each predeclared scale."""
    required = set()
    topic_cases = tuple(c for c in authoritative if c.case_family == "topic_quality")
    for scale in {c.scale_id for c in topic_cases}:
        for axis in ("variant_index", "field_order_id"):
            levels = sorted({getattr(c, axis) for c in topic_cases if c.scale_id == scale})
            for left, right in combinations(levels, 2):
                required.add(("topic_quality", scale, axis, left, right))
    supplied = [(c.case_family, c.scale_id, c.axis, c.left, c.right) for c in algorithm.challenges]
    if len(supplied) != len(required) or set(supplied) != required:
        raise ValueError("gate algorithm must contain the exact required challenge comparisons")


@dataclass(frozen=True, slots=True)
class GateReport:
    candidate_key: str
    candidate_id: str
    status: str
    passed: bool | None
    metrics: tuple[Mapping[str, object], ...]
    challenges: tuple[Mapping[str, object], ...]
    algorithm_id: str
    algorithm_version: str
    algorithm_hash: str
    specification_hash: str
    run_evidence_hash: str
    input_hash: str
    source: tuple

    def __post_init__(self):
        object.__setattr__(self, "metrics", _freeze(self.metrics))
        object.__setattr__(self, "challenges", _freeze(self.challenges))

    def to_payload(self):
        return {
            **{f.name: getattr(self, f.name) for f in fields(self) if f.name != "source"},
            "calibration_only": True,
            "formal_parameter_authority": False,
            "research_parameter_status": "not_frozen",
        }

    @property
    def record_hash(self):
        return canonical_payload_hash(self.to_payload())


def _score_family(group, folded, review_map, projection, algorithm):
    """Count one declared family; public callers must use evaluate_quality_gates."""
    family, scale_id = group[0].case_family, group[0].scale_id
    ids = tuple(sorted(c.probe_case_id for c in group))
    parsed = tuple(
        i for i in ids if folded[i].final_parse is not None and folded[i].final_parse.success
    )
    refused = tuple(
        i
        for i in ids
        if (i in review_map and review_map[i].refusal)
        or (
            folded[i].final_parse is not None
            and not folded[i].final_parse.success
            and folded[i].final_parse.error["code"] == "refusal"
        )
    )
    universe = tuple(i for i in parsed if i not in refused)
    values = tuple(folded[i].final_parse.stance for i in universe)
    counts = Counter(values)
    scale = SCALES[scale_id]
    main = scale_id == "stance-1-7"
    dimension_names = tuple(
        sorted(next(iter(review_map.values())).dimension_passes) if review_map else ()
    )
    semantic_dimensions = tuple(
        {
            "dimension": dimension,
            "reviewed_case_ids": tuple(
                i for i in ids if i in review_map and review_map[i].review_complete
            ),
            "failed_case_ids": tuple(
                i
                for i in ids
                if i in review_map
                and review_map[i].review_complete
                and not review_map[i].dimension_passes[dimension]
            ),
            "passed": all(
                i in review_map
                and review_map[i].review_complete
                and review_map[i].dimension_passes[dimension]
                for i in ids
            ),
        }
        for dimension in dimension_names
    )
    metric = {
        "case_family": family,
        "scale_id": scale_id,
        "scheduled_count": len(ids),
        "parsed_count": len(parsed),
        "refusal_count": len(refused),
        "distribution_count": len(universe),
        "distribution_universe_case_ids": universe,
        "distribution": {str(k): counts[k] for k in scale},
        "categories_used": len(counts),
        "categories_passed": len(counts) >= algorithm.min_main_categories if main else None,
        "minimum_sample_passed": len(universe) >= algorithm.minimum_distribution_n,
        "first_parse": _rate(
            sum(folded[i].first_parse is not None and folded[i].first_parse.success for i in ids),
            ids,
            None,
        ),
        "parse": _rate(len(parsed), ids, algorithm.min_parse, minimum=True),
        "refusal": _rate(len(refused), ids, algorithm.max_refusal),
        "runtime_failure": _rate(
            sum(projection.case_statuses[i] == "runtime_failed" for i in ids), ids, None
        ),
        "lower_endpoint": _rate(
            counts[scale[0]], universe, algorithm.max_main_endpoint if main else None
        ),
        "upper_endpoint": _rate(
            counts[scale[-1]], universe, algorithm.max_main_endpoint if main else None
        ),
        "combined_endpoints": _rate(counts[scale[0]] + counts[scale[-1]], universe, None),
        "contradiction": _rate(
            sum(
                i in review_map and review_map[i].contradiction == "contradiction" for i in universe
            ),
            universe,
            algorithm.max_contradiction,
        ),
        "semantic_dimensions": semantic_dimensions,
    }
    return metric


def evaluate_quality_gates(
    specification: ArtifactEnvelope,
    cases: tuple[ProbeCase, ...],
    projection: ProbeRunProjection,
    algorithm: GateAlgorithm,
    reviews: tuple[SemanticGateEvidence, ...],
    *,
    candidate_key: str,
) -> GateReport:
    if type(specification) is not ArtifactEnvelope or type(algorithm) is not GateAlgorithm:
        raise TypeError("validated specification and explicit GateAlgorithm required")
    from .specification import expand_probe_cases, load_probe_specification

    # JSON transport restores frozen mappings while the loader validates the complete spec.
    import json

    rebuilt = load_probe_specification(
        json.loads(json.dumps(specification.to_payload()["payload"]))
    )
    if (
        rebuilt.output_hash != specification.output_hash
        or projection.specification_hash != specification.output_hash
    ):
        raise ValueError("specification hash mismatch")
    if specification.payload["policy_hashes"]["gate_algorithm"] != algorithm.record_hash:
        raise ValueError("gate algorithm was not bound before execution")
    authoritative = expand_probe_cases(rebuilt)
    if type(cases) is not tuple or any(type(c) is not ProbeCase for c in cases):
        raise ValueError("supplied cases do not match authoritative inventory")
    expected_inventory = {c.probe_case_id: c.record_hash for c in authoritative}
    supplied_inventory = {c.probe_case_id: c.record_hash for c in cases}
    if (
        len(cases) != len(authoritative)
        or supplied_inventory != expected_inventory
        or any(
            c.specification_hash != rebuilt.output_hash
            or canonical_payload_hash(c.content_payload()) != c.record_hash
            for c in cases
        )
    ):
        raise ValueError("supplied cases do not match authoritative inventory")
    _validate_required_challenges(algorithm, authoritative)
    if candidate_key not in TOPIC_ORDER:
        raise ValueError("unknown candidate")
    raw = next(
        t for t in specification.payload["topic_candidates"] if t["candidate_key"] == candidate_key
    )
    topic = ProbeTopicCandidate.create(
        construct=raw["construct"],
        fact_card=raw["fact_card"],
        statements=tuple(raw["statements"]),
        stance_labels_1_7=tuple(raw["stance_labels_1_7"]),
    )
    # Folding also validates the projection inventory/hash and every attempt binding.
    folded = fold_case_attempts(authoritative, projection)
    selected = tuple(c for c in authoritative if c.candidate_id == topic.candidate_id)
    if not selected:
        raise ValueError("missing candidate cases")
    if type(reviews) is not tuple or any(type(r) is not SemanticGateEvidence for r in reviews):
        raise TypeError("reviews require strict SemanticGateEvidence tuples")
    if len({r.case_id for r in reviews}) != len(reviews) or any(
        r.case_id not in folded for r in reviews
    ):
        raise ValueError("duplicate or unknown review case")
    review_map = {r.case_id: r for r in reviews}
    expected_policy_hash = specification.payload["policy_hashes"]["semantic_review_policy"]
    complete_dimension_sets = {tuple(r.dimension_labels) for r in reviews if r.review_complete}
    incomplete = False
    if len(complete_dimension_sets) > 1:
        incomplete = True
    for case in cases:
        final = folded[case.probe_case_id].final_parse
        r = review_map.get(case.probe_case_id)
        if final is not None and (
            r is None
            or r.case_hash != case.record_hash
            or r.parse_hash != final.record_hash
            or r.classifier_id != algorithm.classifier_id
            or r.classifier_version != algorithm.classifier_version
            or r.classifier_hash != algorithm.classifier_hash
            or r.review_policy_hash != expected_policy_hash
            or not r.review_complete
            or not r.dimension_labels
            or set(r.dimension_labels) != set(r.dimension_passes)
            or (final.success and not r.refusal and r.contradiction == "indeterminate")
        ):
            incomplete = True
    metrics = []
    all_passed = True
    for family, scale_id in sorted({(c.case_family, c.scale_id) for c in selected}):
        group = tuple(c for c in selected if (c.case_family, c.scale_id) == (family, scale_id))
        metric = _score_family(group, folded, review_map, projection, algorithm)
        checks = [metric["minimum_sample_passed"], metric["categories_passed"]]
        checks += [v["passed"] for v in metric.values() if isinstance(v, dict) and "passed" in v]
        checks += [v["passed"] for v in metric["semantic_dimensions"]]
        all_passed = all_passed and all(x is not False for x in checks)
        metrics.append(metric)
    challenge_reports = []
    for challenge in algorithm.challenges:
        group = tuple(
            c
            for c in selected
            if c.case_family == challenge.case_family and c.scale_id == challenge.scale_id
        )
        other = "field_order_id" if challenge.axis == "variant_index" else "variant_index"

        def key(c):
            return (
                c.scenario_id,
                c.persona_view_id,
                c.replicate_id,
                c.requested_seed,
                getattr(c, other),
            )

        left = {key(c): c for c in group if getattr(c, challenge.axis) == challenge.left}
        right = {key(c): c for c in group if getattr(c, challenge.axis) == challenge.right}
        registered_scope = {
            (r["replicate_id"], r["requested_seed"]) for r in specification.payload["replicates"]
        }
        strata = {(c.scenario_id, c.persona_view_id, getattr(c, other)) for c in group}
        expected_keys = {
            (scenario, persona, replicate, seed, other_level)
            for scenario, persona, other_level in strata
            for replicate, seed in registered_scope
        }
        matching = (
            bool(left)
            and left.keys() == right.keys()
            and left.keys() == expected_keys
            and len(left) == sum(getattr(c, challenge.axis) == challenge.left for c in group)
            and len(right) == sum(getattr(c, challenge.axis) == challenge.right for c in group)
        )
        pairs = []
        for k in sorted(left, key=repr):
            if k in right:
                a, b = left[k].probe_case_id, right[k].probe_case_id
                if all(
                    folded[i].final_parse is not None
                    and folded[i].final_parse.success
                    and i in review_map
                    and not review_map[i].refusal
                    for i in (a, b)
                ):
                    pairs.append((a, b))
        complete_pairs = matching and len(pairs) == len(left)
        deltas = tuple(
            folded[a].final_parse.stance - folded[b].final_parse.stance for a, b in pairs
        )
        left_values = tuple(folded[a].final_parse.stance for a, b in pairs)
        right_values = tuple(folded[b].final_parse.stance for a, b in pairs)
        dz, tv, passed, reason = None, None, False, None
        if pairs:
            tv = total_variation(left_values, right_values, SCALES[challenge.scale_id])
        try:
            if not complete_pairs:
                raise GateFailure("predeclared pairing incomplete")
            dz = paired_dz(deltas)
            passed = _dz_passes(deltas, algorithm.max_abs_dz) and (
                algorithm.tv_threshold is None or tv <= algorithm.tv_threshold
            )
        except GateFailure as exc:
            reason = str(exc)
        challenge_reports.append(
            {
                "challenge_id": challenge.challenge_id,
                "pairs": tuple(pairs),
                "expected_pairs": len(expected_keys),
                "valid_pairs": len(pairs),
                "left_distribution": {
                    str(k): left_values.count(k) for k in SCALES[challenge.scale_id]
                },
                "right_distribution": {
                    str(k): right_values.count(k) for k in SCALES[challenge.scale_id]
                },
                "left_universe_case_ids": tuple(a for a, b in pairs),
                "right_universe_case_ids": tuple(b for a, b in pairs),
                "mean_delta": None
                if not deltas
                else {"numerator": sum(deltas), "denominator": len(deltas)},
                "sample_standard_deviation": stdev(deltas) if len(deltas) >= 2 else None,
                "deltas": deltas,
                "dz": dz,
                "tv": None
                if tv is None
                else {"numerator": tv.numerator, "denominator": tv.denominator},
                "passed": passed,
                "failure_reason": reason,
                "provider_seed_guaranteed": bool(pairs)
                and all(folded[i].seed_guaranteed for p in pairs for i in p),
            }
        )
        all_passed = all_passed and passed
    status = (
        "runtime_incomplete"
        if projection.status != "complete"
        else "review_incomplete"
        if incomplete
        else "complete"
    )
    if status != "complete":

        def suppress_passes(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "passed":
                        value[key] = None
                    else:
                        suppress_passes(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    suppress_passes(child)

        for metric in metrics:
            suppress_passes(metric)
            for name in tuple(metric):
                if name.endswith("_passed"):
                    metric[name] = None
        for challenge in challenge_reports:
            challenge["passed"] = None
    input_hash = canonical_payload_hash(
        {
            "specification": specification.output_hash,
            "inventory": projection.case_inventory_hash,
            "run": projection.run_evidence_hash,
            "algorithm": algorithm.record_hash,
            "reviews": sorted(r.record_hash for r in reviews),
        }
    )
    for metric in metrics + challenge_reports:
        metric.update(
            algorithm_id=algorithm.algorithm_id,
            algorithm_version=algorithm.algorithm_version,
            input_hash=input_hash,
        )
    return GateReport(
        candidate_key,
        topic.candidate_id,
        status,
        all_passed if status == "complete" else None,
        tuple(metrics),
        tuple(challenge_reports),
        algorithm.algorithm_id,
        algorithm.algorithm_version,
        algorithm.record_hash,
        specification.output_hash,
        projection.run_evidence_hash,
        input_hash,
        (specification, cases, projection, algorithm, reviews),
    )


@dataclass(frozen=True, slots=True)
class TopicSelection:
    status: str
    primary: str | None
    robustness: str | None
    report_hashes: tuple[str, ...]

    def to_payload(self):
        return {
            "status": self.status,
            "primary": self.primary,
            "robustness": self.robustness,
            "report_hashes": self.report_hashes,
            "formal_parameter_authority": False,
            "calibration_only": True,
            "research_parameter_status": "not_frozen",
        }


def select_topic(reports: tuple[GateReport, ...]) -> TopicSelection:
    """Recompute evidence, then apply only the precommitted candidate priority."""
    if type(reports) is not tuple or any(type(r) is not GateReport for r in reports):
        raise TypeError("selection accepts evidence-bound GateReport records only")
    if len(reports) != 3 or {r.candidate_key for r in reports} != set(TOPIC_ORDER):
        raise ValueError("missing, duplicate, or unknown candidate reports")
    for report in reports:
        expected = evaluate_quality_gates(*report.source, candidate_key=report.candidate_key)
        if report.to_payload() != expected.to_payload():
            raise ValueError(
                "report differs from bound evidence; forbidden derived fields rejected"
            )
    if (
        len(
            {
                (r.algorithm_hash, r.specification_hash, r.run_evidence_hash, r.input_hash)
                for r in reports
            }
        )
        != 1
    ):
        raise ValueError("candidate reports require coherent shared algorithm and provenance")
    if any(r.status != "complete" or r.passed is None for r in reports):
        raise ValueError("incomplete runtime/review suppresses all candidate selection")
    ordered = tuple(next(r for r in reports if r.candidate_key == key) for key in TOPIC_ORDER)
    eligible = tuple(r.candidate_key for r in ordered if r.passed)
    return TopicSelection(
        "proposal_only" if eligible else "no_candidate",
        eligible[0] if eligible else None,
        eligible[1] if len(eligible) > 1 else None,
        tuple(r.record_hash for r in ordered),
    )
