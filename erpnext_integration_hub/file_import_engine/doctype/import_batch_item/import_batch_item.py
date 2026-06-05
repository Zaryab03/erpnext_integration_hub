from frappe.model.document import Document


class ImportBatchItem(Document):
	# This controller is intentionally lean.  All state transitions are driven
	# by service classes (file_processor, base_factory, retry_manager) which
	# use frappe.db.set_value() for performance when updating many items at once.
	# Controller hooks are left for future extensibility only.
	pass
