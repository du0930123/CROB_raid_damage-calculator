# ↓↓↓ 이 아래에 Streamlit용 전체 코드 붙여넣기 ↓↓↓

import streamlit as st
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Character:
    name: str
    base_damage: int   # 1타 기본딜
    hits: int          # 타수
    crit_rate: float   # 치명타 확률 (0~1)
    crit_bonus: float  # 치명타 추가딜 (예: 0.30 = +30%)
    mp_cost: int
    party_damage_buff: float = 0.0  # 파티 전체 피해증가 버프(예: 캡틴아이스 0.13)
    lepain_crit_buff: float = 0.0   # 레판: "치명타 추가딜" 보너스(예: 0.35)

    def expected_damage(
        self,
        total_party_damage_buff: float,
        lepain_crit_buff_total: float,
        stone_crit_buff: float
    ) -> float:
        """
        치명타 배율:
          crit_mult = 1 + crit_bonus + lepain + stone_crit
          E[mult] = (1-cr)*1 + cr*crit_mult
        """
        base = self.base_damage * self.hits

        # 치명타가 없는 스킬이면(치확 0) 레판/돌옵션 치피는 의미 없음
        if self.crit_rate <= 0:
            return base * (1 + total_party_damage_buff)

        crit_mult = 1 + self.crit_bonus + lepain_crit_buff_total + stone_crit_buff
        expected_mult = (1 - self.crit_rate) * 1 + self.crit_rate * crit_mult

        return base * expected_mult * (1 + total_party_damage_buff)


# ----------------------------
# 캐릭터 DB
# ----------------------------
CHARACTER_DB: Dict[str, Character] = {
    "눈설탕": Character("눈설탕", 5640000, 5, 0.0, 0.0, 370),
    "스네이크": Character("스네이크", 2325000, 8, 0.0, 0.0, 260),
    "인삼": Character("인삼", 4530000, 3, 0.0, 0.0, 170),

    "비트": Character("비트", 1807500, 15, 0.20, 0.30, 400),
    "캡틴아이스": Character("캡틴아이스", 2025000, 12, 0.25, 0.30, 400,
                          party_damage_buff=0.13),

    "레판": Character("레판", 8320000, 3, 0.20, 0.30, 400,
                    lepain_crit_buff=0.35),
}


def build_party_from_input(tokens: List[str]) -> List[Character]:
    """
    입력 예: ["비트","3","레판","1"]
    """
    if len(tokens) % 2 != 0:
        raise ValueError("파티 구성 입력은 '이름 수량' 쌍으로 입력해야 합니다. 예) 비트 3 레판 1")

    party: List[Character] = []
    for i in range(0, len(tokens), 2):
        name = tokens[i]
        try:
            cnt = int(tokens[i + 1])
        except ValueError:
            raise ValueError(f"수량은 정수여야 합니다: {tokens[i + 1]}")

        if name not in CHARACTER_DB:
            raise KeyError(f"알 수 없는 캐릭터: {name} / 사용 가능: {', '.join(CHARACTER_DB.keys())}")

        if cnt <= 0:
            continue

        party.extend([CHARACTER_DB[name]] * cnt)

    return party


