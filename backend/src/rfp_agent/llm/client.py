import json
import logging
import threading
from dataclasses import astuple, dataclass, replace
from typing import Protocol

log = logging.getLogger(__name__)

MAX_RETRIES = 2                 # CR-12: 정해진 횟수만 재시도
FAILURE_MESSAGE = "처리 실패 — 다시 시도"
CONFIG_FAILURE_MESSAGE = "AI 키 또는 모델 설정 오류 — 설정 확인"
EMBED_MODEL = "gemini-embedding-001"   # 뜻 찾기 문장 벡터 (add-meaning-search)
EMBED_DIMS = 768
EMBED_BATCH = 100
CONFIG_ERROR_CODES = {400, 401, 403, 404}   # 다시 물어도 안 되는 요청 오류 (429 요청 많음은 재시도)


_USAGE_LOCK = threading.Lock()


class LLMFailure(RuntimeError):
    """재시도 뒤에도 응답을 받지 못함."""


class LLMFormatError(LLMFailure):
    """답의 형식이 틀림(JSON 아님, 검사 실패). temperature 0이라 다시 묻지 않는다."""


class LLMConfigError(LLMFailure):
    """키·권한·모델 설정 오류. 다시 물어도 안 되므로 바로 멈춘다."""


@dataclass
class Usage:
    """언어 모델 사용량 (실행 기록, add-run-log). 실행마다 차이를 저장한다."""
    calls: int = 0              # 요청 수 (재시도 포함)
    retries: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0

    def add(self, **counts: int) -> None:
        """여러 스레드가 동시에 더해도 빠지지 않게 잠금 안에서 더한다 (동시 호출)."""
        with _USAGE_LOCK:
            for name, n in counts.items():
                setattr(self, name, getattr(self, name) + n)

    def copy(self) -> "Usage":
        return replace(self)

    def minus(self, before: "Usage") -> "Usage":
        return Usage(*(a - b for a, b in zip(astuple(self), astuple(before), strict=True)))


def usage_of(llm: object) -> Usage | None:
    """사용량을 세는 모델이면 그 Usage (테스트 대역 등은 없을 수 있다)."""
    usage = getattr(llm, "usage", None)
    return usage if isinstance(usage, Usage) else None


class LLM(Protocol):
    model: str

    def generate_json(self, prompt: str, schema: dict) -> dict: ...


def _is_config_error(exc: Exception) -> bool:
    """키·권한·모델 이름 오류 (google.genai ClientError의 code로 본다)."""
    code = getattr(exc, "code", None)
    return isinstance(code, int) and code in CONFIG_ERROR_CODES


def call_with_retry(llm: LLM, prompt: str, schema: dict, validate) -> dict:
    """응답을 검증한다. 연결·시간 초과·서버 오류만 MAX_RETRIES번 더 시도한다 (CR-12).

    형식 오류(JSON 아님, 검사 실패)는 같은 질문에 같은 답이 나오므로 다시 묻지 않고
    LLMFormatError, 키·권한·모델 설정 오류는 LLMConfigError로 바로 올린다
    (update-llm-retry-kinds).
    """
    last: Exception | None = None
    usage = usage_of(llm)
    for attempt in range(MAX_RETRIES + 1):
        if usage:
            usage.add(calls=1, retries=int(attempt > 0))
        try:
            data = llm.generate_json(prompt, schema)
        except json.JSONDecodeError as exc:
            log.warning("언어 모델 답이 JSON이 아님: %s", exc)
            raise LLMFormatError(FAILURE_MESSAGE) from exc
        except Exception as exc:  # noqa: BLE001 - 연결·시간 초과·서버 오류는 재시도
            if _is_config_error(exc):
                log.warning("언어 모델 설정 오류: %s", exc)
                raise LLMConfigError(CONFIG_FAILURE_MESSAGE) from exc
            last = exc
            log.warning("언어 모델 호출 실패 (%d/%d): %s", attempt + 1, MAX_RETRIES + 1, exc)
            continue
        try:
            validate(data)
        except Exception as exc:  # noqa: BLE001 - 검사 실패는 모두 형식 오류
            log.warning("언어 모델 답 형식 오류: %s", exc)
            raise LLMFormatError(FAILURE_MESSAGE) from exc
        return data
    raise LLMFailure(FAILURE_MESSAGE) from last


def embed_with_retry(llm: object, texts: list[str]) -> list[list[float]]:
    """문장 벡터를 EMBED_BATCH개씩 받는다. 재시도·오류 종류는 call_with_retry와 같다.

    벡터 요청은 실행 기록의 AI 호출 수에 넣지 않는다(토큰 수를 주지 않음).
    """
    out: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        part = texts[start:start + EMBED_BATCH]
        last: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                vectors = llm.embed(part)
            except Exception as exc:  # noqa: BLE001 - 연결·시간 초과·서버 오류는 재시도
                if _is_config_error(exc):
                    raise LLMConfigError(CONFIG_FAILURE_MESSAGE) from exc
                last = exc
                log.warning("문장 벡터 요청 실패 (%d/%d): %s", attempt + 1, MAX_RETRIES + 1, exc)
                continue
            if len(vectors) != len(part) or not all(vectors):
                raise LLMFormatError(FAILURE_MESSAGE)
            out.extend(vectors)
            break
        else:
            raise LLMFailure(FAILURE_MESSAGE) from last
    return out


