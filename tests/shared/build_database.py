from .docker.image import Image


def build_database(dockerfile_directory: str) -> None:
	Image('eventsourcingdb', 'latest').build(dockerfile_directory)
