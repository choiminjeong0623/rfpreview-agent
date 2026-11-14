// 홈의 팀 공유(공지사항·시스템 공지·자료실)와 교육·봉사·행사 예시 데이터 (목업 v4.57 Home).
// 게시판·행사 API가 없어 예시로만 보여 준다 (SCR-03_공유.md). 사람 이름은 역할로, 장소는 "예시 사업장"으로 바꿨다.

export type Post = { must?: boolean; isNew: boolean; title: string; by: string; date: string; body: string }
export type SysPost = { kind: string; tone: string; isNew: boolean; title: string; when: string; date: string; body: string }
export type FileRow = { ext: 'PDF' | 'XLSX' | 'DOCX'; name: string; desc: string; by: string; date: string; size: string }
export type HomeEvent = { icon: string; cat: string; title: string; when: string; where: string; cap: string; host: string; state: 'closed' | 'must' | string }

export const NOTICES: Post[] = [
  { must: true, isNew: true, title: '11월부터 기술검토 주간 회의를 수요일 10:00로 옮깁니다', by: '팀장', date: '10-23',
    body: '화요일 오전에 고객 회신 마감이 몰려 회의 시간을 수요일 10:00로 옮깁니다.\n회의 전날 17:00까지 이번 주 마감 건과 도움이 필요한 판정을 팀 업무 탭에 올려 주세요.' },
  { must: true, isNew: true, title: '해외 RFP 원문은 접수 후 7일 안에 검토 등록해 주세요', by: '팀장', date: '10-20',
    body: '메일로 받은 원문과 Addendum은 접수 후 7일 안에 검토 등록해야 원문 보관 기록이 남습니다.\n검토를 바로 시작하지 않더라도 등록만 먼저 해 주세요.' },
  { isNew: false, title: '일탈 목록 표준 문구 v3를 배포했습니다', by: '규칙 담당', date: '10-17',
    body: '고객 회신에서 자주 지적받은 표현을 고쳤습니다. 지식 관리 > 표준 문구에서 바로 볼 수 있습니다.' },
  { isNew: false, title: '10월 사업부 품질 회의 결과 공유', by: '품질 담당', date: '10-15',
    body: '형식시험 성적서 번호 누락으로 고객 질의가 있었습니다. "작성 필요" 항목이 남아 있으면 결재 상신 전에 채워 주세요.' },
  { isNew: false, title: '신규 입사자 소개 (11-02 합류)', by: '팀장', date: '10-13',
    body: '11-02부터 새 팀원이 기술검토팀에 합류합니다. 첫 2주는 GIS 검토를 함께 맡습니다.' },
]

export const SYS_NOTICES: SysPost[] = [
  { kind: '점검', tone: 'st c-grey', isNew: true, title: '10-31(토) 22:00~24:00 정기 점검', when: '예정', date: '10-24',
    body: '점검 시간에는 로그인과 검토 등록, 분석이 멈춥니다.' },
  { kind: '업데이트', tone: 'st c-blue', isNew: true, title: '질의 회신 반영, 제출본 확정 추가', when: '적용됨', date: '10-22',
    body: '결재가 승인되면 그 시점의 판정을 제출본으로 잠급니다.' },
  { kind: '장애', tone: 'st c-red', isNew: false, title: '언어 모델 응답 지연 (14:10~14:55)', when: '해결됨', date: '10-21',
    body: '외부 언어 모델 응답이 늦어져 분석이 멈췄습니다. 14:55에 복구되었습니다.' },
  { kind: '업데이트', tone: 'st c-blue', isNew: false, title: '제품표 일괄 올리기 양식 변경 — 열 2개 추가', when: '적용됨', date: '10-14',
    body: '"적용 규격 판"과 "형식시험 성적서 번호" 열이 추가되었습니다.' },
  { kind: '점검', tone: 'st c-grey', isNew: false, title: '사내 전자결재 연계 점검', when: '끝남', date: '10-12',
    body: '전자결재 연계 서버 교체로 결재 결과 새로 고침이 2시간 동안 멈췄습니다. 지금은 정상입니다.' },
]

export const FILES: FileRow[] = [
  { ext: 'PDF', name: 'IEC 62271-1 2025판 변경 요약.pdf', desc: '이전 판과 달라진 조항 정리', by: '규칙 담당', date: '10-16', size: '1.2 MB' },
  { ext: 'XLSX', name: '고객별 RFP 특이 조건.xlsx', desc: '고객별 반복 요구와 지난 대응', by: '영업 담당', date: '10-10', size: '96 KB' },
  { ext: 'DOCX', name: '질의서 작성 가이드 v2.docx', desc: '좋은 질의 문장 예시와 피할 표현', by: '기술 검토 엔지니어', date: '09-29', size: '310 KB' },
  { ext: 'XLSX', name: '제품표 일괄 올리기 양식.xlsx', desc: '열 2개 추가된 최신 양식 (10-14)', by: '제품 담당', date: '10-14', size: '64 KB' },
  { ext: 'DOCX', name: 'Addendum 처리 체크리스트.docx', desc: '개정 문서를 받았을 때 확인할 9가지', by: '기술 검토 엔지니어', date: '10-02', size: '88 KB' },
]

export const EVENTS: HomeEvent[] = [
  { icon: 'volunteer_activism', cat: '봉사', title: '해안 정화 플로깅', when: '10-25(일) 08:30–12:00', where: '예시 해변 · 버스 07:00 출발', cap: '30 / 30명', host: '사회공헌팀', state: 'closed' },
  { icon: 'school', cat: '교육', title: 'IEC 62271-1 2025판 개정 내용 설명회', when: '11-04(수) 14:00–16:00', where: '예시 사업장 대회의실 · 온라인 함께', cap: '21 / 40명 · 신청 10-30까지', host: '기술검토팀', state: 'open:D-6' },
  { icon: 'health_and_safety', cat: '안전', title: '고전압 시험실 정기 안전 교육', when: '11-05(목) 10:00–11:00', where: '예시 사업장 시험동', cap: '시험실 출입자 필수', host: 'EHS팀', state: 'must' },
  { icon: 'school', cat: '교육', title: 'RFP 검토 AI 활용 실습', when: '11-11(수) 09:30–12:00', where: '예시 캠퍼스 교육실', cap: '14 / 20명 · 신청 11-06까지', host: 'DX추진팀', state: 'open:D-13' },
  { icon: 'volunteer_activism', cat: '봉사', title: '연탄 나눔 봉사', when: '11-14(토) 09:00–13:00', where: '예시 지역 일대', cap: '26 / 30명 · 신청 11-09까지', host: '사회공헌팀', state: 'open:D-16' },
  { icon: 'celebration', cat: '행사', title: '사업부 기술 세미나', when: '11-19(목) 15:00–17:30', where: '예시 캠퍼스 강당', cap: '참석 표시 54명', host: '사업부', state: 'open:참석 표시' },
  { icon: 'school', cat: '교육', title: '해외 계약 상업 조건 기초 (영업·기술 공통)', when: '11-25(수) 13:30–17:30', where: '온라인', cap: '9 / 30명 · 신청 11-20까지', host: '법무팀', state: 'open:D-27' },
  { icon: 'celebration', cat: '행사', title: '사내 동호회 연합 체육대회', when: '11-28(토) 10:00–16:00', where: '예시 사업장 운동장', cap: '112 / 150명 · 신청 11-21까지', host: '인사팀', state: 'open:D-28' },
]
