"""Retry manager with exponential backoff.

Exponential backoff formula:
  delay = base_interval_minutes * (2 ^ retry_count)

This means:
  retry 0 → base_interval minutes
  retry 1 → 2 × base_interval
  retry 2 → 4 × base_interval

The maximum retry count is read from Integration Hub Settings so operators
can change it without a code deployment.
"""
from __future__ import annotations

import frappe
from frappe.utils import now_datetime, add_to_date

from erpnext_integration_hub.utils.cache import get_settings


class RetryManager:

	def schedule_pending_retries(self):
		"""Find eligible items and enqueue them for processing."""
		settings = get_settings()
		max_attempts = int(settings.max_retry_attempts or 3)
		base_interval = int(settings.retry_interval_minutes or 30)

		now = now_datetime()

		items = frappe.db.sql(
			"""
			select
				ibi.name,
				ibi.import_batch,
				ibi.retry_count,
				ibi.last_retry_at,
				ib.docstatus
			from `tabImport Batch Item` ibi
			join `tabImport Batch` ib on ib.name = ibi.import_batch
			where ibi.status = 'Error'
			  and ibi.can_retry = 1
			  and ibi.retry_count < %s
			  and ib.docstatus = 1
			order by ibi.last_retry_at asc
			limit 500
			""",
			(max_attempts,),
			as_dict=True,
		)

		for item in items:
			next_retry_time = self._next_retry_time(
				item.last_retry_at or item.get("creation"),
				item.retry_count or 0,
				base_interval,
			)
			if now >= next_retry_time:
				self._enqueue_retry(item.name)

	def _enqueue_retry(self, item_name: str):
		frappe.db.set_value(
			"Import Batch Item", item_name,
			{
				"status": "Pending",
				"retry_count": frappe.db.get_value("Import Batch Item", item_name, "retry_count") + 1,
				"last_retry_at": now_datetime(),
			},
			update_modified=False,
		)
		# Also reset the linked error log entry's retry count
		frappe.db.sql(
			"""
			update `tabImport Error Log`
			set retry_count = retry_count + 1,
			    last_retry_at = %s
			where import_batch_item = %s
			  and is_resolved = 0
			""",
			(now_datetime(), item_name),
		)

		frappe.enqueue(
			"erpnext_integration_hub.file_import_engine.services.batch_manager.process_item",
			queue="default",
			timeout=600,
			job_id=f"retry_item_{item_name}",
			item_name=item_name,
		)

	@staticmethod
	def _next_retry_time(last_retry, retry_count: int, base_interval: int):
		delay_minutes = base_interval * (2 ** retry_count)
		if last_retry is None:
			return frappe.utils.now_datetime()
		return add_to_date(
			frappe.utils.get_datetime(last_retry),
			minutes=delay_minutes,
		)
