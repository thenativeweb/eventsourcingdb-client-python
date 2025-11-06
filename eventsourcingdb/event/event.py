from dataclasses import dataclass, field
from datetime import datetime
import json
from hashlib import sha256
from typing import Any, TypeVar

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..errors.internal_error import InternalError
from ..errors.validation_error import ValidationError

Self = TypeVar("Self", bound="Event")


@dataclass
class Event:
    data: dict
    source: str
    subject: str
    type: str
    spec_version: str
    event_id: str
    time: datetime
    _time_from_server: str = field(init=False, repr=False)
    data_content_type: str
    predecessor_hash: str
    hash: str
    trace_parent: str | None = None
    trace_state: str | None = None
    signature: str | None = None

    @staticmethod
    def parse(unknown_object: dict) -> "Event":
        source = unknown_object.get("source")
        if not isinstance(source, str):
            raise ValidationError(f"Failed to parse source '{source}' to string.")

        subject = unknown_object.get("subject")
        if not isinstance(subject, str):
            raise ValidationError(f"Failed to parse subject '{subject}' to string.")

        event_type = unknown_object.get("type")
        if not isinstance(event_type, str):
            raise ValidationError(f"Failed to parse event_type '{event_type}' to string.")

        spec_version = unknown_object.get("specversion")
        if not isinstance(spec_version, str):
            raise ValidationError(f"Failed to parse spec_version '{spec_version}' to string.")

        event_id = unknown_object.get("id")
        if not isinstance(event_id, str):
            raise ValidationError(f"Failed to parse event_id '{event_id}' to string.")

        time_from_server = unknown_object.get("time")
        if not isinstance(time_from_server, str):
            raise ValidationError(f"Failed to parse time '{time_from_server}' to string.")
        time = Event.__parse_time(time_from_server)

        data_content_type = unknown_object.get("datacontenttype")
        if not isinstance(data_content_type, str):
            raise ValidationError(
                f"Failed to parse data_content_type '{data_content_type}' to string."
            )

        predecessor_hash = unknown_object.get("predecessorhash")
        if not isinstance(predecessor_hash, str):
            raise ValidationError(
                f"Failed to parse predecessor_hash '{predecessor_hash}' to string."
            )

        event_hash = unknown_object.get("hash")
        if not isinstance(event_hash, str):
            raise ValidationError(f"Failed to parse hash '{event_hash}' to string.")

        trace_parent = unknown_object.get("traceparent")
        if trace_parent is not None and not isinstance(trace_parent, str):
            raise ValidationError(f"Failed to parse trace_parent '{trace_parent}' to string.")

        trace_state = unknown_object.get("tracestate")
        if trace_state is not None and not isinstance(trace_state, str):
            raise ValidationError(f"Failed to parse trace_state '{trace_state}' to string.")

        signature = unknown_object.get("signature")
        if signature is not None and not isinstance(signature, str):
            raise ValidationError(f"Failed to parse signature '{signature}' to string.")

        data = unknown_object.get("data")
        if not isinstance(data, dict):
            raise ValidationError(f"Failed to parse data '{data}' to object.")

        event = Event(
            data=data,
            source=source,
            subject=subject,
            type=event_type,
            spec_version=spec_version,
            event_id=event_id,
            time=time,
            data_content_type=data_content_type,
            predecessor_hash=predecessor_hash,
            hash=event_hash,
            trace_parent=trace_parent,
            trace_state=trace_state,
            signature=signature,
        )
        event._time_from_server = time_from_server

        return event

    def verify_hash(self) -> None:
        metadata = "|".join([
            self.spec_version,
            self.event_id,
            self.predecessor_hash,
            self._time_from_server,
            self.source,
            self.subject,
            self.type,
            self.data_content_type,
        ])

        metadata_bytes = metadata.encode("utf-8")
        data_bytes = json.dumps(
                self.data,
                separators=(',', ':'),
                indent=None,
            ).encode("utf-8")

        metadata_hash = sha256(metadata_bytes).hexdigest()
        data_hash = sha256(data_bytes).hexdigest()

        final_hash = sha256()
        final_hash.update(metadata_hash.encode("utf-8"))
        final_hash.update(data_hash.encode("utf-8"))
        final_hash_hex = final_hash.hexdigest()

        if final_hash_hex != self.hash:
            raise ValidationError("Failed to verify hash.")

    def verify_signature(self, verification_key: Ed25519PublicKey) -> None:
        if self.signature is None:
            raise ValidationError("Signature must not be none.")

        self.verify_hash()

        signature_prefix = "esdb:signature:v1:"

        if not self.signature.startswith(signature_prefix):
            raise ValidationError(f"Signature must start with '{signature_prefix}'.")

        signature_hex = self.signature[len(signature_prefix):]
        try:
            signature_bytes = bytes.fromhex(signature_hex)
        except ValueError as error:
            raise ValidationError("Failed to decode signature.") from error

        hash_bytes = self.hash.encode("utf-8")

        try:
            verification_key.verify(signature_bytes, hash_bytes)
        except Exception as error:
            raise ValidationError("Signature verification failed.") from error

    def to_json(self) -> dict[str, Any]:
        json = {
            "specversion": self.spec_version,
            "id": self.event_id,
            "time": self.time.isoformat(sep="T"),
            "source": self.source,
            "subject": self.subject,
            "type": self.type,
            "datacontenttype": self.data_content_type,
            "predecessorhash": self.predecessor_hash,
            "hash": self.hash,
            "data": self.data,
        }

        if self.trace_parent is not None:
            json["traceparent"] = self.trace_parent
        if self.trace_state is not None:
            json["tracestate"] = self.trace_state
        if self.signature is not None:
            json["signature"] = self.signature
        json["data"] = self.data

        return json

    @staticmethod
    def __parse_time(time_from_server: str) -> datetime:
        if not isinstance(time_from_server, str):
            raise ValidationError(f"Failed to parse time '{time_from_server}' to datetime.")

        rest, sub_seconds = time_from_server.split(".")
        sub_seconds = sub_seconds[:6].ljust(6, "0")
        try:
            return datetime.fromisoformat(f"{rest}.{sub_seconds}")
        except ValueError as value_error:
            raise ValidationError(
                f"Failed to parse time '{time_from_server}' to datetime."
            ) from value_error
        except Exception as other_error:
            raise InternalError(str(other_error)) from other_error
