"""Unit tests for the value transformer functions.

These are pure-ish functions (no DB writes) so tests focus on input/output
contracts and the error paths that would otherwise corrupt mapped data
silently — e.g. a Lookup that fails should respect is_required vs default.
"""
from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_integration_hub.mapping_engine.services.transformer import (
	apply_custom_function,
	apply_expression,
	apply_lookup,
	apply_none,
	apply_static,
)


def sample_custom_fn(value, row, rule):
	"""Reference custom function used by test_apply_custom_function_*."""
	return f"{value}-{row.get('suffix')}"


class TestApplyNone(FrappeTestCase):
	def test_passthrough(self):
		self.assertEqual(apply_none("hello", {}, {}), "hello")

	def test_empty_uses_default(self):
		self.assertEqual(apply_none("", {}, {"default_value": "fallback"}), "fallback")
		self.assertEqual(apply_none(None, {}, {"default_value": "fallback"}), "fallback")

	def test_empty_without_default_is_none(self):
		self.assertIsNone(apply_none("", {}, {}))
		self.assertIsNone(apply_none(None, {}, {}))


class TestApplyStatic(FrappeTestCase):
	def test_ignores_source_value(self):
		self.assertEqual(apply_static("anything", {}, {"default_value": "FIXED"}), "FIXED")

	def test_no_default_returns_none(self):
		self.assertIsNone(apply_static("anything", {}, {}))


class TestApplyLookup(FrappeTestCase):
	def test_successful_lookup(self):
		rule = {
			"lookup_doctype": "Currency",
			"lookup_source_field": "name",
			"lookup_return_field": "currency_name",
		}
		self.assertEqual(apply_lookup("USD", {}, rule), "USD")

	def test_failed_lookup_returns_default_when_not_required(self):
		rule = {
			"lookup_doctype": "Currency",
			"lookup_source_field": "name",
			"lookup_return_field": "currency_name",
			"default_value": "UNKNOWN",
		}
		self.assertEqual(apply_lookup("DOES-NOT-EXIST", {}, rule), "UNKNOWN")

	def test_failed_lookup_throws_when_required(self):
		rule = {
			"lookup_doctype": "Currency",
			"lookup_source_field": "name",
			"lookup_return_field": "currency_name",
			"is_required": 1,
		}
		with self.assertRaises(frappe.ValidationError):
			apply_lookup("DOES-NOT-EXIST", {}, rule)

	def test_empty_value_required_throws(self):
		rule = {
			"lookup_doctype": "Currency",
			"lookup_source_field": "name",
			"lookup_return_field": "currency_name",
			"is_required": 1,
			"source_field": "currency_code",
		}
		with self.assertRaises(frappe.ValidationError):
			apply_lookup(None, {}, rule)

	def test_misconfigured_rule_throws(self):
		rule = {"lookup_doctype": "Currency"}  # missing source/return fields
		with self.assertRaises(frappe.ValidationError):
			apply_lookup("USD", {}, rule)


class TestApplyExpression(FrappeTestCase):
	def test_simple_expression_on_value(self):
		rule = {"expression": "value.upper()", "target_field": "code"}
		self.assertEqual(apply_expression("abc", {}, rule), "ABC")

	def test_expression_can_reference_row(self):
		rule = {"expression": "row['first'] + ' ' + row['last']", "target_field": "full_name"}
		row = {"first": "Jane", "last": "Doe"}
		self.assertEqual(apply_expression(None, row, rule), "Jane Doe")

	def test_blank_expression_passes_through(self):
		rule = {"expression": "  ", "target_field": "code"}
		self.assertEqual(apply_expression("untouched", {}, rule), "untouched")

	def test_unsafe_expression_is_blocked(self):
		# frappe.safe_eval strips dangerous builtins like __import__ / open
		rule = {"expression": "__import__('os').system('echo pwned')", "target_field": "x"}
		with self.assertRaises(frappe.ValidationError):
			apply_expression("x", {}, rule)


class TestApplyCustomFunction(FrappeTestCase):
	def test_calls_function_in_namespace(self):
		rule = {
			"custom_function": (
				"erpnext_integration_hub.mapping_engine.services.test_transformer.sample_custom_fn"
			),
		}
		row = {"suffix": "X1"}
		self.assertEqual(apply_custom_function("ITEM", row, rule), "ITEM-X1")

	def test_rejects_function_outside_namespace(self):
		rule = {"custom_function": "frappe.utils.now"}
		with self.assertRaises(frappe.PermissionError):
			apply_custom_function("value", {}, rule)

	def test_missing_function_throws_validation_error(self):
		rule = {
			"custom_function": "erpnext_integration_hub.mapping_engine.services.test_transformer.does_not_exist"
		}
		with self.assertRaises(frappe.ValidationError):
			apply_custom_function("value", {}, rule)

	def test_no_path_passes_through(self):
		self.assertEqual(apply_custom_function("untouched", {}, {}), "untouched")
