"""그림 속 글자 읽기 (add-ocr). 로컬 Tesseract(영어·한국어)만 쓰고 AI·외부 전송은 없다(CR-01).

글자 신뢰도가 기준보다 낮은 줄은 버린다(CR-04, 지어내지 않음). 같은 엔진 판·같은 그림이면 같은
결과이고, 엔진 판은 처리 판에 들어간다(CR-11). 엔진이 없거나 RFP_OCR=off면 아무것도 읽지 않는다.
"""

from dataclasses import dataclass
from functools import lru_cache

from PIL import Image

from rfp_agent.config import get_settings

LANGS = "eng+kor"
CONFIG = "--psm 6"          # 한 덩어리 글
MIN_CONFIDENCE = 60         # 줄 단어 신뢰도 평균이 이보다 낮으면 버림 [제안]


@dataclass
class OcrLine:
    text: str
    top: float              # 그림 안 위치(픽셀)
    bottom: float
    confidence: float


@lru_cache
def engine_version() -> str | None:
    """쓸 수 있는 엔진 판. 엔진이 없으면 None."""
    try:
        import pytesseract
        return str(pytesseract.get_tesseract_version())
    except Exception:                                   # 엔진(실행 파일)이 없음
        return None


def available() -> bool:
    return get_settings().rfp_ocr != "off" and engine_version() is not None


def version_tag() -> str:
    """처리 판에 붙일 OCR 표시: 엔진 판 또는 ocr-off."""
    return f"ocr{engine_version()}" if available() else "ocr-off"


def read_lines(image: Image.Image) -> list[OcrLine]:
    """그림을 줄로 읽는다. 엔진이 없으면 빈 목록."""
    if not available():
        return []
    import pytesseract

    data = pytesseract.image_to_data(image.convert("L"), lang=LANGS, config=CONFIG,
                                     output_type=pytesseract.Output.DICT)
    lines: dict[tuple, list[int]] = {}
    for i, word in enumerate(data["text"]):
        if word.strip() and float(data["conf"][i]) >= 0:
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append(i)
    out = []
    for key in sorted(lines, key=lambda k: min(data["top"][i] for i in lines[k])):
        idx = lines[key]
        conf = sum(float(data["conf"][i]) for i in idx) / len(idx)
        if conf < MIN_CONFIDENCE:
            continue
        out.append(OcrLine(
            text=" ".join(data["text"][i] for i in sorted(idx, key=lambda i: data["left"][i])),
            top=min(data["top"][i] for i in idx),
            bottom=max(data["top"][i] + data["height"][i] for i in idx),
            confidence=conf))
    return out


PARA_GAP = 1.5              # 줄 위아래 간격이 줄 높이의 이 배를 넘으면 새 단락 (pdf_reader와 같음)


def paragraphs(lines: list[OcrLine]) -> list[str]:
    """읽은 줄을 줄 간격으로 단락으로 묶는다."""
    out: list[list[str]] = []
    prev = None
    for line in lines:
        height = line.bottom - line.top or 1
        if prev is None or line.top - prev.bottom > height * (PARA_GAP - 1):
            out.append([line.text])
        else:
            out[-1].append(line.text)
        prev = line
    return ["\n".join(p) for p in out]
