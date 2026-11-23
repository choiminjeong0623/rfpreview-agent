-- 로그인과 세션 (add-session-auth). 요청 값의 사용자 번호 대신 로그인한 사용자를 쓴다.
-- 비밀번호는 rfp-db set-password · demo-setup --password로만 넣는다. 비밀번호가 없으면 로그인할 수 없다
ALTER TABLE app_user
  ADD COLUMN login_id      VARCHAR(40) UNIQUE,
  ADD COLUMN password_hash VARCHAR(300),
  ADD COLUMN is_active     BOOLEAN NOT NULL DEFAULT true;

-- 마이그레이션이 넣은 기본 사용자에 로그인 아이디 (역할마다 가장 먼저 만든 사용자)
UPDATE app_user u SET login_id = v.login_id
  FROM (VALUES ('ENGINEER', 'engineer'), ('APPROVER', 'approver'), ('COST', 'cost'),
               ('QUALITY', 'quality'), ('SALES', 'sales')) AS v(role, login_id)
 WHERE u.user_id = (SELECT min(user_id) FROM app_user WHERE role = v.role);

-- 세션: 쿠키에는 token만. 로그아웃하면 revoked_at, 만료는 expires_at (고정 만료)
CREATE TABLE user_session (
  token       UUID PRIMARY KEY,
  user_id     INT NOT NULL REFERENCES app_user(user_id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at  TIMESTAMPTZ NOT NULL,
  revoked_at  TIMESTAMPTZ
);
CREATE INDEX user_session_user ON user_session (user_id);
