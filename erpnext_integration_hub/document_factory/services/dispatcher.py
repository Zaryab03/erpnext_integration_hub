"""DocumentDispatcher — routes a mapped_data dict to the correct factory.

This is the single entry point for document creation.  The dispatcher
decouples batch_manager from knowledge of which factories exist.
"""
from __future__ import annotations

import frappe

from .sales_order_factory import SalesOrderFactory
from .purchase_order_factory import PurchaseOrderFactory
from .delivery_note_factory import DeliveryNoteFactory
from .sales_invoice_factory import SalesInvoiceFactory


FACTORY_MAP = {
	"Sales Order": SalesOrderFactory,
	"Purchase Order": PurchaseOrderFactory,
	"Delivery Note": DeliveryNoteFactory,
	"Sales Invoice": SalesInvoiceFactory,
}


class DocumentDispatcher:

	def dispatch(
		self,
		mapped_data: dict,
		target_doctype: str,
		item_name: str,
		company: str,
		auto_submit: bool = False,
	):
		"""Look up the correct factory and create the document.

		Raises frappe.ValidationError if target_doctype is not supported.
		Returns the created frappe.Document.
		"""
		factory_cls = FACTORY_MAP.get(target_doctype)
		if not factory_cls:
			frappe.throw(
				f"No factory registered for target DocType '{target_doctype}'. "
				f"Supported: {', '.join(FACTORY_MAP.keys())}",
				frappe.ValidationError,
			)

		factory = factory_cls()
		return factory.create(mapped_data, item_name, company, auto_submit=auto_submit)
