from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE_ROOT / "scripts"


def test_daily_wrapper_declares_temporary_delivery_identity():
    text = (SCRIPTS / "competitive-research-daily.sh").read_text()

    assert "Delivery status" in text
    assert "Operator: Argus generated and reviewed this CI run." in text
    assert "temporary default Chowmes Telegram gateway" in text
    assert "dedicated Argus bot token/channel is configured" in text
    assert "Athena role: supervisor only, not daily CI operator." in text


def test_weekly_wrapper_declares_temporary_delivery_identity():
    text = (SCRIPTS / "competitive-research-weekly.sh").read_text()

    assert "Delivery status" in text
    assert "Operator: Argus generated and reviewed this CI run." in text
    assert "temporary default Chowmes Telegram gateway" in text
    assert "dedicated Argus bot token/channel is configured" in text
    assert "Athena role: supervisor only, not weekly CI operator." in text
