import pytest,csv,io
from app.pipeline import load_sample
from app.modules.m1_taps import rules
from app.modules.m1_taps.rules import evaluate,decode
from app.config import COLUMNS
from app.errors import DomainError
HEADER=(",".join(COLUMNS)).encode()
def test_bom_real_sample(sample):
    "TRAP-02"
    r=evaluate(sample);assert r["metrics"]["encoding"]=="utf-8-sig" and r["rows"][0][COLUMNS[0]].startswith("00")
def test_legacy_encoding_real_sample():
    "TRAP-01"
    r=evaluate(load_sample("legacy.csv"));assert r["metrics"]["encoding"]=="gb18030" and r["metrics"]["accepted"]>=30
def test_bad_columns_real_sample(sample):
    "TRAP-05"
    assert any(r["reason"]=="BAD_COLUMNS" for r in evaluate(sample)["quarantine"])
def test_duplicate_conflict_real_sample(sample):
    "TRAP-14"
    assert any(r["reason"]=="DUPLICATE_CONFLICT" for r in evaluate(sample)["quarantine"])
def test_identifier_preserved_real_sample(sample):
    "TRAP-08"
    r=evaluate(sample)["rows"][0];assert r[COLUMNS[0]].startswith("00")
def test_three_empty_states():
    "TRAP-18"
    for raw,code in [(b"","EMPTY_FILE"),(b"\n\r\n","BLANK_ONLY"),((",".join(COLUMNS)+"\n").encode(),"HEADER_ONLY")]:
        with pytest.raises(DomainError) as e:evaluate(raw)
        assert e.value.code==code
def test_intake_conservation_real_sample(sample):
    r=evaluate(sample);m=r["metrics"]
    assert m["input"]==m["accepted"]+m["quarantine"]+m["duplicate"]+m["blank"]+m["repeated_headers"]
def test_quoted_newline_is_one_record(sample):
    "TRAP-03"
    r=evaluate(sample);assert any("\n" in str(x) for row in r["rows"] for x in row.values())
def test_mixed_sample_two_segments():
    "TRAP-27 合并包按分段表头切分，两段各自判定编码"
    r=evaluate(load_sample("mixed.csv"));m=r["metrics"]
    assert m["encoding"]=="mixed" and m["segments"]==2
    assert [s["encoding"] for s in r["segments"]]==["utf-8","gb18030"]
    notes={row["event_id"]:row["note"] for row in r["rows"]}
    assert notes["1002"]=="换乘优惠" and notes["1003"]=="早班"
def test_mixed_intake_conservation():
    r=evaluate(load_sample("mixed.csv"));m=r["metrics"]
    assert m["input"]==m["accepted"]+m["quarantine"]+m["duplicate"]+m["blank"]+m["repeated_headers"]
def test_byte_range_decodes_back():
    "每行字节区间在原始包中可回读出同一解码值"
    for name in ("mixed.csv","dirty.csv","legacy.csv","clean.csv"):
        raw=load_sample(name)
        for row in evaluate(raw)["rows"]:
            s,e=row["_bytes"];codec="utf-8" if row["_encoding"]=="utf-8-sig" else row["_encoding"]
            text=raw[s:e].decode(codec)
            assert row["event_id"] in text and (not row.get("note") or row["note"] in text)
def test_dual_valid_bytes_scored_gb18030():
    "TRAP-28 '路'的GB18030字节是合法UTF-8(·)，领域评分裁决为GB18030"
    raw=HEADER+b"\n9001,0009,01,2026-11-16T08:00:00+08:00,success,2.50,"+"路".encode("gb18030")+b"\n"
    r=evaluate(raw)
    assert r["rows"][0]["note"]=="路" and r["rows"][0]["_encoding"]=="gb18030"
    assert r["rows"][0]["_basis"].startswith("scored:")
def test_ambiguous_segment_quarantined(monkeypatch):
    "评分打平即证据不足：整段隔离为未证明，不猜测"
    monkeypatch.setattr(rules,"_score",lambda text:0)
    raw=HEADER+b"\n"+HEADER+b"\n9001,0009,01,2026-11-16T08:00:00+08:00,success,2.50,"+"路".encode("gb18030")+b"\n"
    r=evaluate(raw)
    assert r["rows"]==[] and r["metrics"]["unproven"]>0
    assert any(q["reason"]=="AMBIGUOUS_DECODING" for q in r["quarantine"])
def test_undecodable_segment_quarantined():
    "两种编码都无法解码的字节：整段隔离，其余段不受影响"
    good=HEADER+b"\n9001,0009,01,2026-11-16T08:00:00+08:00,success,2.50,"+"常规".encode()+b"\n"
    bad=HEADER+b"\n9002,0009,01,2026-11-16T09:00:00+08:00,success,2.50,\xff\xfe\n"
    r=evaluate(good+bad)
    assert [row["event_id"] for row in r["rows"]]==["9001"]
    assert any(q["reason"]=="UNDECODABLE" for q in r["quarantine"]) and r["metrics"]["unproven"]>=1
def test_interpretation_conflict():
    "TRAP-29 同一字节串在不同段被解码成两种值，双方全部隔离"
    note_utf8="换乘".encode("utf-8")
    seg_a=HEADER+b"\nA001,0001,01,2026-11-16T08:00:00+08:00,success,2.50,"+"早班".encode("gb18030")+b"\nA002,0001,02,2026-11-16T08:20:00+08:00,success,1.50,"+note_utf8+b"\n"
    seg_b=HEADER+b"\nB001,0002,03,2026-11-16T09:00:00+08:00,success,2.50,"+note_utf8+b"\n"
    r=evaluate(seg_a+seg_b)
    assert [row["event_id"] for row in r["rows"]]==["A001"]
    conflicted={q["event_id"] for q in r["quarantine"] if q["reason"]=="INTERPRETATION_CONFLICT"}
    assert conflicted=={"A002","B001"} and r["metrics"]["unproven"]==2
def test_first_segment_undecodable_raises():
    with pytest.raises(DomainError) as e: evaluate(b"\xff\xfe\x00")
    assert e.value.code=="ENCODING"
def test_unproven_segment_line_numbers():
    "未证明段按物理行逐条登记，行号与全包一致"
    good=HEADER+b"\n9001,0009,01,2026-11-16T08:00:00+08:00,success,2.50,"+"常规".encode()+b"\n"
    bad=HEADER+b"\n9002,0009,01,2026-11-16T09:00:00+08:00,success,2.50,\xff\n"
    r=evaluate(good+bad)
    lines=sorted(q["_line"] for q in r["quarantine"])
    assert lines==[3,4] and all(q["_bytes"] for q in r["quarantine"])
