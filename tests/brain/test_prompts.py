"""Doctrine rule 1: not Algolia-specific. Zero Algolia vocabulary anywhere in
prompts/templates -- tenant name and context come only from input variables
(the DATA block built at runtime), never as hardcoded literals in the
prompt module."""

from __future__ import annotations

import cios.brain.prompts as prompts_module

# Every module-level string constant that becomes part of a prompt sent to
# the model. Kept as an explicit list (not introspected) so a newly added
# prompt constant that someone forgets to name here still gets caught by
# reviewing this file, and so the test fails loudly if a name here goes
# stale (typo-checked by getattr below).
_PROMPT_CONSTANT_NAMES = [
    "SYNTHESIS_SYSTEM",
    "SYNTHESIS_OUTPUT_CONTRACT",
    "REFUTE_SYSTEM",
    "CONTRADICTION_SYSTEM",
    "WEEKLY_SYNTHESIS_SYSTEM",
    "WEEKLY_OUTPUT_CONTRACT",
    "MONTHLY_SYNTHESIS_SYSTEM",
    "MONTHLY_OUTPUT_CONTRACT",
]


def test_all_prompt_constants_are_accounted_for() -> None:
    """Guards against silently missing a newly added prompt constant: every
    module-level all-caps string in prompts.py must appear in our list."""
    actual = {
        name
        for name, value in vars(prompts_module).items()
        if name.isupper() and isinstance(value, str)
    }
    assert actual == set(_PROMPT_CONSTANT_NAMES)


def test_no_algolia_literal_in_any_prompt_template() -> None:
    for name in _PROMPT_CONSTANT_NAMES:
        template = getattr(prompts_module, name)
        assert "algolia" not in template.lower(), f"{name} contains an Algolia literal"


def test_daily_synthesis_prompt_bans_uncited_intent_and_category_shift_claims() -> None:
    system_prompt = prompts_module.SYNTHESIS_SYSTEM.lower()

    assert "do not infer competitor intent" in system_prompt
    assert "do not say a company is trying to shift" in system_prompt
    assert "appears to position" in system_prompt

