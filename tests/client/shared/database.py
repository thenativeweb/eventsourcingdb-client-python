from dataclasses import dataclass
from .testing_database import TestingDatabase


@dataclass
class Database:
	withAuthorization: None
	withoutAuthorization: None
	withInvalidUrl: TestingDatabase
