# 임베딩 모델 비교: gemini-embedding-001 vs BGE-M3

지금 쓰는 `gemini-embedding-001`과 사내 모델 후보 `BGE-M3`(Ollama)에 같은 문제를 내서 비교합니다. 본 코드와 DB는 쓰지 않습니다.

## 무엇을 재나

뜻 찾기의 "항목 연결 후보"(`pipeline/meaning.py`)와 같은 일입니다.

- 문제: `data/seed/item_keys.csv`의 표현 186개(표준 항목 42개, 한국어 82개). 표현 하나를 빼고, 나머지 중 가장 가까운 표현이 같은 항목인지 봅니다. 예: "Rated normal current" → "정격전류"를 찾으면 정답.
- 정답은 사전에 이미 있어서 사람이 따로 만들 필요가 없습니다.

| 지표 | 뜻 |
|---|---|
| 1등 정확도 | 가장 가까운 표현이 같은 항목인 비율 |
| 영어↔한국어 정확도 | 다른 언어 표현만 후보로 둘 때 맞힌 비율 (RFP는 두 언어가 섞여 있음) |
| 지금 문턱 후보 수 / 맞은 비율 | 시스템 조건(1등 0.85 이상, 2등보다 0.03 앞섬)으로 후보를 냈을 때 |
| 추천 문턱 | 후보가 95 % 이상 맞으면서 가장 많이 나오는 문턱. 모델을 바꿀 때 `ITEM_MIN`을 얼마로 할지 |
| 걸린 시간, 추정 비용 | 186개 벡터를 받는 데 |

## 실행 방법 (Windows)

### 1. Ollama 설치와 BGE-M3 받기 (처음 한 번)

1. https://ollama.com/download 에서 Windows용을 받아 설치합니다. PowerShell에서 `winget install Ollama.Ollama`로도 됩니다.
2. 설치가 끝나면 Ollama가 뒤에서 켜집니다(작업 표시줄 오른쪽 아래 아이콘).
3. PowerShell에서 모델을 받습니다 (약 1.2 GB).

   ```powershell
   ollama pull bge-m3
   ollama list        # 목록에 bge-m3 가 보이면 됨
   ```

### 2. 비교 실행

저장소 맨 위 폴더(`C:\RFP\RFP-agent-service-1`)에서 실행합니다. Docker는 켜지 않아도 됩니다.

```powershell
cd C:\RFP\RFP-agent-service-1
python experiments\embedding_compare\compare.py
```

- Gemini 키는 저장소 맨 위 `.env`의 `GEMINI_API_KEY`를 읽습니다.
- `python` 명령이 없으면 백엔드의 uv로 실행합니다.

  ```powershell
  cd backend
  uv run python ..\experiments\embedding_compare\compare.py
  ```

- 한 모델만 돌리기: `--only gemini` 또는 `--only bge-m3`
- Ollama 주소가 다르면: `--ollama-url http://주소:11434`

### 3. 결과

화면에 비교표가 나오고, 같은 내용이 `experiments\embedding_compare\results\`에 저장됩니다.

| 파일 | 내용 |
|---|---|
| `summary.md` | 비교표 (기록 문서·발표에 그대로 씀) |
| `summary.json` | 같은 숫자 (기계용) |
| `details_*.csv` | 문제마다 가장 가까운 표현과 점수. `correct=0`이 틀린 문제 |

결과 파일에는 사전 표현만 들어 있고 RFP 원문은 없습니다.

## 문제가 생기면

| 증상 | 해결 |
|---|---|
| `GEMINI_API_KEY가 없습니다` | `.env`에 키가 있는지 확인. 없으면 `--only bge-m3`로 BGE-M3만 |
| `[bge-m3 (Ollama)] 실패: ... Connection refused` | Ollama가 꺼져 있음. 시작 메뉴에서 Ollama 실행 후 다시 |
| `HTTP 404 ... model "bge-m3" not found` | `ollama pull bge-m3`를 아직 안 함 |
| Gemini `HTTP 429` | 요청이 많음. 잠시 뒤 다시 |

## 한계

- 사전 표현은 짧은 항목 이름입니다. 실제 RFP 문장(긴 문장, 단위·숫자 섞임)에서의 성능은 따로 재야 합니다.
- 비용은 글자 수 ÷ 4로 어림한 토큰 수 기준입니다.
- 결과로 모델을 바꾸기로 하면, 시스템에서는 `RFP_AI_MODE=local`, `RFP_LOCAL_EMBED_MODEL=bge-m3`로 바꾸고 `meaning.py`의 문턱값 3개를 다시 맞춰야 합니다.
