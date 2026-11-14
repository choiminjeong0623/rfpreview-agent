"""합성 묶음 A 문서로 담당자 확인 → 승인까지 돌린다. 명세 review-approval의 Scenario."""

import re

import pytest

from rfp_agent.pipeline import queries, review
from rfp_agent.pipeline.outputs import build_outputs
from rfp_agent.pipeline.run import RunContext, create_run, execute_run
from tests.conftest import FakeLLM

VERSION = "test-dict-v1"


def run_once(conn, paths):
    run_id = create_run(conn, VERSION, None)
    assert execute_run(RunContext(conn, VERSION, None, None), run_id, paths) == "ENGINEER_REVIEW"
    return run_id


def ctx(conn):
    return RunContext(conn, VERSION, None, None)


def judgment(conn, run_id, table, name):
    [j] = [j for j in queries.run_judgments(conn, run_id, limit=500)
           if j["item_name_raw"] == name and j["locations"][0]["table_name"] == table]
    return j


def submit(conn, run_id, comment="질의 1건은 10-27 회신 예정"):
    return review.finish_review(conn, run_id, review.default_user(conn, "APPROVER"), comment)


def codes(found):
    return [c["ar_code"] if isinstance(c, dict) else c.ar_code for c in found]


def test_deviation_run_waits_for_approval(db, spec):
    """Scenario: 일탈 후보가 있는 실행 / 승인 대기 중 수정."""
    run_id = run_once(db, [spec])
    result = submit(db, run_id)
    assert result["stage"] == "APPROVAL" and "AR-01" in codes(result["criteria"])
    assert queries.run_summary(db, run_id)["stage"] == "APPROVAL"
    screen = review.approval(db, run_id)
    assert screen["approval"]["decision"] is None          # 결정 전에는 승인됨이 아니다
    assert "AR-01" in [r["ar_code"] for r in screen["reasons"]]
    assert screen["submission_check"]["deviation_candidates"] == 4
    with pytest.raises(review.ReviewError) as err:          # 승인 대기 중에는 후보를 못 고친다
        review.act(ctx(db), run_id, "risk_flag", 1, "CONFIRM")
    assert err.value.status == 409


def test_review_ratio_criterion(db, spec):
    """Scenario: 확인 필요 비율 — 보증값을 채운 칸을 뺀 확인 필요 비율이 20 %를 넘으면 AR-03."""
    run_id = run_once(db, [spec])
    [ar03] = [c for c in review.criteria(db, run_id) if c.ar_code == "AR-03"]
    assert "기준 20%" in ar03.detail
    pending = [j for j in queries.run_judgments(db, run_id, limit=500)
               if j["result"] == "NEEDS_REVIEW"]
    for j in pending:                                       # 엔지니어가 모두 확인하면 빠진다
        review.act(ctx(db), run_id, "judgment", j["judgment_id"], "CONFIRM")
    assert "AR-03" not in codes(review.criteria(db, run_id))


def test_editing_judgment_logs_and_rebuilds_list(db, spec):
    """Scenario: 판정을 바꿈 — 준수 → 일탈 후보면 이력 1건(이전·새 값·사유), 일탈 목록 다시 생성."""
    run_id = run_once(db, [spec])
    j = judgment(db, run_id, "TS-115-GIS", "Rated normal current")
    assert j["result"] == "COMPLY"
    kept = next(i for i in queries.run_outputs(db, run_id, "DEVIATION")
                if "4,000" in i["text_draft"])
    review.act(ctx(db), run_id, "output_item", kept["item_id"], "CONFIRM")
    review.act(ctx(db), run_id, "judgment", j["judgment_id"], "EDIT",
               {"result": "DEVIATION_CANDIDATE"}, "발주처 해석상 모선 기준 미달")
    [entry] = review.history(db, run_id, "judgment", j["judgment_id"])
    assert entry["action"] == "EDIT" and entry["reason"] == "발주처 해석상 모선 기준 미달"
    assert entry["before_value"]["result"] == "COMPLY"
    assert entry["after_value"]["result"] == "DEVIATION_CANDIDATE"
    deviations = queries.run_outputs(db, run_id, "DEVIATION")
    assert any(s["judgment_id"] == j["judgment_id"] for i in deviations for s in i["sources"])
    again = next(i for i in deviations if "4,000" in i["text_draft"])
    assert again["status"] == "CONFIRMED"                   # 다시 만들어도 확인 결과는 남는다
    check = review.approval(db, run_id)["submission_check"]
    assert check["deviation_candidates"] == 5 and check["missing_judgment_ids"] == []


