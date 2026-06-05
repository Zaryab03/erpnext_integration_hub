import frappe
from frappe.model.document import Document


class SFTPImportProfile(Document):
	def validate(self):
		if self.auth_type == "Password" and not self.password:
			frappe.throw("Password is required when Authentication Type is 'Password'.")

		if self.auth_type == "SSH Key" and not self.private_key:
			frappe.throw("Private Key is required when Authentication Type is 'SSH Key'.")

		if self.port < 1 or self.port > 65535:
			frappe.throw("Port must be between 1 and 65535.")

		if self.remote_path and not self.remote_path.startswith("/"):
			frappe.throw("Remote Path must be an absolute path starting with '/'.")

		if self.archive_remote_path and not self.archive_remote_path.startswith("/"):
			frappe.throw("Archive Remote Path must be an absolute path starting with '/'.")

		# Guard against archiving to the same directory (infinite loop risk)
		if (
			self.archive_remote_path
			and self.remote_path
			and self.archive_remote_path.rstrip("/") == self.remote_path.rstrip("/")
		):
			frappe.throw("Archive Remote Path must be different from Remote Path.")

	def get_password_value(self) -> str:
		return self.get_password("password") if self.auth_type == "Password" else None

	def get_private_key_value(self) -> str:
		return self.get_password("private_key") if self.auth_type == "SSH Key" else None

	def get_passphrase_value(self) -> str:
		return self.get_password("private_key_passphrase") if self.private_key_passphrase else None
