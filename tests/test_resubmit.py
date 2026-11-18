# TRAP-30 转瓶补送：两类受理号关联、按物理样品归并、失败恢复、幂等与迟到版本
from app.modules.m8_resubmit.rules import DSU, merge
from app.pipeline import run, sample_text
from app import store
from app.exporter import evidence_csv
import pytest

HEADER = "id,batch,analyte,kind,pair,value,spike,unit,version,resubmit"


def build(rows):
    base = sample_text().splitlines()
    body = [line + "," for line in base[1:]]
    return "\n".join([HEADER] + body + rows) + "\n"


def aliases_for(result, fragment):
    return next(x["accept_aliases"] for x in result["effective"] if fragment in x.get("accept_aliases", []))


def test_dsu_union_and_find():
    dsu = DSU()
    for x in ("a", "b", "c"):
        dsu.add(x)
    dsu.union("a", "b")
    dsu.union("b", "c")
    assert dsu.find("a") == dsu.find("c")
    dsu.add("z")
    assert dsu.find("z") == "z"


def test_resubmit_links_two_acceptance_numbers():
    r = run(build(["R001S,B01,Pb,sample,P1,0.0032,0,mg/L,2,001S"]))
    assert r["resubmit_links"] == [
        {"batch": "B01", "analyte": "Pb", "new_id": "R001S", "original_id": "001S", "line": 48}]
    assert aliases_for(r, "001S") == ["001S", "R001S"]


def test_resubmit_does_not_create_independent_qc():
    r = run(build(["R001S,B01,Pb,sample,P1,0.0032,0,mg/L,2,001S"]))
    base = run(sample_text())
    # 补送后有效样品数和平行组数不增加：同一物理瓶只算一次质控
    assert len(r["effective"]) == len(base["effective"]) == 40
    assert len(r["parallel"]) == len(base["parallel"]) == 10
    p1 = next(p for p in r["parallel"] if p["pair"] == "P1")
    assert p1["current_id"] == "R001S" and p1["accept_aliases"] == ["001S", "R001S"]
    assert str(p1["left"]) == "0.0032"


def test_resubmit_keeps_original_row_evidence():
    r = run(build(["R001S,B01,Pb,sample,P1,0.0032,0,mg/L,2,001S"]))
    current = next(x for x in r["effective"] if "001S" in x["accept_aliases"])
    assert current["history_lines"] == [2, 48]
    assert current["history_versions"] == [1, 2]
    # 原始行仍可在 M1 接收证据中查到，没有丢失记录
    raw_ids = [x["id"] for x in r["reports"][0]["rows"]]
    assert "001S" in raw_ids and "R001S" in raw_ids


def test_late_older_resubmit_cannot_roll_back_current():
    r = run(build([
        "NEW1,B01,Pb,sample,P3,0.009,0,mg/L,3,003S",
        "LATE1,B01,Pb,sample,P3,0.001,0,mg/L,2,003S",
    ]))
    current = next(x for x in r["effective"] if "003S" in x["accept_aliases"])
    assert current["id"] == "NEW1" and current["rev"] == 3 and str(current["value_mg"]) == "0.009"
    assert set(current["accept_aliases"]) == {"003S", "NEW1", "LATE1"}


def test_same_revision_tie_keeps_last_confirmed():
    r = run(build([
        "T1,B01,Pb,sample,P5,0.008,0,mg/L,2,005S",
        "T2,B01,Pb,sample,P5,0.004,0,mg/L,2,005S",
    ]))
    current = next(x for x in r["effective"] if "005S" in x["accept_aliases"])
    # 同版本时取最后确认（行号更大），结论不被先到的补送固定
    assert current["id"] == "T2" and str(current["value_mg"]) == "0.004"


