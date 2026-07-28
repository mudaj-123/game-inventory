"""P0 仓库结构的无第三方依赖检查。"""

import csv
import subprocess
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


def test_setup_help_documents_optional_checks() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/setup.sh"), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--skip-checks" in result.stdout
    assert "pytest and Ruff" in result.stdout


def test_setup_rejects_unknown_options_before_installing() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/setup.sh"), "--not-an-option"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "unknown option: --not-an-option" in result.stderr
