"""사람이 고친 유형을 AI 유형 질문의 예시로 (add-type-examples, C3, RAG).

- 후보: 다른 문서에서 사람(HUMAN)이 정한 주 유형. 같은 문서(같은 파일 내용 포함)와
  정답지(유형·요구사항)에 든 문장은 빼서 K13 채점을 오염시키지 않는다.
- 줄마다 문장 벡터 코사인 0.80 이상인 후보를 위에서 2개. 동점은 요구사항 번호 순(CR-11).
- 예시는 참고일 뿐 유형은 AI 답과 규칙으로 정한다(CR-01). 벡터를 못 받으면 예시 없이 묻는다.
"""

import psycopg

from rfp_agent.llm.client import LLMFailure
from rfp_agent.pipeline import meaning
from rfp_agent.pipeline.req_eval import normalize

EXAMPLE_MIN = 0.80
PER_LINE = 2
MAX_POOL = 500
EXAMPLE_CHARS = 200

Example = tuple[str, str]          # (사람이 고친 줄 문장, 유형 코드)


def pool(conn: psycopg.Connection, content_hash: str) -> list[tuple[int, str, str]]:
    """(요구사항 번호, 문장, 유형) — 내용이 다른 문서의 사람 주 유형, 정답지 문장 뺌.

    처리 중인 문서는 아직 저장 전이라 내용 해시로 같은 파일(이전 판 처리 포함)을 뺀다.
    """
    rows = conn.execute(
        """SELECT q.requirement_id, q.text_raw, t.type_code
             FROM requirement_type_tag t JOIN requirement q USING (requirement_id)
             JOIN document d ON d.document_id = q.document_id
            WHERE t.is_primary AND t.decided_by = 'HUMAN'
              AND d.content_hash IS DISTINCT FROM %(hash)s
            ORDER BY q.requirement_id DESC LIMIT %(n)s""",
        {"hash": content_hash, "n": MAX_POOL}).fetchall()
    keys = {normalize(t) for (t,) in conn.execute("SELECT text_raw FROM answer_key_row")}
    seen: set[str] = set()
    out = []
    for req_id, text, code in sorted(rows):
        norm = normalize(text)
        if norm in keys or norm in seen:
            continue
        seen.add(norm)
        out.append((req_id, text, code))
    return out


def pick(conn: psycopg.Connection, llm, content_hash: str,
         texts: list[str]) -> list[list[Example]]:
    """줄마다 가까운 사람 예시(최대 2개). 후보·벡터가 없으면 모두 빈 목록."""
    empty: list[list[Example]] = [[] for _ in texts]
    if llm is None or not hasattr(llm, "embed") or not texts:
        return empty
    candidates = pool(conn, content_hash)
    if not candidates:
        return empty
    try:
        vec = meaning.vectors(conn, llm, list(texts) + [t for _, t, _ in candidates])
    except LLMFailure:
        return empty                    # 예시 없이 묻는다 (분석 계속)
    out = []
    for text in texts:
        mine = vec.get(meaning.clean(text))
        if mine is None:
            out.append([])
            continue
        scored = []
        for req_id, other, code in candidates:
            v = vec.get(meaning.clean(other))
            if v is None or meaning.clean(other) == meaning.clean(text):
                continue
            score = meaning.cosine(mine, v)
            if score >= EXAMPLE_MIN:
                scored.append((-round(score, 6), req_id, other, code))
        scored.sort()
        out.append([(" ".join(o.split())[:EXAMPLE_CHARS], c) for _, _, o, c in scored[:PER_LINE]])
    return out
