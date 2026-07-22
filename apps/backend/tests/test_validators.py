import pytest

from smartoncall.services.auth.validators import validate_email


@pytest.mark.parametrize("email", [
    "user@example.com",
    "user.name@example.com",
    "user+tag@example.co.uk",
    "user123@sub.domain.org",
    "a@b.cc",
])
def test_valid_emails(email):
    assert validate_email(email) is True


@pytest.mark.parametrize("email", [
    "",
    "plaintext",
    "@example.com",
    "user@",
    "user@.com",
    "user@com",
    "user @example.com",
    "user@@example.com",
    "user@example",
])
def test_invalid_emails(email):
    assert validate_email(email) is False
