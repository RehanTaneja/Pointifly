from fastapi.testclient import TestClient

from app.cybersource import checkout
from app.main import app

api = TestClient(app)


def pay(**k):
    return api.post("/api/visa/checkout", json={"trip_id": "mia", "amount_usd": 127, "card_id": "chase_sapphire_preferred", **k})


def test_authorized_sale_through_sandbox(fake_cybersource):
    r = pay().json()
    assert r["status"] == "AUTHORIZED" and r["approval_code"] == "831000" and r["card"] == "Chase Sapphire Preferred"
    assert r["environment"] == "Cybersource Sandbox" and r["test_card_last4"] == "1111"
    body = fake_cybersource.requests[0]
    assert body["orderInformation"]["amountDetails"] == {"totalAmount": "127.00", "currency": "USD"}
    assert body["processingInformation"]["capture"] is True
    assert body["paymentInformation"]["card"]["number"] == checkout.TEST_VISA  # never a user's real card


def test_one_gateway_call_per_trip(fake_cybersource):
    pay(); second = pay().json()
    assert second["repeat"] is True and len(fake_cybersource.requests) == 1


def test_decline_is_reported_and_can_retry(fake_cybersource):
    fake_cybersource.response = (201, {"id": "1", "status": "DECLINED", "errorInformation": {"message": "Decline - General decline"}})
    r = pay().json()
    assert r["status"] == "DECLINED" and "General decline" in r["message"]
    pay()
    assert len(fake_cybersource.requests) == 2  # declines aren't cached


def test_http_error_surfaces(fake_cybersource):
    fake_cybersource.response = (401, {"message": "Authentication Failed"})
    r = pay().json()
    assert r["status"] == "ERROR" and r["http_status"] == 401 and "Authentication" in r["message"]


def test_non_visa_card_and_bad_amount_rejected(fake_cybersource):
    assert pay(card_id="amex_gold").status_code == 400
    assert pay(amount_usd=0).status_code == 400
    assert fake_cybersource.requests == []


def test_not_configured(monkeypatch, fake_cybersource):
    monkeypatch.setenv("CYBERSOURCE_SECRET_KEY", "")  # empty overrides the real backend/.env
    assert pay().status_code == 503 and fake_cybersource.requests == []


def test_trigger_range_flagged(fake_cybersource):
    assert pay(trip_id="big", amount_usd=7050).json()["trigger_range_warning"] is True
    assert pay(trip_id="ok", amount_usd=3884).json()["trigger_range_warning"] is False


def test_jwt_shared_secret_sandbox_config(monkeypatch):
    cfg = checkout.merchant_config()
    assert cfg["authentication_type"] == "JWT" and cfg["jwt_key_type"] == "SHARED_SECRET"
    assert cfg["run_environment"] == "apitest.cybersource.com"
    assert "log_config" not in cfg  # SDK default: request logging off


def test_bare_401_gets_a_helpful_message(fake_cybersource):
    fake_cybersource.response = (401, {})
    assert "check the CYBERSOURCE_* keys" in pay().json()["message"]


def test_network_failure_is_a_result_not_a_crash(fake_cybersource, monkeypatch):
    def boom(config, body):
        raise ConnectionError("down")

    monkeypatch.setattr(checkout, "_send", boom)
    r = pay()
    assert r.status_code == 200 and r.json()["authorized"] is False and "unreachable" in r.json()["message"]


def test_authorized_flag(fake_cybersource):
    assert pay().json()["authorized"] is True
    fake_cybersource.response = (502, {"status": "SERVER_ERROR", "message": "Error - General system failure."})
    r = pay(trip_id="other").json()
    assert r["authorized"] is False and r["status"] == "SERVER_ERROR"
