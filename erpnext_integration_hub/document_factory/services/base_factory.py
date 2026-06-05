"""Abstract base factory.

All concrete factories extend BaseFactory and implement _build_document().
The template method create() handles the cross-cutting concerns: creation
logging, batch item status updates, and auto-submit — so each concrete
factory only contains doctype-specific field population logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import frappe
from frappe.utils import now_datetime
from erpnext_integration_hub.utils.audit import log_document_created


class BaseFactory(ABC):

	def create(
		self,
		mapped_data: dict,
		item_name: str,
		company: str,
		auto_submit: bool = False,
	):
		"""Template method.  Calls _build_document(), then insert / submit.

		Returns the created frappe.Document.
		Raises frappe.ValidationError or frappe.PermissionError on failure —
		callers (batch_manager.process_item) catch and log these.
		"""
		doc = self._build_document(mapped_data, company)

		# Ensure company is set — every ERPNext transactional document requires it
		if not doc.get("company"):
			doc.company = company

		doc.flags.ignore_permissions = False  # Respect ERPNext permissions
		doc.insert()

		if auto_submit:
			doc.submit()

		# Persist the audit trail
		batch_name = frappe.db.get_value("Import Batch Item", item_name, "import_batch")
		log_document_created(
			import_batch=batch_name,
			import_batch_item=item_name,
			target_doctype=doc.doctype,
			document_name=doc.name,
			company=company,
			document_status="Submitted" if auto_submit else "Draft",
		)

		return doc

	@abstractmethod
	def _build_document(self, mapped_data: dict, company: str):
		"""Construct and return an unsaved frappe.Document from mapped_data.

		Do not call doc.insert() or doc.submit() here — BaseFactory.create()
		handles that after subclass returns.
		"""

	def _get_default(self, doctype: str, filters: dict, field: str, company: str = None):
		"""Safe helper to fetch a default value from a linked DocType."""
		f = dict(filters)
		if company and "company" not in f:
			f["company"] = company
		return frappe.db.get_value(doctype, f, field)

	def _resolve_company_defaults(self, company: str) -> dict:
		"""Return common company-level defaults used by all factories."""
		abbr = frappe.db.get_value("Company", company, "abbr")
		default_cost_center = f"Main - {abbr}" if abbr else None
		default_warehouse = frappe.db.get_value(
			"Warehouse",
			{"company": company, "is_group": 0},
			"name",
			order_by="creation asc",
		)
		default_price_list = frappe.db.get_value(
			"Price List", {"enabled": 1, "buying": 1}, "name"
		)
		selling_price_list = frappe.db.get_value(
			"Price List", {"enabled": 1, "selling": 1}, "name"
		)
		return {
			"cost_center": default_cost_center,
			"warehouse": default_warehouse,
			"buying_price_list": default_price_list,
			"selling_price_list": selling_price_list,
		}
