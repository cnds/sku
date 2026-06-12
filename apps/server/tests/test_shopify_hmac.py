from __future__ import annotations

from security.shopify import build_shopify_hmac, verify_shopify_hmac


def test_shopify_hmac_verifier_accepts_valid_signature() -> None:
    body = b'{"id": 1}'
    signature = build_shopify_hmac("secret", body)

    assert verify_shopify_hmac("secret", body, signature) is True


def test_shopify_hmac_verifier_rejects_invalid_signature() -> None:
    body = b'{"id": 1}'

    assert verify_shopify_hmac("secret", body, "invalid") is False
    assert verify_shopify_hmac("secret", body, None) is False
