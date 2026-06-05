import frappe
from frappe.model.document import Document


class FileImportProfile(Document):
	def validate(self):
		if self.file_format == "Excel":
			self._validate_excel()
		elif self.file_format == "CSV":
			self._validate_csv()
		elif self.file_format == "JSON":
			self._validate_json()

	def _validate_excel(self):
		if self.excel_header_row and self.excel_data_start_row:
			if self.excel_data_start_row <= self.excel_header_row:
				frappe.throw(
					"Data Start Row must be greater than Header Row.",
					frappe.ValidationError,
				)

	def _validate_csv(self):
		if self.csv_quote_char and len(self.csv_quote_char) > 1:
			frappe.throw("Quote Character must be a single character.", frappe.ValidationError)

	def _validate_json(self):
		if self.json_records_path and not self.json_records_path.startswith("$"):
			frappe.throw(
				"JSON Records Path must be a valid JSONPath expression starting with '$'.",
				frappe.ValidationError,
			)
