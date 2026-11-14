"""FR-07 비교 규칙. 요구값 하나와 제품값 하나로 판정 5종과 여유를 정한다 (코드만, CR-01).

단위는 표기만 맞추고(대소문자, 공백, "kVrms" → "kV") 환산하지 않는다 (CR-10).
"""

import re
from dataclasses import dataclass

from rfp_agent.pipeline.products import IP_CODE, ProductValue, normalize_standard

COMPLY, DEVIATION, QUERY = "COMPLY", "DEVIATION_CANDIDATE", "QUERY_CANDIDATE"
REVIEW, WARRANTY = "NEEDS_REVIEW", "WARRANTY_TO_FILL"

REASONS = {
    "EMPTY": "요구값이 빈칸 — 우리 값을 채움",
    "REDACTED": "요구값이 가림 표시 — 값 없음",
    "DELEGATED": "규격 위임 — 규격 확인 필요",
    "TEXT_VALUE": "문장 요구 — 사람이 읽고 확인",
    "YESNO_CHECK": "예/아니오 항목 — 체크 항목으로 확인",
    "FORMULA": "계산할 수 없는 계산식",
    "RANGE": "범위 값 — 양 끝을 사람이 확인",
    "NO_ITEM_KEY": "항목 사전에 없는 항목",
    "FILLED": "작성 항목인데 요구값이 있음",
    "MULTI_VALUE": "한 칸에 값이 여럿 — 어느 값인지 질의",
    "NO_PRODUCT": "확인 필요 — 기준값 없음 (맞는 정격 행 없음)",
    "PRODUCT_AMBIGUOUS": "비교 제품 행을 하나로 고를 수 없음",
    "NO_PRODUCT_VALUE": "제품값 없음",
    "UNIT_MISSING": "요구값 단위 없음",
    "UNIT_DIFF": "단위가 다름 — 환산하지 않음",
    "BOUNDARY": "경계값 — 요구 '<'와 제품 '≤'가 같은 숫자",
    "CONDITION_DIFF": "조건(시간)이 다름",
    "NO_PRODUCT_TIME": "제품값에 시간 조건 없음",
    "STANDARD_NOT_LISTED": "제품 규격 목록에 없는 규격 (판본 포함 확인)",
    "MEETS": "요구를 맞춤",
    "NOT_MET": "요구를 그대로 맞추지 못함",
    "NOT_INCLUDED": "제품 지원 값에 요구값이 없음",
}


@dataclass
class ReqValue:
    raw: str | None
    cell_form: str
    num: float | None
    operator: str | None
    unit: str | None
    time_s: float | None
    item_key: str | None
    basis_standard: str | None
    flag: str | None
    multi: bool = False             # 한 칸에 숫자가 여럿


@dataclass
class Verdict:
    result: str
    reason: str
    margin: float | None = None
    margin_kind: str | None = None
    margin_direction: str = "NOT_CALC"

    @property
    def reason_text(self) -> str:
        return REASONS.get(self.reason, self.reason)


def unit_key(unit: str | None) -> str | None:
    """표기 차이만 맞춘다: 'KVrms' → 'kv', '°C'·'deg C'·'oC' → '°c', '%/년' → '%'."""
    if not unit:
        return None
    u = re.sub(r"[\s.]", "", unit).lower()
    u = re.sub(r"^(k?[va])(rms|peak|p)$", r"\1", u)
    u = {"℃": "°c", "degc": "°c", "oc": "°c", "cycles": "cycle",
         "month": "months", "months": "months", "개월": "months",
         "year": "years", "years": "years", "년": "years"}.get(u, u)
    return re.sub(r"^%(/년|/year|/yr|peryear|/annum)$", "%", u)


def _fmt(num: float) -> str:
    return f"{num:g}"


def precheck(req: ReqValue, direction: str) -> Verdict | None:
    """제품을 보기 전에 요구값 칸 모양만으로 정해지는 판정."""
    if req.flag == "REDACTED":
        return Verdict(REVIEW, "REDACTED")
    if req.cell_form == "EMPTY":
        return Verdict(WARRANTY, "EMPTY")
    if req.cell_form == "DELEGATED":
        return Verdict(REVIEW, "DELEGATED")
    if req.item_key is None:
        return Verdict(REVIEW, "NO_ITEM_KEY")
    if direction == "FILL":
        return Verdict(REVIEW, "FILLED")
    if req.cell_form == "YESNO":
        return Verdict(REVIEW, "YESNO_CHECK")
    if req.cell_form == "FORMULA" and req.num is None:
        return Verdict(REVIEW, "FORMULA")
    if req.flag == "RANGE":
        return Verdict(REVIEW, "RANGE")
    if direction in ("TEXT", "AI"):
        return Verdict(REVIEW, "TEXT_VALUE")
    if req.cell_form == "TEXT" and direction not in ("IN", "EQ") and req.item_key != "ip_rating":
        return Verdict(REVIEW, "TEXT_VALUE")
    if req.multi and req.num is not None:
        return Verdict(QUERY, "MULTI_VALUE")
    return None


def _strength(sense: str, strength: str, margin: float) -> str:
    if margin <= 0 or strength == "NONE":
        return "NOT_STRENGTH"
    return "STRENGTH" if strength == sense else "NOT_STRENGTH"


