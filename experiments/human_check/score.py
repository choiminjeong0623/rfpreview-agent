"""사람 확인(2026-11-02) 채점 — 사람 2명의 답과 모델 답을 맞춰 본다.

입력 (모두 data/private/diag/, git 제외: 고객 RFP 원문이 들어 있음)
  사람확인_20261102_v3.xlsx     사람 1(박경빈)이 채운 시트. ① F열 Y/N/?, ② E열 유형 코드
  사람확인_결과_20261102.csv    사람 1·2의 답과 모델 답을 한 표로 (사람 2 답의 원본)
  사람확인_열쇠_20261102.csv    시트 번호 → 모델 답·Claude 초안 (시트에는 일부러 넣지 않음)
실행: python3 experiments/human_check/score.py   (Windows: uv run --no-project --python 3.12 ...)
"""
import csv
from pathlib import Path

D = Path(__file__).resolve().parents[2] / "data/private/diag"
rows = list(csv.DictReader(open(D / "사람확인_결과_20261102.csv", encoding="utf-8-sig")))
key = list(csv.reader(open(D / "사람확인_열쇠_20261102.csv", encoding="utf-8-sig")))[1:]
k1 = {int(k[1]): k for k in key if k[0] == "①"}
k2 = {int(k[1]): k for k in key if k[0] == "②"}
yn = lambda v: "Y" if v == "REQUIREMENT" else "N"

print("① 요구사항인가 (두 모델 판단이 갈린 18줄)")
r1 = [r for r in rows if r["시트"] == "①"]
a = [r["사람1(경빈)"] for r in r1]; b = [r["사람2"] for r in r1]
m38 = [yn(k1[int(r["번호"])][3]) for r in r1]; lite = [yn(k1[int(r["번호"])][4]) for r in r1]
for name, h in (("사람1", a), ("사람2", b)):
    v = [i for i, x in enumerate(h) if x in "YN"]
    print(f"  {name}: 판단 {len(v)}줄 ('?' {18-len(v)}) — 3.8 {sum(h[i]==m38[i] for i in v)} / Lite {sum(h[i]==lite[i] for i in v)}")
agree = [i for i in range(18) if a[i] == b[i] and a[i] in "YN"]
print(f"  두 사람 같은 답 {sum(a[i]==b[i] for i in range(18))}/18, 같은 Y/N {len(agree)}줄 기준 — 3.8 {sum(a[i]==m38[i] for i in agree)} / Lite {sum(a[i]==lite[i] for i in agree)}")
print(f"  사람2와 Lite 일치 {sum(b[i]==lite[i] for i in range(18))}/18")

print("\n② 유형 (30줄)")
r2 = [r for r in rows if r["시트"] == "②"]
names = ["Claude초안", "3.8", "3.5L", "3.1L"]
ans = {n: [k2[int(r["번호"])][3 + (0 if j == 0 else j + 1)] for r in r2] for j, n in enumerate(names)}
a = [r["사람1(경빈)"] for r in r2]; b = [r["사람2"] for r in r2]
models = names[1:]
hard = [i for i in range(30) if any(ans[m][i] != ans["Claude초안"][i] for m in models)]
easy = [i for i in range(30) if i not in hard]
print(f"  어려운 줄(모델 하나라도 Claude 초안과 다름) {len(hard)}, 쉬운 줄 {len(easy)}")
for name, h in (("사람1", a), ("사람2", b)):
    print(f"  {name}: " + " / ".join(f"{n} {sum(h[i]==ans[n][i] for i in range(30))}" for n in names)
          + f" | 쉬운 줄 Claude초안과 같음 {sum(h[i]==ans['Claude초안'][i] for i in easy)}/{len(easy)}")
agree = [i for i in range(30) if a[i] == b[i]]
print(f"  두 사람 같은 답 {len(agree)}/30 기준 — " + " / ".join(f"{n} {sum(a[i]==ans[n][i] for i in agree)}" for n in names))
print("  두 사람이 다른 줄(시트 번호):", [int(r2[i]["번호"]) for i in range(30) if a[i] != b[i]])
