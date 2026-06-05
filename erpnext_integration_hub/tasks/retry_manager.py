"""Scheduler entry point for the retry manager."""
import frappe
from erpnext_integration_hub.utils.cache import get_settings


def retry_failed_items():
	"""Re-queue Import Batch Items that are eligible for retry."""
	settings = get_settings()
	if not settings.enabled:
		return

	from erpnext_integration_hub.error_management.services.retry_manager import RetryManager
	RetryManager().schedule_pending_retries()
