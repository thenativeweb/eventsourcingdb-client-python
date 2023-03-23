from .docker_command_failed_error import DockerCommandFailedError
from ..util.remove_whitespace import remove_whitespace
import subprocess


class Container:
	def __init__(self, container_id: str):
		self.__id: str = container_id

	def kill(self) -> None:
		process = subprocess.Popen(['docker', 'kill', self.__id], stderr=subprocess.PIPE)
		_, stderr = process.communicate()

		if process.returncode != 0:
			raise DockerCommandFailedError(f'Kill failed with output: {stderr}')

	def get_exposed_port(self, internal_port: int) -> int:
		docker_command = [
			'docker',
			'inspect',
			f'--format=\'{{{{(index (index .NetworkSettings.Ports "{internal_port}/tcp") 0).HostPort}}}}\'',
			self.__id
		]

		process = subprocess.Popen(docker_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		stdout, stderr = process.communicate()

		if process.returncode != 0:
			raise DockerCommandFailedError(f'Inspect failed with output: {stderr.decode("utf-8")}')

		exposed_port_as_string = remove_whitespace(stdout.decode('utf-8')).replace('\'', '').replace('|', '')

		try:
			return int(exposed_port_as_string)
		except ValueError:
			raise ValueError(f'Could not parse port from: {exposed_port_as_string}')

