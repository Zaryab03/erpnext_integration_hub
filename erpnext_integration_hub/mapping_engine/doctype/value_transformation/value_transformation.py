import frappe
from frappe.model.document import Document


class ValueTransformation(Document):
	def on_update(self):
		from erpnext_integration_hub.utils.cache import get_value_transformation_map
		frappe.cache().hdel("integration_hub", f"vt:{self.transformation_name}")
