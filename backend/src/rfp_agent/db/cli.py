"""DB 명령: rfp-db migrate | seed-rules [--reset-edits] | seed-products [--replace] | setup
| demo-businesses --business 사업명 a.docx [b.docx ...] (시연용 사업, add-project-status)
| load-answer-key 정답지.csv --name 이름 [--human] [--kind REQ --doc 문서] (정답지)
| make-answer-key 공급사답안.docx --name 이름 (요구사항 정답지, add-requirement-answer-key)
| demo-setup [--create] [--file 파일] (빈 DB에 시연 준비, add-demo-setup)"""

import argparse
import re
import sys
from datetime import timedelta
from pathlib import Path

from rfp_agent.config import get_settings
from rfp_agent.db.connection import connect
from rfp_agent.db.migrate import migrate
from rfp_agent.db.seed import SeedReport, seed_products, seed_rules

PRODUCT_FILES = ["product_master.csv"]
# 변압기 손실값 (product_code, no_load_loss_kw, load_loss_kw, aux_loss_kw, is_assumed).
# 파일이 없으면 손실 칸은 비워 둔다.
LOSS_FILE = "trf_spec.csv"


def print_report(title: str, report: SeedReport) -> None:
    print(f"[{title}] " + ", ".join(f"{k} {v}" for k, v in report.counts.items()))
    for line in report.skipped:
        print(f"  건너뜀: {line}")


def run_products(conn, replace: bool = False) -> None:
    product_dir = get_settings().seed_dir / "products"
    files = [product_dir / name for name in PRODUCT_FILES]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        sys.exit(f"제품표가 없습니다: {product_dir} 에 {', '.join(missing)} 를 넣어 주세요.")
    loss_file = product_dir / LOSS_FILE
    print_report("제품표", seed_products(conn, files, loss_file if loss_file.exists() else None,
                                             replace))


def demo_businesses(groups: list[list[str]], customer: str | None, due_in: int) -> None:
    """시연용 사업: --business마다 사업 하나를 만들고 파일 하나마다 검토 하나(설비 범위)를 돌린다.

    고객 원문이 아닌 합성 문서(예: 프로젝트 파일 demo-tests/files)를 넣는다.
    키가 없으면 AI 없이 돈다.
    """
    from rfp_agent.pipeline import business, review, review_info
    from rfp_agent.pipeline.service import run_to_end, start_run

    # 마감일은 화면의 "남은 날"과 같은 DB 날짜(CURRENT_DATE) 기준. 컴퓨터 날짜(KST)로 하면
    # 한국 시간 0~9시에 DB(UTC)와 하루 어긋난다
    with connect() as conn:
        due = conn.execute("SELECT CURRENT_DATE").fetchone()[0] + timedelta(days=due_in)
    for name, *files in groups:
        paths = [Path(f) for f in files]
        missing = [str(p) for p in paths if not p.exists()]
        if not paths or missing:
            sys.exit(f"[{name}] 파일이 없습니다: {', '.join(missing) or '(파일 없음)'}")
        with connect() as conn:
            info = {"due_date": due} | ({"customer_name": customer} if customer else {})
            engineer = review.default_user(conn, "ENGINEER")      # 시작한 사람 = 담당 엔지니어
            business_id = business.create(conn, {"business_name": name, **info}, engineer)
            for path in paths:
                run_id = start_run(conn, engineer)
                review_info.save_on_start(conn, run_id, {"review_name": path.stem, "due_date": due},
                                          engineer)
                business.link(conn, run_id, business_id, engineer)
                stage = run_to_end(run_id, [path])
                print(f"[시연 사업] {name}: 검토 {run_id} {path.name} → {stage}")


def fill_due(due_in: int) -> None:
    """마감이 빈 검토(테스트·스크립트로 만든 것)를 시작일 + due_in일로 채운다.

    개발·시연 DB에서만 사람이 돌린다 (update-due-required, CR-04).
    """
    from rfp_agent.pipeline import review, review_info

    with connect() as conn:
        done = review_info.fill_due(conn, due_in, review.default_user(conn, "ENGINEER"))
    print(f"[마감 채움] 검토 {len(done)}건: 시작일 + {due_in}일")


