"""Scheduler entry point for SFTP polling."""
import frappe
from erpnext_integration_hub.utils.cache import get_settings


def check_all_sftp_profiles():
	"""Poll all active SFTP Import Profiles for new files."""
	settings = get_settings()
	if not settings.enabled:
		return

	profiles = frappe.get_all(
		"SFTP Import Profile",
		filters={"is_active": 1},
		pluck="name",
	)

	for profile_name in profiles:
		frappe.enqueue(
			"erpnext_integration_hub.sftp_import_engine.services.sftp_connector.check_profile",
			queue="short",
			timeout=300,
			job_id=f"sftp_check_{profile_name}",
			profile_name=profile_name,
		)
