"""유형 붙이기 모델 비교: 정답지 100줄 (파일 1, Claude 초안 정답).

- Gemini 설정들을 지금 시스템의 유형 질문 그대로(backend `tasks.type_unclassified`) 새로 돌린다.
- Jev는 다시 부르지 않고 10-25 실험에 남은 답·확률(`정답지_열쇠_모델답.csv`)을 쓴다 (비용 0).
- 섞어 쓰기: Jev 확률이 문턱(기본 0.9) 이상이면 Jev 답, 아니면 그 Gemini 설정의 답.

본 코드는 바꾸지 않고 읽기만 한다. 파이썬 3.12 이상, 표준 라이브러리만 쓴다.

실행 (저장소 맨 위 폴더에서):
    python experiments/model_compare/type_compare.py
    python experiments/model_compare/type_compare.py --config "lite0=gemini-2.5-flash-lite,budget=0"
"""

import argparse
import csv
import importlib.util
import json
import re
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

if sys.version_info < (3, 12):
    sys.exit("파이썬 3.12 이상이 필요합니다 (backend 코드가 3.12 문법을 씀).")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "backend" / "src"
KEY_CSV = HERE / "정답지_Claude초안.csv"
MODEL_CSV = HERE / "정답지_열쇠_모델답.csv"
OUT = HERE / "results"

# 기본 비교 설정: 이름=모델[,budget=N][,level=low|minimal|...]
DEFAULT_CONFIGS = [
    "현재_3.8flash=gemini-3.8-flash",              # 지금 시스템 (생각 설정 없음 = 모델 기본값)
    "목표_2.5lite=gemini-2.5-flash-lite,budget=0",  # 목표 설정 (생각 끔)
]
# USD / 100만 토큰 (입력, 출력). 생각 토큰은 출력 가격. 2026-10-25 기준 정리 페이지 값
PRICES = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
}
KRW = 1500                       # 1달러 = 1,500원 (팀 가정)
BID_FORM_HINT_KIND = "BID_FORM"  # 파일 1의 문서 종류 (시스템이 유형 질문 첫 줄에 넣는 설명)


# ---------- backend 코드 불러오기 (설정 모듈만 가짜로 바꿔 끼움) ----------

def load_backend():
    fake_config = types.ModuleType("rfp_agent.config")
    fake_config.get_settings = lambda: types.SimpleNamespace(rfp_llm_workers=4)
    sys.modules["rfp_agent.config"] = fake_config
    sys.path.insert(0, str(SRC))
    from rfp_agent.llm import tasks  # noqa: E402
    spec = importlib.util.spec_from_file_location(
        "processors", SRC / "rfp_agent" / "pipeline" / "processors.py")
    processors = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(processors)
    return tasks, processors.processor_for(BID_FORM_HINT_KIND).hint


# ---------- Gemini REST (시스템 GeminiLLM과 같은 설정: JSON 스키마, temperature 0) ----------

def read_env_key() -> str:
    import os
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("GEMINI_API_KEY="):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
                if v:
                    return v
    sys.exit("GEMINI_API_KEY가 없습니다 (.env 또는 환경 변수).")


def to_rest_schema(s):
    """JSON 스키마의 type 값을 REST가 받는 대문자로."""
    if isinstance(s, dict):
        return {k: (v.upper() if k == "type" and isinstance(v, str) else to_rest_schema(v))
                for k, v in s.items()}
    if isinstance(s, list):
        return [to_rest_schema(x) for x in s]
    return s


class GeminiRest:
    def __init__(self, key: str, model: str, budget: int | None, level: str | None,
                 workers: int = 4, timeout_s: float = 120):
        self.key, self.model, self.workers, self.timeout_s = key, model, workers, timeout_s
        self.thinking = ({"thinkingBudget": budget} if budget is not None
                         else {"thinkingLevel": level} if level else None)
        self.lock = threading.Lock()
        self.calls = self.input_tokens = self.output_tokens = self.thinking_tokens = 0

    def generate_json(self, prompt: str, schema: dict) -> dict:
        cfg = {"responseMimeType": "application/json", "responseSchema": to_rest_schema(schema),
               "temperature": 0}
        if self.thinking:
            cfg["thinkingConfig"] = self.thinking
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": cfg}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={
            "Content-Type": "application/json", "x-goog-api-key": self.key})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err = RuntimeError(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:400]}")
            err.code = exc.code          # call_with_retry가 설정 오류(400·401·403·404)를 가름
            raise err from exc
        meta = data.get("usageMetadata", {})
        with self.lock:
            self.calls += 1
            self.input_tokens += meta.get("promptTokenCount", 0)
            self.output_tokens += meta.get("candidatesTokenCount", 0)
            self.thinking_tokens += meta.get("thoughtsTokenCount", 0)
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]
                       if not p.get("thought"))
        return json.loads(text)

    def cost_usd(self) -> float | None:
        price = PRICES.get(self.model)
        if not price:
            return None
        return (self.input_tokens * price[0]
                + (self.output_tokens + self.thinking_tokens) * price[1]) / 1e6


