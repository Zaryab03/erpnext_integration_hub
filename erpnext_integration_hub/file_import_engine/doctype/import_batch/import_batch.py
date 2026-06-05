import frappe
from frappe.model.document import Document


class ImportBatch(Document):
	def before_insert(self):
		if not self.batch_date:
			self.batch_date = frappe.utils.today()

	def validate(self):
		# Fetch company from source if not already set
		if self.import_source and not self.company:
			self.company = frappe.db.get_value("Import Source", self.import_source, "company")

		if self.import_source and not self.target_document_type:
			self.target_document_type = frappe.db.get_value(
				"Import Source", self.import_source, "target_document_type"
			)

	def before_submit(self):
		"""Prevent submission if the batch has no file and source type is File Upload."""
		source_type = self.source_type or frappe.db.get_value(
			"Import Source", self.import_source, "source_type"
		)
		if source_type == "File Upload" and not self.file_url:
			frappe.throw(
				"Cannot submit: no file is attached to this batch.",
				frappe.ValidationError,
			)

		# If require_approval is enabled on the source, hold in Pending Approval
		requires = frappe.db.get_value(
			"Import Source", self.import_source, "require_approval"
		)
		if requires and self.status == "Pending":
			self.status = "Pending Approval"
			frappe.throw(
				"This Import Source requires manual approval before processing. "
				"Status set to 'Pending Approval'. An Integration Manager must approve.",
				frappe.ValidationError,
			)

	def on_submit(self):
		# Handled via doc_events in hooks.py → batch_manager.on_batch_submit
		pass

	def on_cancel(self):
		# Handled via doc_events in hooks.py → batch_manager.on_batch_cancel
		pass
