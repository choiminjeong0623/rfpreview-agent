"""받은 문서를 확장자에 따라 단락·표 행 블록으로 읽는다 (add-pdf-input). 고르기는 코드다."""

from pathlib import Path

from rfp_agent.pipeline import docx_reader, pdf_reader
from rfp_agent.pipeline.docx_reader import Block

SUFFIXES = (".docx", ".pdf")


def read_document(path: Path) -> list[Block]:
    if path.suffix.lower() == ".pdf":
        return pdf_reader.read_blocks(path)
    return docx_reader.read_blocks(path)


def read_with_pages(path: Path) -> tuple[list[Block], pdf_reader.PageScan | None]:
    """블록과 쪽마다 읽은 결과 (add-unread-pages). docx는 쪽이 없어 None."""
    if path.suffix.lower() == ".pdf":
        return pdf_reader.read_pdf(path)
    return docx_reader.read_blocks(path), None


def is_pdf(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"
