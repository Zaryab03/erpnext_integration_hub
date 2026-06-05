import frappe
from frappe.model.document import Document


class FieldMappingProfile(Document):
	def validate(self):
		self._validate_rule_sequences()
		self._validate_custom_function_paths()

	def _validate_rule_sequences(self):
		sequences = [r.sequence for r in self.mapping_rules if r.sequence]
		if len(sequences) != len(set(sequences)):
			frappe.throw(
				"Duplicate sequence numbers found in Mapping Rules. Each rule must have a unique sequence.",
				frappe.ValidationError,
			)

	def _validate_custom_function_paths(self):
		from erpnext_integration_hub.utils.validators import validate_custom_function_path
		for rule in self.mapping_rules:
			if rule.transformation_type == "Custom Function":
				validate_custom_function_path(rule.custom_function)

	def on_update(self):
		from erpnext_integration_hub.utils.cache import invalidate_mapping_profile
		invalidate_mapping_profile(self.name)
