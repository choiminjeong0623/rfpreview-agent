"""판정 규칙 화면에서 규칙 사전을 고친다 (SCR-17, add-rule-editing).

원본은 DB이고 data/seed CSV는 시작값이다. 고칠 때마다 rule_edit에 줄 키(자연 키)와
바뀌기 전·후 값을 남기고, 사전을 다시 적재하면 남은 고침을 고친 순서대로 다시 적용한다.
지난 검토 결과가 가리키는 줄(비교 방향·위험 표현·표준 항목)은 지우지 않고 끈다(active).
"""

import json
import re
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from rfp_agent.db.seed import DOC_KINDS, SeedReport

EDITOR_ROLES = ("ENGINEER", "APPROVER")           # [제안] 엔지니어·승인자만 고친다
COMPARE_DIRECTIONS = {"EQ", "GE", "LE", "LT", "IN", "FILL", "TEXT", "AI", "SOURCE"}
ITEM_DIRECTIONS = COMPARE_DIRECTIONS - {"AI"}
STRENGTHS = {"HIGHER", "LOWER", "NONE"}
RISK_KINDS = {"BLANKET", "COST_SHIFT", "OPEN_SCOPE"}
LANGUAGES = {"en", "ko"}
ITEM_KEY = re.compile(r"[a-z][a-z0-9_]{0,39}")
UNDECIDED_CONTEXT = "(조건 미정)"                 # 적재와 같은 빈 조건 표시
DICTIONARY_NAMES = {"compare": "비교 방향", "risk-expressions": "위험 표현",
                    "items": "항목 이름", "doc-kinds": "문서 종류"}


class RuleEditError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Skip(Exception):
    """다시 적용할 수 없는 고침 (적재 보고에 적고 건너뛴다)."""


def _bad(field: str, why: str) -> RuleEditError:
    return RuleEditError(400, f"{field}: {why}")


def _text(value: dict, field: str, label: str, max_len: int, required: bool = True) -> str | None:
    raw = value.get(field)
    text = str(raw).strip() if raw is not None else ""
    if not text:
        if required:
            raise _bad(label, "비어 있습니다.")
        return None
    if len(text) > max_len:
        raise _bad(label, f"{max_len}자를 넘습니다.")
    return text


def _code(value: dict, field: str, label: str, codes: set[str],
          default: str | None = None) -> str | None:
    code = value.get(field) or default
    if code is None:
        return None
    if code not in codes:
        raise _bad(label, f"'{code}'은(는) 코드표에 없습니다 ({', '.join(sorted(codes))}).")
    return code


def _pattern(value: dict, field: str, label: str, required: bool) -> str | None:
    text = _text(value, field, label, 500, required)
    if text is not None:
        try:
            re.compile(text)
        except re.error as exc:
            raise _bad(label, f"'{text}'이 정규식이 아닙니다 ({exc}).") from None
    return text


