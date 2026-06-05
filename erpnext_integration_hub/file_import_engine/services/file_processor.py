"""Orchestrates format detection and parser dispatch for a single file."""
from __future__ import annotations

import os
import frappe

from .excel_parser import ExcelParser
from .csv_parser import CSVParser
from .xml_parser import XMLParser
from .json_parser import JSONParser


EXTENSION_FORMAT_MAP = {
	".xlsx": "Excel",
	".xls": "Excel",
	".csv": "CSV",
	".xml": "XML",
	".json": "JSON",
}


class FileProcessor:
	"""Detect file format and invoke the correct parser.

	Takes raw bytes and a File Import Profile dict; returns a list of row dicts.
	Raises frappe.ValidationError for any file-level problem (bad format,
	unreadable content) so the caller can log a Parse error and move on.
	"""

	def __init__(self, profile: dict):
		self.profile = profile

	def process(self, filename: str, file_content: bytes) -> list[dict]:
		fmt = self._detect_format(filename)
		parser = self._get_parser(fmt)
		return parser.parse(file_content)

	def _detect_format(self, filename: str) -> str:
		"""Prefer the profile's declared format; fall back to file extension."""
		profile_format = self.profile.get("file_format")
		if profile_format:
			return profile_format

		ext = os.path.splitext(filename.lower())[1]
		fmt = EXTENSION_FORMAT_MAP.get(ext)
		if not fmt:
			frappe.throw(
				f"Unsupported file extension '{ext}'. "
				"Supported: .xlsx, .csv, .xml, .json",
				frappe.ValidationError,
			)
		return fmt

	def _get_parser(self, fmt: str):
		parsers = {
			"Excel": ExcelParser,
			"CSV": CSVParser,
			"XML": XMLParser,
			"JSON": JSONParser,
		}
		klass = parsers.get(fmt)
		if not klass:
			frappe.throw(f"No parser available for format '{fmt}'.", frappe.ValidationError)
		return klass(self.profile)
