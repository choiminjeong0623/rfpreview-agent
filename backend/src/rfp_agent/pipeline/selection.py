"""FR-07 비교 제품 고르기. 설비 묶음마다 요구 정격으로 product_master 행을 좁힌다 (코드만).

설비 묶음 = 데이터시트 표 하나의 로마 숫자 구분(I, II, …) 하나, 문장은 문서 + 설비 종류 + 전압.
설계 사례 카드는 기본으로 고르지 않고, 엔지니어가 고른 제품(바꿔 보기)이 있으면 그것을 쓴다.
"""

import re
from dataclasses import dataclass, field

from rfp_agent.pipeline.products import Product

INSTRUMENT = re.compile(r"current transformer|voltage transformer|instrument transformer|"
                        r"surge arrester|lightning arrester|변류기|계기용|피뢰기", re.IGNORECASE)
INSTRUMENT_TABLE = re.compile(r"-(CT|CVT|VT|SA|LA)\b")
GIS = re.compile(r"\bGIS\b|gas[- ]insulated|가스절연", re.IGNORECASE)
BREAKER = re.compile(r"circuit[- ]breaker|차단기", re.IGNORECASE)
BREAKER_TABLE = re.compile(r"-CB\b")
TRANSFORMER = re.compile(r"transformer|변압기", re.IGNORECASE)
TRANSFORMER_TABLE = re.compile(r"TR\b")
SWITCHGEAR = re.compile(r"switchgear|metal[- ]clad|배전반", re.IGNORECASE)
SWITCHGEAR_TABLE = re.compile(r"-SG\b")
GIS_PARTS = {"GIS", "차단기", "단로기", "접지개폐기"}
MV_LIMIT_KV = 52              # 이 전압 미만 차단기는 진공차단기 계열(MV_EQUIP)
KV = re.compile(r"(\d+(?:\.\d+)?)\s*kV", re.IGNORECASE)
# 같은 정격 행이 여럿일 때 베이 이름 → 제품 설명 속 용도
BAYS = [(re.compile(r"incoming|bus[- ]?(section|coupler|tie)", re.IGNORECASE),
         re.compile(r"인입|모선")),
        (re.compile(r"outgoing|feeder", re.IGNORECASE), re.compile(r"피더"))]
IEEE = re.compile(r"IEEE|ANSI|\bUL\b|NEMA")


@dataclass
class GroupContext:
    key: str
    label: str
    family: str | None
    um: float | None = None                       # 설비 최고 전압 (rated_voltage_um)
    nominals: set[float] = field(default_factory=set)
    frequencies: set[str] = field(default_factory=set)
    isc_ka: float | None = None                   # 단시간·차단 전류 요구 중 가장 큰 값
    capacity: tuple[float, str] | None = None
    standard_system: str | None = None


@dataclass
class Selection:
    product: Product | None
    candidates: list[Product]
    chosen_by: str | None                         # AUTO / ENGINEER


def family_of(table_name: str | None, part_title: str | None, target: str | None,
              context: str, um: float | None) -> str | None:
    """설비 종류. 표 이름과 구분 제목을 먼저, 없으면(문장) 적용 대상과 문서 제목을 본다."""
    name, part = table_name or "", part_title or ""
    if INSTRUMENT.search(part) or INSTRUMENT_TABLE.search(name):
        return None                               # 판정용 정격 행이 제품표에 없다
    if table_name is None:
        if target in GIS_PARTS and (target == "GIS" or GIS.search(context)):
            return "GIS"
        part = target or ""
    if GIS.search(name) or GIS.search(part):
        return "GIS"
    if BREAKER.search(part) or BREAKER_TABLE.search(name):
        return "MV_EQUIP" if um is not None and um < MV_LIMIT_KV else "GCB"
    if TRANSFORMER.search(part) or TRANSFORMER_TABLE.search(name):
        return "TRANSFORMER"
    if SWITCHGEAR.search(part) or SWITCHGEAR_TABLE.search(name):
        return "MV_SWGR"
    return None


def voltage_in(text: str | None) -> float | None:
    m = KV.search(text or "")
    return float(m.group(1)) if m else None


