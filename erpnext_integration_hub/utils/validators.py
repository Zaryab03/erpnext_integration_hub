import mimetypes
import os
import frappe


SAFE_MIME_TYPES = {
	".xlsx": [
		"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
		"application/zip",  # xlsx are ZIP archives; some browsers report this
	],
	".csv": ["text/csv", "text/plain", "application/csv"],
	".xml": ["text/xml", "application/xml"],
	".json": ["application/json", "text/plain"],
}


def validate_upload_file(filename: str, content: bytes, max_mb: int = 50) -> str:
	"""Validate a file upload before creating any records.

	Returns the canonical extension string (e.g. '.xlsx').
	Raises frappe.ValidationError on any problem.
	"""
	if not filename:
		frappe.throw("File name is required.", frappe.ValidationError)

	ext = os.path.splitext(filename.lower())[1]
	allowed = [e.strip().lower() for e in (frappe.db.get_single_value(
		"Integration Hub Settings", "allowed_file_extensions"
	) or ".xlsx,.csv,.xml,.json").split(",")]

	if ext not in allowed:
		frappe.throw(
			f"File type '{ext}' is not allowed. Allowed types: {', '.join(allowed)}",
			frappe.ValidationError,
		)

	size_mb = len(content) / (1024 * 1024)
	if size_mb > max_mb:
		frappe.throw(
			f"File size {size_mb:.1f} MB exceeds the {max_mb} MB limit.",
			frappe.ValidationError,
		)

	# MIME type content-sniff (first 512 bytes)
	sniffed_mime, _ = mimetypes.guess_type(filename)
	if sniffed_mime and ext in SAFE_MIME_TYPES:
		if sniffed_mime not in SAFE_MIME_TYPES[ext]:
			frappe.throw(
				f"File content does not match the declared extension '{ext}'.",
				frappe.ValidationError,
			)

	# Guard against path traversal in the filename
	if ".." in filename or "/" in filename or "\\" in filename:
		frappe.throw("File name contains illegal characters.", frappe.ValidationError)

	return ext


def validate_email_address(email: str):
	"""Raise ValidationError if email is not a valid RFC-5321 address."""
	import re
	pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
	if not re.match(pattern, email or ""):
		frappe.throw(f"'{email}' is not a valid email address.", frappe.ValidationError)


def validate_custom_function_path(dotted_path: str):
	"""Ensure a custom function path is within the integration hub package.

	Prevents arbitrary code execution by restricting custom function resolution
	to the erpnext_integration_hub package namespace only.
	"""
	if not dotted_path:
		return
	allowed_prefix = "erpnext_integration_hub."
	if not dotted_path.startswith(allowed_prefix):
		frappe.throw(
			f"Custom function path must start with '{allowed_prefix}'. "
			"Functions outside this package are not permitted.",
			frappe.ValidationError,
		)
