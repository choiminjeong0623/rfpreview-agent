"""제품표(product_master) 행과 항목별 제품값. 값은 칸에 있는 것만 쓰고 지어내지 않는다 (CR-04)."""

import re
from dataclasses import dataclass, field

import psycopg
from psycopg.rows import dict_row

# 칸 → 단위 (원문 단위 그대로, CR-10)
COLUMN_UNITS = {"rated_voltage_kv": "kV", "rated_current_a": "A", "short_circuit_ka": "kA",
                "weight_kg": "kg", "rated_frequency": "Hz",
                "lightning_impulse_kv": "kV", "power_freq_withstand_kv": "kV",
                "switching_impulse_kv": "kV", "peak_current_ka": "kA",
                "making_current_ka": "kA", "breaking_time_ms": "ms",
                "closing_time_ms": "ms", "gas_leakage_percent": "%",
                "partial_discharge_pc": "pC", "warranty_months": "개월",
                "std_lead_time_weeks": "주", "moq": "ea",
                "list_price_usd": "USD", "maintenance_months": "개월",
                "service_life_years": "년"}
# 단시간 전류의 시간: "정격 단시간 전류 40 kA (3초)", "단시간전류 25kA/3s", "단시간 전류 40 kA 3초"
SHORT_TIME = re.compile(r"단시간\s*전류\s*(?:[\d.]+/)?[\d.]+\s*kA\s*[(/]?\s*(\d+(?:\.\d+)?)\s*"
                        r"(?:초|s(?![a-z]))")
# 카탈로그 문장에서 읽는 항목 (item_pm_mapping 열 = description)
DESCRIPTION_VALUES = {
    "gas_leakage_rate": (re.compile(r"누설[^,.]*?연\s*(\d+(?:\.\d+)?)\s*%\s*(이하|미만)?"), "%"),
}
MAX_TEMPERATURE = re.compile(r"to\s*\+?\s*(-?\d+(?:\.\d+)?)\s*°C")
IP_CODE = re.compile(r"IP\s*(\d)(\d)", re.IGNORECASE)
BOUND_WORDS = {"이하": "<=", "미만": "<"}
# 비교값 칸 (0012). comparison_values_assumed가 Y이면 이 칸의 값은 팀 가정이다 (CR-06)
COMPARISON_COLUMNS = frozenset({
    "lightning_impulse_kv", "power_freq_withstand_kv", "switching_impulse_kv", "peak_current_ka",
    "making_current_ka", "breaking_time_ms", "closing_time_ms", "gas_leakage_percent",
    "partial_discharge_pc", "cooling_type", "insulation_medium", "maintenance_months",
    "service_life_years"})


@dataclass
class Product:
    code: str
    name: str
    family: str
    description: str
    standards: str | None
    voltage_kv: float | None
    current_a: float | None
    short_circuit_ka: float | None
    frequency: str | None
    capacity: float | None
    capacity_unit: str | None
    weight_kg: float | None
    ip_rating: str | None
    operating_temp: str | None
    is_design_card: bool
    is_assumed: bool
    losses: tuple[float | None, float | None, float | None]
    loss_is_assumed: bool
    row: dict = field(repr=False, default_factory=dict)
    comparison_assumed: bool = False

    def value_assumed(self, column: str | None) -> bool:
        """그 칸의 값이 팀 가정인가: 제품 전체가 가정이거나, 가정인 비교값 칸에서 읽었으면."""
        return self.is_assumed or (column in COMPARISON_COLUMNS and self.comparison_assumed)

    @property
    def frequencies(self) -> list[str]:
        return [f.strip() for f in (self.frequency or "").split("/") if f.strip()]

    @property
    def standard_list(self) -> list[str]:
        return [normalize_standard(s) for s in re.split(r"[;,]", self.standards or "")
                if s.strip()]

    @property
    def short_time_s(self) -> float | None:
        m = SHORT_TIME.search(self.description)
        return float(m.group(1)) if m else None


