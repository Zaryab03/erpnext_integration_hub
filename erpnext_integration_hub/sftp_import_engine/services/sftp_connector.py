"""Paramiko-based SFTP connector.

Design decisions:
- Context manager (with SFTPSession(...) as sftp) pattern ensures the
  underlying SSH connection is always closed, even on exception.  Long-running
  Frappe Cloud workers must not leak TCP connections.
- Authentication supports both password and SSH key (PEM) with optional
  passphrase.  All sensitive material is decrypted from Frappe's encrypted
  Password field at connection time and never stored in local variables beyond
  the connection call.
- File archival (move on server after download) prevents re-processing on
  the next polling cycle without maintaining a local "seen files" state.
"""
from __future__ import annotations

import fnmatch
import io
import os

import frappe
from frappe.utils import now_datetime

from erpnext_integration_hub.utils.audit import log_error


def check_profile(profile_name: str):
	"""RQ short-queue entry point: connect to one SFTP profile and fetch new files."""
	profile = frappe.get_doc("SFTP Import Profile", profile_name)

	if not profile.is_active:
		return

	log = frappe.new_doc("SFTP Import Log")
	log.sftp_import_profile = profile_name
	log.checked_at = now_datetime()

	try:
		with SFTPSession(profile) as sftp:
			files = sftp.list_files()
			log.files_found = len(files)

			if not files:
				log.status = "No Files"
			else:
				downloaded = 0
				for filename in files:
					content = sftp.download_file(filename)
					if content:
						_create_batch(profile, filename, content)
						downloaded += 1
						if profile.archive_remote_path:
							sftp.archive_file(filename)

				log.files_downloaded = downloaded
				log.batches_created = downloaded
				log.status = "Success"

		frappe.db.set_value(
			"SFTP Import Profile", profile_name, "last_checked_at", now_datetime(),
			update_modified=False,
		)

	except paramiko_auth_error() as exc:
		log.status = "Auth Error"
		log.error_message = str(exc)[:140]
		log_error("Authentication", str(exc), can_retry=False)
	except Exception as exc:
		log.status = "Connection Error"
		log.error_message = str(exc)[:140]
		log_error("Connection", str(exc), can_retry=True, exc=exc)
	finally:
		log.flags.ignore_permissions = True
		log.insert(ignore_permissions=True)
		frappe.db.commit()


def paramiko_auth_error():
	"""Lazy import to avoid ImportError at module load on sites without paramiko."""
	try:
		import paramiko
		return paramiko.AuthenticationException
	except ImportError:
		return Exception


def _create_batch(profile, filename: str, content: bytes):
	from erpnext_integration_hub.email_import_engine.services.attachment_extractor import AttachmentExtractor
	# Re-use AttachmentExtractor since the logic is identical — store bytes, create batch
	extractor = AttachmentExtractor(profile.import_source)
	batch = extractor.create_batch_from_attachment(filename, content)
	# Override source type to SFTP
	frappe.db.set_value("Import Batch", batch.name, "source_type", "SFTP", update_modified=False)
	return batch


class SFTPSession:
	"""Context manager wrapping a paramiko SFTP session."""

	def __init__(self, profile):
		self.profile = profile
		self._ssh = None
		self._sftp = None

	def __enter__(self):
		import paramiko
		self._ssh = paramiko.SSHClient()
		self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

		timeout = int(self.profile.connection_timeout or 30)
		connect_kwargs = {
			"hostname": self.profile.host,
			"port": int(self.profile.port or 22),
			"username": self.profile.username,
			"timeout": timeout,
		}

		if self.profile.auth_type == "Password":
			connect_kwargs["password"] = self.profile.get_password_value()
		else:
			import paramiko
			key_str = self.profile.get_private_key_value()
			passphrase = self.profile.get_passphrase_value()
			pkey = paramiko.RSAKey.from_private_key(
				io.StringIO(key_str),
				password=passphrase,
			)
			connect_kwargs["pkey"] = pkey

		self._ssh.connect(**connect_kwargs)
		self._sftp = self._ssh.open_sftp()
		return self

	def __exit__(self, *args):
		if self._sftp:
			try:
				self._sftp.close()
			except Exception:
				pass
		if self._ssh:
			try:
				self._ssh.close()
			except Exception:
				pass

	def list_files(self) -> list[str]:
		"""Return filenames in remote_path matching file_pattern."""
		remote_path = self.profile.remote_path
		pattern = self.profile.file_pattern or "*"

		try:
			all_files = self._sftp.listdir(remote_path)
		except Exception as e:
			frappe.throw(f"Cannot list SFTP directory '{remote_path}': {e}")

		return [
			f for f in all_files
			if fnmatch.fnmatch(f, pattern) and not f.startswith(".")
		]

	def download_file(self, filename: str) -> bytes | None:
		remote_path = self.profile.remote_path.rstrip("/") + "/" + filename
		buf = io.BytesIO()
		try:
			self._sftp.getfo(remote_path, buf)
		except Exception as e:
			log_error("Connection", f"Cannot download '{remote_path}': {e}", can_retry=True)
			return None
		return buf.getvalue()

	def archive_file(self, filename: str):
		"""Move a downloaded file to archive_remote_path on the server."""
		if not self.profile.archive_remote_path:
			return
		src = self.profile.remote_path.rstrip("/") + "/" + filename
		dst = self.profile.archive_remote_path.rstrip("/") + "/" + filename
		try:
			self._sftp.rename(src, dst)
		except Exception as e:
			# Archive failure is non-fatal; log but continue
			log_error("System", f"Cannot archive '{src}' to '{dst}': {e}", can_retry=False)
