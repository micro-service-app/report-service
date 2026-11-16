import pytest
from fastapi import HTTPException

from app.main import tenant_id


def test_accepts_valid_workspace_ids():
    assert tenant_id("main") == "main"
    assert tenant_id("0f8e2c1a9b7d4e6f") == "0f8e2c1a9b7d4e6f"


@pytest.mark.parametrize("value", [None, "", "a b", "../main"])
def test_rejects_missing_or_invalid_ids(value):
    with pytest.raises(HTTPException) as e:
        tenant_id(value)
    assert e.value.status_code == 401
