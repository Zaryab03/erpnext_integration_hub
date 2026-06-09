from . import __version__ as app_version

app_name = "erpnext_integration_hub"
app_title = "ERPNext Integration Hub"
app_publisher = "Integration Hub"
app_description = "Automated order import engine — File, Email, and SFTP ingestion into ERPNext"
app_email = "admin@example.com"
app_license = "MIT"
app_version = app_version

# ─── Required apps ────────────────────────────────────────────────────────────
# Prevents installation on bare Frappe without ERPNext. Factories reference
# ERPNext DocTypes (Sales Order, Purchase Order, etc.) directly.
required_apps = ["frappe", "erpnext"]

# ─── After install / before uninstall ─────────────────────────────────────────
after_install = "erpnext_integration_hub.setup.after_install"
before_uninstall = "erpnext_integration_hub.setup.before_uninstall"

# ─── Scheduled tasks ──────────────────────────────────────────────────────────
# Cron expressions used instead of Frappe's fixed "hourly"/"daily" keys because
# we need sub-hourly intervals (5 min, 10 min, 15 min).  Each task function is
# a thin wrapper that immediately returns if the hub is disabled or if the
# configured interval has not yet elapsed — hooks.py cannot read DocType settings
# at module load time, so the minimum cron frequency is defined here and the
# effective frequency is governed by Integration Hub Settings at runtime.
scheduler_events = {
	"cron": {
		# Email polling — fastest safe interval for IMAP round-trips
		"*/5 * * * *": [
			"erpnext_integration_hub.tasks.email_import.fetch_all_email_accounts",
		],
		# SFTP polling — slightly slower; SFTP handshake has higher overhead
		"*/10 * * * *": [
			"erpnext_integration_hub.tasks.sftp_import.check_all_sftp_profiles",
		],
		# Retry manager — runs between email and SFTP cycles
		"*/15 * * * *": [
			"erpnext_integration_hub.tasks.retry_manager.retry_failed_items",
		],
	},
	"hourly": [
		"erpnext_integration_hub.tasks.cleanup.archive_completed_batches",
	],
	"daily": [
		"erpnext_integration_hub.tasks.cleanup.purge_old_logs",
	],
}

# ─── Document events ──────────────────────────────────────────────────────────
# Wired on Import Batch only. on_submit triggers document creation so that the
# operator's explicit "Submit" action on the form is the processing trigger —
# consistent with how every other submittable DocType works in ERPNext.
# on_cancel cleans up pending items without touching already-created ERPNext
# documents (those must be cancelled manually to preserve the audit trail).
doc_events = {
	"Import Batch": {
		"on_submit": "erpnext_integration_hub.file_import_engine.services.batch_manager.on_batch_submit",
		"on_cancel": "erpnext_integration_hub.file_import_engine.services.batch_manager.on_batch_cancel",
	},
}

# ─── Row-level security ───────────────────────────────────────────────────────
# Users without System Manager role see only records belonging to companies
# they have access to. Mirrors ERPNext's own company-scoped visibility pattern.
permission_query_conditions = {
	"Import Batch": "erpnext_integration_hub.utils.permissions.get_company_condition",
	"Import Source": "erpnext_integration_hub.utils.permissions.get_company_condition",
	"Import Error Log": "erpnext_integration_hub.utils.permissions.get_import_error_log_condition",
	"Document Creation Log": "erpnext_integration_hub.utils.permissions.get_company_condition",
}

has_permission = {
	"Import Batch": "erpnext_integration_hub.utils.permissions.has_company_permission",
}

# ─── Fixtures ─────────────────────────────────────────────────────────────────
# Roles and Workspace are exported so that `bench migrate` on a fresh site
# creates them automatically. This is the correct Frappe mechanism — not
# after_install Python code that is hard to re-run.
fixtures = [
	# Roles: created from fixtures/role.json on bench migrate / install.
	# Using filter-based export so that bench export-fixtures regenerates them.
	{
		"dt": "Role",
		"filters": [["name", "in", [
			"Integration Manager",
			"Integration Operator",
			"Integration Viewer",
		]]],
	},
	# Workspace: fixtures/workspace.json defines the Integration Hub desk module.
	# The Workspace module field references "File Import Engine" (a valid module)
	# so Frappe's sync logic can resolve it.
	{
		"dt": "Workspace",
		"filters": [["name", "=", "Integration Hub"]],
	},
]

# ─── Jinja environment ────────────────────────────────────────────────────────
jinja = {
	"methods": [
		"erpnext_integration_hub.utils.jinja_helpers.get_batch_summary",
	],
}

# ─── Override DocType classes ─────────────────────────────────────────────────
# Intentionally empty. We do NOT override any ERPNext DocType controllers.
# All logic operates on our own DocTypes or uses frappe.new_doc() for creation.
# This preserves full ERPNext upgrade compatibility.
override_doctype_class = {}

# ─── API surface (documentation comment only) ─────────────────────────────────
# Frappe registers whitelisted methods via the @frappe.whitelist() decorator at
# import time — there is no hooks.py key for this.  The list below is kept as
# a comment so there is one canonical place to audit the HTTP surface.
#
# erpnext_integration_hub.api.import_api.upload_file_for_import   POST
# erpnext_integration_hub.api.import_api.get_batch_status         GET
# erpnext_integration_hub.api.import_api.preview_file_mapping     POST
# erpnext_integration_hub.api.import_api.retry_batch_item         POST
# erpnext_integration_hub.api.import_api.cancel_batch             POST
# erpnext_integration_hub.api.import_api.validate_sftp_connection POST
# erpnext_integration_hub.api.import_api.validate_email_connection POST
# erpnext_integration_hub.api.import_api.get_import_statistics    GET
# erpnext_integration_hub.api.import_api.resolve_error            POST

# ─── App-level includes ───────────────────────────────────────────────────────
# No global JS includes. Each DocType form JS is scoped to its own file.
app_include_js = []
app_include_css = []
