-- 2단계 문서 처리(add-document-pipeline)에 필요한 칸과 사전 표

-- 문서 원본과 줄 번호 기준
ALTER TABLE document ADD COLUMN source_path TEXT;
ALTER TABLE document ADD COLUMN line_basis VARCHAR(4) NOT NULL DEFAULT 'DOCX'
  CHECK (line_basis IN ('TXT','DOCX'));        -- TXT: 팀 추출 txt 줄 번호와 맞춤 (추적표 v3 기준)
-- 구조·추출 결과를 만든 판: 사전 판 + 처리 코드 판 + AI 모델·프롬프트 판 (예: 3cb1c99f8f41-54e98af-rule)
ALTER TABLE document ADD COLUMN processing_key VARCHAR(80);
-- 판이 바뀌면 같은 파일을 새 행으로 다시 처리한다. 이전 실행의 결과(요구사항·위험 조건)는 그대로 남는다 (CR-11).
ALTER TABLE document DROP CONSTRAINT document_file_no_key;
CREATE UNIQUE INDEX ux_document_version ON document (file_no, processing_key);

-- 실행 실패 정보와 언어 모델 기록 (CR-12)
ALTER TABLE review_run ADD COLUMN failed_step VARCHAR(30);
ALTER TABLE review_run ADD COLUMN error_message TEXT;
ALTER TABLE review_run ADD COLUMN llm_model VARCHAR(60);              -- NULL이면 AI 보조 없이 처리
ALTER TABLE review_run ADD COLUMN finished_at TIMESTAMPTZ;

-- 원본·정정본 쌍은 실행과 무관하게 같은 쌍이 한 번만
CREATE UNIQUE INDEX ux_document_pair ON document_pair (LEAST(document_id_a, document_id_b),
                                                     GREATEST(document_id_a, document_id_b));

-- 표·행에 원래 Word 표 번호와 하위 항목 표시
ALTER TABLE table_row ADD COLUMN source_table_no INT;
ALTER TABLE table_row ADD COLUMN cells JSONB;                         -- 칸 원문 전체 (역할 못 찾은 칸 포함)

-- 요구사항 판단 근거
ALTER TABLE requirement ADD COLUMN rule_id VARCHAR(40);               -- 추출·구분 규칙 ID
ALTER TABLE requirement ADD COLUMN supplier_mark CHAR(1) CHECK (supplier_mark IN ('C','D','E'));
ALTER TABLE requirement_type_tag ADD COLUMN ai_type_code VARCHAR(20) REFERENCES requirement_type(type_code);
                                                                      -- 규칙과 AI가 다를 때 AI 판단

-- 값 정리: 위치 칸 (같은 요구사항 안에서 몇 번째 값인지)
ALTER TABLE req_value ADD COLUMN value_seq SMALLINT NOT NULL DEFAULT 1;

-- 위험 조건: 코드가 정한 사실 (AI 설명이 없어도 남음)
ALTER TABLE risk_flag ADD COLUMN facts TEXT;
ALTER TABLE risk_flag ADD COLUMN item_key VARCHAR(40) REFERENCES item_key(item_key);

-- 파일 목록 (기획서 부록 A). 사업 묶음 표를 겸함
CREATE TABLE document_catalog (
  file_no         SMALLINT PRIMARY KEY,
  file_key        VARCHAR(200) NOT NULL UNIQUE,     -- 파일명에 들어 있는 고유 부분
  bundle          CHAR(1) NOT NULL CHECK (bundle IN ('A','B','C','D')),
  language        VARCHAR(10) NOT NULL,
  project_key     VARCHAR(20),                      -- 비면 사업 확인 필요(문서 안에서만 비교)
  note            TEXT
);
ALTER TABLE project ADD COLUMN project_key VARCHAR(20) UNIQUE;

-- 적용 대상 사전 (값 불일치 비교 범위, FR-06)
CREATE TABLE target_object_dict (
  term            VARCHAR(100) PRIMARY KEY,         -- 원문 표현 (소문자 비교)
  target_object   VARCHAR(40) NOT NULL,             -- GIS, 차단기, 케이블, UPS ...
  parent_object   VARCHAR(40)                       -- 차단기 ⊂ GIS
);

-- 유형 규칙표 패턴 종류
ALTER TABLE type_rule ADD COLUMN rule_code VARCHAR(20) UNIQUE;
ALTER TABLE type_rule ADD COLUMN match_kind VARCHAR(10) NOT NULL DEFAULT 'WORD'
  CHECK (match_kind IN ('WORD','REGEX'));

-- 사전을 다시 적재할 때 지우지 않고 갱신하기 위한 자연키 (결과 표가 사전 행을 참조한다)
CREATE UNIQUE INDEX ux_risk_expression ON risk_expression (expression);
CREATE UNIQUE INDEX ux_compare_rule ON compare_rule (table_name, item_no, COALESCE(item_key, ''));

-- 같은 요구가 여러 곳에 있을 때 묶는 열쇠 (표: 표 이름+항목, 문장: 정규화한 문장)
ALTER TABLE requirement ADD COLUMN dedup_key TEXT;
CREATE INDEX ix_requirement_dedup ON requirement (dedup_key);

-- 로그인 전(4단계)까지 검토를 시작하는 기본 사용자
INSERT INTO app_user (user_name, role) VALUES ('기본 엔지니어', 'ENGINEER');
