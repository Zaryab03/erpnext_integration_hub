import frappe
from frappe.model.document import Document

VALID_ERROR_TYPES = {
	"Connection", "Authentication", "Parse", "Mapping",
	"Validation", "Creation", "System"
}


class ErrorNotificationRule(Document):
	def validate(self):
		if self.notify_email:
			from erpnext_integration_hub.utils.validators import validate_email_address
			validate_email_address(self.notify_email)

		if self.error_types:
			provided = {t.strip() for t in self.error_types.split(",")}
			invalid = provided - VALID_ERROR_TYPES
			if invalid:
				frappe.throw(
					f"Invalid error type(s): {', '.join(invalid)}. "
					f"Allowed values: {', '.join(sorted(VALID_ERROR_TYPES))}",
					frappe.ValidationError,
				)
