"""Independent descriptive audit of selected public anonymous Study2 data; does not run author R."""
import csv,datetime,hashlib,json,pathlib,statistics,sys
p=pathlib.Path(sys.argv[1])
assert hashlib.sha256(p.read_bytes()).hexdigest()=="2c38c6f995c96b904c7c3106021f911f244871a74a387a92a221b37249481070"
rows=list(csv.DictReader(p.open(encoding="utf-8-sig")))
def valid(x):return x not in ["","NA"]
def date(x):return datetime.datetime.strptime(x,"%d/%m/%Y").date()
r=[x for x in rows if valid(x["date_completed"])]
assert len(rows)==51 and len(r)==49 and len({x["id_anonym"] for x in rows})==51
for x in r:
 x["days_taken"]=str((date(x["date_completed"])-date(x["date_initiated"])).days)
 x["issues_flagged"]=str(float(x["issues_flagged_text"])+float(x["issues_flagged_repo"]))
 x["qhours_reviewed"]=str(float(x["hours_reviewed"])*4)
result={"total":len(rows),"retained":len(r),"outcomes":{}}
for k in ["hours_reviewed","qhours_reviewed","emails_exchanged","days_taken","issues_flagged_text","issues_flagged_repo","issues_flagged"]:
 vals=[float(x[k]) for x in r if valid(x[k])]
 result["outcomes"][k]={"n":len(vals),"mean":statistics.mean(vals),"sd_sample":statistics.stdev(vals),"median":statistics.median(vals),"max":max(vals),"sum":sum(vals)}
result["both_issue_counts_zero"]=sum(float(x["issues_flagged"])==0 for x in r)
result["email10min_total_hours_assumption"]=result["outcomes"]["hours_reviewed"]["mean"]+result["outcomes"]["emails_exchanged"]["mean"]/6
assert result["both_issue_counts_zero"]==3
print(json.dumps(result,ensure_ascii=False,indent=2))
