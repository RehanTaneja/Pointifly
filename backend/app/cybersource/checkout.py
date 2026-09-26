"""Visa checkout for cash legs through the Cybersource Sandbox (Visa's payment gateway).

Sandbox only: it simulates the gateway and never moves money. The user's linked card isn't
charged; Cybersource's published Visa test card stands in for it. Authentication is JWT with a
shared secret (the SDK's recommended method; HTTP Signature is being deprecated).
Docs: https://developer.cybersource.com/hello-world/testing-guide.html

Keys in backend/.env: CYBERSOURCE_MERCHANT_ID, CYBERSOURCE_KEY_ID, CYBERSOURCE_SECRET_KEY.
"""

import json
from datetime import date

from ..sources.http import env

SANDBOX_HOST = "apitest.cybersource.com"
TEST_VISA = "4111111111111111"  # Cybersource's published sandbox test card, not a real card
# Legacy Cybersource-through-VisaNet test docs map whole-dollar amounts 7001-7145 to canned
# responses (e.g. declines). Real fares in that range may not authorize in the Sandbox.
TRIGGER_RANGE = (7001, 7145)

_PAID: dict[str, dict] = {}  # trip id -> result; one gateway call per trip per server run


class CheckoutError(Exception):
    pass


def configured() -> bool:
    return all(env(k) for k in ("CYBERSOURCE_MERCHANT_ID", "CYBERSOURCE_KEY_ID", "CYBERSOURCE_SECRET_KEY"))


def merchant_config() -> dict:
    return {
        "authentication_type": "JWT",
        "jwt_key_type": "SHARED_SECRET",
        "merchantid": env("CYBERSOURCE_MERCHANT_ID"),
        "merchant_keyid": env("CYBERSOURCE_KEY_ID"),
        "merchant_secretkey": env("CYBERSOURCE_SECRET_KEY"),
        "run_environment": SANDBOX_HOST,  # never production: no real payments in this project
        # No "log_config": the SDK's default keeps request logging off. (Passing a disabled
        # LogConfiguration crashes SDK 0.0.79 while it logs the config.)
    }


def payment_request(trip_id: str, amount_usd: float) -> dict:
    year = date.today().year + 3
    return {
        "clientReferenceInformation": {"code": f"pointifly-{trip_id}"[:50]},
        "processingInformation": {"capture": True},  # authorize and capture (a sale)
        "paymentInformation": {"card": {"number": TEST_VISA, "expirationMonth": "12", "expirationYear": str(year)}},
        "orderInformation": {
            "amountDetails": {"totalAmount": f"{amount_usd:.2f}", "currency": "USD"},
            # Sample billing details from Cybersource's own request examples (test data).
            "billTo": {
                "firstName": "John", "lastName": "Doe", "address1": "1 Market St", "locality": "san francisco",
                "administrativeArea": "CA", "postalCode": "94105", "country": "US", "email": "test@cybs.com",
            },
        },
    }


def _send(config: dict, body: dict) -> tuple[int, dict]:
    """One Cybersource REST call via the official SDK. Returns (HTTP status, response JSON)."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from CyberSource import PaymentsApi
        from CyberSource.rest import ApiException

    try:
        _data, status, raw = PaymentsApi(config).create_payment(json.dumps(body))
        return status, json.loads(raw)
    except ApiException as e:
        try:
            return e.status, json.loads(e.body)
        except (TypeError, ValueError):
            return e.status, {"message": str(e.body)[:300]}


def pay(trip_id: str, amount_usd: float) -> dict:
    """Authorize and capture a cash leg in the Cybersource Sandbox. Idempotent per trip."""
    if trip_id in _PAID:
        return {**_PAID[trip_id], "repeat": True}
    if not configured():
        raise CheckoutError("Cybersource is not configured: set CYBERSOURCE_* keys in backend/.env")
    if not 0 < amount_usd <= 20000:
        raise CheckoutError("Amount must be between $0 and $20,000")
    status, r = _send(merchant_config(), payment_request(trip_id, amount_usd))
    proc = r.get("processorInformation") or {}
    result = {
        "http_status": status,
        "status": r.get("status") or "ERROR",  # AUTHORIZED, DECLINED, INVALID_REQUEST, ...
        "id": r.get("id"),
        "reconciliation_id": r.get("reconciliationId"),
        "approval_code": proc.get("approvalCode"),
        "message": (r.get("errorInformation") or {}).get("message")
        or r.get("message")
        or (f"Cybersource returned HTTP {status}" + (": check the CYBERSOURCE_* keys" if status == 401 else "") if status >= 400 else None),
        "amount_usd": round(amount_usd, 2),
        "test_card_last4": TEST_VISA[-4:],
        "environment": "Cybersource Sandbox",
        "trigger_range_warning": TRIGGER_RANGE[0] <= amount_usd <= TRIGGER_RANGE[1],
    }
    if result["status"] in ("AUTHORIZED", "AUTHORIZED_PENDING_REVIEW"):
        _PAID[trip_id] = result
    return result
