-- PDF 원문 위치의 쪽 번호 (add-pdf-page-location). 쪽마다 첫 줄 번호, 줄 번호 → 쪽 번호
ALTER TABLE document ADD COLUMN page_starts INTEGER[];   -- i번째 값 = i쪽 첫 줄 (PDF만, docx는 NULL)

-- 시작 줄이 그 줄 이하인 가장 큰 쪽 번호. 빈 쪽은 다음 쪽과 시작 줄이 같아 다음 쪽이 골라진다
CREATE FUNCTION line_page(starts INTEGER[], line INTEGER) RETURNS INTEGER
  LANGUAGE sql IMMUTABLE AS $$
    SELECT max(u.n)::int FROM unnest(starts) WITH ORDINALITY AS u(s, n) WHERE u.s <= line
  $$;