def parse_config(spec: str) -> tuple[str, str, int | None, str | None]:
    name, rest = spec.split("=", 1)
    parts = rest.split(",")
    model, budget, level = parts[0].strip(), None, None
    for p in parts[1:]:
        k, v = p.split("=", 1)
        if k.strip() == "budget":
            budget = int(v)
        elif k.strip() == "level":
            level = v.strip()
    return name.strip(), model, budget, level


# ---------- 데이터 ----------

def load_rows() -> list[dict]:
    with KEY_CSV.open(encoding="utf-8-sig", newline="") as f:
        key = {r["번호"]: r for r in csv.DictReader(f)}
    with MODEL_CSV.open(encoding="utf-8-sig", newline="") as f:
        models = {r["번호"]: r for r in csv.DictReader(f)}
    rows = []
    for no, r in key.items():
        m = models.get(no)
        if not m:
            continue
        human = (r.get("사람 확인(맞으면 비움, 다르면 코드)") or "").strip().upper()
        rows.append({
            "no": int(no), "text": r["text"], "context": r.get("context") or None,
            "answer": human or r["Claude초안"].strip().upper(),
            "human_checked": bool(human), "ambiguous": (r.get("애매함(Y)") or "").strip().upper() == "Y",
            "gemini_1025": m["gemini"].strip().upper(), "jev": m["jev"].strip().upper(),
            "jev_prob": float(m["jev_prob"]), "pick": m.get("구분", ""),
        })
    return sorted(rows, key=lambda r: r["no"])


# ---------- 채점 ----------

def score(rows, answers: list[str]) -> dict:
    hit = sum(a == r["answer"] for a, r in zip(answers, rows))
    clear = [(a, r) for a, r in zip(answers, rows) if not r["ambiguous"]]
    diff = [(a, r) for a, r in zip(answers, rows) if r["pick"] == "다른 답"]
    same = [(a, r) for a, r in zip(answers, rows) if r["pick"] != "다른 답"]
    return {"hit": hit, "n": len(rows),
            "clear_hit": sum(a == r["answer"] for a, r in clear), "clear_n": len(clear),
            "diff_hit": sum(a == r["answer"] for a, r in diff), "diff_n": len(diff),
            "same_hit": sum(a == r["answer"] for a, r in same), "same_n": len(same)}


