"""Purchase Order factory."""
from __future__ import annotations

import frappe
from frappe.utils import today, add_days

from .base_factory import BaseFactory


class PurchaseOrderFactory(BaseFactory):

	def _build_document(self, mapped_data: dict, company: str):
		defaults = self._resolve_company_defaults(company)
		doc = frappe.new_doc("Purchase Order")

		doc.company = company
		doc.supplier = mapped_data.get("supplier") or frappe.throw(
			"Mapped data is missing required field 'supplier'.", frappe.ValidationError
		)
		doc.transaction_date = mapped_data.get("transaction_date") or today()
		doc.schedule_date = mapped_data.get("schedule_date") or add_days(today(), 7)
		doc.supplier_delivery_note = mapped_data.get("supplier_delivery_note")
		doc.buying_price_list = (
			mapped_data.get("buying_price_list")
			or mapped_data.get("price_list")
			or defaults["buying_price_list"]
			or "Standard Buying"
		)
		doc.currency = mapped_data.get("currency") or frappe.db.get_value(
			"Company", company, "default_currency"
		)
		doc.set_warehouse = (
			mapped_data.get("set_warehouse")
			or mapped_data.get("warehouse")
			or defaults["warehouse"]
		)

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
				"schedule_date": row.get("schedule_date") or doc.schedule_date,
				"warehouse": row.get("warehouse") or doc.set_warehouse,
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
