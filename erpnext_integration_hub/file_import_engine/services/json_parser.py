"""JSON parser with JSONPath support for nested structures."""
from __future__ import annotations

import json
import frappe


class JSONParser:
	def __init__(self, profile: dict):
		self.profile = profile

	def parse(self, file_content: bytes) -> list[dict]:
		try:
			text = file_content.decode("utf-8-sig")
		except UnicodeDecodeError:
			text = file_content.decode("latin-1", errors="replace")

		try:
			data = json.loads(text)
		except json.JSONDecodeError as e:
			frappe.throw(f"Invalid JSON: {e}", frappe.ValidationError)

		records_path = self.profile.get("json_records_path") or None

		if records_path and records_path != "$":
			records = self._extract_by_jsonpath(data, records_path)
		elif isinstance(data, list):
			records = data
		elif isinstance(data, dict):
			# Heuristic: find the first list value in the root dict
			records = None
			for v in data.values():
				if isinstance(v, list):
					records = v
					break
			if records is None:
				records = [data]
		else:
			frappe.throw("Cannot determine records from JSON structure.", frappe.ValidationError)

		result = []
		for row_idx, record in enumerate(records, start=1):
			if not isinstance(record, dict):
				frappe.throw(
					f"Row {row_idx}: expected a JSON object (dict), got {type(record).__name__}.",
					frappe.ValidationError,
				)
			flat = self._flatten(record)
			flat["_source_row"] = row_idx
			result.append(flat)

		return result

	@staticmethod
	def _extract_by_jsonpath(data, path: str) -> list:
		try:
			from jsonpath_ng import parse as jp_parse
		except ImportError:
			frappe.throw("jsonpath-ng is not installed. Run: pip install jsonpath-ng")

		try:
			expr = jp_parse(path)
		except Exception as e:
			frappe.throw(f"Invalid JSONPath expression '{path}': {e}", frappe.ValidationError)

		matches = [match.value for match in expr.find(data)]
		if not matches:
			frappe.throw(f"JSONPath '{path}' matched no records.", frappe.ValidationError)

		# If the expression matched a single list, unwrap it
		if len(matches) == 1 and isinstance(matches[0], list):
			return matches[0]
		return matches

	@staticmethod
	def _flatten(d: dict, prefix: str = "", sep: str = ".") -> dict:
		"""Flatten nested dicts with dot-notation keys.

		e.g. {"customer": {"name": "Alice"}} → {"customer.name": "Alice"}

		Lists are stored as JSON strings for the mapper to handle.
		"""
		result = {}
		for k, v in d.items():
			key = f"{prefix}{sep}{k}" if prefix else k
			if isinstance(v, dict):
				result.update(JSONParser._flatten(v, key, sep))
			elif isinstance(v, list):
				result[key] = json.dumps(v)
			elif v is None:
				result[key] = None
			else:
				result[key] = str(v).strip() or None
		return result