def load_answer_key(path: Path, name: str, human: bool, kind: str = "TYPE",
                    doc: str | None = None) -> None:
    from rfp_agent.pipeline.evaluation import load_key
    from rfp_agent.pipeline.req_eval import load_req_key

    if not path.exists():
        sys.exit(f"정답지 파일이 없습니다: {path}")
    with connect() as conn:
        if kind == "REQ":
            report = load_req_key(conn, path, name, doc, human)
        else:
            report = load_key(conn, path, name, human)
    who = "사람" if human else "Claude 초안"
    print(f"[정답지] {name} ({who}): {report.rows}줄, 사람 확인 {report.human_checked}줄")
    for line in report.skipped:
        print(f"  건너뜀: {line}")


def make_answer_key(path: Path, name: str) -> None:
    """공급사 답안 docx로 요구사항 정답지를 만든다. 고객 원문이라 DB에만 넣는다."""
    from rfp_agent.pipeline.req_eval import make_supplier_key
    from rfp_agent.pipeline.review import ReviewError

    if not path.exists():
        sys.exit(f"문서가 없습니다: {path}")
    with connect() as conn:
        try:
            report = make_supplier_key(conn, path, name)
        except ReviewError as exc:
            sys.exit(str(exc))
    print(f"[요구사항 정답지] {name} (코드 자동, 사람 확인 전): 조항 {report.rows}줄")


DEMO_FILE = "RFP_Product_Master_Evaluative_EN_With_Product_Switch.docx"
DEMO_KEYS = [("synthetic_rfp28_req.csv", "합성 RFP 28 요구사항", "REQ"),
             ("synthetic_rfp28_type.csv", "합성 RFP 28 유형", "TYPE")]
AI_MODE_TEXT = {"GEMINI": "Gemini(외부로 보냄, 요금)", "LOCAL": "사내 모델",
                "OFF": "AI 끔 — 규칙만"}


def _create_database(url: str) -> None:
    """DATABASE_URL의 DB가 없으면 같은 서버에 만든다. 있으면 그대로."""
    import psycopg
    from psycopg import sql

    head, _, name = url.rpartition("/")
    name = name.split("?")[0]
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        sys.exit(f"DB 이름은 영문·숫자·밑줄만 씁니다: {name}")
    with psycopg.connect(f"{head}/postgres", autocommit=True) as admin:
        if admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            print(f"[시연 준비] DB {name} 있음")
            return
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        print(f"[시연 준비] DB {name} 만듦")


def _run_count(conn) -> int:
    """검토 수. 표가 아직 없는 새 DB는 0."""
    if conn.execute("SELECT to_regclass('public.review_run')").fetchone()[0] is None:
        return 0
    return conn.execute("SELECT count(*) FROM review_run").fetchone()[0]


