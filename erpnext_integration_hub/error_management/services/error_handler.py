"""Central error classification and escalation.

Classification maps Python exception types and error contexts to one of the
six defined error types.  The mapping controls retry eligibility and
notification urgency — it is the most important piece of the error management
system because it governs operational behaviour.
"""
from __future__ import annotations

import frappe
from frappe.utils import now_datetime


# Maps error type → can_retry default.
# Authentication errors never retry (credentials are wrong until fixed).
# Parse errors never retry (the file content won't change).
# Connection errors retry (transient network issue).
# Validation errors don't retry without human intervention.
# Creation errors retry once (may be a transient DB lock).
ERROR_RETRY_MAP = {
	"Connection": True,
	"Authentication": False,
	"Parse": False,
	"Mapping": False,
	"Validation": False,
	"Creation": True,
	"System": True,
}

# Notification urgency — Authentication always alerts; others use rule thresholds.
ALWAYS_ALERT_TYPES = {"Authentication"}


def classify(exc: Exception) -> tuple[str, bool]:
	"""Return (error_type, can_retry) tuple for a given exception.

	Import the exception at classify() call time rather than module level to
	avoid ImportError when paramiko or IMAP libraries are absent.
	"""
	exc_type = type(exc).__name__
	exc_msg = str(exc).lower()

	# Paramiko auth exceptions
	if "authenticationexception" in exc_type or "authentication" in exc_msg:
		return "Authentication", False

	# Connection-level failures
	if any(k in exc_msg for k in ("connection refused", "timed out", "network", "connect")):
		return "Connection", True

	# Frappe validation errors
	if isinstance(exc, frappe.ValidationError):
		return "Validation", False

	if isinstance(exc, frappe.PermissionError):
		return "Creation", True

	# Catch-all
	return "System", True


def escalate(import_batch_name: str, error_type: str):
	"""Check Error Notification Rules and send notifications if thresholds are met."""
	source_name = frappe.db.get_value("Import Batch", import_batch_name, "import_source")

	# Find applicable rules (source-specific first, then global)
	rules = frappe.get_all(
		"Error Notification Rule",
		filters={"is_active": 1},
		fields=["name", "import_source", "error_types", "min_error_count",
		        "notification_interval_minutes", "last_notified_at",
		        "notify_email"],
		order_by="import_source desc",  # specific sources sort before nulls
	)

	for rule in rules:
		if rule.import_source and rule.import_source != source_name:
			continue

		# Check error type filter
		if rule.error_types:
			allowed = {t.strip() for t in rule.error_types.split(",")}
			if error_type not in allowed:
				continue

		# Check minimum error count
		error_count = frappe.db.count(
			"Import Error Log",
			{
				"import_batch": import_batch_name,
				"error_type": error_type,
				"is_resolved": 0,
			},
		)
		if error_count < (rule.min_error_count or 1):
			continue

		# Check notification interval
		if rule.last_notified_at:
			elapsed = (now_datetime() - frappe.utils.get_datetime(rule.last_notified_at)).total_seconds() / 60
			if elapsed < (rule.notification_interval_minutes or 60):
				continue

		_send_notification(rule, import_batch_name, error_type, error_count)

	# Always alert for authentication errors regardless of rules
	if error_type in ALWAYS_ALERT_TYPES:
		_send_auth_alert(source_name, import_batch_name, error_type)


def _send_notification(rule: dict, batch_name: str, error_type: str, error_count: int):
	recipients = []
	if rule.notify_email:
		recipients.append(rule.notify_email)

	# Fetch user emails from notify_users multiselect
	user_emails = frappe.db.sql(
		"""
		select u.email from `tabUser` u
		join `tabIntegration Hub Notify User` n on n.user = u.name
		where n.parent = %s
		""",
		(rule.name,),
		pluck=True,
	)
	recipients.extend(user_emails)

	if not recipients:
		return

	batch = frappe.db.get_value(
		"Import Batch", batch_name,
		["import_source", "total_records", "error_count"],
		as_dict=True,
	)

	frappe.sendmail(
		recipients=recipients,
		subject=f"[Integration Hub] {error_type} errors in batch {batch_name}",
		message=(
			f"<b>Batch:</b> {batch_name}<br>"
			f"<b>Source:</b> {batch.import_source}<br>"
			f"<b>Error Type:</b> {error_type}<br>"
			f"<b>Error Count:</b> {error_count} of {batch.total_records} records<br>"
			f"<br>Please review Import Error Log in ERPNext for details."
		),
		now=True,
	)

	frappe.db.set_value(
		"Error Notification Rule", rule.name, "last_notified_at", now_datetime(),
		update_modified=False,
	)


def _send_auth_alert(source_name: str, batch_name: str, error_type: str):
	"""Send immediate alert for authentication failures using global error email."""
	alert_email = frappe.db.get_single_value("Integration Hub Settings", "error_alert_email")
	if not alert_email:
		return
	frappe.sendmail(
		recipients=[alert_email],
		subject=f"[Integration Hub] IMMEDIATE: {error_type} failure — {source_name}",
		message=(
			f"An <b>{error_type}</b> error occurred for Import Source <b>{source_name}</b>.<br>"
			f"Batch: {batch_name}<br><br>"
			"This type of error will NOT retry automatically. "
			"Please check credentials in the SFTP/Email Import configuration."
		),
		now=True,
	)
