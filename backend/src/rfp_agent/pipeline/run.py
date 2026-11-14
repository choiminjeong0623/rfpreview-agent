"""검토 실행 하나를 LangGraph 흐름으로 돌린다: 문서별 ①~⑤ → 위험 조건 ⑥ → 판정 ⑦ → 보증값 ⑧
→ 손실 환산 → 일탈·질의 목록 ⑨ → 제안 포인트.

실행 상태는 review_run에 남기고, AI 호출이 재시도 뒤에도 실패하면 FAILED와 실패 단계를 기록한다
(CR-12). 결과는 모두 run_id에 묶인다.
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TypedDict

import psycopg
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from psycopg.types.json import Jsonb

from rfp_agent.config import get_settings
from rfp_agent.llm import tasks
from rfp_agent.llm.client import FAILURE_MESSAGE, LLM, LLMConfigError, LLMFailure, Usage, usage_of
from rfp_agent.llm.evidence import EvidenceSpan, evidence_id, parse_evidence_id
from rfp_agent.llm.parallel import run_ordered, workers_of
from rfp_agent.pipeline import code_version, dictionaries, doc_add, graph_flow, meaning, ocr
from rfp_agent.pipeline.assignments import build_assignments
from rfp_agent.pipeline.document import Choice, DocumentResult, Report, process_document
from rfp_agent.pipeline.engineering import build_checks
from rfp_agent.pipeline.judge import judge_run
from rfp_agent.pipeline.loss import build_losses
from rfp_agent.pipeline.numbers import josa
from rfp_agent.pipeline.outputs import build_outputs
from rfp_agent.pipeline.proposals import build_proposals
from rfp_agent.pipeline.risk import (
    FLAG_KIND,
    RiskCandidate,
    ValueRef,
    find_clause_risks,
    find_value_mismatches,
)
from rfp_agent.pipeline.warranty import build_warranty

log = logging.getLogger(__name__)

DEFAULT_USER = "기본 엔지니어"    # 로그인(4단계) 전까지 0003에서 만든 사용자


class RunState(TypedDict, total=False):
    run_id: int
    paths: list[str]
    choices: dict[str, dict]      # 파일 이름 → 사람이 정한 {bundle, doc_kind}
    document_ids: list[int]
    readable_ids: list[int]
    risk_count: int
    judgment_count: int
    check_count: int
    warranty_count: int
    loss_count: int
    output_count: int
    proposal_count: int
    assignment_count: int
    meaning_count: int
    action: str                   # 사람 단계에서 받은 동작 (update-graph-stops)
    rewind_to: str                # 되돌려 다시 처리할 단계 (add-step-rewind)


# 세부 진행 기록: (run_id, {"part", "done", "total", "file_index", "file_count"})
ProgressWriter = Callable[[int, dict], None]


def write_progress(conn: psycopg.Connection) -> ProgressWriter:
    """자동 커밋 연결로 세부 진행을 바로 적는다.

    문서 하나는 한 트랜잭션 안에서 처리하므로 같은 연결로 적으면 끝날 때까지 화면에 보이지 않는다.
    진행 기록이 실패해도 처리는 계속한다.
    """
    def write(run_id: int, detail: dict) -> None:
        try:
            conn.execute(
                "UPDATE review_run SET graph_state = graph_state || "
                "jsonb_build_object('detail', %s::jsonb, 'updated_at', now()) WHERE run_id = %s",
                (Jsonb(detail), run_id))
        except psycopg.Error as exc:
            log.warning("진행 기록 실패 (실행 %s): %s", run_id, exc)
    return write


@dataclass
class RunContext:
    conn: psycopg.Connection
    version: str                # 사전·제품표 판 (dict_version)
    llm: LLM | None
    txt_dir: Path | None
    progress: ProgressWriter | None = None     # 없으면 세부 진행을 적지 않는다 (테스트·CLI)
    checkpointer: BaseCheckpointSaver | None = None   # 없으면 같은 DB로 연결을 열어 만든다

    @property
    def processing_key(self) -> str:
        """문서 처리 결과를 다시 쓸 수 있는 조건: 사전 판 + 처리 코드 판 + AI 모델·프롬프트 판."""
        ai = f"{self.llm.model}/{tasks.PROMPT_VERSION}" if self.llm else "rule"
        # OCR 엔진 판이 바뀌면 같은 파일도 새로 분석한다 (add-ocr, CR-11)
        return f"{self.version}-{code_version()}-{ai}-{ocr.version_tag()}"


def create_run(conn: psycopg.Connection, version: str, llm: LLM | None,
               started_by: int | None = None) -> int:
    if started_by is None:
        started_by = conn.execute("SELECT min(user_id) FROM app_user WHERE user_name = %s",
                                  (DEFAULT_USER,)).fetchone()[0]
    run_id = conn.execute(
        """INSERT INTO review_run (started_by, stage, dict_version, llm_model, graph_state)
           VALUES (%s, 'PROCESSING', %s, %s, %s) RETURNING run_id""",
        (started_by, version, llm.model if llm else None,
         Jsonb({"step": "created", "code_version": code_version(),
                "prompt_version": tasks.PROMPT_VERSION})),
    ).fetchone()[0]
    conn.commit()
    return run_id


class RunCancelled(Exception):
    """사람이 처리 중인 검토를 취소했다 (add-run-control)."""


def check_cancel(conn: psycopg.Connection, run_id: int) -> None:
    """취소 요청이 있으면 멈춘다. 진행을 기록할 때마다 부른다."""
    row = conn.execute("SELECT cancel_requested_at FROM review_run WHERE run_id = %s",
                       (run_id,)).fetchone()
    if row and row[0] is not None:
        raise RunCancelled(run_id)


def cancel_message(conn: psycopg.Connection, run_id: int) -> str:
    who = conn.execute(
        """SELECT u.user_name FROM review_run r LEFT JOIN app_user u
                ON u.user_id = r.cancel_requested_by WHERE r.run_id = %s""",
        (run_id,)).fetchone()
    return josa(f"{(who and who[0]) or '사용자'}이(가) 분석을 취소했습니다.")


def _close_step(conn: psycopg.Connection, run_id: int) -> None:
    conn.execute("UPDATE run_step_time SET finished_at = now() "
                 "WHERE run_id = %s AND finished_at IS NULL", (run_id,))


def _set_step(conn: psycopg.Connection, run_id: int, step: str) -> None:
    check_cancel(conn, run_id)
    # 실행 기록(add-run-log): 앞 단계를 닫고 이 단계 시작 시각을 적는다. attempt = 다시 시도 횟수
    _close_step(conn, run_id)
    conn.execute(
        """INSERT INTO run_step_time (run_id, attempt, step)
           SELECT run_id, retry_count, %s FROM review_run WHERE run_id = %s
           ON CONFLICT (run_id, attempt, step) DO UPDATE
           SET started_at = now(), finished_at = NULL""", (step, run_id))
    # 단계가 바뀌면 세부 진행을 지우고 마지막 진행 시각을 새로 적는다
    conn.execute("UPDATE review_run SET graph_state = graph_state || %s || "
                 "jsonb_build_object('updated_at', now()) WHERE run_id = %s",
                 (Jsonb({"step": step, "detail": None}), run_id))
    conn.commit()


def _reporter(ctx: RunContext, run_id: int, file_index: int, file_count: int,
              conn: psycopg.Connection | None = None) -> Report:
    def report(part: str, done: int | None = None, total: int | None = None) -> None:
        # 문서 하나는 한 트랜잭션이라 여기서 멈추면 그 문서의 반쯤 만든 결과는 되돌려진다
        check_cancel(conn or ctx.conn, run_id)
        if ctx.progress:
            ctx.progress(run_id, {"part": part, "done": done, "total": total,
                                  "file_index": file_index, "file_count": file_count})
    return report


def _documents_node(ctx: RunContext):
    def node(state: RunState) -> RunState:
        conn, run_id = ctx.conn, state["run_id"]
        _set_step(conn, run_id, "documents")
        dicts = dictionaries.load(conn)
        paths = state["paths"]
        results = _process_all(ctx, run_id, paths, state.get("choices") or {}, dicts)
        ids = [r.document_id for r in results]
        reused = sum(r.reused for r in results)
        examples = sum(r.type_examples for r in results)
        reprocessed = sum(r.reprocessed for r in results)
        lines = sum(r.reprocessed_lines for r in results)
        conn.execute("UPDATE review_run SET documents_reused = %s, graph_state = graph_state || "
                     "jsonb_build_object('type_examples', %s::int, "
                     "'documents_reprocessed', %s::int, 'lines_reprocessed', %s::int) "
                     "WHERE run_id = %s",
                     (reused, examples, reprocessed, lines, run_id))
        projects = {r[0] for r in conn.execute(
            "SELECT DISTINCT project_id FROM document WHERE document_id = ANY(%s)", (ids,))}
        if len(projects) == 1 and None not in projects:
            conn.execute("UPDATE review_run SET project_id = %s WHERE run_id = %s",
                         (projects.pop(), run_id))
            conn.commit()
        return {"document_ids": ids}
    return node


def _save_run_document(conn: psycopg.Connection, run_id: int, document_id: int) -> None:
    conn.execute("INSERT INTO run_document VALUES (%s, %s) ON CONFLICT DO NOTHING",
                 (run_id, document_id))
    conn.commit()


class _Turns:
    """문서 저장 차례: 올린 순서대로 한 문서씩 저장한다 (문서 병렬 처리, C1).

    무거운 일(구조·추출·AI)은 동시에 하고 저장만 차례로 해서, 문서·요구사항 번호와
    같은 요구 묶기·파일 번호가 차례로 처리할 때와 같다(CR-11).
    """

    def __init__(self) -> None:
        self._next = 0
        self._cond = threading.Condition()

    @contextmanager
    def wait(self, i: int):
        with self._cond:
            self._cond.wait_for(lambda: self._next == i)
        yield

    def finish(self, i: int) -> None:
        """i번 문서가 끝났다(저장했거나, 다시 썼거나, 실패). 앞 문서가 끝난 뒤 차례를 넘긴다."""
        with self._cond:
            self._cond.wait_for(lambda: self._next >= i)
            if self._next == i:
                self._next = i + 1
            self._cond.notify_all()


def _process_all(ctx: RunContext, run_id: int, paths: list[str], choices: dict[str, dict],
                 dicts) -> list[DocumentResult]:
    """문서들을 처리한다. RFP_DOC_WORKERS가 2 이상이고 문서가 여럿이면 동시에 (C1).

    한 문서가 실패해도 나머지 문서는 저장한 뒤 올린 순서로 첫 오류를 낸다
    (다시 시도하면 저장한 문서는 다시 쓴다, NFR-05).
    """
    conn = ctx.conn
    workers = max(1, get_settings().rfp_doc_workers)

    def choice_of(path: str) -> Choice | None:
        chosen = choices.get(Path(path).name)
        return Choice(**chosen) if chosen else None

    if workers <= 1 or len(paths) <= 1:
        results = []
        for i, path in enumerate(paths, 1):
            result = process_document(conn, Path(path), dicts, ctx.processing_key, ctx.llm,
                                      ctx.txt_dir, _reporter(ctx, run_id, i, len(paths)),
                                      choice_of(path))
            _save_run_document(conn, run_id, result.document_id)
            results.append(result)
        return results

    conn.commit()
    turns = _Turns()

    def job(i: int, path: str) -> DocumentResult:
        try:
            with graph_flow.open_like(conn) as own:
                result = process_document(own, Path(path), dicts, ctx.processing_key, ctx.llm,
                                          ctx.txt_dir,
                                          _reporter(ctx, run_id, i + 1, len(paths), own),
                                          choice_of(path), lambda: turns.wait(i))
                _save_run_document(own, run_id, result.document_id)
                return result
        finally:
            turns.finish(i)

    outcomes: list[DocumentResult | BaseException] = []
    with ThreadPoolExecutor(max_workers=min(workers, len(paths)),
                            thread_name_prefix="rfp-doc") as pool:
        futures = [pool.submit(job, i, p) for i, p in enumerate(paths)]
        for fut in futures:
            try:
                outcomes.append(fut.result())
            except BaseException as exc:  # noqa: BLE001 - 나머지를 저장한 뒤 다시 올린다
                outcomes.append(exc)
    for o in outcomes:
        if isinstance(o, BaseException):
            raise o
    return outcomes  # type: ignore[return-value]


PAIR_MIN_SHARED = 50          # 데이터시트 항목이 이만큼 겹치면 같은 문서의 다른 판 후보


def _pairs_node(ctx: RunContext):
    """같은 데이터시트 항목을 많이 공유하는 문서 쌍을 후보로 낸다 (FR-01). 확정은 사람이."""
    def node(state: RunState) -> RunState:
        conn, run_id = ctx.conn, state["run_id"]
        _set_step(conn, run_id, "pairs")
        shared = conn.execute(
            """SELECT LEAST(a.document_id, b.document_id), GREATEST(a.document_id, b.document_id),
                      count(*)
               FROM requirement a JOIN requirement b ON b.dedup_of = a.requirement_id
               WHERE a.document_id = ANY(%(ids)s) AND b.document_id = ANY(%(ids)s)
                 AND a.source_kind = 'TABLE_CELL'
               GROUP BY 1, 2 HAVING count(*) >= %(min)s""",
            {"ids": state["document_ids"], "min": PAIR_MIN_SHARED}).fetchall()
        for doc_a, doc_b, count in shared:
            conn.execute(
                """INSERT INTO document_pair (document_id_a, document_id_b, relation, status,
                                             evidence)
                   VALUES (%s, %s, 'DUPLICATE_CONTENT', 'CANDIDATE', %s)
                   ON CONFLICT DO NOTHING""",
                (doc_a, doc_b, f"데이터시트 항목 {count}개 겹침"))
        conn.commit()
        return {}
    return node


def _section_titles(conn: psycopg.Connection, document_ids: list[int]) -> dict[int, list[str]]:
    """절 id → 자기 제목부터 최상위 절 제목까지."""
    rows = {sid: (parent, title) for sid, parent, title in conn.execute(
        "SELECT section_id, parent_id, title FROM section WHERE document_id = ANY(%s)",
        (document_ids,))}
    out: dict[int, list[str]] = {}
    for sid in rows:
        titles, cur = [], sid
        while cur is not None:
            parent, title = rows[cur]
            titles.append(title or "")
            cur = parent
        out[sid] = titles
    return out


def clause_candidates(conn: psycopg.Connection, document_ids: list[int],
                      dicts: dictionaries.PipelineDicts) -> list[RiskCandidate]:
    """조항 하나에 위험 표현이 여럿이면 종류별로 후보 하나에 모은다 ("deemed" + "no deviation")."""
    titles = _section_titles(conn, document_ids)
    by_key: dict[tuple, RiskCandidate] = {}
    for req_id, dedup_of, section_id, text in conn.execute(
            """SELECT requirement_id, dedup_of, section_id, text_raw FROM requirement
               WHERE document_id = ANY(%s) AND req_kind = 'REQUIREMENT'
               ORDER BY requirement_id""", (document_ids,)):
        for expr in find_clause_risks(text, titles.get(section_id, []), dicts.risk_expressions):
            target = dedup_of or req_id         # 같은 문장이 여러 문서에 있으면 대표 하나만
            kind = FLAG_KIND[expr.risk_kind]
            cand = by_key.get((kind, target))
            if cand is None:
                by_key[(kind, target)] = RiskCandidate(kind, [target], expression=expr,
                                                       facts=f"표현: {expr.expression}")
            elif expr.expression not in cand.facts:
                cand.facts += f", {expr.expression}"
    return list(by_key.values())


def value_refs(conn: psycopg.Connection, document_ids: list[int]) -> list[ValueRef]:
    rows = conn.execute(
        """SELECT v.value_id, v.requirement_id, d.document_id, p.project_key, v.item_key,
                  v.num_value, v.unit_raw, v.target_object, v.basis_standard, v.equipment_key,
                  d.file_no, min(l.line_start), v.raw_text, tr.table_id, v.value_seq,
                  tr.table_id IS NOT NULL AND EXISTS (
                      SELECT 1 FROM req_value w WHERE w.requirement_id = v.requirement_id
                      AND w.value_seq > 1) AS multi,
                  tr.item_no || '|' || lower(regexp_replace(tr.item_name_raw, '\\s+', ' ', 'g'))
                      AS row_label
           FROM req_value v
           JOIN requirement r USING (requirement_id)
           LEFT JOIN table_row tr ON tr.row_id = r.row_id
           JOIN document d ON d.document_id = r.document_id
           LEFT JOIN project p ON p.project_id = d.project_id
           JOIN requirement_location rl ON rl.requirement_id = r.requirement_id
           JOIN source_location l ON l.location_id = rl.location_id
                                 AND l.document_id = r.document_id
           WHERE r.document_id = ANY(%s) AND r.req_kind = 'REQUIREMENT'
             AND v.num_value IS NOT NULL AND v.item_key IS NOT NULL
             AND v.flag IS DISTINCT FROM 'RANGE'
           GROUP BY v.value_id, d.document_id, p.project_key, tr.table_id, tr.item_no,
                    tr.item_name_raw
           ORDER BY v.value_id""", (document_ids,))
    return [ValueRef(key=r[0], requirement_key=r[1], document_key=r[2], project_key=r[3],
                     item_key=r[4], num_value=float(r[5]), unit=r[6], target_object=r[7],
                     basis_standard=r[8], equipment_key=r[9],
                     location=f"파일 {r[10]} {r[11]}행", raw_text=r[12], table_key=r[13],
                     seq=r[14], multi=r[15], row_label=r[16])
            for r in rows]


def _save_risks(ctx: RunContext, run_id: int, candidates: list[RiskCandidate],
                known: dict[tuple, tuple[int, str | None, str | None]] | None = None) -> int:
    """위험 조건 후보를 저장한다. known(열쇠 → 이전 risk_id·설명)에 같은 후보가 있으면
    AI에 다시 묻지 않고 이전 설명과 근거 문장을 이어 쓴다 (문서 추가·다시 시도)."""
    conn = ctx.conn
    known = dict(known or {})
    # (가) 이어 쓸 설명을 찾고, AI에 물을 후보는 근거 조각을 DB에서 먼저 읽는다
    plans: list[tuple[RiskCandidate, int | None, tuple | None, list[EvidenceSpan]]] = []
    for cand in candidates:
        reused, spans = None, []
        expr_id = cand.expression.expr_id if cand.expression else None
        hit = known.pop((cand.risk_kind, expr_id, cand.item_key, tuple(sorted(set(cand.members)))),
                        None)
        if hit and (hit[1] is not None or ctx.llm is None):
            reused = hit
        elif ctx.llm is not None:
            # 근거 조각: 후보 요구사항의 원문 위치마다 ID(E-문서-위치)를 붙여 AI에 준다
            spans = [EvidenceSpan(evidence_id(doc_id, loc_id), text)
                     for doc_id, loc_id, text in conn.execute(
                         """SELECT DISTINCT q.document_id, rl.location_id, q.text_raw
                            FROM requirement q
                            JOIN requirement_location rl USING (requirement_id)
                            WHERE q.requirement_id = ANY(%s)
                            ORDER BY q.document_id, rl.location_id""", (cand.members,))]
        plans.append((cand, expr_id, reused, spans))
    # (나) AI 설명은 동시에 받는다 (NFR-10). 결과는 후보 순서대로
    llm = ctx.llm
    asks = [i for i, p in enumerate(plans) if p[3]]
    answers = run_ordered([lambda p=plans[i]: _explain_and_verify(llm, p[0], p[3])
                           for i in asks], workers_of(llm)) if asks else []
    explanations = dict(zip(asks, answers, strict=True))
    # (다) 원래 순서대로 저장한다 (risk_id 순서가 차례로 할 때와 같음)
    for n, (cand, expr_id, reused, _) in enumerate(plans):
        answer = explanations.get(n)
        # 근거 대조에서 버린 설명은 이유만 남긴다 (update-ai-answer-checks)
        explained = answer if isinstance(answer, tasks.RiskExplanation) else None
        dropped = answer.reason if isinstance(answer, tasks.DroppedExplanation) else None
        risk_id = conn.execute(
            """INSERT INTO risk_flag (run_id, risk_kind, expr_id, explanation_ai, status, facts,
                                      item_key, explanation_drop_reason, explanation_check)
               VALUES (%s, %s, %s, %s, 'CANDIDATE', %s, %s, %s, %s) RETURNING risk_id""",
            (run_id, cand.risk_kind, expr_id,
             reused[1] if reused else explained.text if explained else None, cand.facts,
             cand.item_key, dropped,
             reused[2] if reused else explained.check if explained else None),
        ).fetchone()[0]
        if reused:
            conn.execute("UPDATE claim_evidence SET target_id = %s WHERE run_id = %s "
                         "AND target_table = 'risk_flag' AND target_id = %s",
                         (risk_id, run_id, reused[0]))
        values = cand.value_members or [None] * len(cand.members)
        for req_id, value_id in zip(cand.members, values, strict=True):
            conn.execute("INSERT INTO risk_flag_member VALUES (%s, %s, %s) "
                         "ON CONFLICT DO NOTHING", (risk_id, req_id, value_id))
        if explained:
            _save_claims(conn, run_id, "risk_flag", risk_id, "RISK_EXPLANATION", explained.claims,
                         explained.verdicts)
    return len(candidates)


def _explain_and_verify(llm: LLM, cand: RiskCandidate, spans: list[EvidenceSpan]):
    """설명을 받고, 코드 대조를 통과하면 검증 에이전트에 한 번 더 묻는다 (add-claim-verifier)."""
    out = tasks.explain_risk(llm, cand.risk_kind, cand.facts, spans)
    if isinstance(out, tasks.RiskExplanation):
        sources = {s.evidence_id: s.text[:800] for s in spans}
        out = replace(out, verdicts=tuple(tasks.check_support(llm, out.claims,
                                                                          sources)))
    return out


def _save_claims(conn: psycopg.Connection, run_id: int, table: str, target_id: int,
                 claim_type: str, claims, verdicts: tuple[str, ...] = ()) -> None:
    """AI 설명 문장마다 인용과 근거 위치를 남긴다. 코드가 인용을 확인한 문장만 온다.

    검증 에이전트가 YES가 아니라고 한 문장은 NEEDS_REVIEW (add-claim-verifier).
    """
    for n, claim in enumerate(claims):
        status = "SUPPORTED" if not verdicts or verdicts[n] == "YES" else "NEEDS_REVIEW"
        claim_id = conn.execute(
            """INSERT INTO claim_evidence (run_id, target_table, target_id, claim_type,
                                           claim_text, exact_quote, relation, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING claim_id""",
            (run_id, table, target_id, claim_type, claim.text, claim.quote, claim.relation,
             status),
        ).fetchone()[0]
        locations = dict.fromkeys(parsed[1] for i in claim.evidence_ids
                                  if (parsed := parse_evidence_id(i)))
        for seq, location_id in enumerate(locations, start=1):
            conn.execute("INSERT INTO claim_evidence_source (claim_id, location_id, source_seq) "
                         "VALUES (%s, %s, %s)", (claim_id, location_id, seq))


def _risks_node(ctx: RunContext):
    def node(state: RunState) -> RunState:
        conn, run_id = ctx.conn, state["run_id"]
        _set_step(conn, run_id, "risks")
        dicts = dictionaries.load(conn)
        readable = readable_documents(conn, state["document_ids"])
        candidates = clause_candidates(conn, readable, dicts)
        candidates += find_value_mismatches(value_refs(conn, readable), dicts.values.parents)
        with conn.transaction():
            # 다시 돌리면(문서 추가·다시 시도) 새로 만든 뒤 이전 위험 조건과 바꾼다. 같은 열쇠의
            # 사람 확인 상태와 목록 항목 연결을 이어받는다 (FR-10 ⑤)
            old = doc_add.risk_snapshot(conn, run_id)
            count = _save_risks(ctx, run_id, candidates, doc_add.risk_explanations(conn, old))
            if old:
                conn.execute("DELETE FROM claim_evidence WHERE run_id = %s AND target_table = "
                             "'risk_flag' AND target_id = ANY(%s)", (run_id, list(old)))
            doc_add.replace_risks(conn, run_id, old)
        return {"risk_count": count, "readable_ids": readable}
    return node


def readable_documents(conn: psycopg.Connection, document_ids: list[int]) -> list[int]:
    return [r[0] for r in conn.execute(
        "SELECT document_id FROM document WHERE document_id = ANY(%s) AND readable ORDER BY 1",
        (document_ids,))]


def rebuild_outputs(ctx: RunContext, run_id: int, document_ids: list[int]) -> dict[str, int]:
    """판정 뒤 단계(보증값·손실·목록·제안)를 다시 만든다.

    제품을 바꾸거나 손실값을 고친 뒤에도 쓴다.
    """
    state: RunState = {"run_id": run_id, "readable_ids": document_ids}
    counts = {}
    for _, key, build in STEPS:
        counts[key] = build(ctx, state)
        ctx.conn.commit()
    return counts


def _judge_node(ctx: RunContext):
    def node(state: RunState) -> RunState:
        conn, run_id = ctx.conn, state["run_id"]
        _set_step(conn, run_id, "judge")
        old = doc_add.current_judgments(conn, run_id)
        count = judge_run(conn, run_id, state["readable_ids"])
        # 같은 줄(요구값·비교 제품·비교 규칙)의 확정·수정·반려를 이어받는다 (FR-10 ⑤)
        doc_add.carry_judgments(conn, run_id, old)
        # 문서 추가로 다시 판정했으면 바뀜·추가·사라짐을 남긴다 (add-revision-notice)
        doc_add.record_revision(conn, run_id, old)
        conn.commit()
        return {"judgment_count": count}
    return node


def _meaning_node(ctx: RunContext):
    """뜻 찾기 벡터와 후보 (add-meaning-search). 실패해도 분석은 계속한다."""
    def node(state: RunState) -> RunState:
        conn, run_id = ctx.conn, state["run_id"]
        _set_step(conn, run_id, "meaning")
        count = meaning.build(conn, run_id, state["readable_ids"], ctx.llm)
        conn.commit()
        return {"meaning_count": count}
    return node


def _step_node(ctx: RunContext, step: str, key: str, build):
    def node(state: RunState) -> RunState:
        _set_step(ctx.conn, state["run_id"], step)
        count = build(ctx, state)
        ctx.conn.commit()
        return {key: count}
    return node


STEPS = [
    ("check", "check_count",
     lambda ctx, s: build_checks(ctx.conn, s["run_id"], s["readable_ids"])),
    ("warranty", "warranty_count", lambda ctx, s: build_warranty(ctx.conn, s["run_id"])),
    ("loss", "loss_count", lambda ctx, s: build_losses(ctx.conn, s["run_id"])),
    ("outputs", "output_count",
     lambda ctx, s: build_outputs(ctx.conn, s["run_id"], s["readable_ids"], ctx.llm)),
    ("proposals", "proposal_count",
     lambda ctx, s: build_proposals(ctx.conn, s["run_id"], ctx.llm)),
    ("assign", "assignment_count", lambda ctx, s: build_assignments(ctx.conn, s["run_id"])),
]
COUNTS = ["risk_count", "judgment_count"] + [key for _, key, _ in STEPS]


# 사람 단계 노드(멈춤 자리) → 단계 칸 (update-graph-stops, C2)
STOPS = {"engineer_review": "ENGINEER_REVIEW", "approval": "APPROVAL", "rejected": "REJECTED"}
# 멈춤 자리마다 사람 동작 → 다음 노드. 갈 곳은 이 표로 코드가 고른다 (CR-01)
# rewind(단계부터 다시 처리, add-step-rewind)는 받은 단계(rewind_to)로 간다
NEXT = {
    "engineer_review": {"submit": "approval", "add_documents": "documents", "rewind": None},
    "approval": {"approve": END, "reject": "rejected", "withdraw": "engineer_review"},
    "rejected": {"reopen": "engineer_review"},
}
PIPELINE = ["documents", "pairs", "risks", "judge", "meaning"] + [s for s, _, _ in STEPS]


def _stop_node(name: str):
    """흐름을 멈추고 사람 동작을 기다린다. 이어 갈 때 받은 동작을 상태에 남긴다."""
    def node(state: RunState) -> RunState:
        got = interrupt({"stop": STOPS[name]})
        action = got["action"]
        if action not in NEXT[name]:
            raise ValueError(f"{name}에서 받을 수 없는 동작: {action}")
        out: RunState = {"action": action}
        if action == "add_documents":       # 처음 파일 + 더한 파일로 문서 처리부터 다시
            out |= {"paths": got["paths"], "choices": got["choices"]}
        if action == "rewind":              # 고른 처리 단계부터 다시 (사람 확정은 이어받음)
            if got["step"] not in PIPELINE:
                raise ValueError(f"처리 단계가 아닙니다: {got['step']}")
            out |= {"rewind_to": got["step"]}
        return out
    return node


def _router(name: str):
    def route(state: RunState) -> str:
        action = state["action"]
        return state["rewind_to"] if action == "rewind" else NEXT[name][action]
    return route


def build_graph(ctx: RunContext, checkpointer: BaseCheckpointSaver | None = None):
    """처리 단계를 일직선으로 잇고, 저장소가 있으면 끝에 사람 단계 세 곳을 더한다."""
    graph = StateGraph(RunState)
    graph.add_node("documents", _documents_node(ctx))
    graph.add_node("pairs", _pairs_node(ctx))
    graph.add_node("risks", _risks_node(ctx))
    graph.add_node("judge", _judge_node(ctx))
    graph.add_node("meaning", _meaning_node(ctx))
    for step, key, build in STEPS:
        graph.add_node(step, _step_node(ctx, step, key, build))
    graph.add_edge(START, PIPELINE[0])
    for a, b in zip(PIPELINE, PIPELINE[1:], strict=False):
        graph.add_edge(a, b)
    if checkpointer is None:
        graph.add_edge(PIPELINE[-1], END)
        return graph.compile()
    for name in STOPS:
        graph.add_node(name, _stop_node(name))
        goes = {g for g in NEXT[name].values() if g is not None}
        if "rewind" in NEXT[name]:
            goes |= set(PIPELINE)
        graph.add_conditional_edges(name, _router(name), sorted(goes, key=str))
    graph.add_edge(PIPELINE[-1], "engineer_review")
    return graph.compile(checkpointer=checkpointer)


def execute_run(ctx: RunContext, run_id: int, paths: list[Path],
                choices: dict[str, dict] | None = None, rewind: str | None = None) -> str:
    """실행을 끝까지 돌리고 마지막 단계를 돌려준다 (ENGINEER_REVIEW 또는 FAILED).

    rewind는 담당자 확인에서 멈춘 흐름을 그 처리 단계부터 다시 돌릴 때 (add-step-rewind).
    """
    conn = ctx.conn
    # 다시 시도(add-run-control)할 때 같은 파일·분류로 돌리려고 입력을 남긴다
    conn.execute("UPDATE review_run SET graph_state = graph_state || %s WHERE run_id = %s",
                 (Jsonb({"inputs": {"paths": [str(p) for p in paths],
                                    "choices": choices or {}}}), run_id))
    conn.commit()
    usage = usage_of(ctx.llm)
    before = usage.copy() if usage else None
    inputs = {"run_id": run_id, "paths": [str(p) for p in paths], "choices": choices or {},
              "rewind": rewind}
    try:
        with graph_flow.saver_for(ctx) as saver:
            graph = build_graph(ctx, saver)
            config = graph_flow.config(run_id)
            start, resumed = graph_flow.start_input(graph, run_id, inputs)
            conn.execute(
                "UPDATE review_run SET graph_state = graph_state || %s WHERE run_id = %s",
                (Jsonb({"resumed_from": resumed,
                        "skipped_steps": PIPELINE.index(resumed) if resumed else 0}), run_id))
            conn.commit()
            state = graph.invoke(start, config)
    except Exception as exc:
        conn.rollback()
        step = conn.execute("SELECT graph_state->>'step' FROM review_run WHERE run_id = %s",
                            (run_id,)).fetchone()[0]
        if isinstance(exc, RunCancelled):
            message = cancel_message(conn, run_id)
            log.info("검토 실행 %s 취소 (%s)", run_id, step)
        else:
            message = (str(exc) if isinstance(exc, LLMConfigError)   # 키·모델 설정 오류
                       else FAILURE_MESSAGE if isinstance(exc, LLMFailure)
                       else f"{FAILURE_MESSAGE}: {exc}")
            log.exception("검토 실행 %s 실패 (%s)", run_id, step)
        conn.execute(
            """UPDATE review_run SET stage = 'FAILED', failed_step = %s, error_message = %s,
                      finished_at = now() WHERE run_id = %s""", (step, message, run_id))
        _finish_log(conn, run_id, usage, before)
        conn.commit()
        return "FAILED"
    conn.execute(
        """UPDATE review_run SET stage = 'ENGINEER_REVIEW', finished_at = now(),
                  graph_state = graph_state || %s || jsonb_build_object('updated_at', now())
            WHERE run_id = %s""",
        (Jsonb({"step": "done", "detail": None, **{k: state.get(k, 0) for k in COUNTS}}),
         run_id))
    _finish_log(conn, run_id, usage, before)
    conn.commit()
    return "ENGINEER_REVIEW"


def _finish_log(conn: psycopg.Connection, run_id: int, usage: Usage | None,
                before: Usage | None) -> None:
    """실행 기록: 열린 단계를 닫고 이번 처리의 AI 사용량을 더한다 (다시 시도하면 쌓인다)."""
    _close_step(conn, run_id)
    if usage is None or before is None:
        return
    d = usage.minus(before)
    conn.execute(
        """UPDATE review_run SET llm_calls = llm_calls + %s, llm_retries = llm_retries + %s,
                  llm_input_tokens = llm_input_tokens + %s,
                  llm_output_tokens = llm_output_tokens + %s,
                  llm_thinking_tokens = llm_thinking_tokens + %s
            WHERE run_id = %s""",
        (d.calls, d.retries, d.input_tokens, d.output_tokens, d.thinking_tokens, run_id))


def switch_product(ctx: RunContext, run_id: int, group: str, product_code: str | None,
                   chosen_by: int | None = None) -> dict[str, int]:
    """엔지니어가 설비 묶음의 비교 제품을 바꾼다 (None이면 자동 선택으로 되돌린다).

    그 묶음만 다시 판정하고(이전 판정은 is_current = false로 남긴다) 뒤 단계를 다시 만든다.
    """
    conn = ctx.conn
    if product_code is not None and conn.execute(
            "SELECT 1 FROM product_master WHERE product_code = %s",
            (product_code,)).fetchone() is None:
        raise KeyError(product_code)
    with conn.transaction():
        if product_code is None:
            conn.execute("DELETE FROM run_product_choice WHERE run_id = %s "
                         "AND equipment_group = %s", (run_id, group))
        else:
            conn.execute(
                """INSERT INTO run_product_choice (run_id, equipment_group, product_code,
                                                   chosen_by)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (run_id, equipment_group) DO UPDATE
                   SET product_code = EXCLUDED.product_code, chosen_by = EXCLUDED.chosen_by,
                       chosen_at = now()""", (run_id, group, product_code, chosen_by))
    ids = readable_documents(conn, [r[0] for r in conn.execute(
        "SELECT document_id FROM run_document WHERE run_id = %s", (run_id,))])
    counts = {"judgment_count": judge_run(conn, run_id, ids, only_groups={group})}
    conn.commit()
    return counts | rebuild_outputs(ctx, run_id, ids)
