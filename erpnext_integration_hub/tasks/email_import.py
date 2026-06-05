"""Scheduler entry point for email polling.

This module contains nothing but the thin wrapper function that Frappe's
scheduler calls by dotted path.  All business logic lives in the service layer.
The wrapper pattern prevents long-running logic from executing at import time
and keeps the service classes testable without a running scheduler.
"""
import frappe
from erpnext_integration_hub.utils.cache import get_settings


def fetch_all_email_accounts():
	"""Fetch new emails from all active Email Import Accounts.

	Guards:
	- Hub must be enabled in Integration Hub Settings.
	- Each account is processed in a separate enqueued job so that one failing
	  IMAP connection cannot block other accounts.
	"""
	settings = get_settings()
	if not settings.enabled:
		return

	accounts = frappe.get_all(
		"Email Import Account",
		filters={"is_active": 1},
		pluck="name",
	)

	for account_name in accounts:
		frappe.enqueue(
			"erpnext_integration_hub.email_import_engine.services.email_fetcher.fetch_account",
			queue="short",
			timeout=300,
			job_id=f"email_fetch_{account_name}",
			account_name=account_name,
		)
