"""Sales Invoice factory."""
from __future__ import annotations

import frappe
from frappe.utils import today

from .base_factory import BaseFactory


class SalesInvoiceFactory(BaseFactory):

	def _build_document(self, mapped_data: dict, company: str):
		defaults = self._resolve_company_defaults(company)
		doc = frappe.new_doc("Sales Invoice")

		doc.company = company
		doc.customer = mapped_data.get("customer") or frappe.throw(
			"Mapped data is missing required field 'customer'.", frappe.ValidationError
		)
		doc.posting_date = mapped_data.get("posting_date") or today()
		doc.posting_time = mapped_data.get("posting_time") or "00:00:00"
		doc.due_date = mapped_data.get("due_date") or doc.posting_date
		doc.selling_price_list = (
			mapped_data.get("selling_price_list")
			or mapped_data.get("price_list")
			or defaults["selling_price_list"]
			or "Standard Selling"
		)
		doc.currency = mapped_data.get("currency") or frappe.db.get_value(
			"Company", company, "default_currency"
		)
		doc.cost_center = (
			mapped_data.get("cost_center") or defaults["cost_center"]
		)
		doc.set_warehouse = (
			mapped_data.get("set_warehouse")
			or mapped_data.get("warehouse")
			or defaults["warehouse"]
		)
		doc.po_no = mapped_data.get("po_no") or mapped_data.get("customer_po_number")
		doc.po_date = mapped_data.get("po_date")

		child_tables = mapped_data.get("_child_tables") or {}
		item_rows = child_tables.get("items") or self._single_item_rows(mapped_data)

		if not item_rows:
			frappe.throw("Mapped data contains no item rows.", frappe.ValidationError)

		for row in item_rows:
			doc.append("items", {
				"item_code": row.get("item_code") or frappe.throw(
					"Item row missing 'item_code'.", frappe.ValidationError
				),
				"qty": float(row.get("qty") or 1),
				"rate": float(row.get("rate") or row.get("price") or 0),
				"uom": row.get("uom") or frappe.db.get_value("Item", row.get("item_code"), "stock_uom"),
				"cost_center": row.get("cost_center") or doc.cost_center,
				"sales_order": row.get("sales_order") or row.get("against_sales_order"),
				"description": row.get("description") or row.get("item_name"),
			})

		doc.set_missing_values()
		return doc

	@staticmethod
	def _single_item_rows(mapped_data: dict) -> list:
		if not mapped_data.get("item_code"):
			return []
		return [{
			"item_code": mapped_data["item_code"],
			"qty": mapped_data.get("qty") or 1,
			"rate": mapped_data.get("rate") or mapped_data.get("price") or 0,
			"uom": mapped_data.get("uom"),
		}]