@dataclass
class Dictionary:
    """사전 하나의 줄 키·검사·읽기·쓰기. 값(dict)은 API와 rule_edit 기록에 같은 모양으로 쓴다."""
    name: str
    table: str
    id_column: str
    key_fields: tuple[str, ...]
    fields: tuple[str, ...]

    def key_of(self, value: dict) -> dict:
        return {f: value.get(f) for f in self.key_fields}

    def value_of(self, row: dict) -> dict:
        return {f: row.get(f) for f in self.fields}

    def validate(self, conn: psycopg.Connection, value: dict) -> dict:
        raise NotImplementedError

    def _select(self) -> str:
        return f"SELECT * FROM {self.table}"

    def by_id(self, conn: psycopg.Connection, row_id: str) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(f"{self._select()} WHERE {self.id_column} = %s AND {self._live()}",
                              (self._id(row_id),)).fetchone()
        return self._decorate(conn, row) if row else None

    def by_key(self, conn: psycopg.Connection, key: dict) -> dict | None:
        """줄 키로 찾는다. 꺼진 줄도 찾는다 (같은 키로 다시 추가하면 되살린다)."""
        where = " AND ".join(f"{f} IS NOT DISTINCT FROM %s" for f in self.key_fields)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(f"{self._select()} WHERE {where}",
                              [key[f] for f in self.key_fields]).fetchone()
        return self._decorate(conn, row) if row else None

    def _id(self, row_id: str):
        try:
            return int(row_id)
        except ValueError:
            raise RuleEditError(404, f"{DICTIONARY_NAMES[self.name]} 사전에 {row_id}이(가) "
                                     "없습니다.") from None

    def _live(self) -> str:
        return "active"

    def _decorate(self, conn: psycopg.Connection, row: dict) -> dict:
        return row

    def is_live(self, row: dict) -> bool:
        return bool(row.get("active", True))

    def write(self, conn: psycopg.Connection, row: dict | None, value: dict) -> None:
        """row가 있으면 그 줄을 value로 바꾸고 켠다. 없으면 새로 넣는다."""
        cols = list(self.fields)
        if row is None:
            conn.execute(f"INSERT INTO {self.table} ({', '.join(cols)}) "
                         f"VALUES ({', '.join(['%s'] * len(cols))})", [value[c] for c in cols])
        else:
            sets = ", ".join(f"{c} = %s" for c in cols)
            conn.execute(f"UPDATE {self.table} SET {sets}, active = TRUE "
                         f"WHERE {self.id_column} = %s",
                         [*(value[c] for c in cols), row[self.id_column]])

    def remove(self, conn: psycopg.Connection, row: dict) -> None:
        conn.execute(f"UPDATE {self.table} SET active = FALSE WHERE {self.id_column} = %s",
                     (row[self.id_column],))


class CompareDictionary(Dictionary):
    def validate(self, conn, value):
        item_key = _text(value, "item_key", "표준 항목키", 40, required=False)
        if item_key and not conn.execute(
                "SELECT 1 FROM item_key WHERE item_key = %s AND active", (item_key,)).fetchone():
            raise _bad("표준 항목키", f"'{item_key}'이(가) 항목 이름 사전에 없습니다.")
        return {
            "table_name": _text(value, "table_name", "대상 표", 100),
            "item_no": _text(value, "item_no", "항목 번호", 20),
            "item_key": item_key,
            "direction": _code(value, "direction", "비교 방향", COMPARE_DIRECTIONS),
            "time_condition": bool(value.get("time_condition")),
            "strength_direction": _code(value, "strength_direction", "강점 방향", STRENGTHS),
            "process_note": _text(value, "process_note", "처리", 1000, required=False),
        }


class RiskDictionary(Dictionary):
    def validate(self, conn, value):
        return {
            "expression": _text(value, "expression", "표현", 100),
            "language": _code(value, "language", "언어", LANGUAGES),
            "risk_kind": _code(value, "risk_kind", "종류", RISK_KINDS),
            "context_rule": _text(value, "context_rule", "위험 후보로 보는 조건", 1000,
                                  required=False) or UNDECIDED_CONTEXT,
        }