@dataclass
class ProductValue:
    raw: str
    num: float | None = None
    unit: str | None = None
    operator: str = "="
    time_s: float | None = None
    items: list[str] = field(default_factory=list)     # 주파수 목록, 규격 목록
    column: str | None = None


def normalize_standard(text: str) -> str:
    """'IEC 62271-100(2012)' → 'IEC 62271-100' (판본은 비교하지 않고 확인 필요로 남긴다)."""
    text = re.sub(r"\(.*?\)", "", text).strip()
    return re.sub(r"\s+", " ", text).upper()


def _num(value) -> float | None:
    return float(value) if value is not None else None


def load_products(conn: psycopg.Connection) -> list[Product]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute("SELECT * FROM product_master ORDER BY product_code").fetchall()
    return [Product(
        code=r["product_code"], name=r["product_name"], family=r["family"],
        description=r["description"] or "", standards=r["standards"],
        voltage_kv=_num(r["rated_voltage_kv"]), current_a=_num(r["rated_current_a"]),
        short_circuit_ka=_num(r["short_circuit_ka"]), frequency=r["rated_frequency"],
        capacity=_num(r["rated_capacity"]), capacity_unit=r["rated_capacity_unit"],
        weight_kg=_num(r["weight_kg"]), ip_rating=r["ip_rating"],
        operating_temp=r["operating_temp"], is_design_card=r["is_design_card"],
        is_assumed=r["is_assumed"] == "Y",
        losses=(_num(r["noload_loss_kw"]), _num(r["load_loss_kw"]), _num(r["aux_loss_kw"])),
        loss_is_assumed=bool(r["loss_is_assumed"]), row=r,
        comparison_assumed=r.get("comparison_values_assumed") == "Y",
    ) for r in rows]


def _fmt(num: float) -> str:
    return f"{num:g}"


def product_value(product: Product, item_key: str, column: str | None) -> ProductValue | None:
    """연결표(item_pm_mapping)의 칸에서 항목값을 읽는다. 칸이 비면 None."""
    if column is None:
        return None
    if column == "description":
        pattern, unit = DESCRIPTION_VALUES.get(item_key, (None, None))
        m = pattern.search(product.description) if pattern else None
        if not m:
            return None
        return ProductValue(raw=m.group(0), num=float(m.group(1)), unit=unit,
                            operator=BOUND_WORDS.get(m.group(2) or "", "="), column=column)
    if column == "rated_frequency":
        if not product.frequencies:
            return None
        return ProductValue(raw=f"{product.frequency} Hz", unit="Hz", items=product.frequencies,
                            column=column)
    if column == "standards":
        if not product.standard_list:
            return None
        return ProductValue(raw=product.standards or "", items=product.standard_list,
                            column=column)
    if column == "operating_temp":
        m = MAX_TEMPERATURE.search(product.operating_temp or "")
        if not m:
            return None
        return ProductValue(raw=product.operating_temp or "", num=float(m.group(1)), unit="°C",
                            column=column)
    if column == "ip_rating":
        if not product.ip_rating:
            return None
        return ProductValue(raw=product.ip_rating, items=[product.ip_rating], column=column)
    if column == "product_name":
        return ProductValue(raw=product.name, column=column)
    if column == "rated_capacity":
        if product.capacity is None:
            return None
        return ProductValue(raw=f"{_fmt(product.capacity)} {product.capacity_unit}",
                            num=product.capacity, unit=product.capacity_unit, column=column)
    value = product.row.get(column)
    if value is None or value == "":
        return None
    if column in COLUMN_UNITS:
        num = float(value)
        time = product.short_time_s if column == "short_circuit_ka" else None
        raw = f"{_fmt(num)} {COLUMN_UNITS[column]}" + (f" ({_fmt(time)}초)" if time else "")
        return ProductValue(raw=raw, num=num, unit=COLUMN_UNITS[column], time_s=time,
                            column=column)
    return ProductValue(raw=str(value), column=column)
