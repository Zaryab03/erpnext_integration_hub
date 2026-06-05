"""Batch lifecycle management — called from doc_events in hooks.py."""
from __future__ import annotations

import json
import frappe
from frappe.utils import now_datetime

from erpnext_integration_hub.utils.audit import log_error


def on_batch_submit(doc, method=None):
	"""Enqueue the parse+process job when an Import Batch is submitted.

	Using the batch name as job_id ensures that double-clicking Submit does not
	enqueue two jobs for the same batch.
	"""
	frappe.db.set_value("Import Batch", doc.name, "status", "Queued", update_modified=False)
	frappe.enqueue(
		"erpnext_integration_hub.file_import_engine.services.batch_manager.process_batch",
		queue="long",
		timeout=3600,
		job_id=f"process_batch_{doc.name}",
		batch_name=doc.name,
	)


def on_batch_cancel(doc, method=None):
	"""Cancel all pending items when a batch is cancelled."""
	frappe.db.sql(
		"""
		update `tabImport Batch Item`
		set status = 'Skipped'
		where import_batch = %s
		  and status in ('Pending', 'Processing')
		""",
		(doc.name,),
	)
	frappe.db.set_value("Import Batch", doc.name, "status", "Cancelled", update_modified=False)
	frappe.db.commit()


def process_batch(batch_name: str):
	"""RQ worker entry point: parse file, create batch items, enqueue per-item jobs.

	This function is executed inside the long queue worker.  It must be
	importable by Frappe's enqueue() by dotted path.
	"""
	batch = frappe.get_doc("Import Batch", batch_name)
	frappe.db.set_value(
		"Import Batch", batch_name,
		{"status": "Processing", "started_at": now_datetime()},
		update_modified=False,
	)
	frappe.db.commit()

	try:
		_parse_and_create_items(batch)
	except Exception as exc:
		import traceback
		log_error(
			"Parse",
			str(exc),
			import_batch=batch_name,
			exc=exc,
			can_retry=False,
		)
		frappe.db.set_value(
			"Import Batch", batch_name,
			{
				"status": "Failed",
				"error_message": str(exc)[:140],
				"completed_at": now_datetime(),
			},
			update_modified=False,
		)
		frappe.db.commit()
		return

	# Enqueue one job per item (default queue for throughput scalability)
	items = frappe.get_all(
		"Import Batch Item",
		filters={"import_batch": batch_name, "status": "Pending"},
		pluck="name",
	)

	for item_name in items:
		frappe.enqueue(
			"erpnext_integration_hub.file_import_engine.services.batch_manager.process_item",
			queue="default",
			timeout=600,
			job_id=f"process_item_{item_name}",
			item_name=item_name,
		)


def _parse_and_create_items(batch):
	"""Read the attached file, parse it, bulk-insert Import Batch Items."""
	source = frappe.get_doc("Import Source", batch.import_source)

	# Resolve File Import Profile
	profile_name = (
		source.file_import_profile
		or frappe.db.get_value("SFTP Import Profile", source.sftp_import_profile, "file_import_profile")
		if source.source_type == "SFTP"
		else source.file_import_profile
	)
	if not profile_name:
		frappe.throw(f"No File Import Profile linked to Import Source '{source.name}'.")

	profile = frappe.get_doc("File Import Profile", profile_name).as_dict()

	# Retrieve file content
	if not batch.file_url:
		frappe.throw("Import Batch has no attached file.")

	file_doc = frappe.get_doc("File", {"file_url": batch.file_url})
	file_content = file_doc.get_content()
	if isinstance(file_content, str):
		file_content = file_content.encode("utf-8")

	from erpnext_integration_hub.file_import_engine.services.file_processor import FileProcessor
	rows = FileProcessor(profile).process(batch.file_name or "file", file_content)

	if not rows:
		frappe.throw("File parsed successfully but contained no data rows.")

	frappe.db.set_value("Import Batch", batch.name, "total_records", len(rows), update_modified=False)

	# Bulk-insert items to avoid N round-trips for large files
	settings = frappe.get_single("Integration Hub Settings")
	chunk_size = settings.processing_batch_size or 500

	for chunk_start in range(0, len(rows), chunk_size):
		chunk = rows[chunk_start: chunk_start + chunk_size]
		for row in chunk:
			item = frappe.new_doc("Import Batch Item")
			item.import_batch = batch.name
			item.row_number = row.get("_source_row", chunk_start + rows.index(row) + 1)
			item.status = "Pending"
			item.raw_data = json.dumps(row, default=str)
			item.flags.ignore_permissions = True
			item.insert(ignore_permissions=True)
		frappe.db.commit()


