# ERPNext Integration Hub

**Eliminate manual order entry.** ERPNext Integration Hub is a production ready Frappe app that automatically imports Sales Orders, Purchase Orders, Delivery Notes, and Sales Invoices into ERPNext from files, emails, and SFTP servers with full mapping control, error tracking, and audit trails.

---

## What It Does

Most businesses receive orders from customers or suppliers in different formats an Excel sheet from one customer, a CSV attachment from another, an XML file dropped on an SFTP server by a third-party system. Without an integration hub, someone manually keys all of that data into ERPNext every day. That person makes mistakes, works late, and slows down fulfilment.

This app solves that problem by giving you:

- **Three ingestion channels** — upload a file directly from the desk, poll an email inbox for attachments, or pull files from an SFTP server on a schedule
- **A visual mapping engine** — configure which source column maps to which ERPNext field, with transformations (static values, lookups, Python expressions) — no code required
- **Automatic document creation** — validated, correctly structured ERPNext documents created in the background via job queues
- **Error management with retry logic** — every failure is logged with a full stack trace, row number, and raw data snapshot; failed items can be retried with exponential backoff
- **Company-scoped security** — operators only see batches belonging to their company; credentials (IMAP passwords, SFTP keys) are AES-256 encrypted
- **A full audit trail** — every created document, every error, every retry is permanently recorded

---

## Supported Document Types

| ERPNext Document | Auto-created from imported data |
|---|---|
| Sales Order | Yes |
| Purchase Order | Yes |
| Delivery Note | Yes |
| Sales Invoice | Yes |

---

## Supported Import Sources

| Channel | How it works |
|---|---|
| **File Upload** | Operator uploads Excel/CSV/XML/JSON directly from the ERPNext desk |
| **Email (IMAP)** | App polls a configured mailbox every 5 minutes; attachments matching your filter are auto-imported |
| **SFTP** | App connects to a remote SFTP server every 10 minutes; matching files are downloaded, imported, then archived on the server |

---

## Prerequisites

Before installing, make sure your environment meets these requirements:

### 1. Frappe Bench

You need a working Frappe bench installation (version 15 or higher).

```bash
# Verify your Frappe version
bench version
# Must show: frappe 15.x.x
```

