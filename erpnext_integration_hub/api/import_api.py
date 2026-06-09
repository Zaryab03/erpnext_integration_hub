"""Whitelisted API endpoints for the Integration Hub.

All endpoints:
1. Require an authenticated Frappe session (or API key+secret).
2. Enforce role-based access via frappe.only_for().
3. Accept and return JSON via Frappe's standard {"message": ...} envelope.
4. Contain zero business logic — they delegate entirely to service classes.

Why no business logic in APIs: API functions can be called from the Frappe
desk, REST clients, or tests. Keeping them thin ensures business rules are
always enforced via the service layer regardless of entry point.
"""
from __future__ import annotations

import frappe


@frappe.whitelist()
def upload_file_for_import(import_source: str, file_content_b64: str = None):
	"""Accept a base64-encoded file and create a pending Import Batch.

	Parameters
	----------
	import_source : str
		Name of the Import Source to use.
	file_content_b64 : str
		Base64-encoded file content.  When called from the Frappe desk form,
		the file is already in frappe.request.files instead.
	"""
	frappe.only_for(["Integration Manager", "Integration Operator", "System Manager"])

	import base64
	import os

	# Support both multipart/form-data (from desk) and base64 (from REST clients)
	if file_content_b64:
		try:
			content = base64.b64decode(file_content_b64)
			filename = frappe.form_dict.get("file_name") or "upload.xlsx"
		except Exception:
			frappe.throw("Invalid base64 file content.", frappe.ValidationError)
	elif frappe.request and frappe.request.files:
		uploaded = list(frappe.request.files.values())[0]
		filename = uploaded.filename
		content = uploaded.read()
	else:
		frappe.throw("No file provided.", frappe.ValidationError)

	# Validate before creating any records
	settings = frappe.get_single("Integration Hub Settings")
	from erpnext_integration_hub.utils.validators import validate_upload_file
	validate_upload_file(filename, content, max_mb=settings.max_file_size_mb or 50)

	source = frappe.get_doc("Import Source", import_source)
	if not source.is_active:
		frappe.throw(f"Import Source '{import_source}' is not active.", frappe.ValidationError)

	# Store file using Frappe's file API (not raw filesystem path)
	file_doc = frappe.new_doc("File")
	file_doc.file_name = filename
	file_doc.is_private = 1
	file_doc.content = content
	file_doc.flags.ignore_permissions = True
	file_doc.insert(ignore_permissions=True)

	ext = os.path.splitext(filename.lower())[1].lstrip(".")
	fmt_map = {"xlsx": "Excel", "xls": "Excel", "csv": "CSV", "xml": "XML", "json": "JSON"}

	batch = frappe.new_doc("Import Batch")
	batch.import_source = import_source
	batch.company = source.company
	batch.status = "Pending"
	batch.batch_date = frappe.utils.today()
	batch.file_name = filename
	batch.file_url = file_doc.file_url
	batch.file_format = fmt_map.get(ext)
	batch.source_type = "File Upload"
	batch.target_document_type = source.target_document_type
	batch.flags.ignore_permissions = True
	batch.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"batch_name": batch.name, "file_url": file_doc.file_url}


@frappe.whitelist()
def get_batch_status(batch_name: str) -> dict:
	"""Return live status and progress counters for an Import Batch."""
	frappe.only_for(["Integration Manager", "Integration Operator", "Integration Viewer", "System Manager"])

	batch = frappe.db.get_value(
		"Import Batch",
		batch_name,
		[
			"status", "total_records", "processed_records",
			"success_count", "error_count", "skipped_count",
			"started_at", "completed_at", "error_message",
		],
		as_dict=True,
	)
	if not batch:
		frappe.throw(f"Import Batch '{batch_name}' not found.", frappe.DoesNotExistError)

	# Attach recent errors (last 10)
	errors = frappe.get_all(
		"Import Error Log",
		filters={"import_batch": batch_name},
		fields=["name", "error_type", "error_message", "row_number", "can_retry", "is_resolved"],
		order_by="creation desc",
		limit=10,
	)
	batch["recent_errors"] = errors
	return batch


@frappe.whitelist()
def preview_file_mapping(import_source: str, file_content_b64: str, file_name: str = "preview.xlsx") -> dict:
	"""Parse a file and apply mapping without creating any records.

	Returns the first 5 mapped rows for operator validation before submission.
	No database writes occur in this function — it is entirely read-only.
	"""
	frappe.only_for(["Integration Manager", "Integration Operator", "System Manager"])

	import base64
	try:
		content = base64.b64decode(file_content_b64)
	except Exception:
		frappe.throw("Invalid base64 content.", frappe.ValidationError)

	source = frappe.get_doc("Import Source", import_source)
	profile_doc = frappe.get_doc("File Import Profile", source.file_import_profile)
	profile = profile_doc.as_dict()

	from erpnext_integration_hub.file_import_engine.services.file_processor import FileProcessor
	from erpnext_integration_hub.mapping_engine.services.mapper import Mapper

	rows = FileProcessor(profile).process(file_name, content)
	mapper = Mapper(source.mapping_profile)

	preview = []
	errors = []
	for row in rows[:5]:
		try:
			mapped = mapper.map(row)
			preview.append({"raw": row, "mapped": mapped})
		except Exception as e:
			errors.append({"raw": row, "error": str(e)})

	return {
		"total_rows": len(rows),
		"preview": preview,
		"mapping_errors": errors,
	}


