"""분석 전 문서 분류 추천 (등록 화면). 규칙만 쓰고 아무것도 저장하지 않는다 (CR-01)."""

import hashlib
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from rfp_agent.pipeline import classify as cls
from rfp_agent.pipeline import docx_reader
from rfp_agent.pipeline.docx_reader import Block
from rfp_agent.pipeline.reader import is_pdf, read_with_pages


class UnreadableFile(Exception):
    """docx·PDF로 열리지 않는 파일 (빈 파일, 이름만 docx 등)."""


def _catalog(conn: psycopg.Connection) -> list[cls.CatalogEntry]:
    return [cls.CatalogEntry(*r) for r in conn.execute(
        "SELECT file_no, file_key, bundle, language, project_key FROM document_catalog")]


def preview(conn: psycopg.Connection, paths: list[Path]) -> list[dict]:
    catalog = _catalog(conn)
    kind_rules = cls.load_kind_rules(conn)
    out = []
    for path in paths:
        try:
            blocks, scan = read_with_pages(path)
        except Exception as exc:          # python-docx는 여러 종류의 예외를 낸다
            raise UnreadableFile(path.name) from exc
        c = cls.classify(path.name, blocks, catalog, kind_rules)
        in_catalog = c.file_no is not None
        bundle, reason = cls.suggest_bundle(c, in_catalog)
        # 등록 검사가 다시 읽지 않게 결과를 파일 내용 해시로 남긴다 (add-run-queue, NFR-11)
        remember(conn, path, {"rule_bundle": c.bundle, "readable": c.readable,
                              "unread_reason": main_reason(scan)})
        out.append(dict(
            file_name=path.name, in_catalog=in_catalog, file_no=c.file_no, doc_kind=c.doc_kind,
            bundle=bundle, language=c.language, standard_system=c.standard_system,
            readable=c.readable, judge_target=bundle in ("A", "B") and c.readable,
            needs_review=c.doc_kind == "UNKNOWN", reason=reason,
            page_count=scan.page_count if scan else None,
            unread_pages=len(scan.unread) if scan else 0,
            unread_reason=main_reason(scan)))
    return out


def main_reason(scan) -> str | None:
    """읽지 못한 쪽의 가장 많은 이유 (같으면 먼저 나온 것)."""
    if not scan or not scan.unread:
        return None
    return Counter(u["reason"] for u in scan.unread).most_common(1)[0][0]


# 판정할 문서를 모두 읽지 못한 이유 (add-unread-pages)
UNREAD_WHY = {"OCR_LOW_CONF": "모든 쪽 OCR 실패", "OCR_EMPTY": "모든 쪽 OCR 실패",
              "OCR_OFF": "OCR 꺼짐", "OCR_MISSING": "OCR 엔진 없음"}
NO_TEXT = "글자를 읽을 수 없는 파일"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remember(conn: psycopg.Connection, path: Path, result: dict) -> None:
    conn.execute("""INSERT INTO preview_cache (content_hash, result) VALUES (%s, %s)
                    ON CONFLICT (content_hash) DO UPDATE SET result = EXCLUDED.result,
                      created_at = now()""", (_digest(path), Jsonb(result)))
    conn.commit()


def _light(path: Path, catalog, kind_rules) -> dict | None:
    """미리 보기 결과가 없을 때 가볍게 본다 (OCR 없음): docx는 OCR 없이 읽고, PDF는 첫 쪽 글자
    층만 본다. PDF는 첫 쪽만으로 판독 여부를 알 수 없어 글자가 있으면 읽을 수 있다고 보고,
    첫 쪽에 글자가 없으면 판단하지 않는다(None, 분석에 맡김)."""
    if is_pdf(path):
        blocks = pdf_first_page(path)
        if not blocks:
            return None
        c = cls.classify(path.name, blocks, catalog, kind_rules)
        return {"rule_bundle": c.bundle, "readable": True, "unread_reason": None, "light": True}
    c = cls.classify(path.name, docx_reader.read_blocks(path, use_ocr=False), catalog,
                     kind_rules)
    return {"rule_bundle": c.bundle, "readable": c.readable, "unread_reason": None, "light": True}


def pdf_first_page(path: Path) -> list[Block]:
    """PDF 첫 쪽 글자 층의 줄 (OCR 없음). 열 수 없거나 글자가 없으면 빈 목록."""
    import pdfplumber
    try:
        with pdfplumber.open(str(path)) as pdf:
            if not pdf.pages:
                return []
            lines = [ln["text"] for ln in pdf.pages[0].extract_text_lines() if ln["text"].strip()]
    except Exception:
        return []
    return [Block(seq=n, kind="P", text=t, line_no=n + 1, line_count=1, page=1)
            for n, t in enumerate(lines)]


def judge_target_problem(conn: psycopg.Connection, paths: list[Path],
                         bundles: dict[str, str]) -> tuple[str, str | None] | None:
    """판정 대상 문서가 없으면 그 까닭 (등록 거절, CR-09). 있으면 None.

    ("NO_TARGET", None): 묶음 A·B 문서가 없음. ("UNREAD", 이유): 판정 대상으로 고른 문서를
    모두 읽지 못함 (add-unread-pages). 분석과 같은 규칙(문서 목록 묶음, 없으면 C)에 사람이 정한
    묶음을 덮어쓴다 (bundles: 파일 이름 → 묶음).
    열 수 없는 파일이 있으면 판단하지 않고 None을 돌려 분석 실패로 보이게 한다.
    문서를 다시 읽지 않는다 (add-run-queue, NFR-11): 등록 화면 미리 보기 결과(같은 파일 해시)를
    쓰고, 없으면 OCR 없이 가볍게 본다(_light). 읽지 못해 거절하는 것은 미리 보기 결과가 있을 때만.
    """
    catalog = _catalog(conn)
    kind_rules = cls.load_kind_rules(conn)
    unread: list[str] = []
    for path in paths:
        row = conn.execute("SELECT result FROM preview_cache WHERE content_hash = %s",
                           (_digest(path),)).fetchone()
        try:
            seen = row[0] if row else _light(path, catalog, kind_rules)
        except Exception:                 # 열 수 없는 docx는 지금처럼 분석 실패로 남긴다
            return None
        if seen is None:                  # 첫 쪽에 글자가 없는 PDF: 분석에 맡긴다
            return None
        if bundles.get(path.name, seen["rule_bundle"]) not in ("A", "B"):
            continue
        # 가볍게 본 결과로는 읽지 못했다고 거절하지 않는다
        if seen["readable"] or seen.get("light"):
            return None
        unread.append(UNREAD_WHY.get(seen.get("unread_reason") or "", NO_TEXT))
    if unread:
        return "UNREAD", Counter(unread).most_common(1)[0][0]
    return "NO_TARGET", None
