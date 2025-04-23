import docker
from docker import errors

def build_database(dockerfile_directory: str) -> None:
    """Build the database image using the Docker SDK."""
    client = docker.from_env()
    try:
        client.images.build(
            path=dockerfile_directory,
            tag='eventsourcingdb:latest',
            rm=True
        )
    except errors.BuildError as e:
        raise RuntimeError(f"Failed to build database image: {e}")
    except errors.APIError as e:
        raise RuntimeError(f"Docker API error: {e}")
