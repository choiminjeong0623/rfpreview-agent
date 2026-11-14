"""처리 세부 진행 기록 (명세 review-run, change update-processing-progress)."""

import psycopg
from psycopg.types.json import Jsonb

from rfp_agent.pipeline import queries
from rfp_agent.pipeline.run import RunContext, create_run, execute_run, write_progress
from tests.conftest import FakeLLM
from tests.docx_factory import build_gis_spec

VERSION = "test-dict-v1"


def test_type_tagging_progress_counts(seeded_db, db_url, tmp_path):
    """Scenario: 유형 붙이기 진행 개수 — 처리 도중 다른 연결에서 바로 보인다."""
    path = build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")
    llm = FakeLLM()
    run_id = create_run(seeded_db, VERSION, llm)
    seen: list[dict] = []
    with psycopg.connect(db_url, autocommit=True) as side:
        write = write_progress(side)

        def progress(rid: int, detail: dict) -> None:
            write(rid, detail)
            # 본 처리 트랜잭션이 열려 있어도 다른 연결에서 바로 읽힌다
            seen.append(side.execute("SELECT graph_state->'detail' FROM review_run "
                                     "WHERE run_id = %s", (run_id,)).fetchone()[0])

        ctx = RunContext(seeded_db, VERSION, llm, None, progress)
        assert execute_run(ctx, run_id, [path]) == "ENGINEER_REVIEW"

    parts = [d["part"] for d in seen]
    assert parts[:3] == ["classify", "structure", "extract"]
    assert "label" in parts and "save" in parts
    typed = [d for d in seen if d["part"] == "type"]
    assert typed, "규칙으로 유형을 못 정한 줄이 있어야 한다"
    assert any(0 < d["done"] <= d["total"] for d in typed)
    assert typed[-1]["done"] == typed[-1]["total"]
    assert all((d["file_index"], d["file_count"]) == (1, 1) for d in seen)
    labels = [d for d in seen if d["part"] == "label"]
    assert [d["done"] for d in labels] == sorted(d["done"] for d in labels)


def test_finished_run_clears_detail(seeded_db, tmp_path):
    """Scenario: 단계가 바뀌면 세부 진행을 지움."""
    path = build_gis_spec(tmp_path / "synthetic_154kV_GIS_spec.docx")
    run_id = create_run(seeded_db, VERSION, None)
    seeded_db.execute("UPDATE review_run SET graph_state = graph_state || %s WHERE run_id = %s",
                      (Jsonb({"detail": {"part": "type", "done": 1, "total": 2,
                                         "file_index": 1, "file_count": 1}}), run_id))
    assert execute_run(RunContext(seeded_db, VERSION, None, None), run_id, [path]) \
        == "ENGINEER_REVIEW"
    summary = queries.run_summary(seeded_db, run_id)
    assert summary["step"] == "done"
    assert summary["step_detail"] is None
    assert summary["step_updated_at"] >= summary["started_at"]


def test_run_list_has_step_detail(seeded_db):
    """Scenario: 목록에도 세부 진행."""
    run_id = create_run(seeded_db, VERSION, None)
    write_progress(seeded_db)(run_id, {"part": "type", "done": 120, "total": 400,
                                       "file_index": 1, "file_count": 1})
    seeded_db.commit()
    row = next(r for r in queries.run_list(seeded_db) if r["run_id"] == run_id)
    assert row["stage"] == "PROCESSING"
    assert (row["step_detail"]["part"], row["step_detail"]["done"],
            row["step_detail"]["total"]) == ("type", 120, 400)
