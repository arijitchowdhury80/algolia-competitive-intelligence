from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"


def test_daily_wrapper_declares_argus_delivery_identity():
    text = (SCRIPTS / "competitive-research-daily.sh").read_text()

    assert "Delivery status" in text
    assert "Operator: Argus generated and reviewed this CI run." in text
    assert "dedicated Argus Telegram gateway" in text
    assert "Athena role: supervisor only, not daily CI operator." in text


def test_weekly_wrapper_declares_argus_delivery_identity():
    text = (SCRIPTS / "competitive-research-weekly.sh").read_text()

    assert "Delivery status" in text
    assert "Operator: Argus generated and reviewed this CI run." in text
    assert "dedicated Argus Telegram gateway" in text
    assert "Athena role: supervisor only, not weekly CI operator." in text
