import math
from typing import Dict, List, Optional

from src.characters import Character
from src.stones import combine_energy_color_effect, job_damage_bonus_for_instance
from src.jobs import job_speed_ratio_for_instance


def calculate_party(
    party: List[Character],
    common_damage_buff: float,
    stone_crit_buff: float,
    weakness_bonus_by_color: Dict[str, float],
    energy_decrease_by_color: Dict[str, float],
    energy_increase_by_color: Optional[Dict[str, float]] = None,
    job_per_instance: Optional[List[Optional[str]]] = None,
    job_damage_buff_by_job: Optional[Dict[str, float]] = None,
):
    energy_increase_by_color = energy_increase_by_color or {}
    job_per_instance = job_per_instance if job_per_instance is not None else [None] * len(party)
    job_damage_buff_by_job = job_damage_buff_by_job or {}

    party_damage_buff_total = max((c.party_damage_buff for c in party), default=0.0)
    lepain_crit_buff_total = max((c.lepain_crit_buff for c in party), default=0.0)

    total_damage = 0.0
    total_mp = 0
    total_dmg_per_mp_sum = 0.0
    detail: Dict[str, Dict[str, float]] = {}

    for i, c in enumerate(party):
        extra_dmg_bonus = job_damage_bonus_for_instance(
            index=i,
            job_per_instance=job_per_instance,
            job_damage_buff_by_job=job_damage_buff_by_job,
        )

        dmg = c.expected_damage(
            common_damage_buff=common_damage_buff,
            party_damage_buff_total=party_damage_buff_total,
            lepain_crit_buff_total=lepain_crit_buff_total,
            stone_crit_buff=stone_crit_buff,
            weakness_bonus_by_color=weakness_bonus_by_color,
            extra_dmg_bonus=extra_dmg_bonus,
        )

        total_damage += dmg

        mp_mult = 1.0 + combine_energy_color_effect(
            c.color, energy_decrease_by_color, energy_increase_by_color
        )
        mp_mult = max(0.0, mp_mult)
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
    energy_increase_by_color: Optional[Dict[str, float]] = None,
    job_per_instance: Optional[List[Optional[str]]] = None,
    job_damage_buff_by_job: Optional[Dict[str, float]] = None,
    job_energy_alpha: float = 1.0,
    job_energy_alpha_by_job: Optional[Dict[str, float]] = None,
    jelly_pickups_per_cycle: Optional[float] = None,
    seconds_per_cycle: Optional[float] = None,
) -> float:
    energy_increase_by_color = energy_increase_by_color or {}
    job_per_instance = job_per_instance if job_per_instance is not None else [None] * len(party)
    job_damage_buff_by_job = job_damage_buff_by_job or {}

    party_damage_buff_total = max((c.party_damage_buff for c in party), default=0.0)
    lepain_crit_buff_total = max((c.lepain_crit_buff for c in party), default=0.0)

    base_sum = 0.0
    eff_sum = 0.0

    for i, c in enumerate(party):
        extra_dmg_bonus = job_damage_bonus_for_instance(
            index=i,
            job_per_instance=job_per_instance,
            job_damage_buff_by_job=job_damage_buff_by_job,
        )

        dmg = c.expected_damage(
            common_damage_buff=common_damage_buff,
            party_damage_buff_total=party_damage_buff_total,
            lepain_crit_buff_total=lepain_crit_buff_total,
            stone_crit_buff=stone_crit_buff,
            weakness_bonus_by_color=weakness_bonus_by_color,
            extra_dmg_bonus=extra_dmg_bonus,
        )

        base_mp = c.mp_cost if c.mp_cost > 0 else 0

        if base_mp > 0:
            base_sum += dmg / base_mp

        mp_mult = 1.0 + combine_energy_color_effect(
            c.color, energy_decrease_by_color, energy_increase_by_color
        )
        mp_mult = max(0.0, mp_mult)
        eff_mp = int(math.ceil(c.mp_cost * mp_mult)) if c.mp_cost > 0 else 0

        if eff_mp > 0:
            # ✅ 직업 에너지 보너스는 "이 캐릭터 한 명"에게만 적용 (파티 전체에 뭉뚱그려 곱하지 않음)
            job_speed_ratio = job_speed_ratio_for_instance(
                index=i,
                job_per_instance=job_per_instance,
                job_energy_alpha=job_energy_alpha,
                job_energy_alpha_by_job=job_energy_alpha_by_job,
                jelly_pickups_per_cycle=jelly_pickups_per_cycle,
                seconds_per_cycle=seconds_per_cycle,
            )
            eff_sum += (dmg / eff_mp) * job_speed_ratio

    if base_sum <= 0:
        return 1.0

    # ✅ 게임속도 버프만 파티 전체에 균일하게 곱함 (전원이 동시에 빨라지는 효과이므로)
    game_speed_mult = 1.0 + game_speed_alpha * game_speed_buff
    return (eff_sum * game_speed_mult) / base_sum


def compute_required_energy(boss_hp: float, total_dmg_per_mp_sum: float) -> float:
    if boss_hp <= 0:
        return 0.0

    if total_dmg_per_mp_sum <= 0:
        return float("inf")

    return boss_hp / total_dmg_per_mp_sum
