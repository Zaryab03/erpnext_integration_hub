import frappe


def get_batch_summary(batch_name: str) -> dict:
	"""Jinja helper exposed to email templates."""
	if not batch_name:
		return {}
	return frappe.db.get_value(
		"Import Batch",
		batch_name,
		["status", "total_records", "success_count", "error_count", "skipped_count"],
		as_dict=True,
	) or {}
