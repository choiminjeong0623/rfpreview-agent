import shutil

import pytest

from rfp_agent.db.migrate import migrate
from rfp_agent.db.seed import SeedError, seed_products, seed_rules

from .conftest import FIXTURES


def test_migrate_applies_each_file_once(empty_db, settings):
    """Scenario: 빈 DB에 처음 적용 / 두 번째 실행 / 유형 7종."""
    first = migrate(empty_db, settings.migrations_dir)
    assert first[:2] == ["0001_schema_v1", "0002_reference_codes"]
    assert migrate(empty_db, settings.migrations_dir) == []
    types = dict(empty_db.execute("SELECT type_code, default_role FROM requirement_type"))
    assert len(types) == 7
    assert types["COST"] == "COST"


def test_seed_rules_is_repeatable(empty_db, settings):
    """Scenario: 두 번 적재."""
    migrate(empty_db, settings.migrations_dir)
    first = seed_rules(empty_db, settings.seed_dir)
    second = seed_rules(empty_db, settings.seed_dir)
    assert first.counts == second.counts
    assert first.counts["compare_rule"] == 39
    row = empty_db.execute(
        "SELECT direction, time_condition FROM compare_rule "
        "WHERE table_name = 'TS-115-GIS' AND item_no = '16'"
    ).fetchone()
    assert row == ("GE", True)
    fixed = empty_db.execute(
        "SELECT fixed_value FROM company_fixed_value WHERE fixed_key = 'manufacturer'"
    ).fetchone()
    assert fixed == ("LS ELECTRIC",)


def test_seed_products_later_file_wins_and_losses(empty_db, settings):
    """Scenario: 뒤 파일이 이긴다 / 손실값과 팀 가정 / 제품표에 없는 손실값."""
    migrate(empty_db, settings.migrations_dir)
    report = seed_products(
        empty_db,
        [FIXTURES / "products.csv", FIXTURES / "products_v2.csv"],
        FIXTURES / "losses.csv",
    )
    assert report.counts["product_master"] == 3
    assert report.skipped == ["loss: TRF-NONE (제품표에 없음)"]
    trf = empty_db.execute(
        "SELECT product_name, noload_loss_kw, load_loss_kw, aux_loss_kw, loss_is_assumed "
        "FROM product_master WHERE product_code = 'TRF-HV'"
    ).fetchone()
    assert trf[0] == "초고압 변압기 (550 kV 이하)"
    assert [float(v) for v in trf[1:4]] == [60, 300, 8]
    assert trf[4] is True
    card = empty_db.execute(
        "SELECT is_design_card FROM product_master WHERE product_code = 'GIS-145-P7'"
    ).fetchone()
    assert card == (True,)


def test_seed_products_replace_clears_old_products_and_runs(empty_db, settings, tmp_path):
    """Scenario: 제품표 바꾸기 / 이전 제품이 남아 있음"""
    migrate(empty_db, settings.migrations_dir)
    seed_products(empty_db, [FIXTURES / "products.csv"])
    run_id = empty_db.execute(
        "INSERT INTO review_run (started_by, stage, dict_version) "
        "VALUES (1, 'ENGINEER_REVIEW', 'test') RETURNING run_id").fetchone()[0]
    empty_db.execute("INSERT INTO run_product_choice (run_id, equipment_group, product_code) "
                     "VALUES (%s, 'g', 'GIS-145')", (run_id,))
    new_file = tmp_path / "new.csv"
    new_file.write_text("product_code,product_name,family,family_name,is_assumed,source_doc\n"
                        "GIS-245-50,GIS 245kV 50kA,GIS,Gas-insulated switchgear,N,CAT p.1\n",
                        encoding="utf-8")

    kept = seed_products(empty_db, [new_file])
    assert kept.skipped == ["파일에 없는 이전 제품 3개가 DB에 남아 있음 "
                            "(비우려면 seed-products --replace)"]

    report = seed_products(empty_db, [new_file], replace=True)
    assert report.skipped == []
    codes = empty_db.execute("SELECT product_code FROM product_master").fetchall()
    assert codes == [("GIS-245-50",)]
    families = empty_db.execute("SELECT family, family_name FROM product_family").fetchall()
    assert families == [("GIS", "Gas-insulated switchgear")]
    assert empty_db.execute("SELECT count(*) FROM review_run").fetchone()[0] == 0


def test_unknown_direction_stops_without_loading(empty_db, settings, tmp_path):
    """Scenario: 모르는 비교 방향."""
    migrate(empty_db, settings.migrations_dir)
    seed_dir = tmp_path / "seed"
    shutil.copytree(settings.seed_dir, seed_dir)
    rules = seed_dir / "compare_rules.csv"
    rules.write_text(rules.read_text(encoding="utf-8-sig").replace(",≥,", ",약간 큼,", 1),
                     encoding="utf-8")
    with pytest.raises(SeedError, match="TS-115-GIS"):
        seed_rules(empty_db, seed_dir)
    assert empty_db.execute("SELECT count(*) FROM item_key").fetchone()[0] == 0
