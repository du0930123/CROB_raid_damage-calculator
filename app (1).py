import streamlit as st
import math
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Character:
    name: str
    base_damage: int
    hits: int
    crit_rate: float
    crit_bonus: float
    mp_cost: int
    color: str  # "빨강" | "노랑" | "파랑"
    party_damage_buff: float = 0.0
    lepain_crit_buff: float = 0.0

    def expected_damage(
        self,
        common_damage_buff: float,        # 전원 공통(유틸/돌옵 등)
        conditional_damage_buff: float,   # 색/조건부(약점/석류 등)
        party_damage_buff: float,         # 캡틴 13% (최대 1회)
        lepain_crit_buff_total: float,    # 레판 35% (최대 1회)
        stone_crit_buff: float,           # 돌옵 치피
        boss_color: str,
        color_damage_bonus: float         # 색 일치 추가 피해증가(+30% 등)
    ) -> float:
        base = self.base_damage * self.hits

        is_match = (boss_color != "선택 안 함" and self.color == boss_color)

        # ✅ 피해증가율은 "합산" 규칙
        # - 전원 공통: common + party(캡틴)
        # - 색 일치 스킬만: + conditional(약점/석류 등) + color_damage_bonus
        dmg_mult = 1 + common_damage_buff + party_damage_buff
        if is_match:
            dmg_mult += conditional_damage_buff + color_damage_bonus

        # 치명타 기대값
        if self.crit_rate <= 0:
            return base * dmg_mult

        crit_mult = 1 + self.crit_bonus + lepain_crit_buff_total + stone_crit_buff
        expected_mult = (1 - self.crit_rate) + self.crit_rate * crit_mult

        return base * expected_mult * dmg_mult


CHARACTER_DB: Dict[str, Character] = {
    # 빨강
    "뱀파": Character("뱀파", 4462500, 4, 0.0, 0.0, 340, color="빨강"),
    "인삼": Character("인삼", 4530000, 3, 0.0, 0.0, 170, color="빨강"),
    "비트": Character("비트", 1807500, 15, 0.20, 0.30, 400, color="빨강"),
    "레판": Character("레판", 8320000, 3, 0.20, 0.30, 400, color="빨강", lepain_crit_buff=0.35),

    # 노랑
    "스네이크": Character("스네이크", 2325000, 8, 0.0, 0.0, 260, color="노랑"),

    # 파랑
    "눈설탕": Character("눈설탕", 5640000, 5, 0.0, 0.0, 370, color="파랑"),
    "캡틴아이스": Character("캡틴아이스", 2025000, 12, 0.25, 0.30, 400, color="파랑", party_damage_buff=0.13),
}


def build_party_from_text(text: str) -> List[Character]:
    tokens = text.split()
    if len(tokens) % 2 != 0:
        raise ValueError("파티 구성은 '이름 수량' 쌍이어야 합니다.")

    party: List[Character] = []
    for i in range(0, len(tokens), 2):
        name = tokens[i]
        cnt = int(tokens[i + 1])
        if name not in CHARACTER_DB:
            raise KeyError(f"알 수 없는 캐릭터: {name}")
        if cnt <= 0:
            continue
        party.extend([CHARACTER_DB[name]] * cnt)
    return party


def calculate_party(
    party: List[Character],
    common_damage_buff: float,
    conditional_damage_buff: float,
    stone_crit_buff: float,
    boss_color: str,
    color_damage_bonus: float
):
    # ✅ 중첩 금지: 각각 1번만
    party_damage_buff = max((c.party_damage_buff for c in party), default=0.0)
    lepain_crit_buff = max((c.lepain_crit_buff for c in party), default=0.0)

    total_damage = 0.0
    total_mp = 0

    for c in party:
        total_damage += c.expected_damage(
            common_damage_buff=common_damage_buff,
            conditional_damage_buff=conditional_damage_buff,
            party_damage_buff=party_damage_buff,
            lepain_crit_buff_total=lepain_crit_buff,
            stone_crit_buff=stone_crit_buff,
            boss_color=boss_color,
            color_damage_bonus=color_damage_bonus
        )
        total_mp += c.mp_cost

    eff = total_damage / total_mp if total_mp > 0 else 0.0
    return total_damage, eff, total_mp, party_damage_buff, lepain_crit_buff


