from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql://rfp:rfp@localhost:5433/rfp"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    # AI 묶음 동시 호출 개수와 요청 하나의 시간 제한(초) (update-llm-concurrency, NFR-10)
    rfp_llm_workers: int = 4
    rfp_llm_timeout_s: float = 120
    # 한 검토의 문서를 동시에 처리하는 개수 (add-document-processors, NFR-10). 1이면 차례로
    rfp_doc_workers: int = 2
    # 스캔 PDF·그림 속 글자 읽기 (add-ocr): on | off. 엔진(Tesseract)이 없으면 off와 같다
    rfp_ocr: str = "on"
    # AI 사용 방식 (add-ai-mode, NFR-07): gemini(외부) | local(사내 OpenAI 호환 주소) | off(규칙만)
    rfp_ai_mode: str = "gemini"
    rfp_local_llm_url: str | None = None        # 예: http://llm.사내/v1
    rfp_local_llm_model: str | None = None
    rfp_local_llm_key: str | None = None
    rfp_local_embed_model: str | None = None    # 없으면 사내 방식에서 뜻 찾기 건너뜀
    migrations_dir: Path = REPO_ROOT / "db" / "migrations"
    seed_dir: Path = REPO_ROOT / "data" / "seed"
    # RFP 원문처럼 저장소에 올리지 않는 자료 (data/private/README.md)
    private_data_dir: Path = REPO_ROOT / "data" / "private"
    # 협조 요청 메일 (update-role-handoff-mail). 시연·개발은 Mailpit, 실제 사내 서버는 값만 바꾼다.
    rfp_smtp_host: str | None = None
    rfp_smtp_port: int = 1025
    rfp_smtp_user: str | None = None
    rfp_smtp_password: str | None = None
    rfp_mail_from: str = "rfp-agent@example.com"
    rfp_mail_cost: str | None = None
    rfp_mail_quality: str | None = None
    rfp_mail_sales: str | None = None

    @property
    def docx_dir(self) -> Path:
        return self.private_data_dir / "rfp_docx"

    @property
    def upload_dir(self) -> Path:
        """화면에서 올린 RFP 원문 (git에 올리지 않는 data/private 아래)."""
        return self.private_data_dir / "uploads"

    @property
    def txt_dir(self) -> Path:
        """팀 추출 txt. 있으면 원문 위치 줄 번호를 이 txt에 맞춘다."""
        return self.private_data_dir / "rfp_txt"


@lru_cache
def get_settings() -> Settings:
    return Settings()
