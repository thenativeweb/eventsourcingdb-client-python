import pytest

from cryptography.hazmat.primitives.asymmetric import ed25519
from eventsourcingdb import EventCandidate, Container
from eventsourcingdb.errors.validation_error import ValidationError
from hashlib import sha256

from ..conftest import TestData


class TestVerifySignature:
    @staticmethod
    @pytest.mark.asyncio
    async def test_returns_error_if_signature_is_none(
        test_data: TestData,
    ) -> None:
        container = Container().with_image_tag("preview")
        container.start()

        try:
            client = container.get_client()

            written_events = await client.write_events(
                [
                    EventCandidate(
                        source="https://www.eventsourcingdb.io",
                        subject="/test",
                        type="io.eventsourcingdb.test",
                        data={"value": 23}
                    )
                ],
            )

            assert len(written_events) == 1

            written_event = written_events[0]
            assert written_event.signature is None

            public_key = ed25519.Ed25519PrivateKey.generate().public_key()

            with pytest.raises(ValidationError):
                written_event.verify_signature(public_key)
        finally:
            container.stop()

    @staticmethod
    @pytest.mark.asyncio
    async def test_returns_error_if_hash_verification_fails(
        test_data: TestData,
    ) -> None:
        container = Container().with_image_tag("preview").with_signing_key()
        container.start()

        try:
            client = container.get_client()

            written_events = await client.write_events(
                [
                    EventCandidate(
                        source="https://www.eventsourcingdb.io",
                        subject="/test",
                        type="io.eventsourcingdb.test",
                        data={"value": 23}
                    )
                ],
            )

            assert len(written_events) == 1

            written_event = written_events[0]
            assert written_event.signature is not None

            invalid_hash_data = "invalid hash".encode("utf-8")
            invalid_hash = sha256(invalid_hash_data).hexdigest()
            written_event.hash = invalid_hash

            verification_key = container.get_verification_key()

            with pytest.raises(ValidationError):
                written_event.verify_signature(verification_key)
        finally:
            container.stop()

    @staticmethod
    @pytest.mark.asyncio
    async def test_returns_error_if_signature_verification_fails(
        test_data: TestData,
    ) -> None:
        container = Container().with_image_tag("preview").with_signing_key()
        container.start()

        try:
            client = container.get_client()

            written_events = await client.write_events(
                [
                    EventCandidate(
                        source="https://www.eventsourcingdb.io",
                        subject="/test",
                        type="io.eventsourcingdb.test",
                        data={"value": 23}
                    )
                ],
            )

            assert len(written_events) == 1

            written_event = written_events[0]
            assert written_event.signature is not None

            valid_signature = written_event.signature
            tampered_signature = valid_signature + "0123456789abcdef"
            written_event.signature = tampered_signature

            verification_key = container.get_verification_key()

            with pytest.raises(ValidationError):
                written_event.verify_signature(verification_key)
        finally:
            container.stop()

    @staticmethod
    @pytest.mark.asyncio
    async def test_verifies_the_signature(
        test_data: TestData,
    ) -> None:
        container = Container().with_image_tag("preview").with_signing_key()
        container.start()

        try:
            client = container.get_client()

            written_events = await client.write_events(
                [
                    EventCandidate(
                        source="https://www.eventsourcingdb.io",
                        subject="/test",
                        type="io.eventsourcingdb.test",
                        data={"value": 23}
                    )
                ],
            )

            assert len(written_events) == 1

            written_event = written_events[0]
            assert written_event.signature is not None

            verification_key = container.get_verification_key()

            written_event.verify_signature(verification_key)
        finally:
            container.stop()