class GeminiLLM:
    def __init__(self, api_key: str, model: str, workers: int = 4, timeout_s: float = 120):
        from google import genai

        self.model = model
        self.usage = Usage()
        self.workers = workers              # 동시에 보낼 묶음 수 (llm/parallel.py)
        self.timeout_s = timeout_s
        # 요청 하나의 시간 제한(밀리초). 넘으면 예외 → call_with_retry가 다시 시도(CR-12)
        self._client = genai.Client(api_key=api_key,
                                    http_options={"timeout": int(timeout_s * 1000)})

    def generate_json(self, prompt: str, schema: dict) -> dict:
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config={"response_mime_type": "application/json", "response_schema": schema,
                    "temperature": 0},
        )
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            self.usage.add(input_tokens=meta.prompt_token_count or 0,
                           output_tokens=meta.candidates_token_count or 0,
                           thinking_tokens=getattr(meta, "thoughts_token_count", 0) or 0)
        return json.loads(response.text)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """문장 벡터 (뜻 찾기, add-meaning-search)."""
        response = self._client.models.embed_content(
            model=EMBED_MODEL, contents=texts, config={"output_dimensionality": EMBED_DIMS})
        return [list(e.values) for e in response.embeddings]


class HTTPStatusFailure(RuntimeError):
    """사내 모델 HTTP 오류. code로 설정 오류(400·401·403·404)와 재시도할 오류를 가른다."""

    def __init__(self, code: int, message: str):
        super().__init__(f"HTTP {code}: {message}")
        self.code = code


class LocalLLM:
    """사내 서버의 OpenAI 호환 모델 (add-ai-mode). 정한 주소로만 보낸다.

    vLLM·Ollama·사내 게이트웨이가 주는 /chat/completions·/embeddings를 부른다.
    """

    def __init__(self, base_url: str, model: str, api_key: str | None = None,
                 embed_model: str | None = None, workers: int = 4, timeout_s: float = 120,
                 transport=None):
        import httpx

        self.model = model
        self.embed_model = embed_model
        self.usage = Usage()
        self.workers = workers
        self.timeout_s = timeout_s
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(base_url=base_url.rstrip("/") + "/", headers=headers,
                                  timeout=timeout_s, transport=transport)

    def _post(self, path: str, body: dict) -> dict:
        response = self._http.post(path, json=body)
        if response.status_code >= 400:
            raise HTTPStatusFailure(response.status_code, response.text[:200])
        return response.json()

    def generate_json(self, prompt: str, schema: dict) -> dict:
        data = self._post("chat/completions", {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "answer", "schema": schema}},
        })
        usage = data.get("usage") or {}
        self.usage.add(input_tokens=usage.get("prompt_tokens") or 0,
                       output_tokens=usage.get("completion_tokens") or 0)
        return json.loads(data["choices"][0]["message"]["content"])

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.embed_model:
            raise HTTPStatusFailure(404, "사내 벡터 모델이 정해지지 않음 (RFP_LOCAL_EMBED_MODEL)")
        data = self._post("embeddings", {"model": self.embed_model, "input": texts})
        rows = sorted(data["data"], key=lambda r: r.get("index", 0))
        return [list(r["embedding"]) for r in rows]


AI_MODES = ("gemini", "local", "off")


def ai_mode(settings) -> str:
    """지금 쓰는 방식: GEMINI · LOCAL · OFF. 설정이 모자라면 OFF(규칙만)."""
    mode = (settings.rfp_ai_mode or "gemini").strip().lower()
    if mode not in AI_MODES:
        log.warning("알 수 없는 RFP_AI_MODE=%s — AI 끄기로 처리", mode)
        return "OFF"
    if mode == "gemini":
        return "GEMINI" if settings.gemini_api_key else "OFF"
    if mode == "local":
        return "LOCAL" if settings.rfp_local_llm_url and settings.rfp_local_llm_model else "OFF"
    return "OFF"


def ai_model(settings) -> str | None:
    return {"GEMINI": settings.gemini_model, "LOCAL": settings.rfp_local_llm_model,
            "OFF": None}[ai_mode(settings)]


def embed_model(settings) -> str | None:
    """지금 방식의 문장 벡터 모델 이름 (벡터 저장 열쇠)."""
    return {"GEMINI": EMBED_MODEL, "LOCAL": settings.rfp_local_embed_model,
            "OFF": None}[ai_mode(settings)]


def make_llm(settings) -> LLM | None:
    """방식에 따라 Gemini·사내 모델·None.

    None이면 AI 보조 단계를 건너뛰고 코드 규칙만으로 처리한다.
    """
    mode = ai_mode(settings)
    workers, timeout_s = settings.rfp_llm_workers, settings.rfp_llm_timeout_s
    if mode == "GEMINI":
        return GeminiLLM(settings.gemini_api_key, settings.gemini_model, workers, timeout_s)
    if mode == "LOCAL":
        return LocalLLM(settings.rfp_local_llm_url, settings.rfp_local_llm_model,
                        settings.rfp_local_llm_key, settings.rfp_local_embed_model,
                        workers, timeout_s)
    return None
