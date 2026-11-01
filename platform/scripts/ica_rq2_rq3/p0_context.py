"""Numerical context from original completed P0-B (not P0c) one-step cases.

No transport/runtime imports. The immutable ledger and frozen inputs are read
directly; no old CSV/report is treated as evidence. All 1512 research cases,
including 84 embedded pilot cases, enter descriptive cells; 14 technical cases
are integrity-checked but excluded. Cases/draws are NOT network replications.
No p-values, confidence intervals or new manipulation verdicts are generated.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sqlite3


SOURCE_ROOT = Path("V:/Agent EX/Agent-EX-evidence/2026-10-29/p0b-controlled-v1/private-evidence/restore-v1")
OUTPUT_ROOT = Path("V:/Agent EX/Agent-EX-evidence/2026-11-01/ica-rq2-rq3-v1/p0-context")
ARCHIVE_SHA256 = "5e2b9ba7c114f2203802542f0bbce3973bd1377174aa027d7305f54c30851517"


def encoded(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def _rate(a, b):
    return a/b if b else None


def numeric_usage(raw):
    """Original persisted parser retained these three token accounting fields."""
    out = {k:raw[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    if (any(type(v) is not int or v < 0 for v in out.values())
            or out["prompt_tokens"]+out["completion_tokens"] != out["total_tokens"]):
        raise ValueError("Invalid observed token accounting")
    return out


def summarize_numeric(rows):
    """Observed numerator/denominator cells by topic/start/feed/visibility.

    Original semantic coordinate only. Surface proposition/mapping factors,
    reason variants and nested draws are pooled within these context cells;
    their observed coverage is recorded, not interpreted as new replications.
    """
    required = ("topic_key", "initial_stance", "feed_condition", "source_labels_visible",
                "output_stance", "pilot", "reverse_proposition", "reverse_mapping",
                "reason_index", "draw_seed")
    grouped = defaultdict(list)
    for r in rows:
        if any(k not in r for k in required):
            raise ValueError("Missing numeric context field; no inferred replacements")
        if (type(r["initial_stance"]) is not int or type(r["output_stance"]) is not int
                or not 1 <= r["initial_stance"] <= 7 or not 1 <= r["output_stance"] <= 7
                or type(r["source_labels_visible"]) is not bool
                or r["feed_condition"] not in {"none", "low", "high"}):
            raise ValueError("Invalid observed numeric factor")
        grouped[tuple(r[k] for k in required[:4])].append(r)
    out = []
    for (topic, start, feed, visible), group in sorted(grouped.items()):
        ys = [r["output_stance"] for r in group]
        n = len(ys)
        counts = Counter(ys)
        row = dict(topic_key=topic, initial_stance=start, feed_condition=feed,
                   source_labels_visible=visible, n_cases=n,
                   n_held=sum(y == start for y in ys), n_changed=sum(y != start for y in ys),
                   n_upward=sum(y > start for y in ys), n_downward=sum(y < start for y in ys),
                   n_pilot_embedded=sum(bool(r["pilot"]) for r in group),
                   n_distinct_draw_seeds=len({r["draw_seed"] for r in group}),
                   n_reason_variants=len({r["reason_index"] for r in group}),
                   n_surface_factor_combinations=len({(r["reverse_proposition"], r["reverse_mapping"]) for r in group}),
                   output_sum=sum(ys), output_mean=sum(ys)/n,
                   signed_change_sum=sum(y-start for y in ys),
                   signed_change_mean=sum(y-start for y in ys)/n,
                   abs_change_sum=sum(abs(y-start) for y in ys),
                   abs_change_mean=sum(abs(y-start) for y in ys)/n,
                   aggregation="pooled_proposition_mapping_reason_nested_draws",
                   unit="fixed_one_step_case_not_network_replicate")
        for name in ("held", "changed", "upward", "downward"):
            row[name+"_rate"] = row["n_"+name]/n
        for k in range(1,8):
            row[f"output_count_{k}"] = counts[k]
            row[f"output_share_{k}"] = counts[k]/n
        for before, after in ((5,3),(3,5)):
            key = f"{before}_to_{after}"
            den = n if start == before else 0
            num = counts[after] if start == before else 0
            row["n_"+key], row["denominator_"+key] = num, den
            row["rate_"+key] = _rate(num,den)
        out.append(row)
    return out


def read_completed(source_root=SOURCE_ROOT):
    """Read immutable original ledger, independently check saved-response parse.

    Explicit close in finally; before/after hashes cover DB and all three inputs.
    Original archive hash is a supplied locator, not falsely claimed reverified.
    """
    base = Path(source_root).resolve()
    paths = {"ledger": base/"run/ledger/ledger.sqlite3",
             **{name: base/"inputs"/(name+".json") for name in ("cases", "contract", "admission")}}
    ledger = paths["ledger"]
    if any(Path(str(ledger)+s).exists() for s in ("-wal", "-shm", "-journal")):
        raise ValueError("Closed restored ledger required; sidecar present")
    before = {k: sha256(p) for k,p in paths.items()}
    cases, contract, admission = [json.loads(paths[k].read_bytes()) for k in ("cases", "contract", "admission")]
    if (contract.get("mode") != "accepted-production" or contract.get("schema") != "p0b.runtime.v1"
            or contract.get("research_limit") != 1512 or contract.get("technical_limit") != 14
            or admission.get("schema") != "p0b.admission.v1"):
        raise ValueError("Original P0-B contract required, not another diagnostic")
    if contract["acceptance_sha256"] != before["admission"]:
        raise ValueError("Admission input hash differs from frozen contract")
    by_id = {c["case_id"]: c for c in cases}
    if len(by_id) != len(cases) or Counter(c["kind"] for c in cases) != {"research":1512, "technical":14}:
        raise ValueError("Exact original research/technical case coverage required")
    db = sqlite3.connect(ledger.as_uri()+"?mode=ro&immutable=1", uri=True)
    db.row_factory = sqlite3.Row
    numeric, observed_counts = [], Counter()
    seen = set()
    try:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("SQLite quick_check failed")
        frozen = db.execute("SELECT payload,hash FROM frozen WHERE singleton=1").fetchone()
        if not frozen or hashlib.sha256(frozen["payload"]).hexdigest() != frozen["hash"]:
            raise ValueError("Frozen binding checksum mismatch")
        binding = json.loads(frozen["payload"])
        if binding != dict(cases=cases, contract=contract, version="p0b.runtime.v1"):
            raise ValueError("Inputs differ from ledger frozen binding")
        if db.execute("SELECT COUNT(*) FROM global_halt").fetchone()[0] != 0:
            raise ValueError("Historical ledger has global halt")
        for a in db.execute("SELECT * FROM attempts ORDER BY case_id"):
            cid = a["case_id"]
            if cid in seen or cid not in by_id or a["state"] != "committed" or a["error"] is not None:
                raise ValueError("Incomplete or duplicate original successful coverage")
            seen.add(cid)
            case = by_id[cid]
            if a["kind"] != case["kind"]:
                raise ValueError("Case kind mismatch")
            observed_counts[a["kind"]] += 1
            if a["wire"] != encoded(case["request"]) or hashlib.sha256(a["wire"]).hexdigest() != a["wire_sha256"]:
                raise ValueError("Frozen wire mismatch")
            expected_request = "p0b-"+hashlib.sha256(frozen["hash"].encode()+b"\0"+cid.encode()).hexdigest()
            if a["request_id"] != expected_request:
                raise ValueError("Request binding identity mismatch")
            headers, envelope = json.loads(a["response_headers"]), json.loads(a["response_body"])
            saved = dict(status=a["response_status"], headers=headers,
                         body_sha256=hashlib.sha256(a["response_body"]).hexdigest())
            if hashlib.sha256(encoded(saved)).hexdigest() != a["response_sha256"]:
                raise ValueError("Saved raw response checksum mismatch")
            content = json.loads(envelope["choices"][0]["message"]["content"])
            label = content["stance"]
            if label not in case["original_semantic_by_label"]:
                raise ValueError("Response selected an unfrozen label")
            output = case["original_semantic_by_label"][label]
            result = json.loads(a["result"])
            expected_result = dict(case_id=cid, confidence=content["confidence"],
                                   original_semantic_score=output, request_id=expected_request,
                                   response_sha256=a["response_sha256"], selected_label=label,
                                   usage=numeric_usage(envelope["usage"]))
            if result != expected_result:
                raise ValueError("Persisted result differs from independent raw-response parse")
            if a["kind"] == "research":
                numeric.append(dict(topic_key=case["topic"], initial_stance=case["original_semantic_score"],
                    feed_condition=case["feed"], source_labels_visible=case["source_labels_visible"],
                    output_stance=output, pilot=case["pilot"], reverse_proposition=case["reverse_proposition"],
                    reverse_mapping=case["reverse_mapping"], reason_index=case["reason_index"], draw_seed=case["draw_seed"]))
        if seen != set(by_id) or observed_counts != {"research":1512, "technical":14}:
            raise ValueError("Original completed coverage mismatch")
    finally:
        db.close()
    after = {k: sha256(p) for k,p in paths.items()}
    if before != after:
        raise ValueError("Original evidence changed during read-only analysis")
    sidecars_absent = not any(Path(str(ledger)+s).exists() for s in ("-wal", "-shm", "-journal"))
    if not sidecars_absent:
        raise ValueError("Unexpected SQLite sidecar appeared")
    verification = dict(schema="ica2027.p0-original-context.v1", source_paths={k:str(p) for k,p in paths.items()},
        source_sha256_before=before, source_sha256_after=after, source_hashes_unchanged=True,
        sqlite_uri_mode="ro&immutable=1", query_only=True, connection_explicitly_closed=True,
        quick_check="ok", sidecars_absent=sidecars_absent, frozen_inputs_match_ledger=True,
        independent_saved_response_parse_verified=True, research_cases=1512, technical_cases_excluded=14,
        embedded_pilot_cases=sum(r["pilot"] for r in numeric), model=contract["model"],
        original_archive_sha256_supplied=ARCHIVE_SHA256, archive_bytes_reverified_here=False,
        source_labels_visible_observed=sorted({r["source_labels_visible"] for r in numeric}),
        missing_comparisons=["source-label visibility contrast: all original cases have labels hidden"],
        unavailable_fields_not_inferred=["realized network exposure history", "network matched seed", "source group identity"],
        historical_joint_stage_a_b_admission="NOT PASSED; historical status retained, not recomputed or revised",
        inference_scope="descriptive fixed one-step cases; no network replication, P0c, p-values, CI or new manipulation verdict",
        pooling="proposition reversal, response mapping reversal, fixed reason variant, nested draw seed",
        semantic_axis="original proposition semantic score, not display code or reversed proposition agreement")
    return numeric, verification


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    allowed = OUTPUT_ROOT.resolve()
    if output != allowed and allowed not in output.parents:
        raise ValueError("Output must remain within approved p0-context directory")
    numeric, verification = read_completed(args.source_root)
    rows = summarize_numeric(numeric)
    if not rows or sum(r["n_cases"] for r in rows) != 1512:
        raise ValueError("Context cells do not conserve research cases")
    output.mkdir(parents=True, exist_ok=True)
    csvpath, jsonpath = output/"p0_context.csv", output/"verification.json"
    if csvpath.exists() or jsonpath.exists():
        raise FileExistsError("Refusing to overwrite an existing context delivery")
    with csvpath.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    verification.update(output_rows=len(rows), output_columns=list(rows[0]),
                        p0_context_sha256=sha256(csvpath))
    jsonpath.write_text(json.dumps(verification, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(dict(output_rows=len(rows), research_cases=1512, unchanged_source_hashes=True,
                          output=str(output), csv_sha256=verification["p0_context_sha256"])))


if __name__ == "__main__":
    main()