class ItemDictionary(Dictionary):
    """표준 항목. 같은 뜻 원문 표현(item_alias)은 그 줄의 aliases 칸으로 함께 고친다."""

    def _id(self, row_id):
        return row_id

    def _decorate(self, conn, row):
        row["aliases"] = [a for (a,) in conn.execute(
            "SELECT alias_text FROM item_alias WHERE item_key = %s ORDER BY alias_text",
            (row["item_key"],))]
        return row

    def validate(self, conn, value):
        key = _text(value, "item_key", "표준 항목키", 40)
        if not ITEM_KEY.fullmatch(key):
            raise _bad("표준 항목키", "영어 소문자로 시작하고 소문자·숫자·밑줄만 씁니다.")
        aliases, seen = [], set()
        for raw in value.get("aliases") or []:
            alias = str(raw).strip()
            if len(alias) > 200:
                raise _bad("같은 뜻 원문 표현", f"'{alias[:20]}…'이 200자를 넘습니다.")
            if alias and alias.lower() not in seen:
                seen.add(alias.lower())
                aliases.append(alias)
        return {
            "item_key": key,
            "name_ko": _text(value, "name_ko", "한글 이름", 80),
            "default_direction": _code(value, "default_direction", "기본 비교 방향",
                                       ITEM_DIRECTIONS),
            "strength_direction": _code(value, "strength_direction", "강점 방향", STRENGTHS,
                                        default="NONE"),
            "note": _text(value, "note", "비고", 1000, required=False),
            "aliases": sorted(aliases),
        }

    def check_aliases(self, conn, value: dict) -> None:
        taken = conn.execute(
            "SELECT alias_text, item_key FROM item_alias "
            "WHERE alias_text = ANY(%s) AND item_key <> %s ORDER BY alias_text",
            (value["aliases"], value["item_key"])).fetchone()
        if taken:
            raise RuleEditError(409, f"같은 뜻 원문 표현 '{taken[0]}'은(는) 이미 "
                                     f"{taken[1]}에 있습니다.")

    def write(self, conn, row, value):
        self.check_aliases(conn, value)
        cols = ("name_ko", "default_direction", "strength_direction", "note")
        conn.execute(
            f"""INSERT INTO item_key (item_key, {', '.join(cols)}) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (item_key) DO UPDATE SET
                  {', '.join(f'{c} = EXCLUDED.{c}' for c in cols)}, active = TRUE""",
            (value["item_key"], *(value[c] for c in cols)))
        conn.execute("DELETE FROM item_alias WHERE item_key = %s", (value["item_key"],))
        for alias in value["aliases"]:
            conn.execute("INSERT INTO item_alias (item_key, alias_text) VALUES (%s, %s)",
                         (value["item_key"], alias))

    def users(self, conn, key: str) -> dict[str, int]:
        rules, mappings = conn.execute(
            """SELECT (SELECT count(*) FROM compare_rule WHERE item_key = %s AND active),
                      (SELECT count(*) FROM item_pm_mapping WHERE item_key = %s)""",
            (key, key)).fetchone()
        return {"비교 방향 규칙": rules, "제품표 연결": mappings}

    def remove(self, conn, row):
        used = {k: n for k, n in self.users(conn, row["item_key"]).items() if n}
        if used:
            where = ", ".join(f"{k} {n}줄" for k, n in used.items())
            raise RuleEditError(409, f"{row['item_key']}을(를) 쓰는 곳이 있어 지울 수 없습니다: "
                                     f"{where}.")
        # 꺼진 항목의 표현이 다른 항목에 쓰일 수 있게 표현은 지운다 (이력에 남음)
        conn.execute("DELETE FROM item_alias WHERE item_key = %s", (row["item_key"],))
        super().remove(conn, row)


class DocKindDictionary(Dictionary):
    """문서 종류 규칙. 가리키는 결과가 없어 실제로 지운다."""

    def _live(self):
        return "TRUE"

    def validate(self, conn, value):
        try:
            priority = int(value.get("priority"))
        except (TypeError, ValueError):
            raise _bad("순서", "숫자가 아닙니다.") from None
        if priority < 1:
            raise _bad("순서", "1 이상이어야 합니다.")
        return {
            "priority": priority,
            "doc_kind": _code(value, "doc_kind", "문서 종류", DOC_KINDS),
            "name_pattern": _pattern(value, "name_pattern", "파일 이름 표현", required=True),
            "page_pattern": _pattern(value, "page_pattern", "첫 장 표현", required=False),
            "note": _text(value, "note", "비고", 1000, required=False),
        }

    def write(self, conn, row, value):
        cols = list(self.fields)
        if row is None:
            conn.execute(f"INSERT INTO doc_kind_rule ({', '.join(cols)}) "
                         f"VALUES ({', '.join(['%s'] * len(cols))})", [value[c] for c in cols])
        else:
            conn.execute(f"UPDATE doc_kind_rule SET {', '.join(f'{c} = %s' for c in cols)} "
                         "WHERE doc_kind_rule_id = %s",
                         [*(value[c] for c in cols), row["doc_kind_rule_id"]])

    def remove(self, conn, row):
        conn.execute("DELETE FROM doc_kind_rule WHERE doc_kind_rule_id = %s",
                     (row["doc_kind_rule_id"],))


