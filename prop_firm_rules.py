from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PropFirmRuleProfile:
    firm_name: str = "NOT CONFIRMED"
    account_model: str = "not confirmed"
    evaluation_stage: str = "not confirmed"
    restricted_event_impact_levels: tuple[str, ...] = ()
    restricted_currencies: tuple[str, ...] = ()
    restricted_instruments: tuple[str, ...] = ()
    no_trade_before_minutes: int | None = None
    no_trade_after_minutes: int | None = None
    restricted_actions: tuple[str, ...] = ()
    source_url: str = "RULE NOT VERIFIED"
    verified_on: str = "RULE NOT VERIFIED"
    verified: bool = False
    notes: str = "Official prop-firm restrictions must be checked directly before acting on any news-based rule."

    def to_message_block(self) -> str:
        if not self.verified:
            return (
                "Prop-firm news rule: RULE NOT VERIFIED. "
                "Check the current official rules for the exact firm/account model before using this reminder as a trading restriction."
            )

        actions = ", ".join(self.restricted_actions) if self.restricted_actions else "not specified"
        before = self.no_trade_before_minutes if self.no_trade_before_minutes is not None else "not specified"
        after = self.no_trade_after_minutes if self.no_trade_after_minutes is not None else "not specified"
        impact = ", ".join(self.restricted_event_impact_levels) if self.restricted_event_impact_levels else "not specified"

        return (
            f"Prop-firm rule: {self.firm_name} / {self.account_model} / {self.evaluation_stage}\n"
            f"Restricted impact: {impact}\n"
            f"Restricted instruments/currencies: {', '.join(self.restricted_instruments or self.restricted_currencies or ['not specified'])}\n"
            f"No-trade window: {before} min before and {after} min after release\n"
            f"Restricted actions: {actions}\n"
            f"Verified source: {self.source_url} (verified on {self.verified_on})"
        )


def get_default_prop_firm_rule_profile() -> PropFirmRuleProfile:
    return PropFirmRuleProfile()


def get_prop_firm_rule_profile_from_env() -> PropFirmRuleProfile:
    import os

    verified = os.getenv("PROP_FIRM_RULES_VERIFIED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if not verified:
        return get_default_prop_firm_rule_profile()

    def _split_csv(value: str | None) -> tuple[str, ...]:
        if not value:
            return ()
        return tuple(part.strip() for part in value.split(",") if part.strip())

    return PropFirmRuleProfile(
        firm_name=os.getenv("PROP_FIRM_NAME", "NOT CONFIRMED"),
        account_model=os.getenv("PROP_FIRM_ACCOUNT_MODEL", "not confirmed"),
        evaluation_stage=os.getenv("PROP_FIRM_STAGE", "not confirmed"),
        restricted_event_impact_levels=_split_csv(os.getenv("PROP_FIRM_RESTRICTED_IMPACT_LEVELS")),
        restricted_currencies=_split_csv(os.getenv("PROP_FIRM_RESTRICTED_CURRENCIES")),
        restricted_instruments=_split_csv(os.getenv("PROP_FIRM_RESTRICTED_INSTRUMENTS")),
        no_trade_before_minutes=int(os.getenv("PROP_FIRM_NO_TRADE_BEFORE_MINUTES", "0")) or None,
        no_trade_after_minutes=int(os.getenv("PROP_FIRM_NO_TRADE_AFTER_MINUTES", "0")) or None,
        restricted_actions=_split_csv(os.getenv("PROP_FIRM_RESTRICTED_ACTIONS")),
        source_url=os.getenv("PROP_FIRM_RULE_SOURCE_URL", "RULE NOT VERIFIED"),
        verified_on=os.getenv("PROP_FIRM_RULE_VERIFIED_ON", "RULE NOT VERIFIED"),
        verified=True,
    )
