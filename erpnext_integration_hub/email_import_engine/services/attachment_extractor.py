"""Saves email attachment bytes into Frappe's file system and creates an Import Batch."""
from __future__ import annotations

import os
import frappe


class AttachmentExtractor:

	def __init__(self, import_source_name: str):
		self.import_source_name = import_source_name

	def create_batch_from_attachment(self, filename: str, content: bytes):
		"""Store attachment in Frappe Files, then create and return an Import Batch."""
		# Save to Frappe file system (private, not public)
		file_doc = frappe.new_doc("File")
		file_doc.file_name = filename
		file_doc.is_private = 1
		file_doc.content = content
		file_doc.flags.ignore_permissions = True
		file_doc.insert(ignore_permissions=True)

		ext = os.path.splitext(filename.lower())[1].lstrip(".")
		format_map = {
			"xlsx": "Excel", "xls": "Excel",
			"csv": "CSV",
			"xml": "XML",
			"json": "JSON",
		}

		source = frappe.get_doc("Import Source", self.import_source_name)

		batch = frappe.new_doc("Import Batch")
		batch.import_source = self.import_source_name
		batch.company = source.company
		batch.status = "Pending"
		batch.file_name = filename
		batch.file_url = file_doc.file_url
		batch.file_format = format_map.get(ext)
		batch.source_type = "Email"
		batch.target_document_type = source.target_document_type
		batch.flags.ignore_permissions = True
		batch.insert(ignore_permissions=True)

		frappe.db.commit()
		return batch
