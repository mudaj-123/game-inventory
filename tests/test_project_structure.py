"""P0 仓库结构的无第三方依赖检查。"""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_template_preserves_barcode_as_text() -> None:
    with (ROOT / "data/catalog/barcode_catalog.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert rows
    assert rows[0]["barcode"] == "00000000"
    assert all(isinstance(row["barcode"], str) for row in rows)


def test_spec_uses_canonical_filename() -> None:
    assert (ROOT / "PROJECT_SPEC.md").is_file()
    assert not (ROOT / "PROJECT_SPEC (1).md").exists()
