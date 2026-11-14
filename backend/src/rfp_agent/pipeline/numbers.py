"""CR-07 문장 속 숫자. AI 문장에는 숫자 대신 {v1} 같은 자리표시자를 쓰게 하고, 코드가 근거 값으로
채운 뒤 문장 속 숫자를 근거 값과 다시 대조한다."""

import re
from dataclasses import dataclass

PLACEHOLDER = re.compile(r"\{(\w+)\}")
NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


def fmt(num: float | None) -> str:
    """4000 → '4,000', 0.5 → '0.5', 3.0 → '3'."""
    if num is None:
        return ""
    return f"{num:,.6f}".rstrip("0").rstrip(".") if num != int(num) else f"{int(num):,}"


def _plain(number: str) -> str:
    text = number.replace(",", "")
    return text.rstrip("0").rstrip(".") if "." in text else text


def numbers_in(text: str) -> list[str]:
    return [_plain(m.group(0)) for m in NUMBER.finditer(text)]


# "과(와)", "(으)로"처럼 둘 다 적은 조사. 자리표시자 값을 모르는 언어 모델이 이렇게 쓰므로
# 값을 채운 뒤 앞 글자에 맞게 고른다.
PAIRED = re.compile(r"(\S)\s?(과\(와\)|와\(과\)|\(으\)로|이\(가\)|가\(이\)"
                    r"|을\(를\)|를\(을\)|은\(는\)|는\(은\))")
# 받침 있는 조사, 받침 없는 조사
PARTICLES = {"과": ("과", "와"), "와": ("과", "와"), "(으)로": ("으로", "로"), "이": ("이", "가"),
             "가": ("이", "가"), "을": ("을", "를"), "를": ("을", "를"), "은": ("은", "는"),
             "는": ("은", "는")}
# 한글이 아닌 끝 글자를 읽었을 때 받침: 0 영, 1 일, 3 삼, 6 육, 7 칠, 8 팔, L 엘, M 엠, N 엔, R 알
CODA = set("013678LMNRlmnr")
RIEUL = set("178Llr")                       # ㄹ 받침 뒤에는 "(으)로"가 "로"


def _coda(ch: str) -> tuple[bool, bool]:
    """(받침이 있는지, 그 받침이 ㄹ인지)."""
    if "가" <= ch <= "힣":
        final = (ord(ch) - 0xAC00) % 28
        return final != 0, final == 8
    return ch in CODA, ch in RIEUL


# 자리표시자 바로 뒤에 붙은 한쪽 조사("{p}는", "{v2}로"). 값을 채우기 전에 둘 다 적은 꼴로 바꿔
# 채운 값의 끝 글자에 맞게 고른다 ("GIS-145-40는" → "GIS-145-40은").
AFTER_SLOT = re.compile(r"(\{\w+\})(으로|로|은|는|이|가|을|를|과|와)(?=[\s.,;:!?)\]·]|$)")
PAIR_OF = {"은": "은(는)", "는": "은(는)", "이": "이(가)", "가": "이(가)", "을": "을(를)",
           "를": "을(를)", "과": "과(와)", "와": "과(와)", "으로": "(으)로", "로": "(으)로"}


def pair_slots(template: str) -> str:
    """'{p}는 {v2}로' → '{p}은(는) {v2}(으)로'."""
    return AFTER_SLOT.sub(lambda m: m.group(1) + PAIR_OF[m.group(2)], template)


def josa(text: str) -> str:
    """'1 % 이내과(와) <0.5(으)로' → '1 % 이내와 <0.5로'. 앞 글자의 받침으로 조사를 고른다."""
    def pick(m: re.Match) -> str:
        has, rieul = _coda(m.group(1))
        pair = m.group(2)
        name = "(으)로" if pair == "(으)로" else pair[0]
        if name == "(으)로" and rieul:
            return m.group(1) + "로"
        return m.group(1) + PARTICLES[name][0 if has else 1]
    return PAIRED.sub(pick, text)


@dataclass
class Filled:
    text: str
    check: str                  # OK / MISMATCH
    detail: str | None          # 근거에 없는 숫자


def filled_with(text: str, values: dict[str, str]) -> bool:
    """이미 채운 문장에 지금 근거 값이 모두 들어 있는지. 값이 바뀌었으면 문장을 다시 써야 한다."""
    return all(v in text for v in values.values() if v)


def fill(template: str, values: dict[str, str]) -> Filled:
    """자리표시자를 채우고, 채운 문장 속 숫자가 모두 근거 값(values)에 있는지 본다."""
    text = josa(PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), pair_slots(template)))
    allowed = {n for v in values.values() for n in numbers_in(v)}
    wrong = [n for n in numbers_in(text) if n not in allowed]
    if PLACEHOLDER.search(text):
        wrong += [m.group(0) for m in PLACEHOLDER.finditer(text)]
    if wrong:
        return Filled(text, "MISMATCH", "근거와 다른 숫자: " + ", ".join(dict.fromkeys(wrong)))
    return Filled(text, "OK", None)
