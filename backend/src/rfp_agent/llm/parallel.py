"""AI 묶음 동시 호출 (change update-llm-concurrency, NFR-10).

일꾼 스레드는 언어 모델만 부른다. 진행 알림·취소 확인·DB 일은 부르는 스레드(on_done)에서 한다.
결과는 보낸 순서대로 돌려주므로 동시 개수와 상관없이 같은 결과가 나온다(CR-11).
"""

from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait

from rfp_agent.config import get_settings


def workers_of(llm: object) -> int:
    """모델에 동시 개수가 있으면 그것, 없으면(테스트 대역 등) 설정값."""
    n = getattr(llm, "workers", None)
    if not isinstance(n, int):
        n = get_settings().rfp_llm_workers
    return max(1, n)


def run_ordered[T](jobs: Sequence[Callable[[], T]], workers: int,
                   on_done: Callable[[int, T], None] | None = None) -> list[T]:
    """jobs를 최대 workers개 동시에 돌리고 결과를 jobs 순서대로 돌려준다.

    on_done(번호, 결과)은 일이 끝날 때마다 부르는 스레드에서 부른다(끝난 순서).
    일이나 on_done이 예외를 내면 아직 시작하지 않은 일은 버리고 그 예외를 올린다.
    """
    if not jobs:
        return []
    results: list[T] = [None] * len(jobs)  # type: ignore[list-item]
    if workers <= 1 or len(jobs) == 1:
        for i, job in enumerate(jobs):
            results[i] = job()
            if on_done:
                on_done(i, results[i])
        return results
    pool = ThreadPoolExecutor(max_workers=min(workers, len(jobs)),
                              thread_name_prefix="rfp-llm")
    try:
        index: dict[Future, int] = {pool.submit(job): i for i, job in enumerate(jobs)}
        pending = set(index)
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            # 같은 때 끝난 일은 번호 순서로 알린다
            for fut in sorted(done, key=index.__getitem__):
                i = index[fut]
                results[i] = fut.result()
                if on_done:
                    on_done(i, results[i])
    finally:
        # 정상이면 이미 다 끝났고, 예외면 시작하지 않은 일을 버린다
        pool.shutdown(wait=True, cancel_futures=True)
    return results