def demo_setup(create: bool, file: Path | None) -> None:
    """빈 DB에 시연 데이터를 한 번에 준비한다. 검토가 있는 DB는 거절하고 지우지 않는다."""
    from rfp_agent.llm.client import ai_mode

    settings = get_settings()
    path = file or settings.docx_dir / DEMO_FILE
    if create:
        _create_database(settings.database_url)
    with connect() as conn:
        if (n := _run_count(conn)) > 0:
            sys.exit(f"검토가 {n}건 있는 DB입니다. 시연 준비는 검토가 없는 DB에서만 합니다"
                     " (지우지 않습니다). 새 DB 이름으로 --create 하세요.")
    if not path.exists():
        sys.exit(f"시연 파일이 없습니다: {path}\n"
                 "  cd backend && uv run python ../generate_risk_rfp.py && "
                 "uv run python ../generate_switch_rfp.py")
    print(f"[시연 준비] AI 방식: {AI_MODE_TEXT[ai_mode(settings)]}")
    with connect() as conn:
        applied = migrate(conn, settings.migrations_dir)
        print(f"[마이그레이션] 적용 {len(applied)}건")
        print_report("규칙 사전", seed_rules(conn, settings.seed_dir))
        run_products(conn)
    for csv_name, name, kind in DEMO_KEYS:
        load_answer_key(settings.seed_dir / "answer_keys" / csv_name, name, False, kind,
                        DEMO_FILE.removesuffix(".docx") if kind == "REQ" else None)
    demo_businesses([["시연 사업", str(path)]], "Demo Grid Co.", 14)
    print("[시연 준비] 끝. 이 DB로 백엔드를 띄우면 검토 목록에 시연 검토가 하나 보입니다.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rfp-db")
    parser.add_argument("command", choices=["migrate", "seed-rules", "seed-products", "setup",
                                            "demo-businesses", "load-answer-key",
                                            "make-answer-key", "fill-due", "demo-setup"])
    parser.add_argument("path", nargs="?",
                        help="load-answer-key: 정답지 CSV / make-answer-key: 공급사 답안 docx")
    parser.add_argument("--name", help="load-answer-key: 정답지 이름 (같은 이름이면 줄을 바꿈)")
    parser.add_argument("--human", action="store_true",
                        help="load-answer-key: 사람이 만든 정답지 (주지 않으면 Claude 초안)")
    parser.add_argument("--kind", choices=["TYPE", "REQ"], default="TYPE",
                        help="load-answer-key: TYPE 유형 정답지(기본) / REQ 요구사항 정답지")
    parser.add_argument("--doc", help="--kind REQ: 대상 문서 이름(파일 이름에 든 글자)")
    parser.add_argument("--business", action="append", nargs="+", metavar=("사업명", "DOCX"),
                        help="demo-businesses: 사업명과 docx 파일들 (여러 번 줄 수 있음)")
    parser.add_argument("--customer", help="demo-businesses: 고객사 (주지 않으면 비움)")
    parser.add_argument("--due-in", type=int, default=14,
                        help="demo-businesses: 오늘부터 제출 마감까지 날 수 (기본 14), "
                             "fill-due: 시작일부터 채울 마감까지 날 수")
    parser.add_argument("--replace", action="store_true",
                        help="이전 제품과 검토 실행 결과를 지우고 파일 내용만 넣음")
    parser.add_argument("--create", action="store_true",
                        help="demo-setup: DATABASE_URL의 DB가 없으면 만듦")
    parser.add_argument("--file", help="demo-setup: 시연 파일 (기본: 합성 RFP 파일 28)")
    parser.add_argument("--reset-edits", action="store_true",
                        help="화면에서 고친 규칙을 버리고 사전 파일 내용만 넣음 (이력은 남음)")
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.command == "demo-businesses":
        if not args.business or any(len(g) < 2 for g in args.business):
            parser.error("--business 사업명 a.docx [b.docx ...] 가 필요합니다")
        demo_businesses(args.business, args.customer, args.due_in)
        return
    if args.command == "demo-setup":
        demo_setup(args.create, Path(args.file) if args.file else None)
        return
    if args.command == "fill-due":
        fill_due(args.due_in)
        return
    if args.command == "load-answer-key":
        if not args.path or not args.name:
            parser.error("load-answer-key 정답지.csv --name 이름 이 필요합니다")
        load_answer_key(Path(args.path), args.name, args.human, args.kind, args.doc)
        return
    if args.command == "make-answer-key":
        if not args.path or not args.name:
            parser.error("make-answer-key 공급사답안.docx --name 이름 이 필요합니다")
        make_answer_key(Path(args.path), args.name)
        return
    with connect() as conn:
        if args.command in ("migrate", "setup"):
            applied = migrate(conn, settings.migrations_dir)
            print(f"[마이그레이션] 적용 {len(applied)}건 {applied}")
        if args.command in ("seed-rules", "setup"):
            print_report("규칙 사전", seed_rules(conn, settings.seed_dir, args.reset_edits))
        if args.command in ("seed-products", "setup"):
            run_products(conn, args.replace)


if __name__ == "__main__":
    main()
