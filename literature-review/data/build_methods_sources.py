"""Derive current included journal sources; preserve the frozen round-one source table."""
import pathlib,csv,collections,json
R=pathlib.Path(__file__).resolve().parents[1]
def read(p):return list(csv.DictReader(p.open(encoding="utf-8-sig",newline="")))
records=read(R/"data/literature_master.csv");venues=read(R/"data/method_venue_map.csv")
alias={v:x for x in venues for v in x.get("master_venue_ids","").split(";") if v}
included=[x for x in records if x["screening_status"]=="included"]
journals=[x for x in included if x["document_type"] in ["journal_article","review"]]
groups=collections.defaultdict(list)
for x in journals:groups[x["venue_id"]].append(x)
fields=["source_venue_id","map_venue_id","venue","included_count","method_core_count","method_validation_count","direct_comparator_count","application_count","record_ids","work_id_groups","publication_years","method_types","contribution_types","value_to_agent_ex","coverage_limit","checked_date"]
rows=[]
for vid,g in sorted(groups.items()):
 v=alias.get(vid);ids=[x["record_id"] for x in g]
 years=sorted({x["online_first_date"][:4] or x["volume_year"] for x in g})
 row=dict(source_venue_id=vid,map_venue_id=v["venue_id"] if v else "",venue=v["venue"] if v else g[0]["venue"],included_count=len(g),method_core_count=sum(x["method_relevance_tier"]=="core_method" for x in g),method_validation_count=sum(x["method_relevance_tier"]=="method_validation" for x in g),direct_comparator_count=sum(x["method_relevance_tier"]=="direct_comparator" for x in g),application_count=sum(x["method_relevance_tier"]=="application" for x in g),record_ids=";".join(ids),work_id_groups=len({x["work_id"] for x in g}),publication_years=";".join(years),method_types=";".join(sorted({x["method_type"] for x in g if x["method_type"]})),contribution_types=";".join(sorted({t for x in g for t in x["method_contribution_type"].split(";") if t})),value_to_agent_ex=" | ".join(x["record_id"]+":"+x["reason"] for x in g),coverage_limit="Included formal journal articles/reviews only;excludes candidate/frontier/conference;source distribution not whole-journal coverage or recommendation;reading/version limits remain in cards/master",checked_date="2026-11-28")
 rows.append(row)
with (R/"data/core_source_journals_methods.csv").open("w",encoding="utf8",newline="") as f:
 w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
assert sum(x["included_count"] for x in rows)==len(journals)
assert {i for x in rows for i in x["record_ids"].split(";")}=={x["record_id"] for x in journals}
identity=dict(records=len(records),coded_work_id_groups=len({x["work_id"] for x in records}),included_records=len(included),included_work_id_groups=len({x["work_id"] for x in included}),included_journal_records=len(journals),included_conference_records=sum(x["document_type"]=="conference_paper" for x in included),journal_sources=len(rows),duplicate_dois=[d for d,n in collections.Counter(x["doi"].lower() for x in records if x["doi"]).items() if n>1],blank_work_ids=sum(not x["work_id"] for x in records),interpretation="work_id groups are coded bibliographic units,not proof of statistical or substantive independence;known related versions retained within records")
(R/"data/work_identity_current.json").write_text(json.dumps(identity,ensure_ascii=False,indent=2),encoding="utf8")
print(json.dumps(identity,ensure_ascii=False))
