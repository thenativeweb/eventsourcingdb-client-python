from dataclasses import dataclass
import subprocess

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

    def get_exposed_port(self, internal_port: int) -> int:
        docker_command = [
            'docker',
            'inspect',
            # this is a string that cannot be break apart in a useful way
            # pylint: disable=line-too-long
            f'--format=\'{{{{(index (index .NetworkSettings.Ports "{internal_port}/tcp") 0).HostPort}}}}\'',
            # pylint: enable=line-too-long
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

            exposed_port_as_string = remove_whitespace(
                stdout.decode('utf-8')
            ).replace('\'', '').replace('|', '')

        try:
            return int(exposed_port_as_string)
        except ValueError as value_error:
            raise ValueError(
                f'Could not parse port from: {exposed_port_as_string}'
            ) from value_error