def test_merge_failure_missing_target_recovers_to_standalone():
    r = run(build(["RX,B01,Pb,sample,P1,0.009,0,mg/L,2,GHOST999"]))
    assert any(q["reason"] == "RESUBMIT_TARGET_MISSING" for q in r["quarantine"])
    assert r["resubmit_links"] == []
    # 归并失败后从最后确认的样品恢复：RX 独立保留、原值不丢
    rx = next(x for x in r["effective"] if x["id"] == "RX")
    assert str(rx["value_mg"]) == "0.009" and rx["accept_aliases"] == ["RX"]


def test_resubmit_self_reference_quarantined():
    r = run(build(["SELF,B01,Pb,sample,P2,0.005,0,mg/L,2,SELF"]))
    assert any(q["reason"] == "RESUBMIT_SELF" for q in r["quarantine"])
    assert r["resubmit_links"] == []


def test_duplicate_resubmit_edge_quarantined():
    r = run(build([
        "C1,B02,Pb,sample,P6,0.011,0,mg/L,2,006S",
        "C1,B02,Pb,sample,P6,0.013,0,mg/L,3,006S",
    ]))
    assert any(q["reason"] == "RESUBMIT_DUPLICATE" for q in r["quarantine"])
    # 首次补送仍归并成功，重复边不新增记录
    assert [(l["new_id"], l["original_id"]) for l in r["resubmit_links"]] == [("C1", "006S")]


def test_resubmit_cycle_edge_quarantined_but_chain_kept():
    r = run(build([
        "X,B01,Pb,sample,P4,0.005,0,mg/L,2,004S",
        "Y,B01,Pb,sample,P4,0.006,0,mg/L,2,X",
        "004S,B01,Pb,sample,P4,0.007,0,mg/L,2,Y",
    ]))
    assert any(q["reason"] == "RESUBMIT_CYCLE" for q in r["quarantine"])
    assert {(l["new_id"], l["original_id"]) for l in r["resubmit_links"]} == {("X", "004S"), ("Y", "X")}
    current = next(x for x in r["effective"] if "004S" in x["accept_aliases"])
    assert set(current["accept_aliases"]) == {"004S", "X", "Y"}


def test_retry_same_batch_creates_no_new_record():
    text = build(["R001S,B01,Pb,sample,P1,0.0032,0,mg/L,2,001S"])
    a = store.save(text, run(text))
    b = store.save(text, run(text))
    assert a["id"] == b["id"] and a["digest"] == b["digest"]
    assert len(store.history()) >= 1


def test_evidence_export_contains_both_numbers_and_current():
    text = build(["R001S,B01,Pb,sample,P1,0.0032,0,mg/L,2,001S"])
    item = store.save(text, run(text))
    exported = evidence_csv(item)
    assert "resubmit_link" in exported and "physical_sample" in exported
    assert "R001S" in exported and "001S" in exported


def test_legacy_file_without_resubmit_column_still_runs():
    r = run(sample_text())
    assert len(r["reports"]) == 8
    assert r["reports"][2]["metrics"]["补送归并"] == 0
    assert r["resubmit_links"] == []
    assert all(x["accept_aliases"] == [x["id"]] for x in r["effective"])


def test_resubmit_scoped_by_batch_and_analyte():
    # 同号但不同检测域的引用不能跨域并瓶
    text = sample_text().splitlines()
    extra_as = [line.replace(",Pb,", ",As,") for line in text[1:21]]
    rows = [line + "," for line in text[1:]] + [l + "," for l in extra_as] + \
           ["R9,B02,As,sample,P6,0.002,0,mg/L,2,006S"]
    res = run("\n".join([HEADER] + rows) + "\n")
    # B02/As 域没有 006S（006S 属于 B02/Pb），引用目标缺失应隔离
    assert any(q["reason"] == "RESUBMIT_TARGET_MISSING" for q in res["quarantine"])


def test_blank_resubmit_column_treated_as_original():
    text = build([])
    r = run(text)
    assert r["resubmit_links"] == []
    assert len(r["effective"]) == 40


