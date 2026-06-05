"""CSV parser with configurable delimiter, encoding, and BOM handling."""
from __future__ import annotations

import csv
import io
import frappe

DELIMITER_MAP = {
	"Comma": ",",
	"Semicolon": ";",
	"Tab": "\t",
	"Pipe": "|",
}

ENCODING_MAP = {
	"UTF-8": "utf-8-sig",   # utf-8-sig strips BOM automatically
	"UTF-16": "utf-16",
	"Latin-1": "latin-1",
	"Windows-1252": "cp1252",
}


class CSVParser:
	def __init__(self, profile: dict):
		self.profile = profile

	def parse(self, file_content: bytes) -> list[dict]:
		encoding_key = self.profile.get("csv_encoding") or "UTF-8"
		encoding = ENCODING_MAP.get(encoding_key, "utf-8-sig")

		try:
			text = file_content.decode(encoding)
		except (UnicodeDecodeError, LookupError):
			try:
				import chardet
				detected = chardet.detect(file_content)
				text = file_content.decode(detected.get("encoding") or "utf-8", errors="replace")
			except Exception as e:
				frappe.throw(f"Cannot decode CSV file: {e}", frappe.ValidationError)

		delimiter_key = self.profile.get("csv_delimiter") or "Comma"
		delimiter = DELIMITER_MAP.get(delimiter_key, ",")
		quote_char = (self.profile.get("csv_quote_char") or '"')[:1] or '"'
		has_header = bool(self.profile.get("csv_has_header", True))
		skip_empty = bool(self.profile.get("skip_empty_rows", True))

		reader = csv.reader(io.StringIO(text), delimiter=delimiter, quotechar=quote_char)
		rows = list(reader)

		if not rows:
			return []

		if has_header:
			raw_headers = rows[0]
			headers = [h.strip().lower().replace(" ", "_") for h in raw_headers]
			data_rows = rows[1:]
		else:
			# Generate positional headers: col_1, col_2, ...
			headers = [f"col_{i+1}" for i in range(len(rows[0]))]
			data_rows = rows

		result = []
		for row_idx, row in enumerate(data_rows, start=2 if has_header else 1):
			if skip_empty and all(v.strip() == "" for v in row):
				continue
			# Pad short rows to header length
			padded = row + [""] * (len(headers) - len(row))
			row_dict = {headers[i]: padded[i].strip() or None for i in range(len(headers))}
			row_dict["_source_row"] = row_idx
			result.append(row_dict)

		return result
