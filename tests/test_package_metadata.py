from importlib.metadata import metadata


class TestPackageMetadata:
    @staticmethod
    def test_provides_the_extra_pandas_which_installs_pandas() -> None:
        package_metadata = metadata("eventsourcingdb")
        requirements = package_metadata.get_all("Requires-Dist") or []

        assert "pandas" in (package_metadata.get_all("Provides-Extra") or [])
        assert any(
            requirement.startswith("pandas")
            and requirement.endswith("extra == 'pandas'")
            for requirement in requirements
        )