def test_resubmit_column_is_optional_in_header():
    from app.reader import read_rows
    from app.modules.m1_samples.rules import FIELDS, OPTIONAL_FIELDS
    from app.errors import BusinessError
    fields = FIELDS + OPTIONAL_FIELDS
    nine = "id,batch,analyte,kind,pair,value,spike,unit,version\nX,B,Pb,sample,P,1,0,mg/L,1\n"
    rows, _, _ = read_rows(nine, fields, optional=set(OPTIONAL_FIELDS))
    assert rows[0]["resubmit"] == ""
    ten = "id,batch,analyte,kind,pair,value,spike,unit,version,resubmit\nX,B,Pb,sample,P,1,0,mg/L,1,\n"
    assert read_rows(ten, fields, optional=set(OPTIONAL_FIELDS))[0][0]["resubmit"] == ""
    for bad in (
        "id,batch,analyte,kind,pair,value,spike,unit\nX,B,Pb,sample,P,1,0,mg/L\n",
        "id,batch,analyte,kind,pair,value,spike,unit,version,extra\nX,B,Pb,sample,P,1,0,mg/L,1,x\n",
        "id,id,batch,analyte,kind,pair,value,spike,unit,version\nX,X,B,Pb,sample,P,1,0,mg/L,1\n",
    ):
        with pytest.raises(BusinessError, match="字段不匹配"):
            read_rows(bad, fields, optional=set(OPTIONAL_FIELDS))


def test_merge_helper_returns_links_and_bad_edges():
    ctx = {"quarantine": []}
    rows = [
        {"id": "a", "batch": "B", "analyte": "Pb", "pair": "P", "kind": "sample", "rev": 1, "line": 1, "resubmit": ""},
        {"id": "b", "batch": "B", "analyte": "Pb", "pair": "P", "kind": "sample", "rev": 2, "line": 2, "resubmit": "a"},
    ]
    effective, links, bad = merge(rows, ctx)
    assert len(effective) == 1 and effective[0]["id"] == "b"
    assert links and not bad and effective[0]["accept_aliases"] == ["a", "b"]


def test_cycle_line_points_to_the_actual_resubmit_row():
    # 同一受理号多版多行时，隔离与链接的行号必须定位到具体补送行
    r = run(build([
        "X,B01,Pb,sample,P4,0.005,0,mg/L,2,004S",
        "Y,B01,Pb,sample,P4,0.006,0,mg/L,2,X",
        "004S,B01,Pb,sample,P4,0.007,0,mg/L,2,Y",
    ]))
    cycle = next(q for q in r["quarantine"] if q["reason"] == "RESUBMIT_CYCLE")
    assert cycle["line"] == 50
    assert {l["line"] for l in r["resubmit_links"]} == {48, 49}


def test_duplicate_edge_keeps_first_line_in_link():
    r = run(build([
        "C1,B02,Pb,sample,P6,0.011,0,mg/L,2,006S",
        "C1,B02,Pb,sample,P6,0.013,0,mg/L,3,006S",
    ]))
    dup = next(q for q in r["quarantine"] if q["reason"] == "RESUBMIT_DUPLICATE")
    assert dup["line"] == 49
    assert r["resubmit_links"][0]["line"] == 48


def test_identity_drift_is_quarantined_and_original_kept():
    r = run(build(["R002S,B01,Pb,sample,P9,0.004,0,mg/L,2,002S"]))
    q = next(x for x in r["quarantine"] if x["reason"] == "RESUBMIT_IDENTITY_DRIFT")
    assert q["id"] == "R002S"
    assert r["resubmit_links"] == []
    # 原瓶 002S 仍以最后确认值独立存在，未与漂移补送并瓶
    original = next(x for x in r["effective"] if x["id"] == "002S")
    assert original["accept_aliases"] == ["002S"]
    # 原 P2 配对完好；漂移行独立成组并显式报配对缺失，而非静默污染结论
    p2 = next(p for p in r["parallel"] if p["pair"] == "P2")
    assert p2["status"] == "PASS" and p2["current_id"] == "002S"
    p9 = [p for p in r["parallel"] if p["pair"] == "P9"]
    assert any(p["status"] == "PAIR_MISSING" for p in p9)
