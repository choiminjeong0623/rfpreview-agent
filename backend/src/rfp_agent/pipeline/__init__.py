"""RFP 문서 처리 흐름 (업무 흐름 ①~⑥).

각 단계는 메모리 위의 순수 함수이고, DB 쓰기는 document.py·run.py에서 한다.
"""

import hashlib
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent
# 문서 하나의 처리 결과(①~⑤)를 바꾸는 코드. 조회·실행 코드는 넣지 않는다.
DOCUMENT_MODULES = ["classify", "dictionaries", "docx_reader", "document", "extract", "line_map",
                    "pdf_reader", "reader", "structure", "type_tags", "values"]


def code_version() -> str:
    """문서 처리 코드 내용으로 만든 판 번호. 규칙 코드가 바뀌면 문서를 다시 처리한다."""
    digest = hashlib.sha256()
    for path in [PIPELINE_DIR / f"{name}.py" for name in DOCUMENT_MODULES]:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:7]
