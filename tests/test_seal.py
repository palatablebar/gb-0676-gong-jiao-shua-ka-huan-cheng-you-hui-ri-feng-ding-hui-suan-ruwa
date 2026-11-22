import json
from app.pipeline import execute,load_sample
from app import store
HEADER=b"event_id,card,route,event_time,result,reported,note"
GOOD=HEADER+b"\n9001,0009,01,2026-11-16T08:00:00+08:00,success,2.50,"+"常规".encode()+b"\n"
BROKEN=HEADER+b"\n9002,0009,01,2026-11-16T09:00:00+08:00,success,2.50,\xff\xfe\n"
def test_retry_same_package_adds_no_records(client):
    "同包重试不新增采信记录"
    a=client.post("/api/runs",json={"sample":"mixed.csv"}).get_json()
    b=client.post("/api/runs",json={"sample":"mixed.csv"}).get_json()
    assert a["run_id"]==b["run_id"] and b["reused"] is True
    assert len(client.get("/api/runs").get_json()["runs"])==1
def test_unproven_blocks_seal_and_archive(client):
    "任一行无法证明解释前不得封存"
    import io
    up=client.post("/api/upload",data={"file":(io.BytesIO(GOOD+BROKEN),"broken.csv")},content_type="multipart/form-data")
    assert up.status_code==200
    run=up.get_json()
    assert run["stages"][6]["metrics"]["unproven"]>0 and run["stages"][6]["metrics"]["ready"] is False
    url="/api/runs/"+run["run_id"]
    r=client.post(url+"/review",json={"version":1,"decision":"已复核"})
    assert r.status_code==409 and r.get_json()["code"]=="UNPROVEN_INTERPRETATION"
    assert client.get(url+"/archive").status_code==409
    assert client.post(url+"/review",json={"version":1,"decision":"退回复核"}).status_code==200
def test_stale_version_switch_keeps_old_intact(client):
    "版本切换失败仍保留完整旧版"
    p=client.post("/api/runs",json={"sample":"mixed.csv"}).get_json();url="/api/runs/"+p["run_id"]
    assert client.post(url+"/review",json={"version":1,"decision":"已复核"}).status_code==200
    assert client.post(url+"/review",json={"version":1,"decision":"退回复核"}).status_code==409
    run=client.get(url).get_json()
    assert run["version"]==2 and run["decision"]=="已复核" and len(run["stages"])==7
def test_original_bytes_preserved(client):
    "原始文件不能误删：字节入blob只增不删，重试不重复存"
    p=client.post("/api/runs",json={"sample":"mixed.csv"}).get_json()
    client.post("/api/runs",json={"sample":"mixed.csv"})
    with store.connect() as db:
        blobs=db.execute("SELECT sha256,data FROM blobs").fetchall()
    assert len(blobs)==1 and bytes(blobs[0][1])==load_sample("mixed.csv")
    r=client.get(f"/api/runs/{p['run_id']}/bytes?start=0&end=20")
    assert r.status_code==200 and r.get_json()["hex"]==load_sample("mixed.csv")[:20].hex()
def test_bytes_endpoint_validates_range(client):
    p=client.post("/api/runs",json={"sample":"mixed.csv"}).get_json();url=f"/api/runs/{p['run_id']}/bytes"
    assert client.get(url).status_code==422
    assert client.get(url+"?start=20&end=3").status_code==422
    assert client.get(url+"?start=0&end=99999").status_code==422
def test_bytes_endpoint_offers_both_candidates(client):
    p=client.post("/api/runs",json={"sample":"mixed.csv"}).get_json()
    row=next(r for r in p["stages"][5]["rows"] if r["event_id"]=="1003")
    s,e=row["_bytes"]
    body=client.get(f"/api/runs/{p['run_id']}/bytes?start={s}&end={e}").get_json()
    assert "早班" in body["gb18030"] and body["utf-8"] is None
def test_card_day_unique_and_sealable(client):
    "每卡每日唯一卡日应收，跨编码来源并入同一卡日"
    p=client.post("/api/runs",json={"sample":"mixed.csv"}).get_json()
    days=p["stages"][6]["card_days"]
    assert [(d["card"],d["business_day"]) for d in days]==[("0001","2026-11-16"),("0002","2026-11-16")]
    assert days[0]["receivable"]=="5.50" and days[0]["events"]==3 and days[1]["receivable"]=="2.50"
    assert p["stages"][6]["metrics"]["ready"] is True
    assert client.post(f"/api/runs/{p['run_id']}/review",json={"version":1,"decision":"已复核"}).status_code==200
    assert client.get(f"/api/runs/{p['run_id']}/archive").status_code==200
def test_byte_coverage_balanced(client):
    "字节级对平：每字节被且仅被结算一次"
    for name in ("dirty.csv","clean.csv","legacy.csv","mixed.csv"):
        p=client.post("/api/runs",json={"sample":name}).get_json()
        m=p["stages"][5]["metrics"]
        assert m["byte_balanced"] is True and m["balanced"] is True
def test_review_page_renders(client):
    client.post("/api/runs",json={"sample":"mixed.csv"})
    html=client.get("/review").data.decode()
    assert "卡日应收" in html and "字节区间" in html and "换乘优惠" in html and "早班" in html
