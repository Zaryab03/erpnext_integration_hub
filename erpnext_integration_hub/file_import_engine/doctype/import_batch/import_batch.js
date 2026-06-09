// Import Batch form client script.
//
// Architecture note: ALL business logic lives in Python (batch_manager.py and
// the service layer). This file contains ONLY UI concerns:
//   - Adding action buttons that call whitelisted Python API methods.
//   - Refreshing progress indicators.
//   - Displaying operator-friendly status messages.
//
// No validation, no field derivation, no business rules here.

frappe.ui.form.on("Import Batch", {

	refresh(frm) {
		frm.trigger("set_indicators");
		frm.trigger("add_action_buttons");
		if (["Queued", "Processing"].includes(frm.doc.status)) {
			frm.trigger("start_progress_polling");
		}
	},

	set_indicators(frm) {
		const colour_map = {
			"Pending": "orange",
			"Queued": "yellow",
			"Processing": "blue",
			"Completed": "green",
			"Partially Processed": "orange",
			"Failed": "red",
			"Cancelled": "grey",
			"Archived": "grey",
		};
		frm.page.set_indicator(
			frm.doc.status,
			colour_map[frm.doc.status] || "grey"
		);
	},

	add_action_buttons(frm) {
		// Upload & process button — only when draft and source type is File Upload
		if (
			frm.doc.docstatus === 0 &&
			frm.doc.status === "Pending" &&
			frm.doc.source_type === "File Upload" &&
			frm.doc.import_source
		) {
			frm.add_custom_button(__("Upload File"), () => {
				frm.trigger("show_file_upload_dialog");
			}, __("Actions"));
		}

		// Retry all errors — available to Integration Manager when batch has errors
		if (
			frm.doc.docstatus === 1 &&
			["Partially Processed", "Failed"].includes(frm.doc.status) &&
			frm.doc.error_count > 0 &&
			frappe.user.has_role("Integration Manager")
		) {
			frm.add_custom_button(__("Retry All Errors"), () => {
				frappe.confirm(
					__("Re-queue all errored items in this batch?"),
					() => frm.trigger("retry_all_errors")
				);
			}, __("Actions"));
		}

		// View errors link
		if (frm.doc.error_count > 0) {
			frm.add_custom_button(__("View Errors ({0})", [frm.doc.error_count]), () => {
				frappe.set_route("List", "Import Error Log", {
					import_batch: frm.doc.name,
					is_resolved: 0,
				});
			});
		}

		// View created documents link
		if (frm.doc.success_count > 0) {
			frm.add_custom_button(
				__("Created Documents ({0})", [frm.doc.success_count]),
				() => {
					frappe.set_route("List", "Document Creation Log", {
						import_batch: frm.doc.name,
					});
				}
			);
		}
	},

	show_file_upload_dialog(frm) {
		const dialog = new frappe.ui.Dialog({
			title: __("Upload File for Import"),
			fields: [
				{
					fieldname: "file",
					fieldtype: "Attach",
					label: __("File"),
					reqd: 1,
					description: __("Supported formats: Excel (.xlsx), CSV, XML, JSON"),
				},
			],
			primary_action_label: __("Upload & Save"),
			primary_action(values) {
				// Attach the file URL to the batch, then let the user Submit
				frm.set_value("file_url", values.file);
				frm.set_value("file_name", values.file.split("/").pop());
				dialog.hide();
				frm.save();
			},
		});
		dialog.show();
	},

	retry_all_errors(frm) {
		frappe.call({
			method: "erpnext_integration_hub.api.import_api.retry_all_batch_errors",
			args: { batch_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Re-queuing errored items…"),
			callback(r) {
				if (!r.exc) {
					frappe.show_alert({
						message: __("Items re-queued for processing."),
						indicator: "green",
					});
					frm.reload_doc();
				}
			},
		});
	},

	start_progress_polling(frm) {
		// Poll every 4 seconds while the batch is actively processing.
		// Polling stops automatically when status reaches a terminal state.
		const poll_interval = setInterval(() => {
			if (!frm.doc.name || frm.is_dirty()) {
				clearInterval(poll_interval);
				return;
			}
			frappe.call({
				method: "erpnext_integration_hub.api.import_api.get_batch_status",
				args: { batch_name: frm.doc.name },
				callback(r) {
					if (r.message) {
						const s = r.message;
						// Update counters without a full page reload
						frm.set_value("status", s.status, null, true);
						frm.set_value("total_records", s.total_records, null, true);
						frm.set_value("processed_records", s.processed_records, null, true);
						frm.set_value("success_count", s.success_count, null, true);
						frm.set_value("error_count", s.error_count, null, true);
						frm.trigger("set_indicators");

						// Show a progress bar in the form header
						const pct = s.total_records
							? Math.round((s.processed_records / s.total_records) * 100)
							: 0;
						frm.dashboard.show_progress(
							__("Processing"),
							pct,
							__("{0} / {1} records", [s.processed_records, s.total_records])
						);

						if (!["Queued", "Processing"].includes(s.status)) {
							clearInterval(poll_interval);
							frm.reload_doc();
						}
					}
				},
			});
		}, 4000);
	},
});
