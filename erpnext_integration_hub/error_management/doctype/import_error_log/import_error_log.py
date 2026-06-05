import frappe
from frappe.model.document import Document


class ImportErrorLog(Document):
	def before_save(self):
		# Stamp resolution metadata when is_resolved is set for the first time
		if self.is_resolved and not self.resolved_at:
			self.resolved_by = frappe.session.user
			self.resolved_at = frappe.utils.now_datetime()
