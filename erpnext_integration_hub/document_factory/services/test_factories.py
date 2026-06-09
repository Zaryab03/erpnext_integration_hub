"""Tests for document factories and the dispatcher.

These are the highest-risk components in the app: a bug here creates wrong
financial documents (Sales Orders, Invoices, etc.) directly in a company's
books. Tests build a mapped_data dict — exactly what the Mapper would hand
off — and assert on the resulting (unsubmitted) document.

Test fixtures (Customer / Item) are created against whatever Company already
exists on the site and are rolled back automatically by FrappeTestCase, so
these tests are portable across sites without depending on demo data names.
"""
from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_integration_hub.document_factory.services.dispatcher import (
	FACTORY_MAP,
	DocumentDispatcher,
)
from erpnext_integration_hub.document_factory.services.sales_order_factory import SalesOrderFactory


def _ensure_customer(name, customer_group, territory):
	if frappe.db.exists("Customer", name):
		return name
	doc = frappe.get_doc({
		"doctype": "Customer",
		"customer_name": name,
		"customer_group": customer_group,
		"territory": territory,
	}).insert(ignore_permissions=True)
	return doc.name


def _ensure_item(code, item_group):
	if frappe.db.exists("Item", code):
		return code
	doc = frappe.get_doc({
		"doctype": "Item",
		"item_code": code,
		"item_name": code,
		"item_group": item_group,
		"stock_uom": "Nos",
		"is_stock_item": 0,
	}).insert(ignore_permissions=True)
	return doc.name


class FactoryTestBase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.get_all("Company", limit=1, pluck="name")[0]
		customer_group = frappe.get_all("Customer Group", limit=1, pluck="name")[0]
		territory = frappe.get_all("Territory", limit=1, pluck="name")[0]
		item_group = frappe.get_all("Item Group", limit=1, pluck="name")[0]

		cls.customer = _ensure_customer("IH-Test-Customer", customer_group, territory)
		cls.item_code = _ensure_item("IH-TEST-ITEM-1", item_group)


class TestSalesOrderFactory(FactoryTestBase):
	def _mapped_data(self, **overrides):
		data = {
			"customer": self.customer,
			"_child_tables": {
				"items": [
					{"item_code": self.item_code, "qty": "3", "rate": "100"},
				],
			},
		}
		data.update(overrides)
		return data

	def test_builds_sales_order_with_child_items(self):
		factory = SalesOrderFactory()
		doc = factory._build_document(self._mapped_data(), self.company)

		self.assertEqual(doc.doctype, "Sales Order")
		self.assertEqual(doc.customer, self.customer)
		self.assertEqual(doc.company, self.company)
		self.assertEqual(len(doc.items), 1)
		self.assertEqual(doc.items[0].item_code, self.item_code)
		self.assertEqual(doc.items[0].qty, 3.0)
		self.assertEqual(doc.items[0].rate, 100.0)

	def test_missing_customer_throws_validation_error(self):
		factory = SalesOrderFactory()
		mapped = self._mapped_data()
		mapped.pop("customer")
		with self.assertRaises(frappe.ValidationError):
			factory._build_document(mapped, self.company)

	def test_missing_item_rows_throws_validation_error(self):
		factory = SalesOrderFactory()
		mapped = {"customer": self.customer}  # no _child_tables, no flat item_code
		with self.assertRaises(frappe.ValidationError):
			factory._build_document(mapped, self.company)

	def test_single_item_fallback_from_flat_fields(self):
		factory = SalesOrderFactory()
		mapped = {
			"customer": self.customer,
			"item_code": self.item_code,
			"qty": "5",
			"rate": "50",
		}
		doc = factory._build_document(mapped, self.company)
		self.assertEqual(len(doc.items), 1)
		self.assertEqual(doc.items[0].qty, 5.0)
		self.assertEqual(doc.items[0].rate, 50.0)

	def test_create_inserts_and_logs(self):
		"""End-to-end through BaseFactory.create(): insert + Document Creation Log."""
		# create() needs a real Import Batch Item to attribute the log to.
		# Build the minimal fixture chain: File Import Profile → Import Source →
		# Import Batch → Import Batch Item.
		file_profile = frappe.get_doc({
			"doctype": "File Import Profile",
			"profile_name": "IH-Test-Profile",
			"file_format": "CSV",
		}).insert(ignore_permissions=True)

		mapping_profile = frappe.get_doc({
			"doctype": "Field Mapping Profile",
			"profile_name": "IH-Test-Mapping",
			"target_doctype": "Sales Order",
		}).insert(ignore_permissions=True)

		source = frappe.get_doc({
			"doctype": "Import Source",
			"source_name": "IH-Test-Source",
			"company": self.company,
			"is_active": 1,
			"source_type": "File Upload",
			"file_import_profile": file_profile.name,
			"mapping_profile": mapping_profile.name,
			"target_document_type": "Sales Order",
		}).insert(ignore_permissions=True)

		batch = frappe.get_doc({
			"doctype": "Import Batch",
			"import_source": source.name,
			"company": self.company,
			"status": "Processing",
			"batch_date": frappe.utils.today(),
			"source_type": "File Upload",
			"target_document_type": "Sales Order",
			"file_name": "test.csv",
			"file_format": "CSV",
		}).insert(ignore_permissions=True)

		item = frappe.get_doc({
			"doctype": "Import Batch Item",
			"import_batch": batch.name,
			"row_number": 1,
			"status": "Processing",
		}).insert(ignore_permissions=True)

		factory = SalesOrderFactory()
		doc = factory.create(self._mapped_data(), item.name, self.company, auto_submit=False)

		self.assertTrue(frappe.db.exists("Sales Order", doc.name))
		self.assertEqual(doc.docstatus, 0)

		log_exists = frappe.db.exists("Document Creation Log", {
			"import_batch_item": item.name,
			"document_name": doc.name,
			"target_doctype": "Sales Order",
		})
		self.assertTrue(log_exists)


class TestDocumentDispatcher(FactoryTestBase):
	def test_dispatch_routes_to_correct_factory(self):
		self.assertIn("Sales Order", FACTORY_MAP)
		self.assertIs(FACTORY_MAP["Sales Order"], SalesOrderFactory)

	def test_dispatch_unsupported_doctype_throws(self):
		dispatcher = DocumentDispatcher()
		with self.assertRaises(frappe.ValidationError):
			dispatcher.dispatch({}, "Stock Entry", "ITEM-DOES-NOT-EXIST", self.company)
