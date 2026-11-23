"""실행 소유권을 저장 순간에 확인한다 (update-run-fencing, NFR-12).

`check_cancel`은 토큰을 읽고 비교만 해서, 비교한 뒤 커밋하기 전에 다른 연결이 작업을 다시 넣으면
밀려난 실행의 결과가 저장됐다. 여기서는 커밋 직전에, 같은 트랜잭션 안에서 검토 행을 잠그고
(`FOR UPDATE`) 토큰을 다시 읽는다. 작업 넣기(`run_queue.enqueue`·`reclaim`)도 같은 행을
UPDATE로 잠그므로 둘 중 먼저 잠근 쪽이 이기고 다른 쪽은 기다린다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.pq import TransactionStatus


class RunSuperseded(Exception):
    """이 실행의 토큰이 더는 검토의 토큰이 아니다: 새 실행이 맡았다 (add-run-queue).

    결과를 쓰지 않고 멈춘다 (NFR-12, 한 검토에 도는 실행은 하나).
    """


def ensure_owned(conn: psycopg.Connection, run_id: int, token: str) -> None:
    """검토 행을 잠그고 토큰이 아직 이 실행의 것인지 본다. 아니면 RunSuperseded.

    잠금은 부른 트랜잭션이 끝날 때(커밋·되돌림) 풀린다.
    """
    row = conn.execute("SELECT run_token::text FROM review_run WHERE run_id = %s FOR UPDATE",
                       (run_id,)).fetchone()
    if row is None or row[0] != token:
        raise RunSuperseded(run_id)


class OwnedConnection:
    """처리 흐름의 연결 감싸개: 커밋할 때마다 소유권을 확인한다.

    `commit()`과 바깥 `transaction()` 블록의 끝에서 `ensure_owned`를 부르고, 나머지는 원래
    연결로 넘긴다. 단계가 부르는 함수(목록·손실 환산 등) 안의 커밋도 고치지 않고 같은 규칙을
    따른다. 그 함수들을 사람 동작 API에서 부를 때는 감싸지 않은 연결이라 지금과 같다.
    """

    def __init__(self, conn: psycopg.Connection, run_id: int, token: str) -> None:
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "token", token)

    @property
    def raw(self) -> psycopg.Connection:
        return self._conn

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._conn, name, value)

    def __enter__(self) -> OwnedConnection:
        self._conn.__enter__()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._conn.__exit__(*exc)

    def _busy(self) -> bool:
        return self._conn.info.transaction_status != TransactionStatus.IDLE

    def commit(self) -> None:
        if self._busy():                        # 쓸 것이 있을 때만 (빈 커밋은 확인할 것이 없음)
            ensure_owned(self._conn, self.run_id, self.token)
        self._conn.commit()

    @contextmanager
    def transaction(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
        # 바깥 블록은 psycopg가 commit()을 거치지 않고 커밋하므로 블록 끝에서 직접 확인한다.
        # 확인에서 멈추면 블록 안에서 예외가 나 그 트랜잭션은 되돌려진다
        outer = not self._busy()
        with self._conn.transaction(*args, **kwargs) as tx:
            yield tx
            if outer:
                ensure_owned(self._conn, self.run_id, self.token)


def own(conn: psycopg.Connection, run_id: int, token: str | None) -> psycopg.Connection:
    """토큰이 있으면 감싼 연결, 없으면(CLI·예전 호출) 그대로."""
    if token is None or isinstance(conn, OwnedConnection):
        return conn
    return OwnedConnection(conn, run_id, token)  # type: ignore[return-value]


def same_owner(like: Any, conn: psycopg.Connection) -> psycopg.Connection:
    """`like`가 감싼 연결이면 새 연결도 같은 실행·토큰으로 감싼다 (문서 병렬 처리 스레드)."""
    if isinstance(like, OwnedConnection):
        return OwnedConnection(conn, like.run_id, like.token)  # type: ignore[return-value]
    return conn
