# data/private

저장소에 올리지 않는 자료를 두는 곳입니다. 이 파일 말고는 모두 git에서 제외됩니다.

| 경로 | 내용 |
|---|---|
| `rfp_docx/*.docx` | 팀 프로젝트에서는 운영진이 준 고객 RFP 22개(가림 처리본)를 두었습니다. **공개본에는 없습니다.** |
| `rfp_docx/RFP_Product_Master_*.docx` | 저장소 맨 위의 `generate_evaluative_rfp.py` → `generate_collaboration_rfp.py` → `generate_risk_rfp.py` → `generate_switch_rfp.py` 순서로 만드는 시연용 합성 RFP |

Docker Compose는 이 폴더를 백엔드 컨테이너의 `/app/data/private`에 붙입니다. 화면에서 올린 docx는 `uploads/`에 저장됩니다.