# ============================
# Streamlit UI
# ============================
st.set_page_config(page_title="CROB 파티 딜 계산", page_icon="🧮")
st.title("🧮 쿠오븐 레이드파티 기대 딜량 계산")
st.caption("제작 : 카카오톡 오픈채팅방 쿠키런 only 레이드런방 - 오늘컨별로네")
st.markdown("---")
st.caption("입력 예: 비트 3 레판 1  |  이름과 수량을 공백으로 구분")
st.markdown("---")
st.caption("유틸 버프 종류 : 공주(+12%), 치어리더(+12%), 생케(+27%)")

tab1, tab2 = st.tabs(["단일 파티 계산", "파티 여러 개 비교"])


with tab1:
    with st.expander("사용 가능한 캐릭터 (색상 포함)", expanded=False):
        for color in ["빨강", "노랑", "파랑"]:
            names = [k for k, v in CHARACTER_DB.items() if v.color == color]
            st.write(f"- {color}: " + ", ".join(names))

    party_text = st.text_input("파티 구성", value="스네이크 3 캡틴아이스 1")

    colb1, colb2 = st.columns(2)
    with colb1:
        boss_color = st.selectbox("보스 색깔 선택", ["선택 안 함", "빨강", "노랑", "파랑"])
    with colb2:
        color_bonus_pct = st.number_input("색 일치 추가 피해증가율(%)", min_value=0.0, max_value=300.0, value=30.0, step=1.0)

    # ✅ 피해증가율 입력을 2개로 분리
    col1, col2 = st.columns(2)
    with col1:
        common_damage_buff_pct = st.number_input(
            "공통 피해증가율(%) (유틸/돌옵 등 전원 적용)",
            min_value=0.0, max_value=1000.0, value=67.0, step=1.0
        )
    with col2:
        conditional_damage_buff_pct = st.number_input(
            "색/조건부 피해증가율(%) (약점/석류 등 색 일치 스킬만)",
            min_value=0.0, max_value=1000.0, value=0.0, step=1.0
        )

    stone_crit_buff_pct = st.number_input(
        "돌옵션 중 치명타 피해 증가율 (%)",
        min_value=0.0, max_value=1000.0, value=67.0, step=1.0
    )

    use_boss_hp = st.checkbox("보스 체력 기준 계산")
    boss_hp = None
    if use_boss_hp:
        boss_hp = st.number_input("보스 체력", min_value=1.0, value=100_000_000.0, step=1_000_000.0, format="%.0f")

    if st.button("단일 파티 계산"):
        try:
            party = build_party_from_text(party_text)
            dmg, eff, mp, party_buff, lepain_buff = calculate_party(
                party=party,
                common_damage_buff=common_damage_buff_pct / 100.0,
                conditional_damage_buff=conditional_damage_buff_pct / 100.0,
                stone_crit_buff=stone_crit_buff_pct / 100.0,
                boss_color=boss_color,
                color_damage_bonus=color_bonus_pct / 100.0
            )

            st.subheader("적용 요약")
            st.write(f"- 보스 색깔: **{boss_color}**")
            st.write(f"- 색 일치 추가 피해증가율: **{color_bonus_pct:.0f}%** (색 일치 스킬만, 합산)")
            st.write(f"- 공통 피해증가율: **{common_damage_buff_pct:.0f}%** (전원 적용)")
            st.write(f"- 색/조건부 피해증가율: **{conditional_damage_buff_pct:.0f}%** (색 일치 스킬만)")
            st.write(f"- 캡틴아이스 피해증가: **{party_buff*100:.2f}%** (최대 1회)")
            st.write(f"- 레판 치명타 추가딜: **{lepain_buff*100:.2f}%** (최대 1회)")

            st.metric("스킬 1회 사용시 총 딜량(1사이클)", f"{dmg:,.0f}")
            st.metric("스킬에너지당 딜량", f"{eff:,.2f}")

            if use_boss_hp:
                cycles = math.ceil(boss_hp / dmg)
                st.write(f"- 필요 파티 사이클: **{cycles} 회**")
                st.caption(f"※ 다같이 스킬을 1번씩 사용하는 파티 사이클을 {cycles}회 반복해야 보스를 처치할 수 있다는 의미")
                st.write(f"- 예상 총 스킬에너지 소모: **{cycles * mp:,}**")

        except Exception as e:
            st.error(str(e))


