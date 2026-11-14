"""임베딩 모델 비교: gemini-embedding-001 vs BGE-M3 (Ollama).

뜻 찾기의 "항목 연결 후보"(add-meaning-search B3)와 같은 일을 떼어 두 모델에 같은 문제를 낸다.
정답은 data/seed/item_keys.csv(표준 항목키마다 같은 뜻 표현)이고, 사람이 따로 만들 필요가 없다.

문제: 표현 하나를 빼고, 나머지 표현 중 가장 가까운 것이 같은 항목인지 본다(모든 표현에 대해).
본 코드는 쓰지 않고 파이썬 표준 라이브러리만 쓴다. 결과는 results/ 아래에 저장한다.

실행 (저장소 맨 위 폴더에서):
    python experiments/embedding_compare/compare.py
    python experiments/embedding_compare/compare.py --only bge-m3      # 하나만
"""

import argparse
import csv
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ITEM_KEYS = ROOT / "data" / "seed" / "item_keys.csv"
OUT = Path(__file__).resolve().parent / "results"

# 시스템과 같은 값 (backend/src/rfp_agent/llm/client.py, pipeline/meaning.py)
GEMINI_MODEL = "gemini-embedding-001"
GEMINI_DIMS = 768
GEMINI_PRICE_PER_M = 0.15        # USD / 100만 토큰 (2026-11-02 조사)
BATCH = 100
ITEM_MIN = 0.85                  # 항목 연결 후보 문턱
ITEM_GAP = 0.03                  # 1등이 2등보다 앞서야 하는 만큼
TARGET_PRECISION = 0.95          # 문턱 찾기: 후보가 이만큼 맞을 때 가장 많이 내는 문턱

HANGUL = re.compile(r"[가-힣]")


# ---------- 데이터 ----------

def load_items(path: Path) -> list[tuple[str, str]]:
    """(표준 항목키, 표현) 목록. 한글 이름과 같은 뜻 원문 표현을 모두 표현으로 본다."""
    rows: list[tuple[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            key = (r.get("표준 항목키") or "").strip()
            if not key:
                continue
            texts = [r.get("한글 이름") or ""] + (r.get("같은 뜻의 원문 표현(;로 구분)") or "").split(";")
            seen = set()
            for t in texts:
                t = " ".join(t.split())
                if t and t.lower() not in seen:
                    seen.add(t.lower())
                    rows.append((key, t))
    return rows


def is_korean(text: str) -> bool:
    return bool(HANGUL.search(text))


# ---------- 모델 ----------

def read_env_key() -> str | None:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _post(url: str, body: dict, headers: dict, timeout: float = 120) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}") from exc


def embed_gemini(texts: list[str], key: str) -> list[list[float]]:
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
           ":batchEmbedContents")
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        part = texts[i:i + BATCH]
        body = {"requests": [{"model": f"models/{GEMINI_MODEL}",
                              "content": {"parts": [{"text": t}]},
                              "outputDimensionality": GEMINI_DIMS} for t in part]}
        data = _post(url, body, {"x-goog-api-key": key})
        out += [e["values"] for e in data["embeddings"]]
    return out


def embed_ollama(texts: list[str], url: str, model: str) -> list[list[float]]:
    """우리 시스템 사내 모델 연결과 같은 OpenAI 호환 /v1/embeddings."""
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        data = _post(f"{url.rstrip('/')}/v1/embeddings", {"model": model, "input": texts[i:i + BATCH]}, {})
        rows = sorted(data["data"], key=lambda r: r["index"])
        out += [r["embedding"] for r in rows]
    return out


# ---------- 채점 ----------

def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def evaluate(rows: list[tuple[str, str]], vecs: list[list[float]]) -> tuple[dict, list[dict]]:
    n = len(rows)
    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            sim[i][j] = sim[j][i] = cosine(vecs[i], vecs[j])
    count_by_key: dict[str, int] = {}
    for k, _ in rows:
        count_by_key[k] = count_by_key.get(k, 0) + 1
    langs_by_key: dict[str, set] = {}
    for k, t in rows:
        langs_by_key.setdefault(k, set()).add(is_korean(t))

    details, item_scores = [], []
    top1 = cross_total = cross_hit = 0
    asked = 0
    for i, (key, text) in enumerate(rows):
        if count_by_key[key] < 2:          # 같은 항목 표현이 하나뿐이면 문제를 낼 수 없음
            continue
        asked += 1
        others = [j for j in range(n) if j != i]
        best = max(others, key=lambda j: sim[i][j])
        hit = rows[best][0] == key
        top1 += hit
        # 항목마다 최대 점수 (시스템 _item_candidate와 같은 방식)
        per_key: dict[str, float] = {}
        for j in others:
            k = rows[j][0]
            per_key[k] = max(per_key.get(k, -1.0), sim[i][j])
        ranked = sorted(per_key.items(), key=lambda kv: -kv[1])
        (k1, s1), (_, s2) = ranked[0], ranked[1]
        item_scores.append((s1, s1 - s2, k1 == key))
        # 다른 언어 표현만 후보로 둘 때 (영어 → 한국어, 한국어 → 영어)
        cross = None
        if len(langs_by_key[key]) == 2:
            pool = [j for j in others if is_korean(rows[j][1]) != is_korean(text)]
            if pool:
                cbest = max(pool, key=lambda j: sim[i][j])
                cross = rows[cbest][0] == key
                cross_total += 1
                cross_hit += cross
        details.append({"key": key, "text": text, "top1_text": rows[best][1],
                        "top1_key": rows[best][0], "top1_score": round(sim[i][best], 4),
                        "correct": int(hit), "cross_lang_correct": "" if cross is None else int(cross),
                        "item_gap": round(s1 - s2, 4)})

    def at(threshold: float) -> tuple[int, float]:
        picked = [ok for s, gap, ok in item_scores if s >= threshold and gap >= ITEM_GAP]
        return len(picked), (sum(picked) / len(picked) if picked else 0.0)

    sys_n, sys_p = at(ITEM_MIN)
    best_t = None
    for t100 in range(50, 100):
        t = t100 / 100
        cnt, prec = at(t)
        if cnt and prec >= TARGET_PRECISION and (best_t is None or cnt > best_t[1]):
            best_t = (t, cnt, prec)
    summary = {
        "asked": asked,
        "top1_accuracy": top1 / asked if asked else 0.0,
        "cross_lang_accuracy": cross_hit / cross_total if cross_total else 0.0,
        "cross_lang_asked": cross_total,
        "at_system_threshold": {"threshold": ITEM_MIN, "candidates": sys_n,
                                "coverage": sys_n / asked if asked else 0.0, "precision": sys_p},
        "suggested_threshold": None if best_t is None else
            {"threshold": best_t[0], "candidates": best_t[1],
             "coverage": best_t[1] / asked, "precision": best_t[2]},
    }
    return summary, details


