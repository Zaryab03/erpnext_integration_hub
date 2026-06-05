"""IMAP email fetcher.

Design decisions:
- imaplib from stdlib: no additional dependency, wide server compatibility.
- UID-based incremental fetch: avoids reprocessing on each poll cycle.
- Context-managed connection: IMAP connections are closed after each cycle,
  which is required for multi-worker Frappe Cloud deployments where persistent
  connections across request/job boundaries are unsafe.
- Sender whitelist and subject filter evaluated before downloading attachments
  to minimise unnecessary bandwidth.
"""
from __future__ import annotations

import email
import email.policy
import imaplib
import re
from typing import Iterator

import frappe
from frappe.utils import now_datetime

from erpnext_integration_hub.utils.audit import log_error


def fetch_account(account_name: str):
	"""RQ entry point: fetch new emails from one Email Import Account."""
	account = frappe.get_doc("Email Import Account", account_name)

	if not account.is_active:
		return

	log = frappe.new_doc("Email Import Log")
	log.email_import_account = account_name
	log.fetched_at = now_datetime()
	log.status = "Fetched"

	try:
		fetcher = EmailFetcher(account)
		batches_created = fetcher.run(log)
		log.batches_created = batches_created
		log.status = "Processed" if batches_created > 0 else "No Attachments"
	except imaplib.IMAP4.error as exc:
		_handle_connection_error(account_name, log, "Authentication", str(exc))
	except ConnectionRefusedError as exc:
		_handle_connection_error(account_name, log, "Connection", str(exc))
	except Exception as exc:
		_handle_connection_error(account_name, log, "Connection", str(exc), exc=exc)
	finally:
		log.flags.ignore_permissions = True
		log.insert(ignore_permissions=True)
		frappe.db.commit()


def _handle_connection_error(account_name, log, error_type, message, exc=None):
	log.status = "Error"
	log.error_message = message[:140]
	log_error(
		error_type, message,
		import_source=frappe.db.get_value("Email Import Account", account_name, "import_source"),
		exc=exc,
		can_retry=(error_type == "Connection"),
	)


class EmailFetcher:

	def __init__(self, account):
		self.account = account

	def run(self, log) -> int:
		"""Connect, fetch new messages, return number of batches created."""
		conn = self._connect()
		try:
			return self._process_messages(conn, log)
		finally:
			try:
				conn.logout()
			except Exception:
				pass

	def _connect(self):
		account = self.account
		if account.use_ssl:
			conn = imaplib.IMAP4_SSL(account.imap_server, account.imap_port)
		else:
			conn = imaplib.IMAP4(account.imap_server, account.imap_port)

		password = account.get_password("password")
		conn.login(account.username, password)
		conn.select("INBOX")
		return conn

	def _process_messages(self, conn, log) -> int:
		last_uid = self.account.last_fetched_uid or "0"

		# Search for messages with UID greater than last processed
		_, data = conn.uid("search", None, f"UID {int(last_uid)+1}:*")
		uid_list = data[0].split() if data[0] else []

		if not uid_list:
			return 0

		allowed_extensions = [
			e.strip().lower()
			for e in (self.account.allowed_extensions or ".xlsx,.csv,.xml,.json").split(",")
		]
		sender_whitelist = [
			s.strip().lower()
			for s in (self.account.sender_whitelist or "").splitlines()
			if s.strip()
		]
		subject_filter = (self.account.subject_contains or "").lower()

		batches_created = 0
		max_uid = int(last_uid)

		for uid_bytes in uid_list:
			uid = int(uid_bytes)
			_, msg_data = conn.uid("fetch", str(uid).encode(), "(RFC822)")
			raw_email = msg_data[0][1]
			msg = email.message_from_bytes(raw_email, policy=email.policy.default)

			from_email = str(msg.get("From") or "").lower()
			subject = str(msg.get("Subject") or "")
			msg_date = msg.get("Date")

			# Update log with last-seen email metadata
			log.from_email = from_email
			log.subject = subject
			log.message_uid = str(uid)
			log.message_date = msg_date

			# Sender whitelist check
			if sender_whitelist and not any(s in from_email for s in sender_whitelist):
				log.status = "Filtered"
				max_uid = max(max_uid, uid)
				continue

			# Subject filter check
			if subject_filter and subject_filter not in subject.lower():
				log.status = "Filtered"
				max_uid = max(max_uid, uid)
				continue

			attachments = list(self._iter_attachments(msg, allowed_extensions))
			log.attachment_count = len(list(msg.iter_attachments()))
			log.qualifying_attachment_count = len(attachments)

			if not attachments:
				max_uid = max(max_uid, uid)
				continue

			# Create one Import Batch per qualifying attachment
			for filename, content in attachments:
				batch = self._create_batch(filename, content)
				if batch:
					batches_created += 1

			# Move email to processed folder
			if self.account.processed_folder:
				try:
					conn.uid("copy", str(uid).encode(), self.account.processed_folder)
					conn.uid("store", str(uid).encode(), "+FLAGS", "\\Deleted")
					conn.expunge()
				except Exception:
					pass  # Folder move is best-effort; do not fail the import

			max_uid = max(max_uid, uid)

		# Persist the UID cursor
		frappe.db.set_value(
			"Email Import Account", self.account.name,
			{
				"last_fetched_uid": str(max_uid),
				"last_fetched_at": now_datetime(),
			},
			update_modified=False,
		)

		return batches_created

	@staticmethod
	def _iter_attachments(msg, allowed_extensions: list):
		for part in msg.iter_attachments():
			filename = part.get_filename() or ""
			ext = filename.rsplit(".", 1)[-1].lower()
			ext_with_dot = f".{ext}"
			if ext_with_dot in allowed_extensions:
				content = part.get_payload(decode=True)
				if content:
					yield filename, content

	def _create_batch(self, filename: str, content: bytes) -> "frappe.Document | None":
		from erpnext_integration_hub.email_import_engine.services.attachment_extractor import AttachmentExtractor
		extractor = AttachmentExtractor(self.account.import_source)
		return extractor.create_batch_from_attachment(filename, content)
