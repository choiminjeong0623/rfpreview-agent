import os
import re
import zlib
from pathlib import Path

import psycopg
import pytest

from rfp_agent.config import get_settings
from rfp_agent.llm.client import Usage

FIXTURES = Path(__file__).parent / "fixtures"
# 판정 이후 단계 테스트용 고정 제품표. 실제 제품표(data/seed/products)가 바뀌어도 시나리오가
# 같은 입력으로 돌도록 따로 둔다. 실제 제품 데이터로 쓰지 않는다.
JUDGMENT_PRODUCTS = FIXTURES / "judgment_products"
JUDGMENT_PRODUCT_FILES = [JUDGMENT_PRODUCTS / f for f in ("products_a.csv", "products_b.csv")]
JUDGMENT_LOSS_FILE = JUDGMENT_PRODUCTS / "losses.csv"


@pytest.fixture
def db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL이 없어 DB 테스트를 건너뜀")
    return url


@pytest.fixture
def empty_db(db_url: str):
    """빈 public 스키마를 가진 연결. 테스트용 DB만 가리켜야 한다."""
    with psycopg.connect(db_url) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.commit()
        yield conn


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def seeded_db(empty_db, settings):
    """마이그레이션과 규칙 사전까지 넣은 빈 DB."""
    from rfp_agent.db.migrate import migrate
    from rfp_agent.db.seed import seed_rules

    migrate(empty_db, settings.migrations_dir)
    seed_rules(empty_db, settings.seed_dir)
    empty_db.commit()
    return empty_db


# 합성 문서를 판정 대상(묶음 A)으로 보게 하는 문서 목록 행
CATALOG = [(91, "synthetic_judgment", "A"), (92, "synthetic_feeder", "A"),
           (93, "synthetic_154kV_bundle_a", "A")]


@pytest.fixture
def db(seeded_db, settings):
    """규칙 사전 + 제품표 + 합성 문서 목록까지 넣은 DB (판정 이후 단계 테스트용)."""
    from rfp_agent.db.seed import seed_products

    seed_products(seeded_db, JUDGMENT_PRODUCT_FILES, JUDGMENT_LOSS_FILE)
    for file_no, key, bundle in CATALOG:
        seeded_db.execute("INSERT INTO document_catalog (file_no, file_key, bundle, language) "
                          "VALUES (%s, %s, %s, 'en')", (file_no, key, bundle))
    seeded_db.commit()
    return seeded_db


@pytest.fixture
def spec(tmp_path):
    """판정 대상 합성 데이터시트 (230 kV GIS 4,000 A 세 곳, 115 kV GIS)."""
    from tests.docx_factory import build_judgment_spec

    return build_judgment_spec(tmp_path / "synthetic_judgment.docx")


def word_vector(text: str, dims: int = 256) -> list[float]:
    vec = [0.0] * dims
    for word in re.findall(r"\w+", text.lower()):
        vec[zlib.crc32(word.encode()) % dims] += 1.0
    return vec


class FakeLLM:
    """언어 모델 대역. 받은 프롬프트를 모두 기록하고, 스키마에 맞는 기본 답을 낸다."""

    model = "fake-model"

    def __init__(self, fail: bool = False, text: str | None = None):
        self.fail = fail
        self.text = text            # 문장 초안 답 (없으면 자리표시자를 모두 쓴 문장)
        self.prompts: list[str] = []
        self.usage = Usage()        # 실행 기록(add-run-log): 요청마다 토큰 100·10·5로 센다

    def generate_json(self, prompt: str, schema: dict) -> dict:
        self.prompts.append(prompt)
        self.usage.add(input_tokens=100, output_tokens=10, thinking_tokens=5)
        if self.fail:
            raise TimeoutError("응답 시간 초과")
        field = next(iter(schema["properties"]))
        if field == "doc_kind":
            return {"doc_kind": "UNKNOWN"}
        if field == "claims":
            # 첫 근거 조각을 대고, 그 조각의 앞 20글자를 그대로 인용한다
            eid, text = re.search(r"^\[(E-\d+-\d+)\] (.*)$", prompt, re.MULTILINE).groups()
            return {"claims": [{"text": "두 값의 적용 대상이 달라 확인이 필요하다.",
                                "exact_quote": text[:20], "evidence_ids": [eid],
                                "relation": "INFERRED"}]}
        # 묶음 답은 줄 번호(n)와 함께 낸다 (update-ai-answer-checks)
        count = len(re.findall(r"^\d+\. ", prompt, re.MULTILINE))
        if field == "asks":
            # 협조 요청 확인할 점 (add-handoff-questions): asks에 n → 문장을 두면 그 답
            return {"asks": [{"n": n, "text": self.asks.get(n, "이 조건을 반영할 수 있는지 "
                                                         "확인 부탁드립니다.")}
                             for n in range(count - self.asks_short)]}
        if field == "texts":
            lines = re.findall(r"^\d+\. .*\(자리표시자: (.*)\)$", prompt, re.MULTILINE)
            # text의 "{all}"은 그 줄의 자리표시자 전부로 바꾼다 (자리표시자를 모두 써야 AI 문장)
            return {"texts": [{"n": n, "text": (self.text or "초안: {all}").replace(
                "{all}", " ".join(re.findall(r"\{\w+\}", marks)))}
                for n, marks in enumerate(lines)]}
        default = {"labels": "REQUIREMENT", "types": "NONE", "verdicts": "YES"}[field]
        return {field: [{"n": n, "v": default} for n in range(count)]}

    asks: dict[int, str] = {}
    asks_short = 0                  # 답에서 뺄 줄 수 (줄 번호 형식 오류 시험)

    # 뜻 찾기(add-meaning-search): 단어를 해시해 세는 벡터. 같은 단어가 많을수록 가깝다.
    # vectors에 글을 넣으면 그 벡터를 쓰고, embed_fail이면 매번 실패한다.
    vectors: dict[str, list[float]] = {}
    embed_fail = False

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embedded = getattr(self, "embedded", []) + list(texts)
        if self.embed_fail:
            raise TimeoutError("응답 시간 초과")
        return [self.vectors.get(t) or word_vector(t) for t in texts]


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture(autouse=True)
def fake_mailer():
    """협조 요청 메일은 진짜로 보내지 않는다(update-role-handoff-mail). 보낸 메일은 .sent에."""
    from rfp_agent.notify.mail import FakeMailer, set_mailer

    mailer = FakeMailer(addresses={"COST": "cost@test", "QUALITY": "quality@test",
                                   "SALES": "sales@test"})
    set_mailer(mailer)
    yield mailer
    set_mailer(None)