def table_voltage(table_name: str | None) -> float | None:
    """'TS-230-GIS' → 230, 'TS-22STR' → 22."""
    m = re.search(r"-(\d{2,3})(?=[A-Z-])", table_name or "")
    return float(m.group(1)) if m else None


def _keep(pool: list[Product], test) -> list[Product]:
    """조건에 맞는 것이 하나도 없으면 그 조건은 건너뛴다."""
    kept = [p for p in pool if test(p)]
    return kept or pool


def candidates(products: list[Product], ctx: GroupContext) -> list[Product]:
    if ctx.family is None:
        return []
    pool = [p for p in products
            if p.family == ctx.family and p.voltage_kv is not None and not p.is_design_card]
    if not pool:
        return []
    # 전압: Um과 같은 제품 → Um 이상 중 가장 낮은 제품 → 공칭 전압과 같은 제품
    low_nominal = min(ctx.nominals) if ctx.nominals else None
    if ctx.um is not None and (same := [p for p in pool if p.voltage_kv == ctx.um]):
        pool = same
    elif ctx.um is not None and low_nominal is not None and (band := [
            p for p in pool if low_nominal <= p.voltage_kv <= ctx.um]):
        pool = band                               # 공칭 전압과 Um 사이 (22 kV 계통의 22.9 kV)
    elif ctx.um is not None and ctx.family != "TRANSFORMER" and (
            higher := [p for p in pool if p.voltage_kv >= ctx.um]):
        # 개폐 장치는 높은 등급 제품을 쓸 수 있지만 변압기는 전압이 맞아야 한다.
        low = min(p.voltage_kv for p in higher)
        pool = [p for p in higher if p.voltage_kv == low]
    elif ctx.nominals and (same := [p for p in pool if p.voltage_kv in ctx.nominals]):
        pool = same
    elif ctx.nominals and ctx.family != "TRANSFORMER" and (
            higher := [p for p in pool if p.voltage_kv >= max(ctx.nominals)]):
        low = min(p.voltage_kv for p in higher)
        pool = [p for p in higher if p.voltage_kv == low]
    else:
        return []
    if ctx.frequencies:
        pool = _keep(pool, lambda p: not p.frequencies or ctx.frequencies <= set(p.frequencies))
    if ctx.standard_system == "IEC":
        pool = _keep(pool, lambda p: not p.standards or "IEC" in p.standards)
    elif ctx.standard_system == "IEEE_UL":
        pool = _keep(pool, lambda p: not p.standards or bool(IEEE.search(p.standards)))
    if ctx.isc_ka is not None:
        enough = [p for p in pool if p.short_circuit_ka is not None
                  and p.short_circuit_ka >= ctx.isc_ka]
        if enough:
            least = min(p.short_circuit_ka for p in enough)
            pool = [p for p in enough if p.short_circuit_ka == least]
    if ctx.capacity is not None:
        num, unit = ctx.capacity
        pool = _keep(pool, lambda p: p.capacity_unit == unit and p.capacity == num)
    return sorted(pool, key=lambda p: p.code)


def by_bay(pool: list[Product], row_label: str | None) -> Product | None:
    """정격 행이 여럿이면 행의 베이 이름(Incoming·Outgoing feeder 등)과 제품 용도를 맞춘다."""
    if not row_label:
        return None
    for bay, use in BAYS:
        if bay.search(row_label):
            hits = [p for p in pool if use.search(p.description[:40])]
            return hits[0] if len(hits) == 1 else None
    return None


def select(products: list[Product], ctx: GroupContext, override: str | None,
           row_label: str | None = None) -> Selection:
    if override is not None:
        chosen = next((p for p in products if p.code == override), None)
        return Selection(chosen, [chosen] if chosen else [], "ENGINEER")
    pool = candidates(products, ctx)
    if len(pool) == 1:
        return Selection(pool[0], pool, "AUTO")
    if len(pool) > 1 and (hit := by_bay(pool, row_label)):
        return Selection(hit, pool, "AUTO")
    return Selection(None, pool, None)
