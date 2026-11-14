"""협조 요청 메일 발송 (update-role-handoff-mail). SMTP는 이 모듈에서만 부른다.

설정은 환경 변수만 쓴다(RFP_SMTP_*, RFP_MAIL_*). 부서 주소가 없으면 지어내지 않고 보내지 않는다.
테스트는 set_mailer(FakeMailer(...))로 바꿔 보낸 메일을 목록으로 확인한다.
"""

import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from rfp_agent.config import get_settings

log = logging.getLogger(__name__)

MAX_RETRIES = 3                 # CR-12: 정해진 횟수만 다시 시도 (처음 1번 + 3번)
TIMEOUT_S = 10


class MailFailure(RuntimeError):
    """다시 시도한 뒤에도 보내지 못함."""


class Mailer(Protocol):
    def address(self, role: str) -> str | None: ...
    def sender(self) -> str: ...
    def send(self, message: EmailMessage) -> None: ...


class SmtpMailer:
    """환경 변수로 정한 SMTP 서버로 보낸다."""

    def address(self, role: str) -> str | None:
        s = get_settings()
        value = {"COST": s.rfp_mail_cost, "QUALITY": s.rfp_mail_quality,
                 "SALES": s.rfp_mail_sales}.get(role)
        return (value or "").strip() or None

    def sender(self) -> str:
        return get_settings().rfp_mail_from

    def send(self, message: EmailMessage) -> None:
        s = get_settings()
        if not s.rfp_smtp_host:
            raise MailFailure("메일 서버(RFP_SMTP_HOST)가 설정되지 않았습니다.")
        with smtplib.SMTP(s.rfp_smtp_host, s.rfp_smtp_port, timeout=TIMEOUT_S) as smtp:
            if s.rfp_smtp_user:
                smtp.starttls()
                smtp.login(s.rfp_smtp_user, s.rfp_smtp_password or "")
            smtp.send_message(message)


@dataclass
class FakeMailer:
    """테스트용: 보낸 메일을 모은다. fail_times만큼 먼저 실패한다(발송 실패 시나리오)."""
    addresses: dict[str, str] = field(default_factory=dict)
    fail_times: int = 0
    sent: list[EmailMessage] = field(default_factory=list)
    tries: int = 0

    def address(self, role: str) -> str | None:
        return self.addresses.get(role)

    def sender(self) -> str:
        return "rfp-agent@test"

    def send(self, message: EmailMessage) -> None:
        self.tries += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionRefusedError("메일 서버가 응답하지 않습니다")
        self.sent.append(message)


_mailer: Mailer | None = None


def get_mailer() -> Mailer:
    return _mailer or SmtpMailer()


def set_mailer(mailer: Mailer | None) -> None:
    """테스트에서 가짜 발송기로 바꾼다. None이면 SMTP로 돌아간다."""
    global _mailer
    _mailer = mailer


def send_with_retry(mailer: Mailer, message: EmailMessage) -> None:
    last: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            mailer.send(message)
            return
        except MailFailure:
            raise                                   # 설정이 없으면 다시 시도해도 같다
        except Exception as exc:  # noqa: BLE001 - 어떤 발송 오류든 재시도 대상
            last = exc
            log.warning("메일 발송 실패 (%d/%d): %s", attempt + 1, MAX_RETRIES + 1, exc)
    raise MailFailure(f"메일을 보내지 못했습니다: {last}") from last