# ---------- 실행 ----------

def main() -> None:
    ap = argparse.ArgumentParser(description="gemini-embedding-001 vs BGE-M3 (Ollama) 비교")
    ap.add_argument("--only", choices=["gemini", "bge-m3"], help="한 모델만 돌리기")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--ollama-model", default="bge-m3")
    args = ap.parse_args()
    try:                                    # Windows 콘솔·리다이렉트에서도 한글이 깨지지 않게
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    rows = load_items(ITEM_KEYS)
    texts = [t for _, t in rows]
    keys = len({k for k, _ in rows})
    print(f"표현 {len(rows)}개 / 표준 항목 {keys}개 / 한국어 표현 {sum(map(is_korean, texts))}개")

    models = []
    if args.only in (None, "gemini"):
        key = read_env_key()
        if not key:
            sys.exit("GEMINI_API_KEY가 없습니다 (.env 또는 환경 변수). --only bge-m3 로 하나만 돌릴 수 있습니다.")
        models.append(("gemini-embedding-001", lambda: embed_gemini(texts, key)))
    if args.only in (None, "bge-m3"):
        models.append((f"{args.ollama_model} (Ollama)",
                       lambda: embed_ollama(texts, args.ollama_url, args.ollama_model)))

    OUT.mkdir(exist_ok=True)
    results = {}
    chars = sum(len(t) for t in texts)
    for name, run in models:
        print(f"\n[{name}] 벡터 받는 중...")
        t0 = time.perf_counter()
        try:
            vecs = run()
        except Exception as exc:  # noqa: BLE001
            print(f"  실패: {exc}")
            continue
        secs = time.perf_counter() - t0
        summary, details = evaluate(rows, vecs)
        summary |= {"seconds": round(secs, 2), "dims": len(vecs[0]),
                    "approx_cost_usd": round(chars / 4 / 1e6 * GEMINI_PRICE_PER_M, 6)
                    if name.startswith("gemini") else 0.0}
        results[name] = summary
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        with (OUT / f"details_{slug}.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(details[0]))
            w.writeheader()
            w.writerows(details)
        print(f"  1등 정확도 {summary['top1_accuracy']:.1%}, 영어↔한국어 {summary['cross_lang_accuracy']:.1%}, "
              f"{secs:.1f}초")

    if not results:
        sys.exit("결과가 없습니다.")
    (OUT / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 임베딩 모델 비교 결과",
        "",
        f"실행: {time.strftime('%Y-%m-%d %H:%M')} · 문제: `data/seed/item_keys.csv` 표현 {len(rows)}개"
        f"(표준 항목 {keys}개), 표현 하나를 빼고 가장 가까운 표현이 같은 항목인지",
        "",
        "| 지표 | " + " | ".join(results) + " |",
        "|---|" + "---|" * len(results),
    ]

    def row(label, fn):
        lines.append(f"| {label} | " + " | ".join(fn(s) for s in results.values()) + " |")

    row("1등 정확도", lambda s: f"{s['top1_accuracy']:.1%} ({s['asked']}문제)")
    row("영어↔한국어 정확도", lambda s: f"{s['cross_lang_accuracy']:.1%} ({s['cross_lang_asked']}문제)")
    row(f"지금 문턱({ITEM_MIN}) 후보 수 / 맞은 비율",
        lambda s: f"{s['at_system_threshold']['candidates']} / {s['at_system_threshold']['precision']:.1%}")
    row(f"추천 문턱 (맞은 비율 {TARGET_PRECISION:.0%} 이상)",
        lambda s: "없음" if not s["suggested_threshold"] else
        f"{s['suggested_threshold']['threshold']:.2f} (후보 {s['suggested_threshold']['candidates']}, "
        f"{s['suggested_threshold']['precision']:.1%})")
    row("벡터 차원", lambda s: str(s["dims"]))
    row("걸린 시간", lambda s: f"{s['seconds']}초")
    row("추정 비용", lambda s: f"${s['approx_cost_usd']}")
    lines += ["", "틀린 문제는 `details_*.csv`의 correct=0 줄에서 볼 수 있습니다. "
              "비용은 글자 수 ÷ 4로 어림한 토큰 수 기준입니다."]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\n저장: {OUT}")


if __name__ == "__main__":
    main()