@frappe.whitelist()
def retry_batch_item(item_name: str) -> dict:
	"""Manually re-queue a single Import Batch Item for processing."""
	frappe.only_for(["Integration Manager", "System Manager"])

	item = frappe.get_doc("Import Batch Item", item_name)
	if item.status not in ("Error",):
		frappe.throw(
			f"Item '{item_name}' has status '{item.status}'. Only 'Error' items can be retried.",
			frappe.ValidationError,
		)

	from erpnext_integration_hub.error_management.services.retry_manager import RetryManager
	RetryManager()._enqueue_retry(item_name)
	frappe.db.commit()

	return {"status": "queued", "item": item_name}


@frappe.whitelist()
def retry_all_batch_errors(batch_name: str) -> dict:
	"""Re-queue every errored item in a batch. Called from the Import Batch form."""
	frappe.only_for(["Integration Manager", "System Manager"])

	batch = frappe.get_doc("Import Batch", batch_name)
	if batch.docstatus != 1:
		frappe.throw("Batch must be submitted before items can be retried.", frappe.ValidationError)

	error_items = frappe.get_all(
		"Import Batch Item",
		filters={"import_batch": batch_name, "status": "Error", "can_retry": 1},
		pluck="name",
	)
	if not error_items:
		frappe.throw("No retryable errored items found in this batch.", frappe.ValidationError)

	from erpnext_integration_hub.error_management.services.retry_manager import RetryManager
	manager = RetryManager()
	for item_name in error_items:
		manager._enqueue_retry(item_name)

	frappe.db.commit()
	return {"status": "queued", "queued_count": len(error_items)}


@frappe.whitelist()
def cancel_batch(batch_name: str) -> dict:
	"""Cancel a pending or queued Import Batch."""
	frappe.only_for(["Integration Manager", "System Manager"])

	batch = frappe.get_doc("Import Batch", batch_name)
	if batch.status not in ("Pending", "Queued"):
		frappe.throw(
			f"Cannot cancel a batch with status '{batch.status}'. "
			"Only Pending or Queued batches can be cancelled.",
			frappe.ValidationError,
		)
	batch.cancel()
	frappe.db.commit()
	return {"status": "cancelled", "batch": batch_name}


@frappe.whitelist()
def validate_sftp_connection(profile_name: str) -> dict:
	"""Test SFTP credentials without saving any data."""
	frappe.only_for(["Integration Manager", "System Manager"])

	profile = frappe.get_doc("SFTP Import Profile", profile_name)
	try:
		from erpnext_integration_hub.sftp_import_engine.services.sftp_connector import SFTPSession
		with SFTPSession(profile) as sftp:
			files = sftp.list_files()
		return {"success": True, "files_found": len(files), "message": "Connection successful."}
	except Exception as e:
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def validate_email_connection(account_name: str) -> dict:
	"""Test IMAP credentials without saving any data."""
	frappe.only_for(["Integration Manager", "System Manager"])

	account = frappe.get_doc("Email Import Account", account_name)
	import imaplib
	try:
		if account.use_ssl:
			conn = imaplib.IMAP4_SSL(account.imap_server, account.imap_port)
		else:
			conn = imaplib.IMAP4(account.imap_server, account.imap_port)
		conn.login(account.username, account.get_password("password"))
		conn.logout()
		return {"success": True, "message": "IMAP connection successful."}
	except Exception as e:
		return {"success": False, "message": str(e)}


@frappe.whitelist()
def get_import_statistics(company: str = None) -> dict:
	"""Return dashboard-level aggregates for the Integration Hub workspace."""
	frappe.only_for(["Integration Manager", "Integration Operator", "Integration Viewer", "System Manager"])

	filters = {}
	if company:
		filters["company"] = company

	today = frappe.utils.today()

	return {
		"batches_today": frappe.db.count("Import Batch", {**filters, "batch_date": today}),
		"batches_failed": frappe.db.count("Import Batch", {**filters, "status": "Failed"}),
		"batches_processing": frappe.db.count("Import Batch", {**filters, "status": ["in", ["Queued", "Processing"]]}),
		"open_errors": frappe.db.count("Import Error Log", {"is_resolved": 0}),
		"documents_created_today": frappe.db.count(
			"Document Creation Log",
			{"created_at": [">=", f"{today} 00:00:00"]},
		),
	}


@frappe.whitelist()
def resolve_error(error_log_name: str, notes: str = "") -> dict:
	"""Mark an Import Error Log record as resolved."""
	frappe.only_for(["Integration Manager", "Integration Operator", "System Manager"])

	frappe.db.set_value(
		"Import Error Log", error_log_name,
		{
			"is_resolved": 1,
			"resolved_by": frappe.session.user,
			"resolved_at": frappe.utils.now_datetime(),
			"resolution_notes": notes,
		},
	)
	frappe.db.commit()
	return {"status": "resolved", "error_log": error_log_name}
