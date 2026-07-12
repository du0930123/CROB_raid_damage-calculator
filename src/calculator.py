import math
from typing import Dict, List

from src.characters import Character


def calculate_party(
    party: List[Character],
    common_damage_buff: float,
    stone_crit_buff: float,
    weakness_bonus_by_color: Dict[str, float],
    energy_decrease_by_color: Dict[str, float],
):
    party_damage_buff_total = max((c.party_damage_buff for c in party), default=0.0)
    lepain_crit_buff_total = max((c.lepain_crit_buff for c in party), default=0.0)

    total_damage = 0.0
    total_mp = 0
    total_dmg_per_mp_sum = 0.0
    detail: Dict[str, Dict[str, float]] = {}

    for c in party:
        dmg = c.expected_damage(
            common_damage_buff=common_damage_buff,
            party_damage_buff_total=party_damage_buff_total,
            lepain_crit_buff_total=lepain_crit_buff_total,
            stone_crit_buff=stone_crit_buff,
            weakness_bonus_by_color=weakness_bonus_by_color,
        )

        total_damage += dmg

        mp_mult = 1.0 + energy_decrease_by_color.get(c.color, 0.0)
        effective_mp = int(math.ceil(c.mp_cost * mp_mult)) if c.mp_cost > 0 else 0

        total_mp += effective_mp

        dmg_per_mp = (dmg / effective_mp) if effective_mp > 0 else 0.0
        total_dmg_per_mp_sum += dmg_per_mp

        if c.name not in detail:
            detail[c.name] = {
                "count": 0,
                "damage": 0.0,
                "mp": 0.0,
                "dmg_per_mp_sum": 0.0,
            }

        detail[c.name]["count"] += 1
        detail[c.name]["damage"] += dmg
        detail[c.name]["mp"] += effective_mp
        detail[c.name]["dmg_per_mp_sum"] += dmg_per_mp

    return (
        total_damage,
        total_dmg_per_mp_sum,
        total_mp,
        party_damage_buff_total,
        lepain_crit_buff_total,
        detail,
    )


def compute_async_dps_ratio(
    party: List[Character],
    common_damage_buff: float,
    stone_crit_buff: float,
    weakness_bonus_by_color: Dict[str, float],
    energy_decrease_by_color: Dict[str, float],
    game_speed_buff: float = 0.0,
    game_speed_alpha: float = 0.0,
) -> float:
    party_damage_buff_total = max((c.party_damage_buff for c in party), default=0.0)
    lepain_crit_buff_total = max((c.lepain_crit_buff for c in party), default=0.0)

    base_sum = 0.0
    eff_sum = 0.0

    for c in party:
        dmg = c.expected_damage(
            common_damage_buff=common_damage_buff,
            party_damage_buff_total=party_damage_buff_total,
            lepain_crit_buff_total=lepain_crit_buff_total,
            stone_crit_buff=stone_crit_buff,
            weakness_bonus_by_color=weakness_bonus_by_color,
        )

        base_mp = c.mp_cost if c.mp_cost > 0 else 0

        if base_mp > 0:
            base_sum += dmg / base_mp

        mp_mult = 1.0 + energy_decrease_by_color.get(c.color, 0.0)
        eff_mp = int(math.ceil(c.mp_cost * mp_mult)) if c.mp_cost > 0 else 0

        if eff_mp > 0:
            eff_sum += dmg / eff_mp

    if base_sum <= 0:
        return 1.0

    speed_mult = 1.0 + game_speed_alpha * game_speed_buff
    return (eff_sum * speed_mult) / base_sum


def compute_required_energy(boss_hp: float, total_dmg_per_mp_sum: float) -> float:
    if boss_hp <= 0:
        return 0.0

    if total_dmg_per_mp_sum <= 0:
        return float("inf")

    return boss_hp / total_dmg_per_mp_sum