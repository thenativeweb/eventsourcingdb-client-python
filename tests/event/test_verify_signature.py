from hashlib import sha256

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from eventsourcingdb import (
    Container,
    EventCandidate,
    HashVerificationFailedError,
    SignatureVerificationFailedError,
    ValidationError,
)

from ..conftest import TestData
from ..shared.image_tag import get_image_tag
from ..shared.serve_events import read_events_from
from ..shared.stream_server import Api
from .fixtures import (
    READ_EVENTS_FROM_V2_API,
    READ_EVENTS_WITH_HASH_V1,
    READ_EVENTS_WITH_HASH_V2,
    VERIFICATION_KEY_V1,
    VERIFICATION_KEY_V2,
    VERIFICATION_KEY_V2_API,
)

SIGNED_EVENTS = [
    pytest.param(READ_EVENTS_WITH_HASH_V1, VERIFICATION_KEY_V1, 'v1', id='v1'),
    pytest.param(READ_EVENTS_WITH_HASH_V2, VERIFICATION_KEY_V2, 'v1', id='v2'),
    pytest.param(
        READ_EVENTS_FROM_V2_API, VERIFICATION_KEY_V2_API, 'v2', id='v2 from the v2 API'
    ),
]


class TestVerifySignature:
    @staticmethod
    @pytest.mark.asyncio
    async def test_returns_error_if_signature_is_none(
        test_data: TestData,
    ) -> None:
        container = Container().with_image_tag(get_image_tag())
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

            with pytest.raises(ValidationError, match='Signature must not be none.'):
                written_event.verify_signature(public_key)
        finally:
            container.stop()

    @staticmethod
    @pytest.mark.asyncio
    async def test_returns_error_if_hash_verification_fails(
        test_data: TestData,
    ) -> None:
        container = Container().with_image_tag(get_image_tag()).with_signing_key()
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

            invalid_hash_data = b"invalid hash"
            invalid_hash = sha256(invalid_hash_data).hexdigest()
            written_event.hash = invalid_hash

            verification_key = container.get_verification_key()

            with pytest.raises(HashVerificationFailedError):
                written_event.verify_signature(verification_key)
        finally:
            container.stop()

    @staticmethod
    @pytest.mark.asyncio
    async def test_returns_error_if_signature_verification_fails(
        test_data: TestData,
    ) -> None:
        container = Container().with_image_tag(get_image_tag()).with_signing_key()
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

            with pytest.raises(SignatureVerificationFailedError) as error:
                written_event.verify_signature(verification_key)

            assert isinstance(error.value, ValidationError)
        finally:
            container.stop()

    @staticmethod
    @pytest.mark.asyncio
    async def test_verifies_the_signature(
        test_data: TestData,
    ) -> None:
        container = Container().with_image_tag(get_image_tag()).with_signing_key()
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


class TestVerifySignatureOfFixedEvents:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('lines', 'verification_key', 'api'), SIGNED_EVENTS)
    async def test_verifies_the_signature(lines: list[str], verification_key: bytes, api: Api) -> None:
        events = await read_events_from(lines, api)

        assert len(events) == len(lines)
        for event in events:
            event.verify_signature(ed25519.Ed25519PublicKey.from_public_bytes(verification_key))

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('lines', 'verification_key', 'api'), SIGNED_EVENTS)
    async def test_fails_if_the_signature_does_not_match_the_verification_key(
        lines: list[str], verification_key: bytes, api: Api
    ) -> None:
        events = await read_events_from(lines, api)
        other_verification_key = ed25519.Ed25519PrivateKey.generate().public_key()

        for event in events:
            with pytest.raises(SignatureVerificationFailedError, match='Signature verification failed.'):
                event.verify_signature(other_verification_key)

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('lines', 'verification_key', 'api'), SIGNED_EVENTS)
    async def test_fails_if_the_signature_was_changed(
        lines: list[str], verification_key: bytes, api: Api
    ) -> None:
        events = await read_events_from(lines, api)

        for event in events:
            assert event.signature is not None
            event.signature = event.signature[:-2] + ('00' if event.signature[-2:] != '00' else '11')

            with pytest.raises(SignatureVerificationFailedError, match='Signature verification failed.'):
                event.verify_signature(ed25519.Ed25519PublicKey.from_public_bytes(verification_key))

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('lines', 'verification_key', 'api'), SIGNED_EVENTS)
    async def test_fails_if_the_signature_is_malformed(
        lines: list[str], verification_key: bytes, api: Api
    ) -> None:
        events = await read_events_from(lines, api)

        for event in events:
            event.signature = 'esdb:signature:v1:not-hexadecimal'

            with pytest.raises(SignatureVerificationFailedError, match='Failed to decode signature.'):
                event.verify_signature(ed25519.Ed25519PublicKey.from_public_bytes(verification_key))

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(('lines', 'verification_key', 'api'), SIGNED_EVENTS)
    async def test_fails_if_the_hash_is_invalid(lines: list[str], verification_key: bytes, api: Api) -> None:
        events = await read_events_from(
            [line.replace('/books/42', '/books/23') for line in lines], api
        )

        for event in events:
            with pytest.raises(HashVerificationFailedError):
                event.verify_signature(ed25519.Ed25519PublicKey.from_public_bytes(verification_key))
