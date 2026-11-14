"""docx 블록의 줄 번호를 팀 추출 txt의 줄 번호로 맞춘다.

txt는 같은 docx에서 만들었지만 일부 구간의 순서가 다르다. 그래서 줄 원문이 같은 후보 중에서
바로 앞 줄 다음 번호를 먼저 고르고, 아니면 뒤따르는 몇 줄이 같이 맞는 후보를 고른다.
22개 문서에서 내용이 있는 줄은 모두 맞는다 (design.md).
"""

from collections import defaultdict
from pathlib import Path

from rfp_agent.pipeline.docx_reader import Block

CONTEXT = 4


def _lines_of(blocks: list[Block]) -> list[str]:
    out: list[str] = []
    for b in blocks:
        out.extend(b.text.split("\n"))
    return [x.rstrip() for x in out]


def map_lines(blocks: list[Block], txt_path: Path) -> tuple[list[Block], float]:
    """블록 줄 번호를 txt 기준으로 바꾼 새 목록과, 내용 있는 줄 중 맞춘 비율을 돌려준다."""
    ours = _lines_of(blocks)
    ref = [x.rstrip() for x in txt_path.read_text(encoding="utf-8").split("\n")]
    positions: dict[str, list[int]] = defaultdict(list)
    for j, line in enumerate(ref):
        positions[line].append(j)

    def context(i: int, j: int) -> int:
        return sum(1 for d in range(1, CONTEXT + 1)
                   if i + d < len(ours) and j + d < len(ref) and ours[i + d] == ref[j + d])

    used: set[int] = set()
    mapped: list[int | None] = [None] * len(ours)
    prev = -1
    for i, line in enumerate(ours):
        if not line.strip():
            continue
        candidates = [j for j in positions.get(line, ()) if j not in used]
        if not candidates:
            continue
        j = prev + 1 if prev + 1 in candidates else max(
            candidates, key=lambda j: (context(i, j), -abs(j - prev)))
        mapped[i] = j
        used.add(j)
        prev = j

    nonempty = [i for i, line in enumerate(ours) if line.strip()]
    ratio = sum(1 for i in nonempty if mapped[i] is not None) / len(nonempty) if nonempty else 1.0

    result: list[Block] = []
    for b in blocks:
        own = range(b.line_no - 1, b.line_no - 1 + b.line_count)
        hits = [mapped[i] for i in own if mapped[i] is not None]
        if hits:
            b = Block(**{**b.__dict__, "line_no": min(hits) + 1})
        result.append(b)
    return result, ratio
