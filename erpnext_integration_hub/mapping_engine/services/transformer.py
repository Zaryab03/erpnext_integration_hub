"""Value transformers for the five transformation types.

Each transformer function receives:
  value       — the raw source value (str or None)
  row         — the full source row dict (for Expression / Custom Function context)
  rule        — the Field Mapping Rule dict

And returns the transformed value as a string (or None).

Design: transformers are pure functions with no side effects. They do not
read from frappe.form_dict or frappe.request. This makes them unit-testable
without a Frappe context (mock frappe.db.get_value where needed).
"""
from __future__ import annotations

import frappe


def apply_none(value, row: dict, rule: dict):
	"""Pass-through. Returns value unchanged, or rule's default if None."""
	if value is None or value == "":
		return rule.get("default_value") or None
	return value


def apply_static(value, row: dict, rule: dict):
	"""Always return the configured static/default value, ignoring source."""
	return rule.get("default_value") or None


def apply_lookup(value, row: dict, rule: dict):
	"""Look up the source value in a DocType and return the mapped field.

	Example: source value "C001" → Customer where customer_code = "C001"
	         return Customer.name
	"""
	if not value:
		if rule.get("is_required"):
			frappe.throw(
				f"Required lookup field '{rule.get('source_field')}' has no value.",
				frappe.ValidationError,
			)
		return rule.get("default_value") or None

	lookup_doctype = rule.get("lookup_doctype")
	source_field = rule.get("lookup_source_field")
	return_field = rule.get("lookup_return_field")

	if not all([lookup_doctype, source_field, return_field]):
		frappe.throw(
			f"Lookup rule for '{rule.get('target_field')}' is missing "
			"lookup_doctype, lookup_source_field, or lookup_return_field.",
			frappe.ValidationError,
		)

	result = frappe.db.get_value(lookup_doctype, {source_field: value}, return_field)
	if result is None:
		if rule.get("is_required"):
			frappe.throw(
				f"Lookup failed: no {lookup_doctype} found where "
				f"{source_field} = '{value}'.",
				frappe.ValidationError,
			)
		return rule.get("default_value") or None

	return result


def apply_expression(value, row: dict, rule: dict):
	"""Evaluate a Python expression using frappe.safe_eval.

	Context: `value` = source field value, `row` = full source row dict.
	frappe.safe_eval restricts builtins to a safe subset — no import, exec,
	open, __class__, etc.
	"""
	expression = rule.get("expression") or ""
	if not expression.strip():
		return value

	context = {"value": value, "row": row}
	try:
		result = frappe.safe_eval(expression, None, context)
	except Exception as e:
		frappe.throw(
			f"Expression error for field '{rule.get('target_field')}': {e}",
			frappe.ValidationError,
		)

	return str(result).strip() if result is not None else None


def apply_custom_function(value, row: dict, rule: dict):
	"""Call a custom function at a dotted path within erpnext_integration_hub.

	The function signature must be: fn(value, row, rule) -> str | None.
	The path is validated at mapping profile save time, but we guard here too.
	"""
	dotted_path = rule.get("custom_function") or ""
	if not dotted_path:
		return value

	if not dotted_path.startswith("erpnext_integration_hub."):
		frappe.throw(
			f"Custom function '{dotted_path}' is outside the permitted namespace.",
			frappe.PermissionError,
		)

	parts = dotted_path.rsplit(".", 1)
	if len(parts) != 2:
		frappe.throw(f"Invalid custom function path: '{dotted_path}'.")

	module_path, func_name = parts
	try:
		import importlib
		module = importlib.import_module(module_path)
		fn = getattr(module, func_name)
	except (ImportError, AttributeError) as e:
		frappe.throw(
			f"Cannot load custom function '{dotted_path}': {e}",
			frappe.ValidationError,
		)

	try:
		result = fn(value, row, rule)
	except Exception as e:
		frappe.throw(
			f"Custom function '{dotted_path}' raised an error: {e}",
			frappe.ValidationError,
		)

	return str(result).strip() if result is not None else None


TRANSFORMER_MAP = {
	"None": apply_none,
	"": apply_none,
	None: apply_none,
	"Static Value": apply_static,
	"Lookup": apply_lookup,
	"Expression": apply_expression,
	"Custom Function": apply_custom_function,
}
