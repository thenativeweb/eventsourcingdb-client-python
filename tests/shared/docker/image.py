from dataclasses import dataclass
import subprocess

from .container import Container
from .docker_command_failed_error import DockerCommandFailedError


@dataclass
class Image:
    name: str
    tag: str

    def run(self, command: list[str], is_detached: bool, do_expose_ports: bool) -> Container:
        docker_command = ['docker', 'run', '--rm']

        if is_detached:
            docker_command.append('-d')

        
        if do_expose_ports:
            docker_command.append('-P')
        
        """if do_expose_ports:
            # -P behalten und explizite Ports hinzufügen
            docker_command.append('-P')
            docker_command.extend(['-p', '3000:3000'])"""
            



        docker_command.append(self.__get_full_name())
        docker_command.extend(command)

        with subprocess.Popen(
            docker_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as process:
            stdout, stderr = process.communicate()

            if process.returncode != 0:
                raise DockerCommandFailedError(
                    f'Run failed with output: {stderr.decode("utf-8")}')

            container_id = stdout.decode('utf-8').strip()

            return Container(container_id)

    def build(self, directory: str) -> None:
        docker_command = ['docker', 'build', '-t',
                          self.__get_full_name(), directory]

        with subprocess.Popen(docker_command, stderr=subprocess.PIPE) as process:
            _, stderr = process.communicate()

            if process.returncode != 0:
                raise DockerCommandFailedError(
                    f'Build failed with output: {stderr.decode("utf-8")}')

    def __get_full_name(self) -> str:
        return f'{self.name}:{self.tag}'
