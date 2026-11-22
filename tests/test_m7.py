from app.modules.m7_settlement.rules import evaluate
from app.errors import DomainError
import pytest
def test_real_sample_archive_ready(result): assert result["stages"][6]["metrics"]["ready"] is True
def test_real_sample_archive_source_count(result): assert result["stages"][6]["metrics"]["source_lines"]==result["stages"][5]["metrics"]["accepted_inputs"]
def test_real_sample_seal_stable(result):
    rows=result["stages"][5]["rows"];assert evaluate(rows,{})["metrics"]["sha256"]==evaluate(rows,{})["metrics"]["sha256"]
def test_unbalanced_blocked():
    with pytest.raises(DomainError) as e:evaluate([],{"reconcile":{"metrics":{"balanced":False}}})
    assert e.value.code=="UNBALANCED"
def test_duplicate_archive_key():
    with pytest.raises(DomainError):evaluate([{"event_id":"1"},{"event_id":"1"}],{})
def test_real_sample_manifest_has_hash(result): assert len(result["manifest"]["input_sha256"])==64
def test_real_sample_export_rows_match(result): assert result["stages"][6]["rows"]==result["stages"][5]["rows"]
def test_unproven_blocks_ready():
    r=evaluate([],{"quarantine":[{"reason":"UNDECODABLE"}]})
    assert r["metrics"]["ready"] is False and r["metrics"]["unproven"]==1
def test_proven_quarantine_still_ready():
    r=evaluate([],{"quarantine":[{"reason":"BAD_COLUMNS"}]})
    assert r["metrics"]["ready"] is True and r["metrics"]["unproven"]==0
def test_card_day_unique_grouping():
    rows=[{"event_id":"1","card":"01","business_day":"2026-11-16","expected":"2.50","_sources":[2]},
          {"event_id":"2","card":"01","business_day":"2026-11-16","expected":"1.50","_sources":[3]},
          {"event_id":"3","card":"02","business_day":"2026-11-16","expected":"2.50","_sources":[4]}]
    days=evaluate(rows,{})["card_days"]
    assert [(d["card"],d["business_day"],d["receivable"],d["events"]) for d in days]==[("01","2026-11-16","4.00",2),("02","2026-11-16","2.50",1)]
