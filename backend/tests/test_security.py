from app.core.security import hash_password, verify_password


def test_hash_is_not_the_password_and_verifies() -> None:
    hashed = hash_password("correct horse")
    assert hashed != "correct horse"
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "correct horse")


def test_wrong_password_or_garbage_hash_does_not_verify() -> None:
    hashed = hash_password("correct horse")
    assert not verify_password(hashed, "wrong horse")
    assert not verify_password("not-a-hash", "correct horse")