DICTIONARIES: dict[str, Dictionary] = {
    "compare": CompareDictionary(
        "compare", "compare_rule", "compare_rule_id", ("table_name", "item_no", "item_key"),
        ("table_name", "item_no", "item_key", "direction", "time_condition",
         "strength_direction", "process_note")),
    "risk-expressions": RiskDictionary(
        "risk-expressions", "risk_expression", "expr_id", ("expression",),
        ("expression", "language", "risk_kind", "context_rule")),
    "items": ItemDictionary(
        "items", "item_key", "item_key", ("item_key",),
        ("item_key", "name_ko", "default_direction", "strength_direction", "note", "aliases")),
    "doc-kinds": DocKindDictionary(
        "doc-kinds", "doc_kind_rule", "doc_kind_rule_id", ("priority",),
        ("priority", "doc_kind", "name_pattern", "page_pattern", "note")),
}


def dictionary(name: str) -> Dictionary:
    try:
        return DICTIONARIES[name]
    except KeyError:
        raise RuleEditError(404, f"사전 '{name}'이(가) 없습니다.") from None


def _check_actor(conn: psycopg.Connection, actor_id: int | None) -> int:
    if actor_id is None:
        row = conn.execute("SELECT min(user_id) FROM app_user WHERE role = 'ENGINEER'").fetchone()
        actor_id = row[0]
    role = conn.execute("SELECT role FROM app_user WHERE user_id = %s",
                        (actor_id,)).fetchone() if actor_id is not None else None
    if role is None:
        raise RuleEditError(400, f"사용자 {actor_id}이(가) 없습니다.")
    if role[0] not in EDITOR_ROLES:
        raise RuleEditError(403, "규칙은 엔지니어·승인자만 고칠 수 있습니다.")
    return actor_id


def _reason(reason: str | None) -> str:
    if not reason or not reason.strip():
        raise _bad("사유", "고친 사유를 적어 주세요.")
    return reason.strip()


def _same_key(d: Dictionary, row: dict | None, value: dict, current: dict | None = None) -> None:
    """같은 키의 다른 줄이 있으면 막는다. 꺼진 줄은 추가로만 되살린다."""
    if row is None or (current is not None and row[d.id_column] == current[d.id_column]):
        return
    if d.is_live(row):
        raise RuleEditError(409, f"같은 키의 줄이 이미 있습니다: {_key_text(d.key_of(value))}.")
    if current is not None:
        raise RuleEditError(409, f"삭제한 줄과 키가 같습니다: {_key_text(d.key_of(value))}. "
                                 "그 키로 새로 추가하면 되살립니다.")


def _key_text(key: dict) -> str:
    return " / ".join(str(v) for v in key.values() if v is not None)


def _jsonb(value: dict | None) -> Jsonb | None:
    return None if value is None else Jsonb(json.loads(json.dumps(value, default=str)))


def _record(conn, d: Dictionary, key: dict, action: str, before: dict | None,
            after: dict | None, reason: str, actor_id: int) -> int:
    return conn.execute(
        """INSERT INTO rule_edit (dictionary, row_key, action, before_value, after_value,
                                  reason, actor_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING edit_id""",
        (d.name, _jsonb(key), action, _jsonb(before), _jsonb(after), reason,
         actor_id)).fetchone()[0]


def add(conn: psycopg.Connection, name: str, value: dict, reason: str | None,
        actor_id: int | None = None) -> dict:
    """새 줄을 넣는다 (꺼진 같은 키 줄이 있으면 되살린다). 기록한 고침을 낸다."""
    d = dictionary(name)
    with conn.transaction():
        actor_id = _check_actor(conn, actor_id)
        reason = _reason(reason)
        value = d.validate(conn, value)
        row = d.by_key(conn, d.key_of(value))
        _same_key(d, row, value)
        d.write(conn, row, value)
        edit_id = _record(conn, d, d.key_of(value), "ADD", None, value, reason, actor_id)
    return edit(conn, edit_id)


def update(conn: psycopg.Connection, name: str, row_id: str, value: dict, reason: str | None,
           actor_id: int | None = None) -> dict:
    d = dictionary(name)
    with conn.transaction():
        actor_id = _check_actor(conn, actor_id)
        current = _current(conn, d, row_id)
        reason = _reason(reason)
        value = d.validate(conn, value)
        if name == "items" and value["item_key"] != current["item_key"]:
            raise _bad("표준 항목키", "바꿀 수 없습니다. 새 항목으로 추가해 주세요.")
        _same_key(d, d.by_key(conn, d.key_of(value)), value, current)
        before = d.value_of(current)
        d.write(conn, current, value)
        edit_id = _record(conn, d, d.key_of(before), "EDIT", before, value, reason, actor_id)
    return edit(conn, edit_id)


