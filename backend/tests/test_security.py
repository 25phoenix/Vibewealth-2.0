import pytest

from app.core.security import hash_password, validate_password, verify_password


def test_hash_password_uses_argon2id_with_explicit_parameters() -> None:
    password = "correct horse battery staple"

    encoded_hash = hash_password(password)

    assert encoded_hash != password
    assert encoded_hash.startswith("$argon2id$")
    assert encoded_hash.split("$")[2] == "v=19"
    assert encoded_hash.split("$")[3] == "m=65536,t=3,p=4"


def test_password_verification_accepts_only_the_correct_password() -> None:
    encoded_hash = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", encoded_hash) is True
    assert verify_password("incorrect horse battery staple", encoded_hash) is False


def test_hashing_the_same_password_uses_a_new_salt_each_time() -> None:
    password = "correct horse battery staple"

    assert hash_password(password) != hash_password(password)


@pytest.mark.parametrize("password", ["", "12345678901234"])
def test_passwords_shorter_than_15_characters_are_rejected(password: str) -> None:
    with pytest.raises(ValueError, match="at least 15 characters"):
        validate_password(password)

    with pytest.raises(ValueError, match="at least 15 characters"):
        hash_password(password)


def test_password_of_exactly_15_characters_is_accepted() -> None:
    password = "123456789012345"

    validate_password(password)
    assert verify_password(password, hash_password(password)) is True


def test_spaces_are_preserved_without_trimming() -> None:
    password = "  a passphrase with spaces  "
    encoded_hash = hash_password(password)

    assert verify_password(password, encoded_hash) is True
    assert verify_password(password.strip(), encoded_hash) is False


def test_unicode_password_is_preserved_without_normalization() -> None:
    password = "Pässwörd with Unicode 😀"
    encoded_hash = hash_password(password)

    assert verify_password(password, encoded_hash) is True
    assert verify_password("Password with Unicode 😀", encoded_hash) is False


@pytest.mark.parametrize(
    "malformed_hash",
    [
        "not-a-hash",
        "$scrypt$unsupported",
        "$argon2id$v=19$m=bad,t=3,p=4$bad$bad",
    ],
)
def test_malformed_or_unsupported_hashes_fail_safely(malformed_hash: str) -> None:
    assert verify_password("any password", malformed_hash) is False
