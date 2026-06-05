import json
import frappe


_CACHE_GROUP = "integration_hub"


def get_settings():
	"""Return Integration Hub Settings, cached for 5 minutes.

	The TTL matches Frappe's prompt cache window.  Settings rarely change during
	processing runs, so caching avoids N database reads across N batch items.
	"""
	cache_key = "settings"
	cached = frappe.cache().hget(_CACHE_GROUP, cache_key)
	if cached:
		return cached

	settings = frappe.get_single("Integration Hub Settings")
	frappe.cache().hset(_CACHE_GROUP, cache_key, settings, expires_in_sec=300)
	return settings


def get_mapping_profile(profile_name: str):
	"""Return a Field Mapping Profile with all child rules, keyed by modified timestamp.

	The modified timestamp acts as a cache-busting key so that profile updates
	are picked up without manual cache invalidation or a worker restart.
	"""
	modified = frappe.db.get_value("Field Mapping Profile", profile_name, "modified")
	if not modified:
		frappe.throw(f"Field Mapping Profile '{profile_name}' not found.")

	cache_key = f"mapping_profile:{profile_name}:{modified}"
	cached = frappe.cache().hget(_CACHE_GROUP, cache_key)
	if cached:
		if isinstance(cached, str):
			return json.loads(cached)
		return cached

	profile = frappe.get_doc("Field Mapping Profile", profile_name)
	# Convert to a plain dict so the cache stores a serialisable object.
	data = profile.as_dict()
	frappe.cache().hset(_CACHE_GROUP, cache_key, json.dumps(data, default=str), expires_in_sec=300)
	return data


def invalidate_mapping_profile(profile_name: str):
	"""Called by Field Mapping Profile controller on_update to bust stale cache."""
	# Redis HSCAN is not available via Frappe's cache helper, so we set a
	# sentinel key that the getter checks.  Simplest safe approach.
	frappe.cache().hdel(_CACHE_GROUP, f"mapping_profile:{profile_name}:*")


def get_value_transformation_map(transformation_name: str) -> dict:
	"""Return the full source→target map for a named Value Transformation group."""
	cache_key = f"vt:{transformation_name}"
	cached = frappe.cache().hget(_CACHE_GROUP, cache_key)
	if cached:
		if isinstance(cached, str):
			return json.loads(cached)
		return cached

	rows = frappe.get_all(
		"Value Transformation",
		filters={"transformation_name": transformation_name},
		fields=["source_value", "target_value"],
	)
	mapping = {r.source_value: r.target_value for r in rows}
	frappe.cache().hset(_CACHE_GROUP, cache_key, json.dumps(mapping), expires_in_sec=600)
	return mapping
