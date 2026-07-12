from dataclasses import dataclass
from typing import Dict

from src.constants import COLOR_MATCH_BONUS


@dataclass(frozen=True)
class Character:
    name: str
    base_damage: int
    hits: int
    crit_rate: float
    crit_bonus: float
    mp_cost: int
    color: str
    party_damage_buff: float = 0.0
    lepain_crit_buff: float = 0.0

    def expected_damage(
        self,
        common_damage_buff: float,
        party_damage_buff_total: float,
        lepain_crit_buff_total: float,
        stone_crit_buff: float,
        weakness_bonus_by_color: Dict[str, float],
    ) -> float:
        base = self.base_damage * self.hits

        dmg_mult = 1 + common_damage_buff + party_damage_buff_total

        if self.color in weakness_bonus_by_color:
            dmg_mult += COLOR_MATCH_BONUS

        dmg_mult += weakness_bonus_by_color.get(self.color, 0.0)

        if dmg_mult < 0:
            dmg_mult = 0.0

        if self.crit_rate <= 0:
            return base * dmg_mult

        crit_mult = 1 + self.crit_bonus + lepain_crit_buff_total + stone_crit_buff
        expected_mult = (1 - self.crit_rate) + self.crit_rate * crit_mult

        return base * expected_mult * dmg_mult


CHARACTER_DB: Dict[str, Character] = {
    "눈설탕": Character("눈설탕", 5640000, 5, 0.0, 0.0, 370, color="파랑"),
    "캡틴아이스": Character(
        "캡틴아이스",
        2025000,
        12,
        0.25,
        0.30,
        400,
        color="파랑",
        party_damage_buff=0.13,
    ),

    "스네이크": Character("스네이크", 2325000, 8, 0.0, 0.0, 260, color="노랑"),

    "인삼": Character("인삼", 4530000, 3, 0.0, 0.0, 170, color="빨강"),
    "비트": Character("비트", 1807500, 15, 0.20, 0.30, 400, color="빨강"),
    "레판": Character(
        "레판",
        8320000,
        3,
        0.20,
        0.30,
        400,
        color="빨강",
        lepain_crit_buff=0.35,
    ),
    "뱀파": Character("뱀파", 4462500, 4, 0.0, 0.0, 340, color="빨강"),
}