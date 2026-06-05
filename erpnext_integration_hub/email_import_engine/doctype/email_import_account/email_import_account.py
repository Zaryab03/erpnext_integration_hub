import frappe
from frappe.model.document import Document


class EmailImportAccount(Document):
	def validate(self):
		from erpnext_integration_hub.utils.validators import validate_email_address
		validate_email_address(self.email_address)

		if self.imap_port < 1 or self.imap_port > 65535:
			frappe.throw("IMAP Port must be between 1 and 65535.")

		# Validate the linked Import Source is of type Email
		if self.import_source:
			src_type = frappe.db.get_value("Import Source", self.import_source, "source_type")
			if src_type != "Email":
				frappe.throw(
					f"Import Source '{self.import_source}' has type '{src_type}'. "
					"Only 'Email' sources can be linked to an Email Import Account.",
					frappe.ValidationError,
				)

	def get_password(self) -> str:
		"""Return the decrypted IMAP password."""
		return self.get_password("password")
