from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
	name="erpnext_integration_hub",
	version="1.0.0",
	description="Automated order import engine for ERPNext — File, Email, and SFTP ingestion",
	author="Integration Hub",
	author_email="admin@example.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires,
)
