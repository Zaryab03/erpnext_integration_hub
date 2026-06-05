"""Delivery Note factory."""
from __future__ import annotations

import frappe
from frappe.utils import today

from .base_factory import BaseFactory


class DeliveryNoteFactory(BaseFactory):

	def _build_document(self, mapped_data: dict, company: str):
		defaults = self._resolve_company_defaults(company)
		doc = frappe.new_doc("Delivery Note")

		doc.company = company
		doc.customer = mapped_data.get("customer") or frappe.throw(
			"Mapped data is missing required field 'customer'.", frappe.ValidationError
		)
		doc.posting_date = mapped_data.get("posting_date") or today()
		doc.posting_time = mapped_data.get("posting_time") or "00:00:00"
		doc.set_warehouse = (
			mapped_data.get("set_warehouse")
			or mapped_data.get("warehouse")
			or defaults["warehouse"]
		)
		doc.lr_no = mapped_data.get("lr_no") or mapped_data.get("transporter_bill_no")
		doc.lr_date = mapped_data.get("lr_date")
		doc.vehicle_no = mapped_data.get("vehicle_no")

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
				"rate": float(row.get("rate") or 0),
				"uom": row.get("uom") or frappe.db.get_value("Item", row.get("item_code"), "stock_uom"),
				"warehouse": row.get("warehouse") or doc.set_warehouse,
				"against_sales_order": row.get("against_sales_order"),
				"so_detail": row.get("so_detail"),
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
			"rate": mapped_data.get("rate") or 0,
			"uom": mapped_data.get("uom"),
		}]
