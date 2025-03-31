from dataclasses import dataclass
import subprocess
import json
import time

from .docker_command_failed_error import DockerCommandFailedError
from ..util.remove_whitespace import remove_whitespace


@dataclass
class Container:
    # id is the correct name for this member even though it is that short
    # pylint: disable=invalid-name
    id: str
    # pylint: enable=invalid-name

    def kill(self) -> None:
        with subprocess.Popen(['docker', 'kill', self.id], stderr=subprocess.PIPE) as process:
            _, stderr = process.communicate()

            if process.returncode != 0:
                raise DockerCommandFailedError(
                    f'Kill failed with output: {stderr}')

    def get_exposed_port(self, internal_port: int = 3_000) -> int:
        docker_command = [
            'docker',
            'inspect',
            f'--format={{{{json .NetworkSettings.Ports}}}}',
            self.id
        ]

        with subprocess.Popen(
            docker_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        ) as process:
            stdout, stderr = process.communicate()

            if process.returncode != 0:
                raise DockerCommandFailedError(
                    f'Inspect failed with output: {stderr.decode("utf-8")}')
            # Parse the JSON output to get the port mapping
            try:
                port_mappings = json.loads(stdout.decode('utf-8').strip())
                port_key = f"{internal_port}/tcp"
                if port_key not in port_mappings or not port_mappings[port_key]:
                    # Wait briefly and try to restart/refresh the container
                    time.sleep(1)
                    self.restart()
                    time.sleep(2)  # Wait for container to be ready
                    # Try one more time after restart
                    return self.get_exposed_port(internal_port)
                return int(port_mappings[port_key][0]['HostPort'])
            except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
                raise DockerCommandFailedError(
                    f'Failed to parse port mapping: {stdout.decode("utf-8")}. Error: {str(e)}')

    def restart(self):
        """Restart the container"""
        docker_command = ['docker', 'restart', self.id]
        with subprocess.Popen(
            docker_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        ) as process:
            process.communicate()
            if process.returncode != 0:
                raise DockerCommandFailedError('Failed to restart container')
