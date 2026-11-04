import hashlib
import secrets
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import subscriptions
from app.db import SessionLocal, SubscriptionModel, get_utc_now, init_db
from app.main import app


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def _create_profile(client):
    created = client.post("/api/profile", json={})
    assert created.status_code == 200
    data = created.json()
    return data["profile"], {"Authorization": f"Bearer {data['access_token']}"}


def _verified_record(profile_id, status="active", expires_at=None):
    token_reference = secrets.token_urlsafe(32)
    return SubscriptionModel(
        profile_id=profile_id,
        product_id="fourx_premium_monthly",
        purchase_token_hash=hashlib.sha256(token_reference.encode()).hexdigest(),
        purchase_token_ciphertext="test fixture",
        status=status,
        purchase_date=get_utc_now() - timedelta(days=1),
        expires_at=expires_at or get_utc_now() + timedelta(days=30),
        auto_renew_enabled=status == "active",
        acknowledgement_state="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
        verification_status="verified",
        last_verified_at=get_utc_now(),
    )


def test_catalog_exposes_only_the_two_inr_subscription_plans(client):
    response = client.get("/api/subscription/products")
    assert response.status_code == 200
    products = response.json()["products"]
    assert [(item["product_id"], item["price_minor"], item["currency"], item["period"])
            for item in products] == [
        ("fourx_premium_monthly", 4900, "INR", "1 month"),
        ("fourx_premium_yearly", 29900, "INR", "1 year"),
    ]


def test_subscription_status_is_inactive_when_verification_is_unconfigured(
    client, monkeypatch
):
    monkeypatch.setattr(subscriptions, "billing_is_configured", lambda: False)
    _, headers = _create_profile(client)
    response = client.get("/api/subscription/status", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "premium": False,
        "subscription": None,
    }


def test_missing_profile_credential_cannot_read_subscription_status(client):
    assert client.get("/api/subscription/status").status_code == 401


def test_free_profile_cannot_use_spectator_or_premium_customization(client, monkeypatch):
    monkeypatch.setattr(subscriptions, "billing_is_configured", lambda: True)
    _, headers = _create_profile(client)
    assert client.get("/spectator/live-games", headers=headers).status_code == 403
    assert client.post(
        "/api/subscription/spectator-ticket", headers=headers
    ).status_code == 403
    assert client.put("/api/profile/customization", headers=headers, json={
        "board_theme": "singularity",
    }).status_code == 403
    assert client.patch("/api/profile", headers=headers, json={
        "avatar": "titan",
    }).status_code == 403


def test_invalid_google_purchase_is_rejected_without_recording_entitlement(
    client, monkeypatch
):
    monkeypatch.setattr(subscriptions, "billing_is_configured", lambda: True)
    monkeypatch.setattr(
        subscriptions, "_play_subscription",
        lambda _token: (_ for _ in ()).throw(subscriptions.InvalidPurchase()),
    )
    _, headers = _create_profile(client)
    response = client.post("/api/subscription/verify", headers=headers, json={
        "product_id": "fourx_premium_monthly",
        "purchase_token": secrets.token_urlsafe(32),
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Google Play could not verify this purchase"


@pytest.mark.parametrize(
    ("product_id", "price_units"),
    [
        ("fourx_premium_monthly", "49"),
        ("fourx_premium_yearly", "299"),
    ],
)
def test_verified_play_subscription_must_match_the_configured_inr_price(
    product_id, price_units
):
    response = {
        "subscriptionState": "SUBSCRIPTION_STATE_ACTIVE",
        "startTime": "2026-11-01T10:00:00Z",
        "acknowledgementState": "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
        "lineItems": [{
            "productId": product_id,
            "expiryTime": "2026-12-01T10:00:00Z",
            "autoRenewingPlan": {
                "autoRenewEnabled": True,
                "recurringPrice": {
                    "currencyCode": "INR",
                    "units": price_units,
                    "nanos": 0,
                },
            },
        }],
    }
    assert subscriptions._subscription_details(response, product_id)["product_id"] == product_id
    response["lineItems"][0]["autoRenewingPlan"]["recurringPrice"]["units"] = "1"
    with pytest.raises(subscriptions.InvalidPurchase):
        subscriptions._subscription_details(response, product_id)


def test_verified_cancelled_subscription_remains_entitled_until_expiry(
    client, monkeypatch
):
    monkeypatch.setattr(subscriptions, "billing_is_configured", lambda: True)
    monkeypatch.setattr(
        subscriptions,
        "_refresh_subscription",
        lambda _profile, record, _db: record,
    )
    profile, headers = _create_profile(client)
    db = SessionLocal()
    try:
        db.add(_verified_record(
            profile["id"],
            status="canceled",
            expires_at=get_utc_now() + timedelta(days=3),
        ))
        db.commit()
    finally:
        db.close()

    active = client.get("/api/subscription/status", headers=headers)
    assert active.status_code == 200
    assert active.json()["premium"] is True
    assert active.json()["subscription"]["auto_renew_enabled"] is False

    db = SessionLocal()
    try:
        record = db.query(SubscriptionModel).filter(
            SubscriptionModel.profile_id == profile["id"]
        ).one()
        record.expires_at = get_utc_now() - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()
    expired = client.get("/api/subscription/status", headers=headers)
    assert expired.status_code == 200
    assert expired.json()["premium"] is False
