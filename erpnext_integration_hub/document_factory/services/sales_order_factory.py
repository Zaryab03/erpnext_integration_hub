"""Sales Order factory."""
from __future__ import annotations

import frappe
from frappe.utils import today, add_days

from .base_factory import BaseFactory


class SalesOrderFactory(BaseFactory):

	def _build_document(self, mapped_data: dict, company: str):
		defaults = self._resolve_company_defaults(company)
		doc = frappe.new_doc("Sales Order")

		# Header fields
		doc.company = company
		doc.customer = mapped_data.get("customer") or frappe.throw(
			"Mapped data is missing required field 'customer'.", frappe.ValidationError
		)
		doc.transaction_date = mapped_data.get("transaction_date") or today()
		doc.delivery_date = mapped_data.get("delivery_date") or add_days(today(), 7)
		doc.po_no = mapped_data.get("po_no") or mapped_data.get("customer_po_number")
		doc.po_date = mapped_data.get("po_date")
		doc.order_type = mapped_data.get("order_type") or "Sales"
		doc.selling_price_list = (
			mapped_data.get("selling_price_list")
			or mapped_data.get("price_list")
			or defaults["selling_price_list"]
			or "Standard Selling"
		)
		doc.currency = mapped_data.get("currency") or frappe.db.get_value(
			"Company", company, "default_currency"
		)
		doc.set_warehouse = (
			mapped_data.get("set_warehouse")
			or mapped_data.get("warehouse")
			or defaults["warehouse"]
		)

		# Resolve customer's currency / price list if not in mapped data
		customer_currency = frappe.db.get_value("Customer", doc.customer, "default_currency")
		if customer_currency and not mapped_data.get("currency"):
			doc.currency = customer_currency

		# Items
		child_tables = mapped_data.get("_child_tables") or {}
		item_rows = child_tables.get("items") or self._single_item_rows(mapped_data)

		if not item_rows:
			frappe.throw(
				"Mapped data contains no item rows. Check child table mapping.",
				frappe.ValidationError,
			)

		for row in item_rows:
			doc.append("items", {
				"item_code": row.get("item_code") or frappe.throw(
					"Item row missing 'item_code'.", frappe.ValidationError
				),
				"qty": float(row.get("qty") or 1),
				"rate": float(row.get("rate") or row.get("price") or 0),
				"uom": row.get("uom") or frappe.db.get_value("Item", row.get("item_code"), "stock_uom"),
				"delivery_date": row.get("delivery_date") or doc.delivery_date,
				"warehouse": row.get("warehouse") or doc.set_warehouse,
				"description": row.get("description") or row.get("item_name"),
			})

		doc.set_missing_values()
		return doc

	@staticmethod
	def _single_item_rows(mapped_data: dict) -> list:
		"""Fallback: construct a single item row from flat mapped_data fields."""
		if not mapped_data.get("item_code"):
			return []
		return [{
			"item_code": mapped_data["item_code"],
			"qty": mapped_data.get("qty") or 1,
			"rate": mapped_data.get("rate") or mapped_data.get("price") or 0,
			"uom": mapped_data.get("uom"),
			"delivery_date": mapped_data.get("delivery_date"),
		}]