def process_item(item_name: str):
	"""RQ worker entry point: map + validate + create ERPNext document for one item."""
	from erpnext_integration_hub.document_factory.services.dispatcher import DocumentDispatcher

	frappe.db.set_value(
		"Import Batch Item", item_name, "status", "Processing", update_modified=False
	)
	frappe.db.commit()

	item = frappe.get_doc("Import Batch Item", item_name)
	batch = frappe.get_doc("Import Batch", item.import_batch)
	source = frappe.get_doc("Import Source", batch.import_source)

	try:
		raw_data = json.loads(item.raw_data or "{}")

		# Duplicate detection
		if source.duplicate_detection_field:
			dup_value = raw_data.get(source.duplicate_detection_field)
			if dup_value and _is_duplicate(source.name, source.duplicate_detection_field, dup_value):
				frappe.db.set_value(
					"Import Batch Item", item_name,
					{"status": "Skipped", "error_message": f"Duplicate: {source.duplicate_detection_field}={dup_value}"},
					update_modified=False,
				)
				frappe.db.commit()
				_update_batch_status(batch.name)
				return

		# Map
		from erpnext_integration_hub.mapping_engine.services.mapper import Mapper
		mapped_data = Mapper(source.mapping_profile).map(raw_data)

		frappe.db.set_value(
			"Import Batch Item", item_name,
			"mapped_data", json.dumps(mapped_data, default=str),
			update_modified=False,
		)

		# Create ERPNext document
		created_doc = DocumentDispatcher().dispatch(
			mapped_data,
			source.target_document_type,
			item_name,
			batch.company,
			auto_submit=bool(source.auto_submit),
		)

		frappe.db.set_value(
			"Import Batch Item", item_name,
			{
				"status": "Success",
				"created_doctype": source.target_document_type,
				"created_document": created_doc.name,
			},
			update_modified=False,
		)

	except frappe.ValidationError as exc:
		_mark_item_error(item_name, "Validation", str(exc), can_retry=False)
	except frappe.PermissionError as exc:
		_mark_item_error(item_name, "Creation", str(exc), can_retry=True)
	except Exception as exc:
		import traceback as tb
		_mark_item_error(item_name, "System", str(exc), can_retry=True, exc=exc)

	frappe.db.commit()
	_update_batch_status(batch.name)


def _mark_item_error(item_name, error_type, message, can_retry, exc=None):
	from erpnext_integration_hub.utils.audit import log_error
	item = frappe.get_doc("Import Batch Item", item_name)
	log_error(
		error_type, message,
		import_batch=item.import_batch,
		import_batch_item=item_name,
		exc=exc,
		can_retry=can_retry,
	)
	frappe.db.set_value(
		"Import Batch Item", item_name,
		{
			"status": "Error",
			"error_type": error_type,
			"error_message": message[:500],
			"can_retry": 1 if can_retry else 0,
		},
		update_modified=False,
	)


def _is_duplicate(source_name, field, value) -> bool:
	"""Check if a document was already created from this source with this field value."""
	existing_item = frappe.db.exists(
		"Import Batch Item",
		{
			"import_batch": ["in", frappe.get_all(
				"Import Batch",
				filters={"import_source": source_name, "docstatus": ["!=", 2]},
				pluck="name",
			)],
			"status": "Success",
			"raw_data": ["like", f'%"{field}": "{value}"%'],
		},
	)
	return bool(existing_item)


def _update_batch_status(batch_name: str):
	"""Derive and persist the Import Batch terminal status from its items."""
	from erpnext_integration_hub.utils.audit import update_batch_counters
	update_batch_counters(batch_name)

	counts = frappe.db.sql(
		"""
		select status, count(*) as cnt
		from `tabImport Batch Item`
		where import_batch = %s
		  and status != 'Processing'
		group by status
		""",
		(batch_name,),
		as_dict=True,
	)
	total_map = {r.status: r.cnt for r in counts}

	pending_remaining = frappe.db.count(
		"Import Batch Item",
		{"import_batch": batch_name, "status": ["in", ["Pending", "Processing"]]},
	)

	if pending_remaining > 0:
		return  # Not all items done yet

	success = total_map.get("Success", 0)
	error = total_map.get("Error", 0)

	if error == 0:
		new_status = "Completed"
	elif success == 0:
		new_status = "Failed"
	else:
		new_status = "Partially Processed"

	frappe.db.set_value(
		"Import Batch", batch_name,
		{"status": new_status, "completed_at": now_datetime()},
		update_modified=False,
	)
	frappe.db.commit()

	# Fire completion notification if configured
	batch = frappe.get_doc("Import Batch", batch_name)
	source = frappe.get_doc("Import Source", batch.import_source)
	if source.notify_on_completion and source.completion_notify_email:
		_send_completion_notification(batch, source.completion_notify_email, new_status)


def _send_completion_notification(batch, email: str, status: str):
	frappe.sendmail(
		recipients=[email],
		subject=f"Import Batch {batch.name} — {status}",
		message=(
			f"<b>Batch:</b> {batch.name}<br>"
			f"<b>Source:</b> {batch.import_source}<br>"
			f"<b>Status:</b> {status}<br>"
			f"<b>Total:</b> {batch.total_records} | "
			f"<b>Success:</b> {batch.success_count} | "
			f"<b>Errors:</b> {batch.error_count}"
		),
	)
