from decimal import Decimal
from app.reasons import sources
from app.errors import DomainError
def _byte_coverage(rows,bad,excluded,total):
    "校验采纳行、隔离行与排除项的字节区间恰好铺满[0,total)，不重叠不留洞"
    spans=[]
    for row in list(rows)+list(bad):
        span=row.get("_bytes")
        if not span: return None
        spans.append(tuple(span))
    spans+=[tuple(x["_bytes"]) for x in excluded]
    spans.sort();cursor=0
    for start,end in spans:
        if start!=cursor: return False
        cursor=end
    return cursor==total
def evaluate(rows,context):
    intake=context.get("intake")
    bad=context.get("quarantine",[])
    accepted=set(x for row in rows for x in sources(row))
    rejected=set(x for row in bad for x in sources(row))
    if accepted & rejected: raise DomainError("LINEAGE_OVERLAP","同一来源行被重复裁决")
    m={"accepted_inputs":len(accepted),"quarantine_inputs":len(rejected),"output_records":len(rows)}
    if intake:
        excluded=intake["duplicate"]+intake["blank"]+intake["repeated_headers"]
        m.update(input=intake["input"],excluded=excluded,balanced=intake["input"]==len(accepted)+len(rejected)+excluded)
        if "bytes" in intake:
            coverage=_byte_coverage(rows,bad,context.get("intake_excluded",[]),intake["bytes"])
            if coverage is not None:
                m["bytes"]=intake["bytes"];m["byte_balanced"]=coverage
                m["balanced"]=m["balanced"] and coverage
    else:m.update(input=len(accepted)+len(rejected),excluded=0,balanced=True)
    output=[]
    for row in rows:
        expected=Decimal(str(row.get("expected","0")));reported=Decimal(str(row.get("reported","0")))
        output.append({**row,"difference":str(expected-reported),"status":"通过" if expected==reported else "差异"})
    m.update(expected_total=str(sum((Decimal(str(r.get("expected","0"))) for r in rows),Decimal(0))),reported_total=str(sum((Decimal(str(r.get("reported","0"))) for r in rows),Decimal(0))),differences=sum(r["status"]=="差异" for r in output))
    return {"rows":output,"quarantine":[],"metrics":m}
