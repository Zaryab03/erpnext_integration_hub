"""Structured audit helpers.

All functions write to frappe.logger() AND create Import Error Log / Document
Creation Log records as appropriate.  Keeping structured log creation here
prevents duplication across service modules.
"""
import traceback
import frappe


def _get_logger():
	return frappe.logger("integration_hub", allow_site=True, max_size=5, file_count=20)


# Module-level alias — resolved lazily to avoid file creation at import time
class _LazyLogger:
	def __getattr__(self, name):
		return getattr(_get_logger(), name)


logger = _LazyLogger()


def log_error(
	error_type: str,
	message: str,
	import_batch: str = None,
	import_batch_item: str = None,
	import_source: str = None,
	row_number: int = None,
	raw_data_snapshot: dict = None,
	exc: Exception = None,
	can_retry: bool = False,
) -> str:
	"""Create an Import Error Log record and write to the file logger.

	Returns the name of the created Import Error Log document so callers can
	reference it in batch item updates.
	"""
	import json

	stack = ""
	if exc:
		stack = traceback.format_exc()

	logger.error(
		f"[{error_type}] batch={import_batch} item={import_batch_item} "
		f"row={row_number}: {message}"
	)

	error_doc = frappe.new_doc("Import Error Log")
	error_doc.import_batch = import_batch
	error_doc.import_batch_item = import_batch_item
	error_doc.import_source = import_source
	error_doc.error_type = error_type
	error_doc.error_message = message
	error_doc.stack_trace = stack
	error_doc.row_number = row_number
	error_doc.raw_data_snapshot = json.dumps(raw_data_snapshot or {}, default=str)
	error_doc.can_retry = 1 if can_retry else 0
	error_doc.retry_count = 0
	error_doc.flags.ignore_permissions = True
	error_doc.insert(ignore_permissions=True)
	return error_doc.name


def log_document_created(
	import_batch: str,
	import_batch_item: str,
	target_doctype: str,
	document_name: str,
	company: str,
	document_status: str = "Draft",
):
	"""Create an immutable Document Creation Log record."""
	log = frappe.new_doc("Document Creation Log")
	log.import_batch = import_batch
	log.import_batch_item = import_batch_item
	log.target_doctype = target_doctype
	log.document_name = document_name
	log.company = company
	log.document_status = document_status
	log.created_by = frappe.session.user
	log.flags.ignore_permissions = True
	log.insert(ignore_permissions=True)

	logger.info(
		f"Created {target_doctype} '{document_name}' from batch={import_batch} "
		f"item={import_batch_item}"
	)


def update_batch_counters(batch_name: str):
	"""Recount success/error/skipped from child items and persist to Import Batch.

	Called after every item state transition so the batch document reflects live
	progress.  Uses frappe.db.sql aggregation to avoid loading all child records.
	"""
	counts = frappe.db.sql(
		"""
		select
			status,
			count(*) as cnt
		from `tabImport Batch Item`
		where import_batch = %s
		group by status
		""",
		(batch_name,),
		as_dict=True,
	)

	totals = {r.status: r.cnt for r in counts}
	total = sum(totals.values())
	success = totals.get("Success", 0)
	error = totals.get("Error", 0)
	skipped = totals.get("Skipped", 0)
	processed = success + error + skipped

	frappe.db.set_value(
		"Import Batch",
		batch_name,
		{
			"total_records": total,
			"processed_records": processed,
			"success_count": success,
			"error_count": error,
			"skipped_count": skipped,
		},
		update_modified=False,
	)