def calculate_party(
    party: List[Character],
    damage_buff: float,
    stone_crit_buff: float
) -> Tuple[Dict[str, Dict[str, float]], float, float, int, float, float]:
    """
    damage_buff: 돌옵션 제외 피해증가율(예: 0.20)
    stone_crit_buff: 돌옵션 치명타 피해증가율(예: 0.25)
    """

    # ✅ 중첩 금지: 각각 1번만 적용
    party_damage_buff_total = max((c.party_damage_buff for c in party), default=0.0)
    lepain_crit_buff_total = max((c.lepain_crit_buff for c in party), default=0.0)

    total_party_damage_buff = damage_buff + party_damage_buff_total

    total_damage = 0.0
    total_mp = 0
    result: Dict[str, Dict[str, float]] = {}

    for c in party:
        dmg = c.expected_damage(
            total_party_damage_buff=total_party_damage_buff,
            lepain_crit_buff_total=lepain_crit_buff_total,
            stone_crit_buff=stone_crit_buff
        )
        if c.name not in result:
            result[c.name] = {"count": 0, "damage": 0.0, "mp": 0.0}
        result[c.name]["count"] += 1
        result[c.name]["damage"] += dmg
        result[c.name]["mp"] += c.mp_cost

        total_damage += dmg
        total_mp += c.mp_cost

    total_dmg_per_mp = total_damage / total_mp if total_mp > 0 else 0.0

    for name, v in result.items():
        v["dmg_per_mp"] = (v["damage"] / v["mp"]) if v["mp"] > 0 else 0.0

    return result, total_damage, total_dmg_per_mp, total_mp, party_damage_buff_total, lepain_crit_buff_total


# ----------------------------
# Streamlit UI
# ----------------------------
st.set_page_config(page_title="파티 기대 딜 계산기", page_icon="🧮", layout="centered")
st.title("🧮 파티 기대 딜 계산기")
st.caption("입력 예: 비트 3 레판 1  |  이름과 수량을 공백으로 구분")

with st.expander("사용 가능한 캐릭터", expanded=False):
    st.write(", ".join(CHARACTER_DB.keys()))

party_text = st.text_input("파티 구성", value="비트 1 레판 4")

col1, col2 = st.columns(2)
with col1:
    damage_buff_pct = st.number_input("돌옵션의 딜량증가율 + 약점(해당될 경우 +30%) + 석류 딜버프 증가율 (해당될 경우 +30%)", min_value=0.0, max_value=1000.0, value=0.0, step=1.0)
with col2:
    stone_crit_buff_pct = st.number_input("돌옵션 중 치명타 피해 증가율 (%)", min_value=0.0, max_value=1000.0, value=25.0, step=1.0)

run = st.button("계산하기", type="primary")

if run:
    tokens = party_text.split()

    try:
        party = build_party_from_input(tokens)

        if len(party) == 0:
            st.warning("파티가 비어 있어요. 예) 비트 3 레판 1")
        else:
            damage_buff = damage_buff_pct / 100.0
            stone_crit_buff = stone_crit_buff_pct / 100.0

            res, total, eff, total_mp, party_buff_total, lepain_buff_total = calculate_party(
                party=party,
                damage_buff=damage_buff,
                stone_crit_buff=stone_crit_buff
            )

            st.subheader("버프 적용 요약")
            st.write(f"- 캡틴아이스 파티 피해증가 적용: **{party_buff_total*100:.2f}%** (최대 1회)")
            st.write(f"- 레판 치명타 추가딜 적용: **{lepain_buff_total*100:.2f}%** (최대 1회)")
            st.write(f"- 돌옵션 + 약점(해당될 경우 30%) + 석류(해당될 경우30%) 피해증가율: **{damage_buff_pct:.2f}%**")
            st.write(f"- 돌옵션 치명타 피해증가율: **{stone_crit_buff_pct:.2f}%**")

            st.subheader("결과(기대값)")
            st.write(f"- 총 요구 스킬에너지: **{total_mp}**")

            rows = []
            for name, v in res.items():
                rows.append({
                    "캐릭터": name,
                    "수량": int(v["count"]),
                    "총딜(기대값)": int(round(v["damage"])),
                    "총요구스킬에너지": int(v["mp"]),
                    "스킬에너지당 딜량": float(f"{v['dmg_per_mp']:.2f}"),
                })

            st.dataframe(rows, use_container_width=True)

            st.markdown("---")
            st.metric("스킬 1회 사용시 총 딜량(기대값)", f"{total:,.0f}")
            st.metric("스킬에너지당 총 딜량", f"{eff:,.2f}")

    except (ValueError, KeyError) as e:
        st.error(str(e))
