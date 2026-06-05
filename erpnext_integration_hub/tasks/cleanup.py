"""Scheduler entry points for archival and log purge tasks."""
import frappe
from erpnext_integration_hub.utils.cache import get_settings


def archive_completed_batches():
	"""Mark old completed batches as Archived to keep the active list clean."""
	settings = get_settings()
	cutoff_days = getattr(settings, "log_retention_days", 90)

	frappe.db.sql(
		"""
		update `tabImport Batch`
		set status = 'Archived'
		where status in ('Completed', 'Partially Processed', 'Failed')
		  and datediff(now(), modified) > %s
		""",
		(cutoff_days,),
	)
	frappe.db.commit()


def purge_old_logs():
	"""Delete Email Import Log and SFTP Import Log records beyond retention period.

	Import Error Log and Document Creation Log are intentionally excluded —
	they are permanent audit records that must only be deleted by System Manager.
	"""
	settings = get_settings()
	cutoff_days = getattr(settings, "log_retention_days", 90)

	for doctype in ("Email Import Log", "SFTP Import Log"):
		old_names = frappe.get_all(
			doctype,
			filters={"creation": ["<", frappe.utils.add_days(frappe.utils.today(), -cutoff_days)]},
			pluck="name",
			limit=1000,
		)
		for name in old_names:
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

	frappe.db.commit()
