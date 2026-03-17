from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from qt_modula.modules_builtin.importers import (
    JsonImportModule,
    TableImportModule,
    TextImportModule,
)
from qt_modula.modules_builtin.registry import build_registry


def test_import_family_is_registered_between_providers_and_transform() -> None:
    registry, issues = build_registry()
    assert issues == []

    labels = [f"{descriptor.family}/{descriptor.display_name}" for descriptor in registry.descriptors()]

    assert labels.index("Providers/Market Fetcher") < labels.index("Import/Text Import")
    assert labels.index("Import/Table Import") < labels.index("Transform/Datetime Convert")


def test_text_import_stages_path_without_reading(qapp, tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello", encoding="utf-8")

    module = TextImportModule("text_1")
    widget = module.widget()
    qapp.processEvents()

    module.receive_binding("path", str(path))
    qapp.processEvents()

    assert module.snapshot_inputs() == {
        "path": str(path.resolve()),
        "auto_import": False,
    }
    assert module.outputs["content"] == ""
    assert module.outputs["imported"] == 0
    assert "staged path" in str(module.outputs["text"])

    widget.close()
    module.on_close()


def test_text_import_auto_import_reads_file(wait_for, qapp, tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello\nworld", encoding="utf-8")

    module = TextImportModule("text_2")
    widget = module.widget()
    module.receive_binding("auto_import", True)
    module.receive_binding("path", str(path))

    wait_for(lambda: module.outputs["imported"] == 1 and not module.outputs["busy"])
    qapp.processEvents()

    assert module.outputs["content"] == "hello\nworld"
    assert module.outputs["char_count"] == 11
    assert module.outputs["line_count"] == 2
    assert module.outputs["path"] == str(path.resolve())

    widget.close()
    module.on_close()


def test_json_import_failure_clears_stale_outputs(wait_for, qapp, tmp_path: Path) -> None:
    valid = tmp_path / "data.json"
    valid.write_text('{"name":"alpha"}', encoding="utf-8")

    module = JsonImportModule("json_1")
    widget = module.widget()
    module.receive_binding("path", str(valid))
    module.receive_binding("import", 1)
    wait_for(lambda: module.outputs["imported"] == 1 and not module.outputs["busy"])

    missing = tmp_path / "missing.json"
    module.receive_binding("path", str(missing))
    module.receive_binding("import", 1)
    wait_for(lambda: str(module.outputs["error"]) != "" and not module.outputs["busy"])
    qapp.processEvents()

    assert module.outputs["json"] == {}
    assert module.outputs["keys"] == []
    assert module.outputs["item_count"] == 0
    assert module.outputs["path"] == ""
    assert module.outputs["imported"] == 0

    widget.close()
    module.on_close()


def test_table_import_restores_without_implicit_read(qapp, tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    path.write_text("name,value\nalpha,1\n", encoding="utf-8")

    module = TableImportModule("table_1")
    module.restore_inputs(
        {
            "path": str(path.resolve()),
            "auto_import": True,
            "format": "auto",
            "sheet_name": "",
        }
    )
    widget = module.widget()
    qapp.processEvents()

    assert module.snapshot_inputs() == {
        "path": str(path.resolve()),
        "auto_import": True,
        "format": "auto",
        "sheet_name": "",
    }
    assert module.outputs["rows"] == []
    assert module.outputs["imported"] == 0
    assert module.outputs["busy"] is False

    widget.close()
    module.on_close()


def test_table_import_manual_import_reads_csv(wait_for, qapp, tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    path.write_text("name,value\nalpha,1\nbeta,2\n", encoding="utf-8")

    module = TableImportModule("table_2")
    widget = module.widget()
    module.receive_binding("path", str(path))
    module.receive_binding("import", 1)

    wait_for(lambda: module.outputs["imported"] == 1 and not module.outputs["busy"])
    qapp.processEvents()

    assert module.outputs["row_count"] == 2
    assert module.outputs["column_count"] == 2
    assert module.outputs["columns"] == ["name", "value"]
    assert module.outputs["rows"][0] == {"name": "alpha", "value": "1"}

    widget.close()
    module.on_close()


def test_table_import_manual_import_reads_xlsx(wait_for, qapp, tmp_path: Path) -> None:
    path = tmp_path / "rows.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Metrics"
    sheet.append(["name", "value"])
    sheet.append(["alpha", 1])
    workbook.save(path)

    module = TableImportModule("table_3")
    widget = module.widget()
    module.receive_binding("path", str(path))
    module.receive_binding("sheet_name", "Metrics")
    module.receive_binding("import", 1)

    wait_for(lambda: module.outputs["imported"] == 1 and not module.outputs["busy"])
    qapp.processEvents()

    assert module.outputs["rows"] == [{"name": "alpha", "value": 1}]
    assert module.outputs["path"] == str(path.resolve())

    widget.close()
    module.on_close()
