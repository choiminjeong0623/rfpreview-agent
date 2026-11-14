"""분석 전 문서 분류 추천 (등록 화면). 규칙만 쓰고 아무것도 저장하지 않는다 (CR-01)."""

from pathlib import Path

import psycopg

from rfp_agent.pipeline import classify as cls
from rfp_agent.pipeline.reader import read_document


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
            blocks = read_document(path)
        except Exception as exc:          # python-docx는 여러 종류의 예외를 낸다
            raise UnreadableFile(path.name) from exc
        c = cls.classify(path.name, blocks, catalog, kind_rules)
        in_catalog = c.file_no is not None
        bundle, reason = cls.suggest_bundle(c, in_catalog)
        out.append(dict(
            file_name=path.name, in_catalog=in_catalog, file_no=c.file_no, doc_kind=c.doc_kind,
            bundle=bundle, language=c.language, standard_system=c.standard_system,
            readable=c.readable, judge_target=bundle in ("A", "B") and c.readable,
            needs_review=c.doc_kind == "UNKNOWN", reason=reason))
    return out


def has_judge_target(conn: psycopg.Connection, paths: list[Path],
                     bundles: dict[str, str]) -> bool:
    """판정 대상 문서가 하나라도 있는가 (등록 거절, CR-09).

    분석과 같은 규칙(문서 목록 묶음, 없으면 C)에 사람이 정한 묶음을 덮어쓴다
    (bundles: 파일 이름 → 묶음).
    열 수 없는 파일이 있으면 판단하지 않고 True를 돌려 분석 실패로 보이게 한다.
    """
    catalog = _catalog(conn)
    kind_rules = cls.load_kind_rules(conn)
    for path in paths:
        try:
            blocks = read_document(path)
        except Exception:                 # 열 수 없는 docx는 지금처럼 분석 실패로 남긴다
            return True
        c = cls.classify(path.name, blocks, catalog, kind_rules)
        if c.readable and bundles.get(path.name, c.bundle) in ("A", "B"):
            return True
    return False
