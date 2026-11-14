"""문서 하나를 ①~⑤(분류 → 구조 → 추출 → 유형 → 값)까지 처리해 DB에 저장한다.

같은 파일·같은 사전 판으로 이미 처리했으면 다시 하지 않고 저장된 결과를 쓴다 (NFR-05).
"""

import hashlib
import re
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from rfp_agent.llm import tasks
from rfp_agent.llm.client import LLM
from rfp_agent.pipeline import classify as cls
from rfp_agent.pipeline import pdf_reader, type_examples
from rfp_agent.pipeline.dictionaries import PipelineDicts
from rfp_agent.pipeline.docx_reader import find_figures
from rfp_agent.pipeline.extract import Candidate, extract
from rfp_agent.pipeline.line_map import map_lines
from rfp_agent.pipeline.processors import LABEL, TYPE, Processor, Stats, processor_for
from rfp_agent.pipeline.reader import is_pdf, read_document
from rfp_agent.pipeline.structure import (
    MARK_LEGEND,
    LogicalTable,
    Section,
    SectionIndex,
    build_tables,
    find_sections,
)
from rfp_agent.pipeline.type_tags import TypeRule, tag
from rfp_agent.pipeline.values import normalize_candidate, target_of

# 세부 진행 알림: (세부 일, 끝난 줄 수, 전체 줄 수)
# 세부 일은 classify·structure·extract·label·save·type
Report = Callable[[str, int | None, int | None], None]


def _no_report(part: str, done: int | None = None, total: int | None = None) -> None:
    pass


@dataclass
class DocumentResult:
    document_id: int
    file_no: int
    reused: bool
    readable: bool
    requirement_count: int = 0
    type_examples: int = 0          # 사람 예시를 붙여 물은 줄 수 (add-type-examples)
    reprocessed: bool = False       # 점검 뒤 일반 처리기로 다시 물음 (add-document-processors)
    reprocessed_lines: int = 0      # 다시 물은 줄 수 (update-partial-reprocess)




def _next_file_no(conn: psycopg.Connection) -> int:
    # 파일 목록(1~22)에 없는 문서는 101번부터 붙인다.
    last = conn.execute("SELECT COALESCE(max(file_no), 0) FROM document").fetchone()[0]
    return max(100, last) + 1


