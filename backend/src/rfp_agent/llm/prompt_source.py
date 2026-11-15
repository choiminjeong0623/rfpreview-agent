"""프롬프트를 어디서 가져올지 (add-langfuse-prompts, ADR-010).

RFP_LANGFUSE=off(기본)면 코드에 있는 틀(tasks.TEMPLATES)과 판(tasks.PROMPTS)만 쓴다.
on이면 self-host Langfuse에서 역할마다 `rfp-<역할>` 프롬프트의 RFP_LANGFUSE_LABEL 판을 가져온다.
가져온 판이 아래 검사에 걸리거나 Langfuse에 닿지 못하면 그 역할은 코드 판으로 돌아간다(CR-12).

- 판 설정(config)의 code_version이 지금 코드 판과 같아야 한다(코드가 채우는 자리가 그 판 기준)
- 자리표시자({{이름}}) 묶음이 코드 틀과 같아야 한다
- 문서 본문은 데이터라는 규칙(DATA_RULE, CR-14)이 그대로 들어 있어야 한다

실제로 쓴 판은 `t2+lf4`(코드 판 + Langfuse 버전)처럼 남긴다. 한 실행 안에서는 시작할 때 고른
판 묶음(snapshot)을 계속 쓴다(use). 프롬프트 글을 바꾸지 않으므로 판단·계산은 그대로 코드가 한다.
"""

import base64
import contextvars
import logging
import re
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from rfp_agent.config import get_settings

log = logging.getLogger(__name__)

NAME_PREFIX = "rfp-"
_SLOT = re.compile(r"\{\{(\w+)\}\}")

# 코드 판으로 돌아간 이유
FALLBACKS = {
    "NOT_CONFIGURED": "Langfuse 주소나 키가 없음",
    "UNREACHABLE": "Langfuse에 닿지 못함",
    "NOT_FOUND": "Langfuse에 이 표시를 붙인 판이 없음",
    "BAD_FORMAT": "글 프롬프트가 아님",
    "CODE_VERSION": "다른 코드 판에 맞춘 프롬프트",
    "PLACEHOLDERS": "자리표시자가 코드 틀과 다름",
    "DATA_RULE": "문서 본문은 데이터라는 규칙이 빠짐",
}


@dataclass(frozen=True)
class Resolved:
    role: str
    version: str                    # 실행 기록·재사용 열쇠에 남기는 판 (예: t2, t2+lf4)
    template: str
    source: str                     # CODE | LANGFUSE
    langfuse_version: int | None = None
    fallback: str | None = None     # 코드 판으로 돌아간 이유 (FALLBACKS 열쇠)


PromptSet = dict[str, Resolved]


def name_of(role: str) -> str:
    return NAME_PREFIX + role


def slots(template: str) -> set[str]:
    return set(_SLOT.findall(template))


def enabled() -> bool:
    return get_settings().rfp_langfuse == "on"


def code_set(fallback: str | None = None) -> PromptSet:
    from rfp_agent.llm import tasks

    return {role: Resolved(role, version, tasks.TEMPLATES[role], "CODE", None, fallback)
            for role, version in tasks.PROMPTS.items()}


