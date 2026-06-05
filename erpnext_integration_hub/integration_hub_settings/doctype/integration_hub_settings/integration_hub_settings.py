import frappe
from frappe.model.document import Document


class IntegrationHubSettings(Document):
	def validate(self):
		self._validate_positive_integers()
		self._validate_email()
		self._validate_file_extensions()

	def _validate_positive_integers(self):
		int_fields = [
			"max_retry_attempts",
			"retry_interval_minutes",
			"processing_batch_size",
			"max_file_size_mb",
			"email_fetch_interval_minutes",
			"sftp_check_interval_minutes",
			"log_retention_days",
		]
		for f in int_fields:
			val = self.get(f)
			if val is not None and val < 1:
				frappe.throw(f"{self.meta.get_label(f)} must be at least 1.")

	def _validate_email(self):
		if self.error_alert_email:
			from erpnext_integration_hub.utils.validators import validate_email_address
			validate_email_address(self.error_alert_email)

	def _validate_file_extensions(self):
		if not self.allowed_file_extensions:
			return
		for ext in self.allowed_file_extensions.split(","):
			ext = ext.strip()
			if ext and not ext.startswith("."):
				frappe.throw(
					f"File extension '{ext}' must start with a dot (e.g., '.xlsx').",
					frappe.ValidationError,
				)

	def on_update(self):
		# Invalidate settings cache so the updated values are picked up immediately
		frappe.cache().hdel("integration_hub", "settings")
