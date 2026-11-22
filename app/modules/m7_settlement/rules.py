import hashlib,json
from decimal import Decimal
from app.errors import DomainError
from app.reasons import sources,UNPROVEN_CODES
from app.values import number,money
def _card_days(rows):
    "每张卡每个业务日唯一一条应收；分组即唯一，跨编码来源行并入同一卡日"
    groups={}
    for row in rows:
        card,day=row.get("card"),row.get("business_day")
        if not card or not day: continue
        key=(card,day)
        group=groups.setdefault(key,{"receivable":Decimal(0),"events":0,"source_lines":set()})
        group["receivable"]+=number(row.get("expected","0"));group["events"]+=1
        group["source_lines"].update(sources(row))
    return [{"card":card,"business_day":day,"receivable":money(g["receivable"]),"events":g["events"],"source_lines":sorted(g["source_lines"])} for (card,day),g in sorted(groups.items())]
def evaluate(rows,context):
    stages=[v for v in context.values() if isinstance(v,dict) and "metrics" in v]
    balances=[s["metrics"]["balanced"] for s in stages if "balanced" in s["metrics"]]
    if balances and not all(balances): raise DomainError("UNBALANCED","来源行未对平，不能归档")
    ids=[str(r.get("event_id",r.get("_line",""))) for r in rows]
    if len(ids)!=len(set(ids)): raise DomainError("ARCHIVE_DUPLICATE","归档业务键重复")
    unproven=sum(1 for r in context.get("quarantine",[]) if r.get("reason") in UNPROVEN_CODES)
    card_days=_card_days(rows)
    encoded=json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode()
    return {"rows":rows,"quarantine":[],"card_days":card_days,"metrics":{"records":len(rows),"source_lines":len(set(x for row in rows for x in sources(row))),"sha256":hashlib.sha256(encoded).hexdigest(),"ready":unproven==0,"unproven":unproven,"card_days":len(card_days),"differences":sum(r.get("status")=="差异" for r in rows)}}
