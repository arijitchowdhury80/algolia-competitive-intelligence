from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"


def test_daily_wrapper_declares_argus_delivery_identity():
    text = (SCRIPTS / "competitive-research-daily.sh").read_text()

    assert "Argus daily pulse" in text
    assert "Generated and reviewed by Argus." in text
    assert "Athena supervises quality; she is not the daily operator." in text
    assert "Delivery status" not in text


def test_weekly_wrapper_declares_argus_delivery_identity():
    text = (SCRIPTS / "competitive-research-weekly.sh").read_text()

    assert "Argus weekly synthesis" in text
    assert "Generated and reviewed by Argus." in text
    assert "Athena supervises quality; she is not the weekly operator." in text
    assert "Delivery status" not in text
