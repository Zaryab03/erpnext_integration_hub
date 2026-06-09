"""Tests for file parsers (CSV, JSON).

Parsers are the entry point for all imported data — a header-normalisation
or flattening bug here means every downstream mapping rule silently misses
its source field. Tests assert on the exact row-dict shape the Mapper
expects to receive.
"""
from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_integration_hub.file_import_engine.services.csv_parser import CSVParser
from erpnext_integration_hub.file_import_engine.services.json_parser import JSONParser


class TestCSVParser(FrappeTestCase):
	def test_parses_with_header_normalisation(self):
		content = b"Customer Code,Item Code,Qty\nC001,ITEM-1,5\nC002,ITEM-2,3\n"
		parser = CSVParser({"csv_has_header": True})
		rows = parser.parse(content)

		self.assertEqual(len(rows), 2)
		self.assertEqual(rows[0]["customer_code"], "C001")
		self.assertEqual(rows[0]["item_code"], "ITEM-1")
		self.assertEqual(rows[0]["_source_row"], 2)

	def test_skips_empty_rows_by_default(self):
		content = b"Code,Name\nC001,Acme\n,\nC002,Beta\n"
		parser = CSVParser({"csv_has_header": True})
		rows = parser.parse(content)
		self.assertEqual(len(rows), 2)
		self.assertEqual([r["code"] for r in rows], ["C001", "C002"])

	def test_short_rows_are_padded_with_none(self):
		content = b"Code,Name,Email\nC001,Acme\n"
		parser = CSVParser({"csv_has_header": True})
		rows = parser.parse(content)
		self.assertIsNone(rows[0]["email"])

	def test_custom_delimiter(self):
		content = b"Code;Name\nC001;Acme\n"
		parser = CSVParser({"csv_has_header": True, "csv_delimiter": "Semicolon"})
		rows = parser.parse(content)
		self.assertEqual(rows[0]["code"], "C001")
		self.assertEqual(rows[0]["name"], "Acme")

	def test_no_header_generates_positional_columns(self):
		content = b"C001,Acme\nC002,Beta\n"
		parser = CSVParser({"csv_has_header": False})
		rows = parser.parse(content)
		self.assertEqual(rows[0]["col_1"], "C001")
		self.assertEqual(rows[0]["col_2"], "Acme")
		self.assertEqual(rows[0]["_source_row"], 1)

	def test_empty_file_returns_empty_list(self):
		parser = CSVParser({"csv_has_header": True})
		self.assertEqual(parser.parse(b""), [])


class TestJSONParser(FrappeTestCase):
	def test_parses_top_level_array(self):
		content = b'[{"customer": "C001"}, {"customer": "C002"}]'
		parser = JSONParser({})
		rows = parser.parse(content)
		self.assertEqual(len(rows), 2)
		self.assertEqual(rows[0]["customer"], "C001")
		self.assertEqual(rows[0]["_source_row"], 1)

	def test_flattens_nested_dicts_with_dot_notation(self):
		content = b'[{"customer": {"name": "Alice", "code": "C001"}}]'
		parser = JSONParser({})
		rows = parser.parse(content)
		self.assertEqual(rows[0]["customer.name"], "Alice")
		self.assertEqual(rows[0]["customer.code"], "C001")

	def test_lists_are_serialised_as_json_strings(self):
		content = b'[{"customer": "C001", "items": [{"item_code": "I-1"}]}]'
		parser = JSONParser({})
		rows = parser.parse(content)
		self.assertIsInstance(rows[0]["items"], str)
		self.assertIn("I-1", rows[0]["items"])

	def test_finds_first_list_in_root_dict(self):
		content = b'{"meta": {"page": 1}, "orders": [{"customer": "C001"}]}'
		parser = JSONParser({})
		rows = parser.parse(content)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["customer"], "C001")

	def test_jsonpath_extraction(self):
		content = b'{"data": {"orders": [{"customer": "C001"}, {"customer": "C002"}]}}'
		parser = JSONParser({"json_records_path": "$.data.orders[*]"})
		rows = parser.parse(content)
		self.assertEqual(len(rows), 2)
		self.assertEqual(rows[1]["customer"], "C002")

	def test_invalid_json_throws_validation_error(self):
		parser = JSONParser({})
		with self.assertRaises(frappe.ValidationError):
			parser.parse(b"{not valid json")

	def test_non_object_record_throws_validation_error(self):
		content = b'["just-a-string", "another"]'
		parser = JSONParser({})
		with self.assertRaises(frappe.ValidationError):
			parser.parse(content)