with tab2:
    st.caption("파티를 한 줄에 하나씩 입력 (예: 비트 1 레판 4)")
    party_texts = st.text_area(
        "비교할 파티 목록",
        value="비트 1 레판 4\n비트 2 레판 2\n캡틴아이스 1 비트 2 레판 1\n뱀파 1 레판 4\n스네이크 3 캡틴아이스 1",
        height=150
    )

    colb1, colb2 = st.columns(2)
    with colb1:
        boss_color_cmp = st.selectbox("보스 색깔 선택 (비교 기준)", ["선택 안 함", "빨강", "노랑", "파랑"], key="boss_color_cmp")
    with colb2:
        color_bonus_pct_cmp = st.number_input("색 일치 추가 피해증가율(%) (비교 기준)", min_value=0.0, max_value=300.0, value=30.0, step=1.0, key="color_bonus_cmp")

    col1, col2 = st.columns(2)
    with col1:
        common_damage_buff_pct_cmp = st.number_input(
            "공통 피해증가율(%) (비교 기준)",
            min_value=0.0, max_value=1000.0, value=67.0, step=1.0,
            key="cmp_common"
        )
    with col2:
        conditional_damage_buff_pct_cmp = st.number_input(
            "색/조건부 피해증가율(%) (비교 기준)",
            min_value=0.0, max_value=1000.0, value=0.0, step=1.0,
            key="cmp_cond"
        )

    stone_crit_buff_pct_cmp = st.number_input(
        "돌옵션 중 치명타 피해 증가율 (%) (비교 기준)",
        min_value=0.0, max_value=1000.0, value=67.0, step=1.0,
        key="cmp_crit"
    )

    boss_hp_cmp = st.number_input("보스 체력 (비교 기준)", min_value=1.0, value=100_000_000.0, step=1_000_000.0, format="%.0f", key="cmp_hp")

    if st.button("파티 비교 실행"):
        rows = []
        for line in party_texts.splitlines():
            if not line.strip():
                continue
            try:
                party = build_party_from_text(line)
                dmg, eff, mp, _, _ = calculate_party(
                    party=party,
                    common_damage_buff=common_damage_buff_pct_cmp / 100.0,
                    conditional_damage_buff=conditional_damage_buff_pct_cmp / 100.0,
                    stone_crit_buff=stone_crit_buff_pct_cmp / 100.0,
                    boss_color=boss_color_cmp,
                    color_damage_bonus=color_bonus_pct_cmp / 100.0
                )
                cycles = math.ceil(boss_hp_cmp / dmg)
                rows.append({
                    "파티 구성": line,
                    "보스 색": boss_color_cmp,
                    "1사이클 총 딜량": int(dmg),
                    "MP당 딜량": round(eff, 2),
                    "필요 사이클 수": cycles,
                    "총 스킬에너지 소모": cycles * mp,
                })
            except Exception as e:
                rows.append({"파티 구성": line, "오류": str(e)})

        st.dataframe(rows, use_container_width=True)
