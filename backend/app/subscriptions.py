"""Google Play subscription verification and premium entitlements."""

import base64
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from urllib.parse import urlencode
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request as URLRequest, urlopen

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import (
    GooglePlayNotificationModel,
    PlayerProfileModel,
    SubscriptionModel,
    get_db,
    get_utc_now,
)
from app.profiles import profile_from_authorization

logger = logging.getLogger("fourx.subscriptions")
router = APIRouter()

PLAY_PRODUCTS = {
    "fourx_premium_monthly": {
        "name": "Monthly Premium",
        "price_minor": 4900,
        "currency": "INR",
        "period": "1 month",
    },
    "fourx_premium_yearly": {
        "name": "Yearly Premium",
        "price_minor": 29900,
        "currency": "INR",
        "period": "1 year",
    },
}
PLAY_PACKAGE_NAME = "com.neonchess.fourplayer"
PLAY_API_BASE = "https://androidpublisher.googleapis.com/androidpublisher/v3"
PLAY_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
ENTITLED_STATES = {"active", "canceled", "in_grace_period"}
STATUS_REFRESH_SECONDS = 60
SPECTATOR_TICKET_SECONDS = 120
_credentials_lock = threading.Lock()
_credentials_cache: tuple[str, str, float] | None = None
_google_certs_cache: tuple[float, dict[str, dict[str, str]]] | None = None


class PurchaseVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str = Field(min_length=1, max_length=80)
    purchase_token: str = Field(min_length=16, max_length=4096)


class SubscriptionUnavailable(Exception):
    pass


class InvalidPurchase(Exception):
    pass


def _package_name() -> str:
    return os.getenv("GOOGLE_PLAY_PACKAGE_NAME", PLAY_PACKAGE_NAME)


def _token_cipher() -> Optional[Fernet]:
    key = os.getenv("FOURX_PLAY_TOKEN_ENCRYPTION_KEY")
    if not key:
        return None
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return None


def _service_account_path() -> Optional[str]:
    path = os.getenv("GOOGLE_PLAY_SERVICE_ACCOUNT_FILE")
    return path if path and os.path.isfile(path) else None


def billing_is_configured() -> bool:
    return bool(_service_account_path() and _token_cipher())


def _google_access_token() -> str:
    path = _service_account_path()
    if not path:
        raise SubscriptionUnavailable
    global _credentials_cache
    with _credentials_lock:
        try:
            if _credentials_cache and _credentials_cache[0] == path:
                cached_token, expires_at = _credentials_cache[1], _credentials_cache[2]
                if expires_at > time.time() + 60:
                    return cached_token
            with open(path, "r", encoding="utf-8") as credential_file:
                service_account = json.load(credential_file)
            client_email = service_account["client_email"]
            token_uri = service_account["token_uri"]
            if token_uri != "https://oauth2.googleapis.com/token":
                raise ValueError("Unexpected Google OAuth endpoint")
            claims = {
                "iss": client_email,
                "scope": PLAY_SCOPE,
                "aud": token_uri,
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
            }
            assertion = _sign_service_account_jwt(
                service_account["private_key"], claims
            )
            token_request = URLRequest(
                token_uri,
                data=urlencode({
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                }).encode("ascii"),
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urlopen(token_request, timeout=12) as response:
                token_data = json.loads(response.read())
            access_token = token_data["access_token"]
            expires_at = time.time() + int(token_data.get("expires_in", 3600))
            _credentials_cache = (path, access_token, expires_at)
            return access_token
        except SubscriptionUnavailable:
            raise
        except Exception as error:
            logger.error("Google Play credentials could not be loaded or refreshed.")
            raise SubscriptionUnavailable from error


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign_service_account_jwt(private_key_pem: str, claims: dict[str, Any]) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    header = _b64url_encode(json.dumps(
        {"alg": "RS256", "typ": "JWT"}, separators=(",", ":")
    ).encode("utf-8"))
    payload = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header}.{payload}".encode("ascii")
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"), password=None
    )
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise ValueError("Google service-account key must be RSA")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64url_encode(signature)}"


