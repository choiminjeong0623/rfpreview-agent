# 설계

- `tasks.check_support(llm, claims, sources) -> list[str]`: 줄 번호 답(`verdicts: [{n, v}]`, v는 YES/NO/UNSURE). 묻는 글에는 문장, 인용, 그 문장이 댄 근거 조각만 준다(사실 문장은 주지 않음 — 원문으로만 판단하게). 형식 오류는 다시 묻지 않고 모두 UNSURE(update-llm-retry-kinds). 연결 오류는 재시도 뒤 실패(CR-12).
- `run._save_risks`: 설명 묻기와 검증을 한 작업으로 묶어 동시에 보낸다(NFR-10). 결과 순서는 후보 순서.
- `risk_flag.explanation_check` (VERIFIED / NEEDS_REVIEW / NULL). 이어 쓴 설명(문서 추가·다시 시도)은 이전 검증 값을 그대로 옮긴다.
- 비용: 설명 하나에 요청 하나가 더 든다. 위험 조건 후보는 검토당 수십 건이라 판정·추출 묶음보다 훨씬 적다.
- 대안: 같은 프롬프트에서 스스로 확신도를 내게 하기 — 쓰는 쪽이 자기 답을 검사하면 같은 실수를 되풀이하기 쉬워 질문을 나눴다.
