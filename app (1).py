import streamlit as st
import math
from dataclasses import dataclass
from typing import Dict, List


# ============================
# 데이터 구조
# ============================
@dataclass(frozen=True)
class Character:
    name: str
    base_damage: int
    hits: int
    crit_rate: float
    crit_bonus: float
    mp_cost: int
    party_damage_buff: float = 0.0
    lepain_crit_buff: float = 0.0

    def expected_damage(
        self,
        total_party_damage_buff: float,
        lepain_crit_buff_total: float,
        stone_crit_buff: float
    ) -> float:

        base = self.base_damage * self.hits

        if self.crit_rate <= 0:
            return base * (1 + total_party_damage_buff)

        crit_mult = 1 + self.crit_bonus + lepain_crit_buff_total + stone_crit_buff
        expected_mult = (1 - self.crit_rate) + self.crit_rate * crit_mult

        return base * expected_mult * (1 + total_party_damage_buff)


# ============================
# 캐릭터 DB
# ============================
CHARACTER_DB: Dict[str, Character] = {
    "눈설탕": Character("눈설탕", 5640000, 5, 0.0, 0.0, 370),
    "스네이크": Character("스네이크", 2325000, 8, 0.0, 0.0, 260),
    "인삼": Character("인삼", 4530000, 3, 0.0, 0.0, 170),

    "비트": Character("비트", 1807500, 15, 0.20, 0.30, 400),
    "캡틴아이스": Character(
        "캡틴아이스", 2025000, 12, 0.25, 0.30, 400,
        party_damage_buff=0.13
    ),
    "레판": Character(
        "레판", 8320000, 3, 0.20, 0.30, 400,
        lepain_crit_buff=0.35
    ),

    # ✅ 추가 캐릭터: 뱀파
    # 스킬 1회당 4,462,500 공격을 4회 / MP 340
    # 치명타 정보가 없으므로 치명타 없는 스킬로 처리(crit_rate=0, crit_bonus=0)
    "뱀파": Character("뱀파", 4462500, 4, 0.0, 0.0, 340),
}


# ============================
# 파티 파싱
# ============================
def build_party_from_text(text: str) -> List[Character]:
    tokens = text.split()
    if len(tokens) % 2 != 0:
        raise ValueError("파티 구성은 '이름 수량' 쌍이어야 합니다.")

    party = []
    for i in range(0, len(tokens), 2):
        name = tokens[i]
        cnt = int(tokens[i + 1])
        if name not in CHARACTER_DB:
            raise KeyError(f"알 수 없는 캐릭터: {name}")
        party.extend([CHARACTER_DB[name]] * cnt)

    return party


# ============================
# 파티 계산
# ============================
def calculate_party(party, damage_buff, stone_crit_buff):
    party_damage_buff = max((c.party_damage_buff for c in party), default=0.0)
    lepain_crit_buff = max((c.lepain_crit_buff for c in party), default=0.0)

    total_party_damage_buff = damage_buff + party_damage_buff

    total_damage = 0.0
    total_mp = 0

    for c in party:
        total_damage += c.expected_damage(
            total_party_damage_buff,
            lepain_crit_buff,
            stone_crit_buff
        )
        total_mp += c.mp_cost

    eff = total_damage / total_mp if total_mp > 0 else 0.0
    return total_damage, eff, total_mp


# ============================
# Streamlit UI
# ============================
st.set_page_config(page_title="CROB 파티 딜 계산", page_icon="🧮")
st.title("🧮 쿠오븐 레이드파티 기대 딜량 계산")
st.caption("제작 : 카카오톡 오픈채팅방 쿠키런 only 레이드런방 - 오늘컨별로네")
st.markdown("---")
st.caption("입력 예: 비트 3 레판 1  |  이름과 수량을 공백으로 구분")
st.markdown("---")
st.caption("유틸 버프 종류 : 공주(+12%), 치어리더(+12%), 생케(+27%) ")

tab1, tab2 = st.tabs(["단일 파티 계산", "파티 여러 개 비교"])


