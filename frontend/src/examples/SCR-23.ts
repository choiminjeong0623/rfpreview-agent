// 자료실 예시 데이터 (목업 v4.57 Files의 F0 8개). 자료실 API가 없어 예시로만 보여 준다 (SCR-23_공유.md).
// 올린 사람은 역할로, 설명의 지명은 "예시 사업장 A"로 바꿨다. 파일 자체는 없다.

export type FileCat = 'tech' | 'cust' | 'guide' | 'form'
/** [분류, 확장자, 확장자 색(x = 엑셀), 파일 이름, 설명, 올린 사람, 날짜, 크기, 받은 수] */
export type SharedFile = [FileCat, string, string, string, string, string, string, string, number]

export const EXAMPLE_FILES: SharedFile[] = [
  ["tech", "PDF", "", "IEC 62271-1 2025판 변경 요약.pdf", "이전 판과 달라진 조항 31개 정리", "기술 검토 엔지니어 D", "10-16", "1.2 MB", 23],
  ["cust", "XLSX", "x", "고객별 RFP 특이 조건 — 베트남·사우디.xlsx", "고객 12곳의 반복 요구와 지난 대응", "기술 검토 엔지니어 B", "10-10", "96 KB", 31],
  ["guide", "DOCX", "", "질의서 작성 가이드 v2.docx", "좋은 질의 문장 예시와 피할 표현", "기술 검토 엔지니어 C", "09-29", "310 KB", 27],
  ["form", "XLSX", "x", "제품표 일괄 올리기 양식 2026.xlsx", "열 2개 추가된 최신 양식 (10-14)", "설계 담당 D", "10-14", "64 KB", 18],
  ["guide", "DOCX", "", "Addendum 처리 체크리스트.docx", "개정 문서를 받았을 때 확인할 9가지", "기술 검토 엔지니어 A", "10-02", "88 KB", 14],
  ["tech", "XLSX", "x", "형식시험 성적서 색인 2026 상반기.xlsx", "제품별 성적서 번호와 시험 기관", "기술 검토 엔지니어 D", "07-15", "140 KB", 22],
  ["cust", "XLSX", "x", "해외 인증서 목록 (KEMA·CESI) 2026.xlsx", "인증서 번호, 유효 기간, 적용 제품", "설계 담당 D", "06-30", "72 KB", 16],
  ["guide", "PDF", "", "고전압 시험실 안전 수칙.pdf", "EHS팀 배포본 (2026-1)", "결재자", "03-04", "2.4 MB", 40],
]

/** 파일 올리기를 누르면 화면 안에만 생기는 예시 파일 */
export const EXAMPLE_UPLOAD: SharedFile = ["guide", "PDF", "", "GIS 내진 판정 사례 정리.pdf", "예시 사업장 E·J 건 IEEE 693 판정 근거", "기술 검토 엔지니어 A", "10-24", "860 KB", 0]
