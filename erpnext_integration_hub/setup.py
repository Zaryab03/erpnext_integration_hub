import frappe


def after_install():
	"""Create singleton Integration Hub Settings if it does not exist."""
	if not frappe.db.exists("Integration Hub Settings", "Integration Hub Settings"):
		doc = frappe.new_doc("Integration Hub Settings")
		doc.enabled = 1
		doc.max_retry_attempts = 3
		doc.retry_interval_minutes = 30
		doc.email_fetch_interval_minutes = 5
		doc.sftp_check_interval_minutes = 10
		doc.processing_batch_size = 500
		doc.enable_audit_log = 1
		doc.archive_processed_files = 0
		doc.log_retention_days = 90
		doc.max_file_size_mb = 50
		doc.allowed_file_extensions = ".xlsx,.csv,.xml,.json"
		doc.flags.ignore_permissions = True
		doc.insert()
		frappe.db.commit()


def before_uninstall():
	"""Block uninstall if active batches exist."""
	active_count = frappe.db.count(
		"Import Batch",
		{"status": ["in", ["Queued", "Processing"]]},
	)
	if active_count:
		frappe.throw(
			f"Cannot uninstall ERPNext Integration Hub: {active_count} batch(es) are "
			"currently queued or processing. Cancel them before uninstalling.",
			title="Active Batches Exist",
		)
