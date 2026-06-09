"""Unit tests for Mapper.map().

The Mapper sits between raw parsed rows and document creation — a bug here
silently produces wrong field values on real ERPNext documents. Tests build
profile dicts directly (bypassing the cache) so each case is explicit about
the rules under test.
"""
from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_integration_hub.mapping_engine.services.mapper import Mapper


def _mapper_with_profile(profile: dict) -> Mapper:
	mapper = Mapper("__test_profile__")
	mapper._profile_data = profile
	return mapper


class TestMapperBasicMapping(FrappeTestCase):
	def test_maps_fields_in_sequence_order(self):
		profile = {
			"header_case_sensitive": 0,
			"mapping_rules": [
				{"sequence": 2, "source_field": "Cust Name", "target_field": "customer_name"},
				{"sequence": 1, "source_field": "Cust Code", "target_field": "customer"},
			],
		}
		mapper = _mapper_with_profile(profile)
		result = mapper.map({"Cust Code": "C001", "Cust Name": "Acme Inc"})
		self.assertEqual(result["customer"], "C001")
		self.assertEqual(result["customer_name"], "Acme Inc")

	def test_header_normalisation_is_case_insensitive_by_default(self):
		profile = {
			"mapping_rules": [
				{"sequence": 1, "source_field": "Customer Code", "target_field": "customer"},
			],
		}
		mapper = _mapper_with_profile(profile)
		# Source row uses different casing/spacing than the rule
		result = mapper.map({"customer_code": "C002"})
		self.assertEqual(result["customer"], "C002")

	def test_case_sensitive_profile_does_not_normalise(self):
		profile = {
			"header_case_sensitive": 1,
			"mapping_rules": [
				{"sequence": 1, "source_field": "CustomerCode", "target_field": "customer"},
			],
		}
		mapper = _mapper_with_profile(profile)
		# Lowercase key should NOT match the case-sensitive rule
		result = mapper.map({"customercode": "C003"})
		self.assertIsNone(result["customer"])

	def test_rules_without_target_field_are_skipped(self):
		profile = {
			"mapping_rules": [
				{"sequence": 1, "source_field": "ignored", "target_field": ""},
				{"sequence": 2, "source_field": "code", "target_field": "customer"},
			],
		}
		mapper = _mapper_with_profile(profile)
		result = mapper.map({"code": "C004", "ignored": "x"})
		self.assertEqual(result, {"customer": "C004"})

	def test_original_row_is_not_mutated(self):
		profile = {
			"mapping_rules": [
				{"sequence": 1, "source_field": "code", "target_field": "customer"},
			],
		}
		mapper = _mapper_with_profile(profile)
		raw_row = {"code": "C005"}
		mapper.map(raw_row)
		self.assertEqual(raw_row, {"code": "C005"})


class TestMapperRequiredAndDefaults(FrappeTestCase):
	def test_required_field_missing_throws(self):
		profile = {
			"mapping_rules": [
				{
					"sequence": 1,
					"source_field": "code",
					"target_field": "customer",
					"is_required": 1,
				},
			],
		}
		mapper = _mapper_with_profile(profile)
		with self.assertRaises(frappe.ValidationError):
			mapper.map({"code": ""})

	def test_required_field_with_default_does_not_throw(self):
		profile = {
			"mapping_rules": [
				{
					"sequence": 1,
					"source_field": "code",
					"target_field": "customer",
					"is_required": 1,
					"default_value": "FALLBACK",
					"transformation_type": "None",
				},
			],
		}
		mapper = _mapper_with_profile(profile)
		result = mapper.map({"code": ""})
		self.assertEqual(result["customer"], "FALLBACK")

	def test_transformer_none_falls_back_to_default(self):
		profile = {
			"mapping_rules": [
				{
					"sequence": 1,
					"source_field": "code",
					"target_field": "customer",
					"transformation_type": "Static Value",
					"default_value": "STATIC-CUSTOMER",
				},
			],
		}
		mapper = _mapper_with_profile(profile)
		result = mapper.map({"code": "ignored-by-static"})
		self.assertEqual(result["customer"], "STATIC-CUSTOMER")


class TestMapperChildTables(FrappeTestCase):
	def test_child_table_from_json_array_string(self):
		profile = {
			"mapping_rules": [
				{"sequence": 1, "source_field": "code", "target_field": "customer"},
			],
			"child_table_mappings": [
				{
					"target_child_table_fieldname": "items",
					"source_grouping_field": "line_items",
				},
			],
		}
		mapper = _mapper_with_profile(profile)
		raw_row = {
			"code": "C006",
			"line_items": '[{"item_code": "ITEM-1", "qty": "2"}, {"item_code": "ITEM-2", "qty": "1"}]',
		}
		result = mapper.map(raw_row)
		self.assertIn("_child_tables", result)
		items = result["_child_tables"]["items"]
		self.assertEqual(len(items), 2)
		self.assertEqual(items[0]["item_code"], "ITEM-1")

	def test_child_table_handles_non_json_string_gracefully(self):
		profile = {
			"mapping_rules": [],
			"child_table_mappings": [
				{"target_child_table_fieldname": "items", "source_grouping_field": "line_items"},
			],
		}
		mapper = _mapper_with_profile(profile)
		result = mapper.map({"line_items": "not-json"})
		self.assertEqual(result["_child_tables"]["items"], [{"value": "not-json"}])

	def test_no_child_mappings_means_no_child_tables_key(self):
		profile = {"mapping_rules": [{"sequence": 1, "source_field": "code", "target_field": "customer"}]}
		mapper = _mapper_with_profile(profile)
		result = mapper.map({"code": "C007"})
		self.assertNotIn("_child_tables", result)
