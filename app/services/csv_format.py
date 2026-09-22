"""Spreadsheet-safe text cells with an explicit reversible catalog export marker."""

TEXT_ENCODING = "apostrophe-v1"
TEXT_ENCODING_COLUMN = "csv_text_encoding"


def safe_cell(value: object) -> str:
    text = "" if value is None else str(value)
    # Escape literal apostrophes too, so marked exports can be decoded without ambiguity.
    if text.startswith(("'", "\t", "\r", "\n")) or text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def decode_catalog_row(row: dict[str, str]) -> dict[str, str]:
    encoding = row.get(TEXT_ENCODING_COLUMN, "")
    if not encoding:
        return row
    if encoding != TEXT_ENCODING:
        raise ValueError("不支持的 CSV 文本编码标记")
    return {key: value[1:] if isinstance(value, str) and value.startswith("'") else value
            for key, value in row.items()}
