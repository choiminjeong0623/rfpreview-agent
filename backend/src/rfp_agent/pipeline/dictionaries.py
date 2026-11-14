"""DB에 적재된 사전을 처리 단계가 쓰는 모양으로 읽는다."""

from dataclasses import dataclass

import psycopg

from rfp_agent.pipeline.classify import CatalogEntry, KindRule, load_kind_rules
from rfp_agent.pipeline.risk import RiskExpression
from rfp_agent.pipeline.type_tags import TypeRule
from rfp_agent.pipeline.values import Dictionaries


@dataclass
class PipelineDicts:
    catalog: list[CatalogEntry]
    column_roles: dict[str, str]
    values: Dictionaries
    type_rules: list[TypeRule]
    risk_expressions: list[RiskExpression]
    projects: dict[str, int]
    kind_rules: list[KindRule]


def load(conn: psycopg.Connection) -> PipelineDicts:
    catalog = [CatalogEntry(*r) for r in conn.execute(
        "SELECT file_no, file_key, bundle, language, project_key FROM document_catalog")]
    roles = dict(conn.execute("SELECT header_text, column_role FROM column_role_dict"))
    aliases = dict(conn.execute("SELECT a.alias_text, a.item_key FROM item_alias a "
        "JOIN item_key k ON k.item_key = a.item_key WHERE k.active"))
    # 표준 항목의 한글 이름도 별칭으로 쓴다.
    for key, name in conn.execute("SELECT item_key, name_ko FROM item_key WHERE active"):
        aliases.setdefault(name, key)
    targets = list(conn.execute(
        "SELECT term, target_object, parent_object FROM target_object_dict"))
    rules = [TypeRule(*r) for r in conn.execute(
        "SELECT type_rule_id, rule_code, pattern, type_code, match_kind, priority "
        "FROM type_rule ORDER BY priority, rule_code")]
    exprs = [RiskExpression(*r) for r in conn.execute(
        "SELECT expr_id, expression, language, risk_kind FROM risk_expression WHERE active "
        "ORDER BY expr_id")]
    projects = dict(conn.execute(
        "SELECT project_key, project_id FROM project WHERE project_key IS NOT NULL"))
    return PipelineDicts(catalog, roles, Dictionaries.build(aliases, targets), rules, exprs,
                         projects, load_kind_rules(conn))