def _play_request(path: str, method: str = "GET", payload: Optional[dict] = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = URLRequest(
        f"{PLAY_API_BASE}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {_google_access_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=12) as response:
            response_body = response.read()
        return json.loads(response_body) if response_body else {}
    except HTTPError as error:
        if error.code in {400, 404}:
            raise InvalidPurchase from None
        logger.error("Google Play API request failed with HTTP %s.", error.code)
        raise SubscriptionUnavailable from None
    except (URLError, TimeoutError, json.JSONDecodeError):
        logger.error("Google Play API request failed.")
        raise SubscriptionUnavailable from None


def _play_subscription(purchase_token: str) -> dict[str, Any]:
    package = quote(_package_name(), safe="")
    token = quote(purchase_token, safe="")
    return _play_request(
        f"/applications/{package}/purchases/subscriptionsv2/tokens/{token}"
    )


def _acknowledge_purchase(product_id: str, purchase_token: str) -> None:
    package = quote(_package_name(), safe="")
    product = quote(product_id, safe="")
    token = quote(purchase_token, safe="")
    _play_request(
        f"/applications/{package}/purchases/subscriptions/{product}"
        f"/tokens/{token}:acknowledge",
        method="POST",
        payload={},
    )


def _parse_utc(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _database_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _subscription_details(
    response: dict[str, Any],
    required_product_id: Optional[str] = None,
) -> dict[str, Any]:
    provider_state = response.get("subscriptionState")
    state_map = {
        "SUBSCRIPTION_STATE_ACTIVE": "active",
        "SUBSCRIPTION_STATE_CANCELED": "canceled",
        "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "in_grace_period",
        "SUBSCRIPTION_STATE_ON_HOLD": "on_hold",
        "SUBSCRIPTION_STATE_PAUSED": "paused",
        "SUBSCRIPTION_STATE_EXPIRED": "expired",
        "SUBSCRIPTION_STATE_PENDING": "pending",
        "SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED": "expired",
    }
    status = state_map.get(provider_state, "unknown")
    line_items = response.get("lineItems")
    if not isinstance(line_items, list):
        raise InvalidPurchase
    candidates = [
        item for item in line_items
        if isinstance(item, dict) and item.get("productId") in PLAY_PRODUCTS
    ]
    if required_product_id:
        candidates = [item for item in candidates if item.get("productId") == required_product_id]
    if not candidates:
        raise InvalidPurchase
    item = max(candidates, key=lambda value: value.get("expiryTime", ""))
    expires_at = _parse_utc(item.get("expiryTime"))
    if expires_at is None:
        raise InvalidPurchase
    auto_renewing = item.get("autoRenewingPlan")
    recurring_price = (
        auto_renewing.get("recurringPrice")
        if isinstance(auto_renewing, dict)
        else None
    )
    if not isinstance(recurring_price, dict):
        raise InvalidPurchase
    try:
        amount_micros = (
            int(recurring_price["units"]) * 1_000_000
            + int(recurring_price.get("nanos", 0)) // 1000
        )
    except (KeyError, TypeError, ValueError):
        raise InvalidPurchase from None
    expected_micros = PLAY_PRODUCTS[item["productId"]]["price_minor"] * 10_000
    if (
        recurring_price.get("currencyCode") != "INR"
        or amount_micros != expected_micros
    ):
        raise InvalidPurchase
    return {
        "product_id": item["productId"],
        "status": status,
        "purchase_date": _parse_utc(response.get("startTime")),
        "expires_at": expires_at,
        "auto_renew_enabled": bool(
            auto_renewing.get("autoRenewEnabled")
            if isinstance(auto_renewing, dict)
            else False
        ),
        "acknowledgement_state": response.get("acknowledgementState", "unknown"),
        "linked_purchase_token": response.get("linkedPurchaseToken"),
        "obfuscated_account_id": (
            response.get("externalAccountIdentifiers", {}).get("obfuscatedExternalAccountId")
            if isinstance(response.get("externalAccountIdentifiers"), dict)
            else None
        ),
    }


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _obfuscated_profile_id(profile_id: str) -> str:
    return hashlib.sha256(profile_id.encode("utf-8")).hexdigest()


def _save_verified_subscription(
    profile: PlayerProfileModel,
    purchase_token: str,
    details: dict[str, Any],
    db: Session,
) -> SubscriptionModel:
    token_hash = _token_hash(purchase_token)
    record = db.query(SubscriptionModel).filter(
        SubscriptionModel.purchase_token_hash == token_hash
    ).first()
    if record is not None and record.profile_id != profile.id:
        raise HTTPException(status_code=409, detail="This purchase is already linked to another profile")

    linked_token = details.get("linked_purchase_token")
    if isinstance(linked_token, str) and linked_token and linked_token != purchase_token:
        linked_record = db.query(SubscriptionModel).filter(
            SubscriptionModel.purchase_token_hash == _token_hash(linked_token)
        ).first()
        if linked_record and linked_record.profile_id != profile.id:
            raise HTTPException(status_code=409, detail="This purchase is linked to another profile")
        if linked_record:
            linked_record.status = "replaced"
            linked_record.auto_renew_enabled = False

    cipher = _token_cipher()
    if cipher is None:
        raise HTTPException(status_code=503, detail="Google Play verification is not configured")
    encrypted_token = cipher.encrypt(purchase_token.encode("utf-8")).decode("ascii")
    if record is None:
        record = SubscriptionModel(
            profile_id=profile.id,
            product_id=details["product_id"],
            purchase_token_hash=token_hash,
            purchase_token_ciphertext=encrypted_token,
            status=details["status"],
            purchase_date=details["purchase_date"],
            expires_at=details["expires_at"],
            auto_renew_enabled=details["auto_renew_enabled"],
            acknowledgement_state=details["acknowledgement_state"],
            verification_status="verified",
            last_verified_at=get_utc_now(),
        )
        db.add(record)
    else:
        record.product_id = details["product_id"]
        record.purchase_token_ciphertext = encrypted_token
        record.status = details["status"]
        record.purchase_date = details["purchase_date"]
        record.expires_at = details["expires_at"]
        record.auto_renew_enabled = details["auto_renew_enabled"]
        record.acknowledgement_state = details["acknowledgement_state"]
        record.verification_status = "verified"
        record.last_verified_at = get_utc_now()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(SubscriptionModel).filter(
            SubscriptionModel.purchase_token_hash == token_hash
        ).first()
        if existing is None or existing.profile_id != profile.id:
            raise HTTPException(status_code=409, detail="This purchase is already linked to another profile")
        return existing
    db.refresh(record)
    return record


def _verify_and_store(
    profile: PlayerProfileModel,
    purchase_token: str,
    required_product_id: Optional[str],
    db: Session,
) -> Optional[SubscriptionModel]:
    response = _play_subscription(purchase_token)
    details = _subscription_details(response, required_product_id)
    external_account = details["obfuscated_account_id"]
    if external_account and not hmac.compare_digest(
        external_account, _obfuscated_profile_id(profile.id)
    ):
        raise HTTPException(status_code=409, detail="This Google Play purchase belongs to another profile")
    if details["status"] == "pending":
        return None
    if details["acknowledgement_state"] != "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED":
        _acknowledge_purchase(details["product_id"], purchase_token)
        details["acknowledgement_state"] = "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"
    return _save_verified_subscription(profile, purchase_token, details, db)


def _decrypt_purchase_token(record: SubscriptionModel) -> str:
    cipher = _token_cipher()
    if cipher is None:
        raise SubscriptionUnavailable
    try:
        return cipher.decrypt(record.purchase_token_ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError):
        logger.error("A stored Google Play purchase token could not be decrypted.")
        raise SubscriptionUnavailable from None


def _record_is_entitled(record: SubscriptionModel, now: datetime) -> bool:
    return (
        record.verification_status == "verified"
        and record.status in ENTITLED_STATES
        and record.acknowledgement_state == "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"
        and _database_utc(record.expires_at) > now
    )


def _refresh_subscription(
    profile: PlayerProfileModel,
    record: SubscriptionModel,
    db: Session,
) -> SubscriptionModel:
    token = _decrypt_purchase_token(record)
    try:
        refreshed = _verify_and_store(profile, token, record.product_id, db)
    except InvalidPurchase:
        record.status = "revoked"
        record.auto_renew_enabled = False
        record.last_verified_at = get_utc_now()
        db.commit()
        return record
    if refreshed is None:
        record.status = "pending"
        record.auto_renew_enabled = False
        db.commit()
        return record
    return refreshed


def _active_subscription(
    profile: PlayerProfileModel,
    db: Session,
    *,
    force_refresh: bool = False,
) -> Optional[SubscriptionModel]:
    if not billing_is_configured():
        raise HTTPException(status_code=503, detail="Google Play subscription verification is not configured")
    now = get_utc_now()
    records = db.query(SubscriptionModel).filter(
        SubscriptionModel.profile_id == profile.id,
        SubscriptionModel.verification_status == "verified",
        SubscriptionModel.expires_at > now.replace(tzinfo=None),
    ).order_by(
        SubscriptionModel.last_verified_at.desc(),
        SubscriptionModel.expires_at.desc(),
    ).all()
    for record in records:
        age = (now - _database_utc(record.last_verified_at)).total_seconds()
        if not force_refresh and age <= STATUS_REFRESH_SECONDS:
            if _record_is_entitled(record, now):
                return record
            continue
        record = _refresh_subscription(profile, record, db)
        if _record_is_entitled(record, get_utc_now()):
            return record
    return None


def _public_subscription(record: Optional[SubscriptionModel]) -> Optional[dict[str, Any]]:
    if record is None:
        return None
    return {
        "product_id": record.product_id,
        "status": record.status,
        "purchase_date": _database_utc(record.purchase_date).isoformat()
        if record.purchase_date else None,
        "expires_at": _database_utc(record.expires_at).isoformat(),
        "auto_renew_enabled": record.auto_renew_enabled,
        "verification_status": record.verification_status,
    }


def _profile_from_request(authorization: Optional[str], db: Session) -> PlayerProfileModel:
    profile = profile_from_authorization(authorization, db)
    if profile is None:
        raise HTTPException(status_code=401, detail="A device profile credential is required")
    return profile


def require_premium(
    profile: PlayerProfileModel,
    db: Session,
    *,
    force_refresh: bool = False,
) -> SubscriptionModel:
    record = _active_subscription(profile, db, force_refresh=force_refresh)
    if record is None:
        raise HTTPException(status_code=403, detail="An active FOURX Premium subscription is required")
    return record


def _ticket_encode(value: bytes) -> str:
    return _b64url_encode(value)


def _ticket_decode(value: str) -> bytes:
    return _b64url_decode(value)


def _create_spectator_ticket(profile: PlayerProfileModel) -> tuple[str, int]:
    expires_at = int(time.time()) + SPECTATOR_TICKET_SECONDS
    payload = _ticket_encode(json.dumps(
        {"sub": profile.id, "exp": expires_at},
        separators=(",", ":"),
    ).encode("utf-8"))
    signature = hmac.new(
        profile.token_hash.encode("ascii"), payload.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{payload}.{_ticket_encode(signature)}", expires_at


def validate_spectator_ticket(ticket: Optional[str], db: Session) -> PlayerProfileModel:
    try:
        payload_part, signature_part = (ticket or "").split(".", 1)
        payload = json.loads(_ticket_decode(payload_part))
        profile_id = payload["sub"]
        expires_at = int(payload["exp"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="A valid Premium spectator ticket is required") from None
    profile = db.query(PlayerProfileModel).filter(
        PlayerProfileModel.id == profile_id,
        PlayerProfileModel.is_suspended.is_(False),
        PlayerProfileModel.deleted_at.is_(None),
    ).first()
    if profile is None:
        raise HTTPException(status_code=401, detail="A valid Premium spectator ticket is required")
    expected = hmac.new(
        profile.token_hash.encode("ascii"), payload_part.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        supplied = _ticket_decode(signature_part)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="A valid Premium spectator ticket is required") from None
    if expires_at < int(time.time()) or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="A valid Premium spectator ticket is required")
    require_premium(profile, db)
    return profile


@router.get("/api/subscription/products")
def subscription_products():
    return {
        "configured": billing_is_configured(),
        "products": [
            {"product_id": product_id, **details}
            for product_id, details in PLAY_PRODUCTS.items()
        ],
    }


@router.get("/api/subscription/status")
def subscription_status(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _profile_from_request(authorization, db)
    if not billing_is_configured():
        return {
            "configured": False,
            "premium": False,
            "subscription": None,
        }
    record = _active_subscription(profile, db, force_refresh=True)
    return {
        "configured": True,
        "premium": record is not None,
        "subscription": _public_subscription(record),
    }


@router.post("/api/subscription/verify")
def verify_subscription(
    purchase: PurchaseVerification,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _profile_from_request(authorization, db)
    if purchase.product_id not in PLAY_PRODUCTS:
        raise HTTPException(status_code=422, detail="Unsupported Google Play subscription product")
    if not billing_is_configured():
        raise HTTPException(status_code=503, detail="Google Play subscription verification is not configured")
    try:
        record = _verify_and_store(
            profile, purchase.purchase_token, purchase.product_id, db
        )
    except InvalidPurchase:
        logger.warning("Google Play rejected a subscription verification request.")
        raise HTTPException(status_code=400, detail="Google Play could not verify this purchase") from None
    except SubscriptionUnavailable:
        raise HTTPException(status_code=503, detail="Google Play verification is temporarily unavailable") from None
    if record is None:
        return {"configured": True, "premium": False, "status": "pending", "subscription": None}
    return {
        "configured": True,
        "premium": _record_is_entitled(record, get_utc_now()),
        "status": record.status,
        "subscription": _public_subscription(record),
    }


@router.post("/api/subscription/spectator-ticket")
def spectator_ticket(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _profile_from_request(authorization, db)
    require_premium(profile, db)
    ticket, expires_at = _create_spectator_ticket(profile)
    return {"ticket": ticket, "expires_at": expires_at}


@router.post("/api/subscription/google-play/notifications")
async def google_play_notifications(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    audience = os.getenv("GOOGLE_PLAY_RTDN_AUDIENCE")
    expected_email = os.getenv("GOOGLE_PLAY_RTDN_SERVICE_ACCOUNT_EMAIL")
    if not audience or not expected_email:
        raise HTTPException(status_code=503, detail="Google Play notifications are not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Google Pub/Sub authorization is required")
    try:
        claims = _verify_google_oidc_token(authorization[7:], audience)
    except Exception:
        raise HTTPException(status_code=401, detail="Google Pub/Sub authorization is invalid") from None
    if claims.get("email") != expected_email or claims.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="Google Pub/Sub authorization is invalid")

    body = await request.body()
    if len(body) > 65536:
        raise HTTPException(status_code=413, detail="Notification payload is too large")
    try:
        envelope = json.loads(body)
        message = envelope["message"]
        message_id = str(message["messageId"])
        notification = json.loads(base64.b64decode(message["data"], validate=True))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid Google Play notification payload") from None
    if len(message_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid Google Play notification payload")
    if notification.get("packageName") != _package_name():
        raise HTTPException(status_code=400, detail="Notification package does not match FOURX")

    subscription_notification = notification.get("subscriptionNotification")
    notification_type = (
        str(subscription_notification.get("notificationType", "UNKNOWN"))
        if isinstance(subscription_notification, dict)
        else "TEST" if isinstance(notification.get("testNotification"), dict)
        else "UNKNOWN"
    )
    event = db.query(GooglePlayNotificationModel).filter(
        GooglePlayNotificationModel.message_id == message_id
    ).first()
    if event and event.processed_at:
        return {"ok": True, "duplicate": True}
    if event is None:
        event = GooglePlayNotificationModel(
            message_id=message_id,
            notification_type=notification_type,
        )
        db.add(event)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            event = db.query(GooglePlayNotificationModel).filter(
                GooglePlayNotificationModel.message_id == message_id
            ).first()
            if event and event.processed_at:
                return {"ok": True, "duplicate": True}
            if event is None:
                raise HTTPException(status_code=503, detail="Notification could not be recorded")

    try:
        if isinstance(subscription_notification, dict):
            purchase_token = subscription_notification.get("purchaseToken")
            if isinstance(purchase_token, str) and purchase_token:
                record = db.query(SubscriptionModel).filter(
                    SubscriptionModel.purchase_token_hash == _token_hash(purchase_token)
                ).first()
                if record:
                    profile = db.query(PlayerProfileModel).filter(
                        PlayerProfileModel.id == record.profile_id
                    ).first()
                    if profile:
                        try:
                            _refresh_subscription(profile, record, db)
                        except InvalidPurchase:
                            record.status = "revoked"
                            record.auto_renew_enabled = False
                            db.commit()
        event.processed_at = get_utc_now()
        db.commit()
    except SubscriptionUnavailable:
        db.rollback()
        logger.error("Google Play notification processing is temporarily unavailable.")
        raise HTTPException(status_code=503, detail="Notification processing is temporarily unavailable") from None
    return {"ok": True, "duplicate": False}


def _google_signing_certificates() -> dict[str, dict[str, str]]:
    global _google_certs_cache
    now = time.time()
    if _google_certs_cache and _google_certs_cache[0] > now:
        return _google_certs_cache[1]
    request = URLRequest("https://www.googleapis.com/oauth2/v3/certs")
    try:
        with urlopen(request, timeout=12) as response:
            data = json.loads(response.read())
            cache_control = response.headers.get("Cache-Control", "")
        max_age = 3600
        for directive in cache_control.split(","):
            directive = directive.strip()
            if directive.startswith("max-age="):
                max_age = max(60, min(int(directive[8:]), 86400))
        certificates = {
            entry["kid"]: entry for entry in data.get("keys", [])
            if entry.get("kty") == "RSA" and entry.get("alg") == "RS256"
        }
        if not certificates:
            raise ValueError("Google signing certificates were empty")
        _google_certs_cache = (now + max_age, certificates)
        return certificates
    except Exception as error:
        logger.error("Google Pub/Sub signing certificates could not be loaded.")
        raise SubscriptionUnavailable from error


def _verify_google_oidc_token(token: str, audience: str) -> dict[str, Any]:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed token")
    header = json.loads(_b64url_decode(parts[0]))
    claims = json.loads(_b64url_decode(parts[1]))
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise ValueError("Unsupported token signature")
    certificates = _google_signing_certificates()
    key_data = certificates.get(header["kid"])
    if key_data is None:
        global _google_certs_cache
        _google_certs_cache = None
        key_data = _google_signing_certificates().get(header["kid"])
    if key_data is None:
        raise ValueError("Unknown signing key")
    modulus = int.from_bytes(_b64url_decode(key_data["n"]), "big")
    exponent = int.from_bytes(_b64url_decode(key_data["e"]), "big")
    public_key = rsa.RSAPublicNumbers(exponent, modulus).public_key()
    public_key.verify(
        _b64url_decode(parts[2]),
        f"{parts[0]}.{parts[1]}".encode("ascii"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    current_time = int(time.time())
    token_audience = claims.get("aud")
    valid_audience = audience == token_audience or (
        isinstance(token_audience, list) and audience in token_audience
    )
    if (
        claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}
        or not valid_audience
        or int(claims.get("exp", 0)) <= current_time
        or int(claims.get("iat", current_time + 1)) > current_time + 60
    ):
        raise ValueError("Invalid token claims")
    return claims