def main() -> None:
    ap = argparse.ArgumentParser(description="유형 붙이기 모델 비교 (정답지 100줄)")
    ap.add_argument("--config", action="append",
                    help='비교 설정 "이름=모델[,budget=N][,level=low]". 여러 번 줄 수 있음. 주지 않으면 기본 2개')
    ap.add_argument("--mix", type=float, default=0.9, help="섞어 쓰기 Jev 확률 문턱 (기본 0.9)")
    ap.add_argument("--no-hint", action="store_true", help="문서 종류 설명(입찰 서식)을 빼고 묻기")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    tasks, hint = load_backend()
    if args.no_hint:
        hint = None
    rows = load_rows()
    print(f"정답지 {len(rows)}줄 (애매함 {sum(r['ambiguous'] for r in rows)}줄, "
          f"사람 확인 {sum(r['human_checked'] for r in rows)}줄) · 프롬프트 판 {tasks.PROMPT_VERSION}")
    key = read_env_key()

    results = {}   # 이름 → (답 목록, 점수, 부가 정보)
    results["Gemini 3.8 Flash (10-25 기록)"] = ([r["gemini_1025"] for r in rows], None, {"src": "기록"})
    results["Jev (10-25 기록)"] = ([r["jev"] for r in rows], None, {"src": "기록", "cost_krw": "약 8원(기록)"})
    mix_1025 = [r["jev"] if r["jev_prob"] >= args.mix else r["gemini_1025"] for r in rows]
    results[f"섞기 Jev≥{args.mix}+3.8 Flash (10-25 기록)"] = (mix_1025, None, {"src": "기록으로 계산"})

    for spec in args.config or DEFAULT_CONFIGS:
        name, model, budget, level = parse_config(spec)
        llm = GeminiRest(key, model, budget, level)
        print(f"\n[{name}] {model} 생각={llm.thinking or '모델 기본값'} 묻는 중...")
        t0 = time.perf_counter()
        try:
            answers = tasks.type_unclassified(
                llm, [r["text"] for r in rows], contexts=[r["context"] for r in rows],
                doc_hint=hint)
        except Exception as exc:  # noqa: BLE001
            print(f"  실패: {exc}")
            continue
        secs = time.perf_counter() - t0
        usd = llm.cost_usd()
        info = {"src": "새로 잼", "seconds": round(secs, 1), "calls": llm.calls,
                "input_tokens": llm.input_tokens, "output_tokens": llm.output_tokens,
                "thinking_tokens": llm.thinking_tokens,
                "cost_krw": "단가 모름" if usd is None else f"{usd * KRW:.1f}원"}
        results[f"{name} (지금 프롬프트)"] = (answers, None, info)
        mix = [r["jev"] if r["jev_prob"] >= args.mix else a for r, a in zip(rows, answers)]
        results[f"섞기 Jev≥{args.mix}+{name}"] = (mix, None, {"src": "Jev 기록 + 새로 잰 답"})
        print(f"  {secs:.1f}초, 호출 {llm.calls}번, 생각 토큰 {llm.thinking_tokens}")

    OUT.mkdir(exist_ok=True)
    table = {name: (ans, score(rows, ans), info) for name, (ans, _, info) in results.items()}
    # 줄마다 결과
    with (OUT / "type_details.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["번호", "text", "정답", "애매함", "jev_prob"] + list(table))
        for i, r in enumerate(rows):
            w.writerow([r["no"], r["text"], r["answer"], "Y" if r["ambiguous"] else "", r["jev_prob"]]
                       + [ans[i] for ans, _, _ in table.values()])
    (OUT / "type_summary.json").write_text(json.dumps(
        {n: {"score": s, **i} for n, (_, s, i) in table.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    lines = ["# 유형 붙이기 모델 비교 (정답지 100줄)", "",
             f"실행 {time.strftime('%Y-%m-%d %H:%M')} · 대상: 파일 1 정답지 {len(rows)}줄 · "
             f"정답: Claude 초안(사람 확인 {sum(r['human_checked'] for r in rows)}줄) · "
             f"프롬프트 판 {tasks.PROMPT_VERSION}", "",
             "| 경우 | 맞힌 줄 | 애매함 뺀 줄 | 두 모델 답이 달랐던 줄 | 같았던 줄 | 시간 | 생각 토큰 | 비용 | 출처 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, (_, s, i) in table.items():
        lines.append(
            f"| {name} | **{s['hit']}/{s['n']}** | {s['clear_hit']}/{s['clear_n']} | "
            f"{s['diff_hit']}/{s['diff_n']} | {s['same_hit']}/{s['same_n']} | "
            f"{str(i.get('seconds', '—')) + '초' if 'seconds' in i else '—'} | "
            f"{i.get('thinking_tokens', '—')} | {i.get('cost_krw', '—')} | {i['src']} |")
    lines += ["",
              "- 정답은 사람이 아니라 Claude 초안입니다. 100줄 중 70줄은 10-25에 두 모델 답이 달랐던 줄에서 "
              "골라서, 문서 전체 정확도가 아니라 어려운 줄 위주의 비교입니다.",
              "- Jev 답은 10-25 실험 기록입니다(다시 부르지 않음). 지금 Jev 버전과 다를 수 있습니다.",
              "- 지금 프롬프트에는 절·표 제목 문맥과 문서 종류 설명이 들어갑니다. 사람 확정 예시(DB)는 넣지 않았습니다.",
              f"- 비용은 응답의 실제 토큰 수 × 단가(1달러 = {KRW}원)입니다. 100줄 기준이라 문서 전체 비용은 아닙니다."]
    (OUT / "type_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines) + f"\n\n저장: {OUT}")


if __name__ == "__main__":
    main()