def test_editing_judgment_redrafts_only_new_items(db, spec):
    """판정을 바꾸면 새로 생긴 목록 문장만 언어 모델에 묻고, 나머지 문장은 그대로 둔다."""
    llm = FakeLLM()
    run_id = create_run(db, VERSION, llm)
    assert execute_run(RunContext(db, VERSION, llm, None), run_id, [spec]) == "ENGINEER_REVIEW"
    before = {i["item_id"]: i["text_draft"] for i in queries.run_outputs(db, run_id)}
    j = judgment(db, run_id, "TS-115-GIS", "Rated normal current")
    llm.prompts.clear()
    review.act(RunContext(db, VERSION, llm, None), run_id, "judgment", j["judgment_id"], "EDIT",
               {"result": "DEVIATION_CANDIDATE"}, "발주처 해석상 모선 기준 미달")
    drafted = [p for p in llm.prompts if "자리표시자" in p]
    assert len(drafted) == 1                    # 일탈 목록만 한 번, 제안 포인트는 묻지 않음
    assert len(re.findall(r"^\d+\. ", drafted[0], re.MULTILINE)) == 1
    after = queries.run_outputs(db, run_id)
    assert len(after) == len(before) + 1
    assert sorted(before.values()) == sorted(i["text_draft"] for i in after
                                             if not any(s["judgment_id"] == j["judgment_id"]
                                                        for s in i["sources"]))


def test_changed_value_redrafts_sentence(db, spec):
    """근거 값(제품값)이 바뀐 항목은 예전 문장을 쓰지 않고 다시 쓴다 (CR-07)."""
    llm = FakeLLM()
    run_id = create_run(db, VERSION, llm)
    assert execute_run(RunContext(db, VERSION, llm, None), run_id, [spec]) == "ENGINEER_REVIEW"
    j = judgment(db, run_id, "TS-230-GIS", "Rated normal current of main busbar")
    db.execute("UPDATE judgment SET product_value_raw = '3777 A' WHERE judgment_id = %s",
               (j["judgment_id"],))
    llm.prompts.clear()
    build_outputs(db, run_id, [d["document_id"] for d in queries.run_documents(db, run_id)], llm)
    [drafted] = [p for p in llm.prompts if "자리표시자" in p]
    assert len(re.findall(r"^\d+\. ", drafted, re.MULTILINE)) == 1
    [item] = [i for i in queries.run_outputs(db, run_id, "DEVIATION")
              if any(s["judgment_id"] == j["judgment_id"] for s in i["sources"])]
    assert "3777 A" in item["text_draft"]


def test_only_adopted_point_is_delivered(db, spec):
    """Scenario: 2건 중 1건 채택 — 채택한 1건만 전달 대상이다."""
    run_id = run_once(db, [spec])
    points = queries.run_proposals(db, run_id)
    assert len(points) >= 2
    first, second = points[:2]
    review.act(ctx(db), run_id, "proposal_point", first["point_id"], "ADOPT")
    review.act(ctx(db), run_id, "proposal_point", second["point_id"], "DISCARD",
               reason="고객이 중요하게 보지 않는 항목")
    delivered = review.deliverables(db, run_id)["proposals"]
    assert [p["point_id"] for p in delivered] == [first["point_id"]]
    assert "AR-08" in codes(review.criteria(db, run_id))


def test_rejection_records_comment(db, spec):
    """Scenario: 반려 / 승인자가 아닌 사용자."""
    run_id = run_once(db, [spec])
    submit(db, run_id)
    engineer = review.default_user(db, "ENGINEER")
    with pytest.raises(review.ReviewError) as err:          # 엔지니어는 승인할 수 없다
        review.decide(db, run_id, "APPROVED", None, engineer)
    assert err.value.status == 403
    with pytest.raises(review.ReviewError):                 # 반려에는 의견이 필요하다
        review.decide(db, run_id, "REJECTED", "")
    result = review.decide(db, run_id, "REJECTED", "4,000 A 일탈 사유를 보완할 것")
    assert result["stage"] == "REJECTED"
    assert result["approval"]["comment"] == "4,000 A 일탈 사유를 보완할 것"
    assert result["approval"]["decided_at"] is not None
    assert queries.run_summary(db, run_id)["stage"] == "REJECTED"
    assert review.reopen(db, run_id)["stage"] == "ENGINEER_REVIEW"


def test_edits_need_reason_and_keep_team_assumption(db, spec):
    """수정·반려에는 사유가 필요하고, 고친 보증값·문장도 이력에 남는다."""
    run_id = run_once(db, [spec])
    weight = next(w for w in queries.run_warranty(db, run_id, limit=500)
                  if w["item_name_raw"] == "Weight of circuit breaker")
    with pytest.raises(review.ReviewError):
        review.act(ctx(db), run_id, "warranty_candidate", weight["candidate_id"], "EDIT",
                   {"value": "850", "unit": "kg"})
    review.act(ctx(db), run_id, "warranty_candidate", weight["candidate_id"], "EDIT",
               {"value": "850", "unit": "kg"}, "설계팀 회신 값")
    [w] = [w for w in queries.run_warranty(db, run_id, limit=500)
           if w["candidate_id"] == weight["candidate_id"]]
    assert (w["candidate_value"], w["source_kind"], w["status"]) == ("850", "ENGINEER",
                                                                      "CONFIRMED")
    item = queries.run_outputs(db, run_id, "DEVIATION")[0]
    result = review.act(ctx(db), run_id, "output_item", item["item_id"], "EDIT",
                        {"text": "주모선 정격 전류 9,999 A 요구에 대해 일탈을 제출합니다."},
                        "문장 다듬기")
    assert result["after"]["number_check"] == "MISMATCH"   # 근거에 없는 숫자는 경고
    assert len(review.history(db, run_id)) == 2
