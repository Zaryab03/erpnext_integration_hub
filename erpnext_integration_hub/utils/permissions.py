import frappe


def get_company_condition(user=None):
	"""Row-level security: restrict records to companies the user has access to.

	Called by permission_query_conditions in hooks.py for DocTypes that carry a
	`company` field.  System Manager sees everything — all other roles see only
	companies explicitly linked to their User Company access or allowed companies.
	"""
	if not user:
		user = frappe.session.user

	if frappe.has_role("System Manager", user):
		return ""

	# Collect companies the user is permitted to see.  ERPNext stores explicit
	# company access in the User document's `allowed_in_restrict_to_domain` or
	# via User Permission on Company.
	companies = frappe.get_list(
		"User Permission",
		filters={"user": user, "allow": "Company"},
		pluck="for_value",
		ignore_permissions=True,
	)

	if not companies:
		return "1=0"  # No company access → see nothing

	company_list = ", ".join(frappe.db.escape(c) for c in companies)
	return f"`tabImport Batch`.`company` in ({company_list})"


def get_import_error_log_condition(user=None):
	"""Error logs are company-scoped through their parent Import Batch."""
	if not user:
		user = frappe.session.user

	if frappe.has_role("System Manager", user):
		return ""

	companies = frappe.get_list(
		"User Permission",
		filters={"user": user, "allow": "Company"},
		pluck="for_value",
		ignore_permissions=True,
	)

	if not companies:
		return "1=0"

	company_list = ", ".join(frappe.db.escape(c) for c in companies)
	return (
		"`tabImport Error Log`.`import_batch` in ("
		f"select name from `tabImport Batch` where company in ({company_list})"
		")"
	)


def has_company_permission(doc, user=None):
	"""Object-level permission check called by has_permission hook."""
	if not user:
		user = frappe.session.user

	if frappe.has_role("System Manager", user):
		return True

	companies = frappe.get_list(
		"User Permission",
		filters={"user": user, "allow": "Company"},
		pluck="for_value",
		ignore_permissions=True,
	)

	return doc.get("company") in companies
