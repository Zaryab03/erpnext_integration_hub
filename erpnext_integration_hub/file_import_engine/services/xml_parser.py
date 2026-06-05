"""Namespace-aware XML parser using lxml."""
from __future__ import annotations

import frappe


class XMLParser:
	def __init__(self, profile: dict):
		self.profile = profile

	def parse(self, file_content: bytes) -> list[dict]:
		try:
			from lxml import etree
		except ImportError:
			frappe.throw("lxml is not installed. Run: pip install lxml")

		try:
			root = etree.fromstring(file_content)
		except etree.XMLSyntaxError as e:
			frappe.throw(f"XML parse error: {e}", frappe.ValidationError)

		namespace = self.profile.get("xml_namespace") or None
		ns = {"ns": namespace} if namespace else {}

		record_element = self.profile.get("xml_record_element")
		if not record_element:
			frappe.throw(
				"XML Record Element is not configured in the File Import Profile.",
				frappe.ValidationError,
			)

		# Build XPath expression respecting optional namespace
		if namespace:
			xpath_expr = f".//ns:{record_element}"
		else:
			xpath_expr = f".//{record_element}"

		records = root.xpath(xpath_expr, namespaces=ns)
		if not records:
			frappe.throw(
				f"No '{record_element}' elements found in the XML file.",
				frappe.ValidationError,
			)

		result = []
		for row_idx, record in enumerate(records, start=1):
			row_dict = self._element_to_dict(record)
			row_dict["_source_row"] = row_idx
			result.append(row_dict)

		return result

	def _element_to_dict(self, element) -> dict:
		"""Flatten an XML element into a dict.

		Attributes become fields. Child elements with text content become fields.
		Child elements with sub-children are skipped at this level (handled by
		Child Table Mapping configuration).
		"""
		d = {}
		# Element attributes
		for attr_name, attr_value in element.attrib.items():
			key = attr_name.lower().replace("-", "_").replace(".", "_")
			d[key] = attr_value.strip() if attr_value else None

		# Child text nodes
		for child in element:
			local_name = child.tag.split("}")[-1] if "}" in child.tag else child.tag
			key = local_name.lower().replace("-", "_").replace(".", "_")
			if len(child) == 0 and child.text:
				d[key] = child.text.strip() or None
			elif len(child) > 0:
				# Nested element — store raw XML string for child table mapper
				from lxml import etree
				d[key] = etree.tostring(child, encoding="unicode")

		return d
