from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from qt_modula.services.errors import ServiceError
from qt_modula.services.file_import import (
    JsonImportRequest,
    TableImportRequest,
    TextImportRequest,
    read_json_file,
    read_table_file,
    read_text_file,
)


def test_read_text_file_reports_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"

    with pytest.raises(ServiceError) as exc_info:
        read_text_file(TextImportRequest(path=missing))

    assert exc_info.value.kind == "not_found"


def test_read_text_file_supports_utf8_sig(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_bytes("hello\nworld".encode("utf-8-sig"))

    result = read_text_file(TextImportRequest(path=path))

    assert result.content == "hello\nworld"
    assert result.char_count == 11
    assert result.line_count == 2


def test_read_json_file_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ServiceError) as exc_info:
        read_json_file(JsonImportRequest(path=path))

    assert exc_info.value.kind == "validation"
    assert "Invalid JSON file" in exc_info.value.message


def test_read_json_file_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "data.txt"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ServiceError) as exc_info:
        read_json_file(JsonImportRequest(path=path))

    assert "Unsupported JSON file extension" in exc_info.value.message


def test_read_table_file_reads_csv(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    path.write_text("name,value\nalpha,1\nbeta,2\n", encoding="utf-8")

    result = read_table_file(TableImportRequest(path=path))

    assert result.format == "csv"
    assert result.columns == ["name", "value"]
    assert result.row_count == 2
    assert result.rows[0] == {"name": "alpha", "value": "1"}


def test_read_table_file_reads_jsonl_and_wraps_scalars(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text('{"name":"alpha"}\n3\n', encoding="utf-8")

    result = read_table_file(TableImportRequest(path=path))

    assert result.format == "jsonl"
    assert result.columns == ["name", "value"]
    assert result.rows == [{"name": "alpha"}, {"value": 3}]


def test_read_table_file_rejects_invalid_jsonl_row(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text("{bad}\n", encoding="utf-8")

    with pytest.raises(ServiceError) as exc_info:
        read_table_file(TableImportRequest(path=path))

    assert "Invalid JSONL row 1" in exc_info.value.message


def test_read_table_file_reads_xlsx_and_reports_sheet(tmp_path: Path) -> None:
    path = tmp_path / "rows.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Metrics"
    sheet.append(["name", "value"])
    sheet.append(["alpha", 1])
    workbook.save(path)

    result = read_table_file(TableImportRequest(path=path))

    assert result.format == "xlsx"
    assert result.sheet_name == "Metrics"
    assert result.columns == ["name", "value"]
    assert result.rows == [{"name": "alpha", "value": 1}]


def test_read_table_file_rejects_missing_sheet(tmp_path: Path) -> None:
    path = tmp_path / "rows.xlsx"
    workbook = Workbook()
    workbook.active.title = "Sheet1"
    workbook.save(path)

    with pytest.raises(ServiceError) as exc_info:
        read_table_file(TableImportRequest(path=path, sheet_name="Missing"))

    assert "Sheet 'Missing' was not found" in exc_info.value.message