def delete(conn: psycopg.Connection, name: str, row_id: str, reason: str | None,
           actor_id: int | None = None) -> dict:
    d = dictionary(name)
    with conn.transaction():
        actor_id = _check_actor(conn, actor_id)
        current = _current(conn, d, row_id)
        reason = _reason(reason)
        d.remove(conn, current)
        before = d.value_of(current)
        edit_id = _record(conn, d, d.key_of(before), "DELETE", before, None, reason, actor_id)
    return edit(conn, edit_id)


def _current(conn, d: Dictionary, row_id: str) -> dict:
    row = d.by_id(conn, row_id)
    if row is None:
        raise RuleEditError(404, f"{DICTIONARY_NAMES[d.name]} 사전에 {row_id}이(가) 없습니다.")
    return row


EDIT_SELECT = """SELECT e.edit_id, e.dictionary, e.row_key, e.action, e.before_value,
                        e.after_value, e.reason, e.actor_id, u.user_name AS actor_name,
                        e.edited_at, e.discarded_at
                 FROM rule_edit e JOIN app_user u ON u.user_id = e.actor_id"""


def _with_after_key(row: dict) -> dict:
    d = DICTIONARIES[row["dictionary"]]
    row["after_key"] = d.key_of(row["after_value"]) if row["after_value"] else None
    return row


def edit(conn: psycopg.Connection, edit_id: int) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        return _with_after_key(cur.execute(f"{EDIT_SELECT} WHERE e.edit_id = %s",
                                           (edit_id,)).fetchone())


def edits(conn: psycopg.Connection, name: str | None = None) -> list[dict]:
    """고침 이력, 새것부터. 버린 고침도 discarded_at과 함께 낸다 (이력은 지우지 않는다)."""
    if name is not None:
        dictionary(name)
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(f"{EDIT_SELECT} WHERE (%(name)s::text IS NULL OR e.dictionary = "
                           "%(name)s) ORDER BY e.edit_id DESC", {"name": name}).fetchall()
    return [_with_after_key(r) for r in rows]


def _reapply(conn: psycopg.Connection, d: Dictionary, action: str, key: dict,
             after: dict | None) -> None:
    """고침 하나를 다시 적용한다. 화면 고침과 달리 추가는 같은 키 줄이 있으면 덮어쓴다."""
    try:
        if action == "ADD":
            row = d.by_key(conn, key)
            d.write(conn, row, after)
            return
        current = d.by_key(conn, key)
        if current is None or not d.is_live(current):
            raise Skip("고칠 줄이 사전 파일에 없음")
        if action == "EDIT":
            other = d.by_key(conn, d.key_of(after))
            if other is not None and other[d.id_column] != current[d.id_column]:
                raise Skip(f"바꾼 키 {_key_text(d.key_of(after))}의 줄이 이미 있음")
            d.write(conn, current, after)
        else:
            d.remove(conn, current)
    except RuleEditError as exc:
        raise Skip(str(exc)) from None


def replay(conn: psycopg.Connection, report: SeedReport) -> None:
    """사전 파일을 넣은 뒤, 버리지 않은 고침을 고친 순서대로 다시 적용한다."""
    rows = conn.execute("SELECT edit_id, dictionary, row_key, action, after_value FROM rule_edit "
                        "WHERE discarded_at IS NULL ORDER BY edit_id").fetchall()
    applied = 0
    for edit_id, name, key, action, after in rows:
        try:
            with conn.transaction():
                _reapply(conn, DICTIONARIES[name], action, key, after)
            applied += 1
        except Skip as exc:
            report.skipped.append(f"규칙 고침 {edit_id} ({DICTIONARY_NAMES[name]} "
                                  f"{_key_text(key)}): {exc}")
    report.counts["다시 적용한 규칙 고침"] = applied
