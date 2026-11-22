import sqlite3,json,hashlib
from pathlib import Path
from app.config import DATA_DIR
from app.errors import DomainError
def connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA_DIR/"records.db",timeout=20)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,decision TEXT NOT NULL DEFAULT '待复核')")
    db.execute("CREATE TABLE IF NOT EXISTS blobs (sha256 TEXT PRIMARY KEY,data BLOB NOT NULL)")
    return db
def save(run_id,payload,raw=None):
    "同包重试不新增采信记录：批次与原始字节均按摘要幂等写入，同事务提交"
    with connect() as db:
        if raw is not None:
            db.execute("INSERT OR IGNORE INTO blobs(sha256,data) VALUES (?,?)",(hashlib.sha256(raw).hexdigest(),raw))
        created=db.execute("INSERT OR IGNORE INTO runs(id,payload) VALUES (?,?)",(run_id,json.dumps(payload,ensure_ascii=False))).rowcount==1
    return {**get(run_id),"reused":not created}
def get(run_id):
    with connect() as db: row=db.execute("SELECT payload,version,decision FROM runs WHERE id=?",(run_id,)).fetchone()
    if not row: raise DomainError("NOT_FOUND","批次不存在",404)
    return {**json.loads(row[0]),"version":row[1],"decision":row[2]}
def latest():
    with connect() as db: row=db.execute("SELECT id FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
    return get(row[0]) if row else None
def history():
    with connect() as db: return [{"run_id":i,"version":v,"decision":d} for i,v,d in db.execute("SELECT id,version,decision FROM runs ORDER BY rowid DESC")]
def source_slice(run_id,start,end,limit=8192):
    "按字节区间回读原始包，给出hex与两种候选解码，供复核页沿区间查看"
    run=get(run_id)
    with connect() as db: row=db.execute("SELECT data FROM blobs WHERE sha256=?",(run["manifest"]["input_sha256"],)).fetchone()
    if not row: raise DomainError("SOURCE_MISSING","原始字节不存在",404)
    data=bytes(row[0])
    if not (0<=start<end<=len(data)) or end-start>limit: raise DomainError("BAD_RANGE","字节区间无效")
    blob=data[start:end]
    result={"start":start,"end":end,"hex":blob.hex()}
    for encoding in ("utf-8","gb18030"):
        try: result[encoding]=blob.decode(encoding)
        except UnicodeDecodeError: result[encoding]=None
    return result
def review(run_id,version,decision):
    if decision not in {"已复核","退回复核"}: raise DomainError("BAD_DECISION","复核状态无效")
    run=get(run_id)
    if decision=="已复核":
        metrics=run["stages"][-1]["metrics"]
        if metrics.get("unproven"): raise DomainError("UNPROVEN_INTERPRETATION",f"存在{metrics['unproven']}行无法证明解释，不得封存",409)
    with connect() as db:
        cursor=db.execute("UPDATE runs SET version=version+1,decision=? WHERE id=? AND version=?",(decision,run_id,version))
        if cursor.rowcount!=1:
            if not db.execute("SELECT 1 FROM runs WHERE id=?",(run_id,)).fetchone(): raise DomainError("NOT_FOUND","批次不存在",404)
            raise DomainError("STALE_VERSION","版本已更新，请刷新",409)
    return get(run_id)
