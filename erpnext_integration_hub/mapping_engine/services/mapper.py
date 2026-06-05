"""Mapper — applies a Field Mapping Profile to a raw row dict.

The Mapper is the only entry point into the mapping system. It loads the
profile from cache, normalises source headers, applies rules in sequence
order, and returns a structured dict ready for DocumentFactory consumption.
"""
from __future__ import annotations

import frappe
from erpnext_integration_hub.utils.cache import get_mapping_profile
from .transformer import TRANSFORMER_MAP


class Mapper:
	"""Apply a Field Mapping Profile to one source row dict.

	Constructor receives the profile name (string); profile data is loaded
	from cache so that N items in a batch share one DB read.
	"""

	def __init__(self, profile_name: str):
		self.profile_name = profile_name
		self._profile_data = None  # lazy-loaded

	@property
	def profile(self) -> dict:
		if self._profile_data is None:
			self._profile_data = get_mapping_profile(self.profile_name)
		return self._profile_data

	def map(self, raw_row: dict) -> dict:
		"""Transform raw_row using all rules. Returns the mapped header dict
		and a nested `_items` key containing child table rows when child table
		mappings are configured.

		All transformations operate on a copy of raw_row — the original is
		never mutated.
		"""
		source_row = dict(raw_row)  # shallow copy; originals preserved for audit
		case_sensitive = bool(self.profile.get("header_case_sensitive"))

		if not case_sensitive:
			source_row = self._normalise_keys(source_row)

		mapped = {}
		rules = sorted(
			self.profile.get("mapping_rules") or [],
			key=lambda r: int(r.get("sequence") or 0),
		)

		for rule in rules:
			source_field = rule.get("source_field") or ""
			target_field = rule.get("target_field") or ""
			if not target_field:
				continue

			if not case_sensitive:
				source_field = source_field.strip().lower().replace(" ", "_")

			raw_value = source_row.get(source_field)

			# Required check before transformation so the error message names
			# the source field, not the transformed value
			if rule.get("is_required") and (raw_value is None or raw_value == ""):
				if not rule.get("default_value"):
					frappe.throw(
						f"Required source field '{rule.get('source_field')}' is missing or empty.",
						frappe.ValidationError,
					)

			transformation_type = rule.get("transformation_type") or "None"
			transformer_fn = TRANSFORMER_MAP.get(transformation_type, TRANSFORMER_MAP["None"])
			transformed = transformer_fn(raw_value, source_row, rule)

			if transformed is None and rule.get("default_value"):
				transformed = rule["default_value"]

			mapped[target_field] = transformed

		# Child table mapping
		child_mappings = self.profile.get("child_table_mappings") or []
		if child_mappings:
			mapped["_child_tables"] = self._map_child_tables(source_row, child_mappings)

		return mapped

	def _map_child_tables(self, source_row: dict, child_mappings: list) -> dict:
		"""Map child table rows from the source row.

		For flat-file formats (Excel/CSV), all rows have the same structure, so
		child table data is encoded differently: the source row contains a JSON
		array string under the grouping field key.  For XML/JSON formats, the
		raw value may already be a serialised nested structure.
		"""
		import json
		result = {}

		for cm in child_mappings:
			ct_fieldname = cm.get("target_child_table_fieldname")
			source_grouping_field = cm.get("source_grouping_field")

			raw_child_value = source_row.get(source_grouping_field)
			if not raw_child_value:
				continue

			# Attempt to parse as JSON array of dicts
			if isinstance(raw_child_value, str):
				try:
					child_rows_raw = json.loads(raw_child_value)
				except json.JSONDecodeError:
					child_rows_raw = [{"value": raw_child_value}]
			elif isinstance(raw_child_value, list):
				child_rows_raw = raw_child_value
			else:
				child_rows_raw = [{"value": str(raw_child_value)}]

			result[ct_fieldname] = child_rows_raw

		return result

	@staticmethod
	def _normalise_keys(d: dict) -> dict:
		return {
			k.strip().lower().replace(" ", "_"): v
			for k, v in d.items()
		}
