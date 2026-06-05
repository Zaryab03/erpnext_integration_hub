from frappe.model.document import Document


class EmailImportLog(Document):
	# Immutable audit record. No write-back from form. Created by EmailFetcher
	# service only. Controller is intentionally empty.
	pass