def compare(req: ReqValue, prod: ProductValue | None, direction: str, strength: str,
            time_condition: bool = False) -> Verdict:
    """direction: EQ, GE, LE, LT, IN, SOURCE (요구값 기호를 따름). strength: HIGHER, LOWER, NONE."""
    if prod is None:
        return Verdict(REVIEW, "NO_PRODUCT_VALUE")
    if direction == "IN" or (req.item_key == "standard"):
        return _compare_in(req, prod)
    if req.item_key == "ip_rating":
        return _compare_ip(req, prod)
    if direction == "EQ" and prod.items:            # 주파수 "50/60"
        if req.num is None:
            return Verdict(REVIEW, "TEXT_VALUE")
        if unit_key(req.unit) != unit_key(prod.unit):
            return Verdict(REVIEW, "UNIT_DIFF" if req.unit else "UNIT_MISSING")
        hit = _fmt(req.num) in prod.items
        return Verdict(COMPLY if hit else DEVIATION, "MEETS" if hit else "NOT_INCLUDED")
    if req.num is None or prod.num is None:
        return Verdict(REVIEW, "NO_PRODUCT_VALUE" if prod.num is None else "TEXT_VALUE")
    if not req.unit:
        return Verdict(REVIEW, "UNIT_MISSING")
    if unit_key(req.unit) != unit_key(prod.unit):
        return Verdict(REVIEW, "UNIT_DIFF")
    if direction == "SOURCE":
        direction = {"<": "LT", "<=": "LE", ">": "GT", ">=": "GE"}.get(req.operator or "=", "LE")
    elif direction == "GE" and req.operator == ">":
        direction = "GT"
    elif direction in ("LE", "LT") and req.operator == "<":
        direction = "LT"

    if direction in ("GE", "GT"):
        return _compare_higher(req, prod, direction, strength, time_condition)
    if direction in ("LE", "LT"):
        return _compare_lower(req, prod, direction, strength)
    if direction == "EQ":
        same = prod.num == req.num
        return Verdict(COMPLY if same else DEVIATION, "MEETS" if same else "NOT_MET")
    return Verdict(REVIEW, "TEXT_VALUE")


def _compare_higher(req: ReqValue, prod: ProductValue, direction: str, strength: str,
                    time_condition: bool) -> Verdict:
    if direction == "GT" and prod.num == req.num:
        return Verdict(REVIEW, "BOUNDARY")
    if prod.num < req.num:
        return Verdict(DEVIATION, "NOT_MET")
    margin = prod.num - req.num
    if time_condition or req.time_s is not None:
        if req.time_s is not None:
            if prod.time_s is None:
                return Verdict(REVIEW, "NO_PRODUCT_TIME")
            if prod.time_s < req.time_s:
                return Verdict(REVIEW, "CONDITION_DIFF")
            if margin == 0 and prod.time_s > req.time_s:
                ratio = prod.time_s / req.time_s       # 같은 값이면 시간 배수가 여유 [결정]
                return Verdict(COMPLY, "MEETS", ratio, "TIME_RATIO",
                               _strength("HIGHER", strength, ratio - 1))
    return Verdict(COMPLY, "MEETS", margin, "DIFF", _strength("HIGHER", strength, margin))


def _compare_lower(req: ReqValue, prod: ProductValue, direction: str, strength: str) -> Verdict:
    if direction == "LT" and prod.num == req.num:
        # 요구 "<0.5"에 제품 "≤0.5"는 경계값 [결정]. 제품이 딱 그 값이어도 "<"를 못 맞춘다.
        if prod.operator == "<":
            return Verdict(COMPLY, "MEETS", 0.0, "DIFF", "NOT_STRENGTH")
        return Verdict(REVIEW, "BOUNDARY") if prod.operator == "<=" else Verdict(DEVIATION,
                                                                                  "NOT_MET")
    if prod.num > req.num:
        return Verdict(DEVIATION, "NOT_MET")
    margin = req.num - prod.num
    return Verdict(COMPLY, "MEETS", margin, "DIFF", _strength("LOWER", strength, margin))


def _compare_in(req: ReqValue, prod: ProductValue) -> Verdict:
    wanted = req.basis_standard or req.raw
    if not wanted:
        return Verdict(REVIEW, "TEXT_VALUE")
    std = normalize_standard(wanted)
    if not prod.items:
        return Verdict(REVIEW, "NO_PRODUCT_VALUE")
    if std in prod.items:
        return Verdict(COMPLY, "MEETS")
    return Verdict(REVIEW, "STANDARD_NOT_LISTED")


def _compare_ip(req: ReqValue, prod: ProductValue) -> Verdict:
    want, have = IP_CODE.search(req.raw or ""), IP_CODE.search(prod.raw or "")
    if not want:
        return Verdict(REVIEW, "TEXT_VALUE")
    if not have:
        return Verdict(REVIEW, "NO_PRODUCT_VALUE")
    ok = all(int(h) >= int(w) for w, h in zip(want.groups(), have.groups(), strict=True))
    return Verdict(COMPLY if ok else DEVIATION, "MEETS" if ok else "NOT_MET")