def content_hash(path: Path) -> str:
    """원본 파일 내용의 SHA-256. 이름·번호가 같아도 내용이 다르면 다른 문서로 처리한다."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _insert_document(conn, path: Path, c: cls.Classification, dicts: PipelineDicts,
                     line_basis: str, key: str, digest: str,
                     blocks: list | None = None) -> tuple[int, int]:
    """이 처리 판(key)으로 처리한 문서 행을 새로 만든다.

    번호는 파일 목록 → 같은 파일의 이전 번호 → 101번부터.
    """
    previous = conn.execute("SELECT max(file_no) FROM document WHERE source_path = %s",
                            (str(path),)).fetchone()[0]
    file_no = c.file_no or previous or _next_file_no(conn)
    values = dict(
        file_no=file_no, file_name=path.name, bundle=c.bundle, doc_kind=c.doc_kind,
        project_id=dicts.projects.get(c.project_key) if c.project_key else None,
        language=c.language, standard_system=c.standard_system, judge_target=c.judge_target,
        readable=c.readable, classify_by=c.classify_by, needs_review=c.needs_review,
        source_path=str(path), line_basis=line_basis, processing_key=key,
        content_hash=digest,
        # PDF 쪽마다 첫 줄 (add-pdf-page-location)
        page_starts=pdf_reader.page_starts(blocks) if line_basis == "PDF" and blocks else None,
    )
    cols = ", ".join(values)
    marks = ", ".join(f"%({k})s" for k in values)
    doc_id = conn.execute(f"INSERT INTO document ({cols}) VALUES ({marks}) RETURNING document_id",
                          values).fetchone()[0]
    return doc_id, file_no


def _save_sections(conn, document_id: int, sections: list[Section]) -> dict[int, int]:
    ids: dict[int, int] = {}
    for s in sections:
        ids[s.index] = conn.execute(
            """INSERT INTO section (document_id, parent_id, section_no, title, is_toc,
                                    line_start, line_end, structure_flag)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING section_id""",
            (document_id, ids.get(s.parent) if s.parent is not None else None, s.number, s.title,
             s.is_toc, s.line_start, s.line_end, s.structure_flag),
        ).fetchone()[0]
    return ids


def _save_tables(conn, document_id: int, tables: list[LogicalTable], section_ids,
                 sections_index) -> dict[int, int]:
    """표와 행을 저장하고 블록 seq → row_id를 돌려준다."""
    row_ids: dict[int, int] = {}
    for t in tables:
        sec = sections_index.at(t.first_block_seq)
        table_id = conn.execute(
            """INSERT INTO doc_table (document_id, section_id, table_name, source_table_nos,
                                      column_roles, role_flag)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING table_id""",
            (document_id, section_ids.get(sec.index) if sec else None, t.name,
             t.source_table_nos, Jsonb({str(k): v for k, v in t.column_roles.items()}),
             t.role_flag),
        ).fetchone()[0]
        for order, r in enumerate(t.rows):
            parent = row_ids.get(t.rows[r.parent_index].block.seq) if r.parent_index is not None \
                else None
            row_ids[r.block.seq] = conn.execute(
                """INSERT INTO table_row (table_id, parent_row_id, item_no, item_name_raw,
                     unit_raw, required_raw, warranted_raw, supplier_mark, line_no, row_order,
                     source_table_no, cells)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING row_id""",
                (table_id, parent, r.item_no, r.item_name, (r.unit or "")[:40] or None,
                 r.required, r.warranted, r.supplier_mark, r.block.line_no, order,
                 r.block.table_no, Jsonb(r.block.cells)),
            ).fetchone()[0]
    return row_ids


# 협조 요청 유형: 담당(requirement_type.default_role)이 견적·품질·영업인 유형 (0002 기준표)
HANDOFF_TYPES = frozenset({"COST", "TEST", "MAKER_QUAL"})


def _handoff_rules(dicts: PipelineDicts) -> list[TypeRule]:
    return [r for r in dicts.type_rules if r.type_code in HANDOFF_TYPES]


def _refine_with_ai(llm: LLM, candidates: list[Candidate], report: Report,
                    risk_patterns: list[re.Pattern], handoff_rules: list[TypeRule],
                    doc_hint: str | None = None,
                    only: set[int] | None = None) -> list[list[int]]:
    """AI에 물은 절마다 후보 번호 묶음을 돌려준다. only가 있으면 그 후보만 묻는다."""
    by_section: dict[int | None, list[int]] = {}
    for i, c in enumerate(candidates):
        if only is not None and i not in only:
            continue
        # 위험 표현이 든 문장과 협조 요청 유형 규칙에 걸리는 문장은 언어 모델에 묻지 않고
        # 요구사항으로 둔다. 작성 규칙·설명으로 바뀌면 위험 조건 찾기·부서 협조 요청에서
        # 빠지기 때문이다 (CR-01, FR-06·FR-11, update-ai-label-keep-handoff).
        if any(p.search(c.text) for p in risk_patterns) \
                or any(r.matches(c.text) for r in handoff_rules):
            continue
        if c.source_kind == "SENTENCE" and c.req_kind == "REQUIREMENT":
            by_section.setdefault(c.section.index if c.section else None, []).append(i)
    total = sum(len(g) for g in by_section.values())
    report("label", 0, total)
    groups = list(by_section.values())
    # 절마다 40줄씩 묻되 모든 절의 묶음을 함께 동시에 보낸다. 진행은 문서 전체 문장 수로 센다
    answers = tasks.label_sections(
        llm, [(candidates[g[0]].section.title if candidates[g[0]].section else None,
               [candidates[i].text for i in g]) for g in groups],
        lambda done, _: report("label", done, total), doc_hint)
    for group, labels in zip(groups, answers, strict=True):
        for i, label in zip(group, labels, strict=True):
            c = candidates[i]
            if label == "WRITING_RULE":
                c.req_kind, c.rule_id, c.extracted_by = "WRITING_RULE", "E-AI-WRITING-RULE", "AI"
            elif label == "DESCRIPTION":
                c.req_kind, c.rule_id, c.extracted_by = "DESCRIPTION", "E-AI-DESCRIPTION", "AI"
    return groups


@dataclass
class Choice:
    """등록 화면에서 사람이 정한 문서 분류 (없는 칸은 규칙 결과를 쓴다)."""
    bundle: str | None = None
    doc_kind: str | None = None


def process_document(conn: psycopg.Connection, path: Path, dicts: PipelineDicts, key: str,
                     llm: LLM | None, txt_dir: Path | None,
                     report: Report = _no_report, choice: Choice | None = None,
                     ordered: Callable[[], AbstractContextManager] = nullcontext,
                     dedup: bool = True) -> DocumentResult:
    """ordered는 저장 차례를 기다리는 문맥(문서 병렬 처리, C1). 차례로 할 때는 바로 들어간다."""
    report("classify")
    blocks = read_document(path)              # docx 또는 PDF (add-pdf-input)
    line_basis = "PDF" if is_pdf(path) else "DOCX"
    txt = txt_dir / f"{path.stem}.txt" if txt_dir and not is_pdf(path) else None
    if txt and txt.exists():
        blocks, ratio = map_lines(blocks, txt)
        line_basis = "TXT" if ratio == 1.0 else "DOCX"

    c = cls.classify(path.name, blocks, dicts.catalog, dicts.kind_rules)
    if choice:
        c = cls.apply_choice(c, choice.bundle, choice.doc_kind)
        if c.classify_by == "HUMAN":
            # 규칙과 다른 분류는 다른 처리 판으로 둔다. 같은 파일의 다른 검토 결과를 바꾸지 않는다.
            key = f"{key}|H:{c.bundle}:{c.doc_kind}"
    # 저장된 결과는 같은 처리 판 + 같은 파일 내용일 때만 다시 쓴다.
    # (이름이 같은 다른 판 파일이 예전 분석 결과를 받지 않게)
    digest = content_hash(path)
    existing = _find_existing(conn, c, path, key, digest)
    if existing:
        return _reused(conn, existing, c)

    if llm is not None and c.readable and c.classify_by != "HUMAN":
        c = cls.apply_ai_kind(c, tasks.classify_document(llm, path.name,
                                                         cls.first_page_text(blocks)))

    prep, proc, check, lines = None, None, None, 0
    if c.readable:
        proc = processor_for(c.doc_kind)
        prep = _prepare(conn, path, dicts, llm, report, blocks, digest, proc)
        # 처리 뒤 점검 (처리기 표). 걸리면 걸린 이유를 남기고, AI가 있고 AI 답이 점검 결과를
        # 바꿀 수 있으면 틀린 종류 설명이 AI를 잘못 이끌었을 수 있어 떨어진 부분만 일반 처리기
        # (설명 없음)로 한 번 다시 묻는다 (CR-01: 코드가 정함, CR-12: 한 번만)
        check = proc.check(prep.stats) if proc.check else None
        if check and llm is not None and proc.fix:
            lines = _redo(conn, dicts, llm, report, digest, prep, proc.fix)
    # 준비 중 저장한 문장 벡터(캐시)를 먼저 커밋한다. 동시에 처리하는 다른 문서가 같은 글을
    # 넣으려다 이 연결을 기다리며 막히지 않게
    if conn.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS:
        conn.commit()
    try:
        with ordered():
            return _save(conn, path, dicts, key, report, c, blocks, line_basis, digest, dedup,
                         prep, proc, check, lines)
    except psycopg.errors.UniqueViolation:
        # 같은 파일을 거의 동시에 두 검토가 올리면 먼저 넣은 쪽이 이긴다.
        # 진 쪽은 자기 작업을 되돌리고 먼저 처리된 결과를 다시 쓴다
        # (같은 처리 판 + 같은 내용이므로 결과가 같다, CR-11).
        existing = _find_existing(conn, c, path, key, digest)
        if existing is None:
            raise
        return _reused(conn, existing, c)


def _find_existing(conn: psycopg.Connection, c: cls.Classification, path: Path, key: str,
                   digest: str) -> tuple[int, int] | None:
    """같은 처리 판 + 같은 파일 내용으로 이미 처리한 문서."""
    if c.file_no is not None:
        return conn.execute(
            "SELECT document_id, file_no FROM document WHERE file_no = %s "
            "AND processing_key = %s AND content_hash = %s", (c.file_no, key, digest)).fetchone()
    # 파일 목록에 없는 문서는 파일 경로로 찾는다.
    return conn.execute(
        "SELECT document_id, file_no FROM document WHERE source_path = %s "
        "AND processing_key = %s AND content_hash = %s", (str(path), key, digest)).fetchone()


def _reused(conn: psycopg.Connection, existing: tuple[int, int],
            c: cls.Classification) -> DocumentResult:
    count = conn.execute("SELECT count(*) FROM requirement WHERE document_id = %s",
                         (existing[0],)).fetchone()[0]
    return DocumentResult(existing[0], existing[1], True, c.readable, count)


@dataclass
class _Prepared:
    """DB에 쓰기 전에 끝내는 일(구조·추출·AI 문장 구분·유형)의 결과 (C1).

    문서를 동시에 처리할 때 이 일은 동시에 하고, 저장(_save)만 올린 순서대로 한다.
    그래야 문서·요구사항 번호와 같은 요구 묶기가 차례로 할 때와 같다(CR-11).
    """
    sections: list[Section]
    tables: list[LogicalTable]
    candidates: list[Candidate]
    tags: dict[int, list]                       # 후보 번호 → 규칙 유형 표시
    ai_types: dict[int, str]                    # 후보 번호 → AI 유형 (NONE 포함)
    with_examples: int
    stats: Stats
    asked: list[list[int]]                      # AI 문장 구분에 물은 절마다 후보 번호
    rules: dict[int, tuple[str, str]]           # 후보 번호 → AI 문장 구분 전 (rule_id, 추출 방법)


def _prepare(conn, path: Path, dicts: PipelineDicts, llm: LLM | None, report: Report,
             blocks, digest: str, proc: Processor) -> _Prepared:
    report("structure")
    sections = find_sections(blocks)
    tables = build_tables(blocks, dicts.column_roles,
                          supplier_marks=bool(MARK_LEGEND.search("\n".join(
                              b.text for b in blocks[:400]))))

    report("extract")
    risk_terms = [e.pattern for e in dicts.risk_expressions]
    candidates = extract(blocks, sections, tables, proc.rules, risk_terms)
    rules = {i: (c.rule_id, c.extracted_by) for i, c in enumerate(candidates)}
    asked = _refine_with_ai(llm, candidates, report, risk_terms, _handoff_rules(dicts),
                            proc.hint) if llm is not None else []

    tags, unclassified = _tag(dicts, candidates)
    ai_types: dict[int, str] = {}
    with_examples = 0
    if llm is not None and unclassified:
        ai_types, with_examples = _ask_types(conn, llm, report, digest, candidates,
                                             unclassified, proc.hint)
    return _Prepared(sections, tables, candidates, tags, ai_types, with_examples,
                     _stats(candidates, tags, ai_types, tables), asked, rules)


def _tag(dicts: PipelineDicts, candidates: list[Candidate]) -> tuple[dict[int, list], list[int]]:
    """요구사항 줄마다 규칙 유형 표시(코드)와, 규칙에 안 걸린 줄 번호."""
    risk_terms = [e.pattern for e in dicts.risk_expressions]
    tags: dict[int, list] = {}
    unclassified: list[int] = []
    for i, cand in enumerate(candidates):
        if cand.req_kind != "REQUIREMENT":
            continue
        tags[i] = tag(cand, dicts.type_rules, risk_terms)
        if not tags[i]:
            unclassified.append(i)
    return tags, unclassified


def _ask_types(conn, llm: LLM, report: Report, digest: str, candidates: list[Candidate],
               lines: list[int], hint: str | None) -> tuple[dict[int, str], int]:
    """AI에 유형을 묻는다. (후보 번호 → 유형, 사람 예시를 붙인 줄 수)"""
    report("type", 0, len(lines))
    texts = [candidates[i].text for i in lines]
    examples = type_examples.pick(conn, llm, digest, texts)
    codes = tasks.type_unclassified(llm, texts,
                                    lambda done, total: report("type", done, total),
                                    [type_context(candidates[i]) for i in lines],
                                    examples, hint)
    return dict(zip(lines, codes, strict=True)), sum(1 for e in examples if e)


def _stats(candidates: list[Candidate], tags: dict[int, list], ai_types: dict[int, str],
           tables: list[LogicalTable]) -> Stats:
    kept = [c for c in candidates if c.req_kind != "DESCRIPTION"]
    return Stats(
        table_cells=sum(1 for c in kept if c.source_kind == "TABLE_CELL"),
        requirements=sum(1 for c in kept if c.req_kind == "REQUIREMENT"),
        tests=sum(1 for i in tags if any(t.type_code == "TEST" for t in tags[i])
                  or ai_types.get(i) == "TEST"),
        marks=sum(1 for c in kept if c.supplier_mark is not None),
        table_rows=sum(len(t.rows) for t in tables))


def _redo(conn, dicts: PipelineDicts, llm: LLM, report: Report, digest: str, prep: _Prepared,
          fix: str) -> int:
    """점검에서 떨어진 부분만 일반 처리기(설명 없음)로 한 번 다시 묻고 prep을 고친다.

    나머지 절·줄은 첫 답을 그대로 쓴다. 다시 물은 줄 수를 돌려준다 (update-partial-reprocess).
    """
    candidates = prep.candidates
    if fix == LABEL:
        # 요구 문장을 하나도 남기지 않은 절만 AI 문장 구분 전으로 되돌려 다시 묻는다
        dropped = {i for g in prep.asked
                   if all(candidates[i].req_kind != "REQUIREMENT" for i in g) for i in g}
        if not dropped:
            return 0
        for i in dropped:
            candidates[i].req_kind = "REQUIREMENT"
            candidates[i].rule_id, candidates[i].extracted_by = prep.rules[i]
        risk_terms = [e.pattern for e in dicts.risk_expressions]
        _refine_with_ai(llm, candidates, report, risk_terms, _handoff_rules(dicts), None, dropped)
        # 규칙 유형은 다시 붙이고(코드), 새로 요구사항이 된 줄만 유형을 처음 묻는다
        prep.tags, unclassified = _tag(dicts, candidates)
        new = [i for i in unclassified if i not in prep.ai_types]
        if new:
            types, examples = _ask_types(conn, llm, report, digest, candidates, new, None)
            prep.ai_types.update(types)
            prep.with_examples += examples
        lines = len(dropped)
    elif fix == TYPE:
        unknown = [i for i, code in prep.ai_types.items() if code == "NONE"]
        if not unknown:
            return 0
        types, examples = _ask_types(conn, llm, report, digest, candidates, unknown, None)
        prep.ai_types.update(types)
        prep.with_examples += examples
        lines = len(unknown)
    else:
        return 0
    prep.stats = _stats(candidates, prep.tags, prep.ai_types, prep.tables)
    return lines


def _save(conn, path: Path, dicts: PipelineDicts, key: str, report: Report,
          c: cls.Classification, blocks, line_basis: str, digest: str, dedup: bool,
          prep: _Prepared | None, proc: Processor | None, check: str | None,
          lines: int) -> DocumentResult:
    """준비한 결과를 한 트랜잭션으로 저장한다. prep이 없으면 판독 불가 문서."""
    with conn.transaction():
        doc_id, file_no = _insert_document(conn, path, c, dicts, line_basis, key, digest, blocks)
        if prep is None:
            # 판독 불가 문서는 이후 단계를 건너뛴다 (FR-01 예외).
            return DocumentResult(doc_id, file_no, False, False)

        report("save")
        sections, tables, candidates = prep.sections, prep.tables, prep.candidates
        index = SectionIndex(sections)
        section_ids = _save_sections(conn, doc_id, sections)
        row_ids = _save_tables(conn, doc_id, tables, section_ids, index)
        for block, caption in find_figures(blocks):
            # 그림 위치만 남긴다. 그림 속 글자는 읽지 않는다 (OCR 범위 밖)
            sec = index.at(block.seq)
            conn.execute("INSERT INTO doc_figure (document_id, section_id, line_no, caption) "
                         "VALUES (%s, %s, %s, %s)",
                         (doc_id, section_ids.get(sec.index) if sec else None, block.line_no,
                          caption))

        doc_title = " ".join(b.text for b in blocks[:FIRST_TITLE_BLOCKS]) + " " + path.stem
        doc_target = target_of(doc_title, dicts.values)
        saved = 0
        recent_text: list[str] = []
        current_top: int | None = None
        for i, cand in enumerate(candidates):
            if cand.req_kind == "DESCRIPTION":
                continue
            sec_id = section_ids.get(cand.section.index) if cand.section else None
            loc_id = conn.execute(
                """INSERT INTO source_location (document_id, section_id, row_id, line_start,
                                                line_end)
                   VALUES (%s, %s, %s, %s, %s) RETURNING location_id""",
                (doc_id, sec_id, row_ids.get(cand.block.seq), cand.line_start,
                 cand.block.last_line),
            ).fetchone()[0]
            rep = conn.execute(
                "SELECT r.requirement_id FROM requirement r JOIN document d USING (document_id) "
                "WHERE r.dedup_key = %s AND r.dedup_of IS NULL AND r.document_id <> %s "
                "AND d.processing_key = %s ORDER BY r.requirement_id LIMIT 1",
                (cand.dedup_key, doc_id, key)).fetchone() if cand.dedup_key and dedup else None
            req_id = conn.execute(
                """INSERT INTO requirement (document_id, section_id, row_id, source_kind,
                     text_raw, req_kind, dedup_of, extracted_by, confidence, rule_id,
                     supplier_mark, dedup_key)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING requirement_id""",
                (doc_id, sec_id, row_ids.get(cand.block.seq), cand.source_kind, cand.text,
                 cand.req_kind, rep[0] if rep else None, cand.extracted_by,
                 CONFIDENCE.get(cand.extracted_by, 0.7), cand.rule_id, cand.supplier_mark,
                 cand.dedup_key),
            ).fetchone()[0]
            conn.execute("INSERT INTO requirement_location VALUES (%s, %s)", (req_id, loc_id))
            if rep:
                # 같은 요구가 다른 문서에 이미 있으면 대표 요구사항에 위치를 더한다 (CR-03).
                conn.execute("INSERT INTO requirement_location VALUES (%s, %s) "
                             "ON CONFLICT DO NOTHING", (rep[0], loc_id))
            saved += 1

            if cand.req_kind != "REQUIREMENT":
                continue
            for t in prep.tags.get(i, []):
                conn.execute(
                    """INSERT INTO requirement_type_tag (requirement_id, type_code, is_primary,
                                                         decided_by, type_rule_id)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (req_id, t.type_code, t.is_primary, t.decided_by,
                     t.rule.rule_id if t.rule else None),
                )
            code = prep.ai_types.get(i)
            if code and code != "NONE":
                conn.execute(
                    "INSERT INTO requirement_type_tag (requirement_id, type_code, is_primary, "
                    "decided_by) VALUES (%s, %s, TRUE, 'AI')", (req_id, code))

            top = _top_section(cand.section, sections)
            if top != current_top:
                # 앞 문장 문맥은 같은 최상위 절 안에서만 이어 쓴다.
                recent_text.clear()
                current_top = top
            values = normalize_candidate(cand, sections, dicts.values, doc_target,
                                         preceding_text="\n".join(recent_text))
            recent_text.append(cand.text)
            for v in values:
                conn.execute(
                    """INSERT INTO req_value (requirement_id, raw_text, cell_form, num_value,
                         operator, unit_raw, cond_time_s, cond_raw, item_key, target_object,
                         basis_standard, delegated_std, equipment_key, project_id, flag, value_seq)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (req_id, v.raw_text, v.cell_form, v.num_value, v.operator,
                     (v.unit_raw or "")[:40] or None, v.cond_time_s, v.cond_raw, v.item_key,
                     v.target_object, v.basis_standard, v.delegated_std, v.equipment_key,
                     dicts.projects.get(c.project_key) if c.project_key else None, v.flag, v.seq),
                )

        # OCR로 읽은 줄이 있으면 사람이 글자를 확인해야 한다 (add-ocr)
        ocr_lines = sum(b.line_count for b in blocks if b.ocr)
        conn.execute(
            """UPDATE document SET processor = %s, process_check = %s, reprocessed = %s,
                      reprocessed_lines = %s, ocr_lines = %s,
                      needs_review = needs_review OR %s OR %s > 0
                WHERE document_id = %s""",
            (proc.kind, check, lines > 0, lines, ocr_lines, check is not None, ocr_lines, doc_id))

    return DocumentResult(doc_id, file_no, False, True, saved, prep.with_examples, lines > 0,
                          lines)


FIRST_TITLE_BLOCKS = 15
# 추출 방법별 신뢰도. OCR은 글자를 잘못 읽을 수 있어 낮게 둔다 (add-ocr)
CONFIDENCE = {"RULE": 1.0, "AI": 0.7, "OCR": 0.5}


def type_context(cand) -> str | None:
    """AI 유형 질문에 줄 문맥: 절 번호·제목, 표 이름, 표 안 구분 행 (update-type-context)."""
    parts = []
    if cand.section is not None and (cand.section.number or cand.section.title):
        parts.append(f"절 {cand.section.number} {cand.section.title}".strip())
    if cand.table is not None and cand.table.name:
        parts.append(f"표 {cand.table.name}")
    if cand.part_title:
        parts.append(f"구분 {cand.part_title}")
    return " · ".join(parts) or None


def _top_section(section: Section | None, sections: list[Section]) -> int | None:
    while section is not None and section.parent is not None:
        section = sections[section.parent]
    return section.index if section else None


__all__ = ["process_document", "DocumentResult"]
