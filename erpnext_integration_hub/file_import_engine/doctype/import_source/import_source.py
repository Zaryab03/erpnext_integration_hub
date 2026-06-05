import frappe
from frappe.model.document import Document


class ImportSource(Document):
	def validate(self):
		self._validate_ingestion_config()
		self._validate_mapping_profile_target()
		self._validate_notify_email()

	def _validate_ingestion_config(self):
		if self.source_type == "Email" and not self.email_import_account:
			frappe.throw("Email Import Account is required when Source Type is 'Email'.")

		if self.source_type == "SFTP" and not self.sftp_import_profile:
			frappe.throw("SFTP Import Profile is required when Source Type is 'SFTP'.")

		if self.source_type == "File Upload" and not self.file_import_profile:
			frappe.throw("File Import Profile is required when Source Type is 'File Upload'.")

	def _validate_mapping_profile_target(self):
		if not self.mapping_profile:
			return
		profile_target = frappe.db.get_value(
			"Field Mapping Profile", self.mapping_profile, "target_doctype"
		)
		if profile_target and profile_target != self.target_document_type:
			frappe.throw(
				f"Field Mapping Profile '{self.mapping_profile}' targets "
				f"'{profile_target}', but this source targets '{self.target_document_type}'. "
				"They must match."
			)

	def _validate_notify_email(self):
		if self.notify_on_completion and self.completion_notify_email:
			from erpnext_integration_hub.utils.validators import validate_email_address
			validate_email_address(self.completion_notify_email)
