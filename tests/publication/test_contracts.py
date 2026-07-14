from __future__ import annotations

import pytest
from pydantic import ValidationError

from cios.publication.types import RunIdentity


def test_run_identity_valid_identifier_parses() -> None:
    identity = RunIdentity(run_id="cios-20260714T090000Z-12345", tenant_slug="algolia")

    assert identity.run_id == "cios-20260714T090000Z-12345"
    assert identity.tenant_slug == "algolia"


@pytest.mark.parametrize(
    "run_id",
    (
        "../escape",
        "/absolute",
        "contains space",
        "semi;colon",
        "",
    ),
)
def test_run_identity_unsafe_identifier_is_rejected(run_id: str) -> None:
    with pytest.raises(ValidationError):
        RunIdentity(run_id=run_id, tenant_slug="algolia")