# ============================
# 탭 1: 단일 파티
# ============================
with tab1:
    with st.expander("사용 가능한 캐릭터", expanded=False):
        st.write(", ".join(CHARACTER_DB.keys()))

    party_text = st.text_input("파티 구성", value="비트 1 레판 4")

    col1, col2 = st.columns(2)
    with col1:
        damage_buff_pct = st.number_input(
            "돌옵션 및 유틸버프들의 딜량증가율 + 약점(해당될 경우 +30%) + 석류 딜버프 증가율 (해당될 경우 +30%) (%)",
            min_value=0.0, max_value=1000.0, value=0.0
        )
    with col2:
        stone_crit_buff_pct = st.number_input(
            "돌옵션 중 치명타 피해 증가율 (%)",
            min_value=0.0, max_value=1000.0, value=25.0
        )

    use_boss_hp = st.checkbox("보스 체력 기준 계산")
    boss_hp = None
    if use_boss_hp:
        boss_hp = st.number_input(
            "보스 체력",
            min_value=1.0,
            value=100_000_000.0,
            step=1_000_000.0,
            format="%.0f"
        )

    if st.button("단일 파티 계산"):
        try:
            party = build_party_from_text(party_text)
            dmg, eff, mp = calculate_party(
                party,
                damage_buff_pct / 100,
                stone_crit_buff_pct / 100
            )

            st.metric("스킬 1회 사용시 총 딜량(1사이클)", f"{dmg:,.0f}")
            st.metric("스킬에너지당 딜량", f"{eff:,.2f}")

            if use_boss_hp:
                cycles = math.ceil(boss_hp / dmg)
                st.write(f"- 필요 파티 사이클: **{cycles} 회**")
                st.caption(f"※ 다같이 스킬을 1번씩 사용하는 파티 사이클을 {cycles}회 반복해야 보스를 처치할 수 있다는 의미")
                st.write(f"- 예상 총 스킬에너지 소모: **{cycles * mp:,}**")

        except Exception as e:
            st.error(str(e))


# ============================
# 탭 2: 파티 여러 개 비교
# ============================
with tab2:
    st.caption("파티를 한 줄에 하나씩 입력 (예: 비트 1 레판 4)")
    party_texts = st.text_area(
        "비교할 파티 목록",
        value="비트 1 레판 4\n비트 2 레판 2\n캡틴아이스 1 비트 2 레판 1\n뱀파 1 레판 4",
        height=150
    )

    col1, col2 = st.columns(2)
    with col1:
        damage_buff_pct = st.number_input(
            "돌옵션 및 유틸버프들의 딜량증가율 + 약점(해당될 경우 +30%) + 석류 딜버프 증가율(해당될 경우 +30%) (%) ",
            min_value=0.0, max_value=1000.0, value=0.0,
            key="cmp_dmg"
        )
    with col2:
        stone_crit_buff_pct = st.number_input(
            "돌옵션 중 치명타 피해 증가율 (%) ",
            min_value=0.0, max_value=1000.0, value=25.0,
            key="cmp_crit"
        )

    boss_hp = st.number_input(
        "보스 체력 (비교 기준)",
        min_value=1.0,
        value=100_000_000.0,
        step=1_000_000.0,
        format="%.0f"
    )

    if st.button("파티 비교 실행"):
        rows = []

        for line in party_texts.splitlines():
            if not line.strip():
                continue
            try:
                party = build_party_from_text(line)
                dmg, eff, mp = calculate_party(
                    party,
                    damage_buff_pct / 100,
                    stone_crit_buff_pct / 100
                )
                cycles = math.ceil(boss_hp / dmg)

                rows.append({
                    "파티 구성": line,
                    "스킬 1회 사용시 총 딜량 (1사이클)": int(dmg),
                    "스킬에너지당 딜량": round(eff, 2),
                    "필요 사이클 수": cycles,
                    "총 스킬에너지 소모": cycles * mp,
                })

            except Exception as e:
                rows.append({
                    "파티 구성": line,
                    "오류": str(e)
                })

        st.dataframe(rows, use_container_width=True)
