-- 물량표(BOQ) 문서 종류 (add-boq-processor, C1)
ALTER TABLE document DROP CONSTRAINT document_doc_kind_check;
ALTER TABLE document ADD CONSTRAINT document_doc_kind_check CHECK (doc_kind IN
  ('BID_FORM','REQUIREMENT_SPEC','PURCHASE_SPEC','TEST_SPEC','SUPPLIER_SPEC','BOQ','UNKNOWN'));
ALTER TABLE doc_kind_rule DROP CONSTRAINT doc_kind_rule_doc_kind_check;
ALTER TABLE doc_kind_rule ADD CONSTRAINT doc_kind_rule_doc_kind_check CHECK (doc_kind IN
  ('BID_FORM','REQUIREMENT_SPEC','PURCHASE_SPEC','TEST_SPEC','SUPPLIER_SPEC','BOQ'));