class Client:
    """Langfuse 공개 API (Basic 인증: 공개 키·비밀 키). 필요한 것만 쓴다."""

    def __init__(self, host: str, public_key: str, secret_key: str, timeout: float = 5,
                 transport: httpx.BaseTransport | None = None):
        token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        self.http = httpx.Client(base_url=host.rstrip("/"), timeout=timeout,
                                 headers={"Authorization": f"Basic {token}"},
                                 transport=transport)

    def get_prompt(self, name: str, label: str) -> dict | None:
        r = self.http.get(f"/api/public/v2/prompts/{name}", params={"label": label})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def create_prompt(self, name: str, prompt: str, labels: list[str], config: dict,
                      message: str) -> dict:
        r = self.http.post("/api/public/v2/prompts", json={
            "name": name, "type": "text", "prompt": prompt, "labels": labels,
            "config": config, "commitMessage": message, "tags": ["rfp-agent"]})
        r.raise_for_status()
        return r.json()

    def set_labels(self, name: str, version: int, labels: list[str]) -> dict:
        r = self.http.patch(f"/api/public/v2/prompts/{name}/versions/{version}",
                            json={"newLabels": labels})
        r.raise_for_status()
        return r.json()

    def push_traces(self, otlp: dict) -> None:
        # OTLP/HTTP JSON. 직접 보내는 쪽은 수집 판 머리글을 붙인다(Langfuse 공개 API 문서)
        r = self.http.post("/api/public/otel/v1/traces", json=otlp,
                           headers={"x-langfuse-ingestion-version": "4"})
        r.raise_for_status()


    # ── 데이터셋·실험·점수 (add-langfuse-experiments) ──

    def get_dataset(self, name: str) -> dict | None:
        r = self.http.get(f"/api/public/v2/datasets/{quote(name, safe='')}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def create_dataset(self, name: str, description: str, metadata: dict) -> dict:
        r = self.http.post("/api/public/v2/datasets", json={
            "name": name, "description": description, "metadata": metadata})
        r.raise_for_status()
        return r.json()

    def upsert_dataset_item(self, dataset: str, item_id: str, input_: dict, expected: dict,
                            metadata: dict) -> dict:
        # 항목은 id로 덮어쓴다(upsert, Langfuse 데이터 모델 문서)
        r = self.http.post("/api/public/dataset-items", json={
            "datasetName": dataset, "id": item_id, "input": input_, "expectedOutput": expected,
            "metadata": metadata})
        r.raise_for_status()
        return r.json()

    def create_scores(self, scores: list[dict]) -> None:
        if not scores:
            return
        r = self.http.post("/api/public/scores", json=scores)
        r.raise_for_status()

    def project_id(self) -> str | None:
        """키가 속한 프로젝트 id (화면 주소용). 얻지 못하면 None."""
        r = self.http.get("/api/public/projects")
        r.raise_for_status()
        data = r.json().get("data") or []
        return data[0].get("id") if data else None


_transport: httpx.BaseTransport | None = None     # 테스트가 가짜 Langfuse를 끼우는 자리


def client() -> Client | None:
    s = get_settings()
    if not (s.langfuse_host and s.langfuse_public_key and s.langfuse_secret_key):
        return None
    return Client(s.langfuse_host, s.langfuse_public_key, s.langfuse_secret_key,
                  s.rfp_langfuse_timeout_s, _transport)


def check(role: str, data: dict) -> str | None:
    """가져온 판을 쓸 수 있으면 None, 아니면 돌아갈 이유."""
    from rfp_agent.llm import tasks

    text = data.get("prompt")
    if data.get("type", "text") != "text" or not isinstance(text, str):
        return "BAD_FORMAT"
    config = data.get("config") if isinstance(data.get("config"), dict) else {}
    if config.get("code_version") != tasks.PROMPTS[role]:
        return "CODE_VERSION"
    if slots(text) != slots(tasks.TEMPLATES[role]):
        return "PLACEHOLDERS"
    if tasks.DATA_RULE not in text:
        return "DATA_RULE"
    return None


def fetch(label: str) -> PromptSet:
    """역할마다 Langfuse 판을 가져와 검사한다. 닿지 못하면 나머지 역할은 묻지 않는다."""
    from rfp_agent.llm import tasks

    lf = client()
    if lf is None:
        return code_set("NOT_CONFIGURED")
    out: PromptSet = {}
    unreachable = False
    for role, code_version in tasks.PROMPTS.items():
        reason = "UNREACHABLE" if unreachable else None
        data = None
        if not unreachable:
            try:
                data = lf.get_prompt(name_of(role), label)
            except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                log.warning("Langfuse 프롬프트 %s 가져오기 실패: %s", name_of(role), exc)
                unreachable = isinstance(exc, httpx.TransportError)
                reason = "UNREACHABLE"
        if reason is None:
            reason = "NOT_FOUND" if data is None else check(role, data)
        if reason is None:
            n = int(data["version"])
            out[role] = Resolved(role, f"{code_version}+lf{n}", data["prompt"], "LANGFUSE", n)
        else:
            if reason != "NOT_FOUND":
                log.warning("Langfuse 프롬프트 %s: 코드 판을 씀 (%s)", name_of(role),
                            FALLBACKS[reason])
            out[role] = Resolved(role, code_version, tasks.TEMPLATES[role], "CODE", None, reason)
    return out


_cache: dict[str, tuple[float, tuple, PromptSet]] = {}
_lock = threading.Lock()


def resolve(fresh: bool = False) -> PromptSet:
    """지금 쓸 판 묶음. Langfuse 결과는 RFP_LANGFUSE_CACHE_S초 동안 다시 쓴다."""
    if not enabled():
        return code_set()
    from rfp_agent.llm import tasks

    s = get_settings()
    key = (s.rfp_langfuse_label, s.langfuse_host, tuple(sorted(tasks.PROMPTS.items())))
    with _lock:
        hit = _cache.get("set")
        young = hit and time.monotonic() - hit[0] < s.rfp_langfuse_cache_s
        if not fresh and hit and hit[1] == key and young:
            return hit[2]
        found = fetch(s.rfp_langfuse_label)
        _cache["set"] = (time.monotonic(), key, found)
        return found


def clear_cache() -> None:
    with _lock:
        _cache.clear()


_active: contextvars.ContextVar[PromptSet | None] = contextvars.ContextVar("prompt_set",
                                                                           default=None)


@contextmanager
def use(prompt_set: PromptSet) -> Iterator[PromptSet]:
    """이 안에서는 같은 판 묶음을 쓴다 (한 실행 안에서 판이 바뀌지 않게, CR-11)."""
    token = _active.set(prompt_set)
    try:
        yield prompt_set
    finally:
        _active.reset(token)


def current() -> PromptSet:
    active = _active.get()
    if active is not None:
        return active
    return resolve()


def versions(prompt_set: PromptSet | None = None) -> dict[str, str]:
    return {role: r.version for role, r in (prompt_set or current()).items()}


def sources(prompt_set: PromptSet | None = None) -> dict[str, dict]:
    """역할마다 가져온 곳과 코드 판으로 돌아간 이유 (실행 기록·프롬프트 관리 화면)."""
    return {role: {"source": r.source, "langfuse_version": r.langfuse_version,
                   "fallback": r.fallback}
            for role, r in (prompt_set or current()).items()}


def version_of(role: str | None) -> str | None:
    if not role:
        return None
    found = current().get(role)
    return found.version if found else None


def render(role: str, values: dict[str, str]) -> str:
    """틀의 {{이름}}을 한 번에 채운다. 채운 글 안의 {{…}}는 다시 채우지 않는다."""
    template = current()[role].template

    def fill(m: re.Match) -> str:
        return values[m.group(1)]

    return _SLOT.sub(fill, template)
