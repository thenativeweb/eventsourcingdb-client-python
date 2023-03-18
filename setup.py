from setuptools import setup, find_packages

setup(
	name="eventsourcingdb-client-python",
	version="0.0.0",
	author="the native web GmbH",
	author_email="hello@thenativeweb.io",
	description="The Python client for EventSourcingDB.",
	long_description="The Python client for EventSourcingDB.",
	long_description_content_type="text/markdown",
	url="https://github.com/thenativeweb/eventsourcingdb-client-python",
	packages=find_packages(),
	classifiers=[],
	python_requires=">=3.6",
	install_requires=[
		"requests==2.26.0",
	],
)
