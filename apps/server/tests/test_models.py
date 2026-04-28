from __future__ import annotations

import warnings

from models import ShopInstallation


def test_shop_installation_default_timestamp_does_not_emit_deprecation_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ShopInstallation(
            shop_domain="demo.myshopify.com",
            public_token="token",
        )

    assert not [
        warning
        for warning in caught
        if issubclass(warning.category, DeprecationWarning)
    ]