If you do not have a bench, follow the [official Frappe installation guide](https://frappeframework.com/docs/user/en/installation).

### 2. ERPNext

ERPNext must be installed in the same bench and added to the site you intend to use.

```bash
bench get-app erpnext
bench --site your-site.com install-app erpnext
```

### 3. Python 3.10+

```bash
python3 --version
# Must show: Python 3.10.x or higher
```

### 4. Redis

Redis must be running for the background job queue. Frappe bench manages this automatically in production mode, but in development you may need to start it manually:

```bash
bench start   # starts Redis along with all other bench services
```

### 5. Python Libraries

These are installed automatically when you install the app (`pip` handles them). Listed here so your server's network firewall/proxy allows access to PyPI:

| Library | Purpose |
|---|---|
| `openpyxl >= 3.1.0` | Excel (.xlsx) file parsing |
| `lxml >= 4.9.0` | XML file parsing |
| `jsonpath-ng >= 1.6.0` | JSONPath expressions for nested JSON |
| `paramiko >= 3.3.0` | SFTP connections |
| `chardet >= 5.0.0` | Automatic file encoding detection |

---

## Installation

### Step 1 — Get the app

```bash
bench get-app https://github.com/your-org/erpnext_integration_hub
```

Or if you have the source code locally:

```bash
# From your bench directory
cp -r /path/to/erpnext_integration_hub apps/erpnext_integration_hub
pip install -e apps/erpnext_integration_hub
```

### Step 2 — Install on your site

```bash
bench --site your-site.com install-app erpnext_integration_hub
```

This will:
- Create all 17 DocTypes in the database
- Create the three user roles (Integration Manager, Integration Operator, Integration Viewer)
- Create the Integration Hub workspace on the ERPNext desk
- Insert default Integration Hub Settings

### Step 3 — Run migrate

```bash
bench --site your-site.com migrate
```

### Step 4 — Restart bench

```bash
bench restart
```

### Step 5 — Verify installation

Log into your ERPNext desk. You should see **Integration Hub** in the left sidebar or the module list. Navigate to **Integration Hub Settings** and enable the hub.

---

## Quick Start

### Configure a File Import Source

1. Go to **Integration Hub → Configuration → File Import Profile** and create a profile for your file format (e.g., CSV with comma delimiter, has header row).
2. Go to **Mapping Engine → Field Mapping Profile** and define your column-to-field mappings (e.g., source column `Customer Code` → ERPNext field `customer`).
3. Go to **Integration Hub → Configuration → Import Source**, create a source, link your File Import Profile, Field Mapping Profile, and set the target document type to `Sales Order`.
4. Go to **Integration Hub → Imports → Import Batch**, create a new batch, select your Import Source, upload your file, then click **Submit**.
5. The batch is processed in the background. Refresh the form to watch progress. Any errors appear under **View Errors**.

### Configure an Email Import

1. Create an **Email Import Account** with your IMAP server details (password is encrypted automatically).
2. Create an **Import Source** with Source Type = `Email`, link the account and your mapping profile.
3. The scheduler polls the mailbox every 5 minutes. Matching attachments are imported automatically.

### Configure an SFTP Import

1. Create an **SFTP Import Profile** with your server host, port, credentials (password or SSH key), remote path, and file pattern (e.g., `orders_*.csv`).
2. Create an **Import Source** with Source Type = `SFTP`.
3. The scheduler polls the server every 10 minutes. Files are downloaded, imported, and archived.

---

## User Roles

Three roles are created on installation. Assign them in ERPNext's **User** form.

| Role | What they can do |
|---|---|
| **Integration Manager** | Full access — configure sources, mapping profiles, SFTP/email accounts, retry or cancel any batch, resolve errors |
| **Integration Operator** | Day-to-day work — upload files, monitor batches, view errors. Cannot change configuration |
| **Integration Viewer** | Read-only — view batches, logs, and statistics. Useful for business analysts or managers who need visibility |

---

## Running Tests

```bash
bench --site your-site.com set-config allow_tests true
bench --site your-site.com run-tests --app erpnext_integration_hub
```

Expected output: **49 tests, 0 failures.**

---

## Uninstalling

```bash
bench --site your-site.com uninstall-app erpnext_integration_hub
```

The app will refuse to uninstall if any batches are actively processing, to prevent data loss. Cancel or wait for them to complete first.

---

## How This Helps in Industry

### Manufacturing & Distribution

A manufacturer receives purchase orders from 50 retail customers. Each customer emails their order as an Excel sheet in a slightly different format. Previously, a data-entry clerk spent 3–4 hours per day manually creating Sales Orders in ERPNext. With the Integration Hub, a Field Mapping Profile is configured once per customer format, and from that point forward orders arrive, get mapped, and are created in ERPNext automatically — usually within 5 minutes of the email landing.

### Import/Export Trading

A trading company receives supplier invoices as XML files dropped on an SFTP server by their overseas suppliers' ERP system. The Integration Hub polls the SFTP server on a schedule, downloads each file, creates a Purchase Order or Purchase Invoice, and archives the file. The accounts team now works from ERPNext instead of manually entering data from a shared folder.

### Third-Party System Integration

A company uses a legacy order management system that cannot connect directly to ERPNext. The legacy system exports a daily CSV at midnight to an SFTP server. The Integration Hub picks it up automatically every 10 minutes, so by the time the warehouse opens in the morning, all new Sales Orders are already in ERPNext and ready for picking.

### Multi-Location / Multi-Company Operations

The app is designed for multi-company ERPNext setups. Each Import Source is linked to a specific company, and users only see data belonging to their company. A holding group with multiple subsidiary companies can share one ERPNext instance and one Integration Hub installation, with each subsidiary's team working in complete isolation.

### Where to Get Help

| Resource | What you'll find |
|---|---|
| **ERPNext Community Forum** — [discuss.erpnext.com](https://discuss.erpnext.com) | ERPNext and Frappe framework questions, answered by the community and the core team |
| **Frappe Framework Docs** — [frappeframework.com/docs](https://frappeframework.com/docs) | DocType concepts, controller hooks, background jobs, permissions |
| **ERPNext Docs** — [docs.erpnext.com](https://docs.erpnext.com) | Sales Order, Purchase Order, and other document workflows that this app creates |
| **GitHub Issues** | Report bugs or request features on this repository's Issues tab |
| **Frappe Cloud** — [frappecloud.com](https://frappecloud.com) | Managed ERPNext hosting — the Integration Hub is compatible with Frappe Cloud |
| **ERPNext Implementation Partners** | For production deployments with custom mapping requirements, certified ERPNext partners provide paid implementation and support services. Find them at [erpnext.com/partners](https://erpnext.com/partners) |

---

## Architecture Overview

```
File Upload / Email / SFTP
        │
        ▼
  Import Source (config)
        │
        ▼
  Import Batch (submitted → triggers background job)
        │
        ├── File Parser (Excel / CSV / XML / JSON)
        │
        ├── Mapper (Field Mapping Profile + transformations)
        │
        ├── Document Factory (Sales Order / PO / DN / SI)
        │
        └── Audit Trail (Document Creation Log / Import Error Log)
```

Background jobs run on Frappe's Redis queue (`long` queue for batch processing). The scheduler checks email and SFTP sources on configurable intervals. All credentials are stored encrypted. All operations respect ERPNext's company-scoped permissions.

---

## License

MIT
