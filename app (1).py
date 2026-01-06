import streamlit as st
import math
from dataclasses import dataclass
from typing import Dict, List


# ============================
# 고정 규칙
# ============================
COLOR_MATCH_BONUS = 0.30  # 약점으로 선택된 색 스킬은 항상 +30% (자동 적용)
COLOR_OPTIONS = ["빨강", "노랑", "파랑"]


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
    color: str
    party_damage_buff: float = 0.0  # 캡틴아이스 등 (파티 전체 피해증가, 최대 1회)
    lepain_crit_buff: float = 0.0   # 레판 (치명타 추가딜, 최대 1회)

    def expected_damage(
        self,
        common_damage_buff: float,              # 전원 공통 피해증가율(0~)
        party_damage_buff_total: float,         # 캡틴 피해증가(최대 1회, 본인 포함)
        lepain_crit_buff_total: float,          # 레판 치명타 추가딜(최대 1회)
        stone_crit_buff: float,                 # 돌옵 치피(치명타에만 적용)
        weakness_bonus_by_color: Dict[str, float],  # 약점 색별 조건부 피해증가율(음수 가능)
    ) -> float:
        base = self.base_damage * self.hits

        # ✅ 피해증가율은 전부 "합산"해서 한 번만 곱함
        dmg_mult = 1 + common_damage_buff + party_damage_buff_total

        # ✅ 약점 색으로 선택된 색 스킬이면 고정 +30%
        if self.color in weakness_bonus_by_color:
            dmg_mult += COLOR_MATCH_BONUS

        # ✅ 약점 색별 조건부 피해증가율(색마다 다르게, 음수 가능)
        dmg_mult += weakness_bonus_by_color.get(self.color, 0.0)

        # ✅ 피해배율이 음수가 되면 딜이 말이 안 되므로 0으로 클램프
        if dmg_mult < 0:
            dmg_mult = 0.0

        # 치명타 기대값
        if self.crit_rate <= 0:
            return base * dmg_mult

        # ✅ 치명타 배율도 합산: 1 + crit_bonus + lepain + stone_crit
        crit_mult = 1 + self.crit_bonus + lepain_crit_buff_total + stone_crit_buff
        expected_mult = (1 - self.crit_rate) + self.crit_rate * crit_mult

        return base * expected_mult * dmg_mult


# ============================
# 캐릭터 DB
# ============================
CHARACTER_DB: Dict[str, Character] = {
    # 파랑
    "눈설탕": Character("눈설탕", 5640000, 5, 0.0, 0.0, 370, color="파랑"),
    "캡틴아이스": Character("캡틴아이스", 2025000, 12, 0.25, 0.30, 400, color="파랑",
                          party_damage_buff=0.13),

    # 노랑
    "스네이크": Character("스네이크", 2325000, 8, 0.0, 0.0, 260, color="노랑"),

    # 빨강
    "인삼": Character("인삼", 4530000, 3, 0.0, 0.0, 170, color="빨강"),
    "비트": Character("비트", 1807500, 15, 0.20, 0.30, 400, color="빨강"),
    "레판": Character("레판", 8320000, 3, 0.20, 0.30, 400, color="빨강",
                    lepain_crit_buff=0.35),
    "뱀파": Character("뱀파", 4462500, 4, 0.0, 0.0, 340, color="빨강"),
}


# ============================
# 파티 파싱
# ============================
def build_party_from_text(text: str) -> List[Character]:
    tokens = text.split()
    if len(tokens) % 2 != 0:
        raise ValueError("파티 구성은 '이름 수량' 쌍이어야 합니다. 예) 비트 3 레판 1")

    party: List[Character] = []
    for i in range(0, len(tokens), 2):
        name = tokens[i]
        cnt = int(tokens[i + 1])

        if name not in CHARACTER_DB:
            raise KeyError(f"알 수 없는 캐릭터: {name} / 사용 가능: {', '.join(CHARACTER_DB.keys())}")

        if cnt <= 0:
            continue

        party.extend([CHARACTER_DB[name]] * cnt)

    return party


# ============================
# 파티 계산
# ============================
def calculate_party(
    party: List[Character],
    common_damage_buff: float,
    stone_crit_buff: float,
    weakness_bonus_by_color: Dict[str, float],
):
    # ✅ 중첩 금지: 각각 1회만 적용 (최대값 1개만)
    party_damage_buff_total = max((c.party_damage_buff for c in party), default=0.0)
    lepain_crit_buff_total = max((c.lepain_crit_buff for c in party), default=0.0)

    total_damage = 0.0
    total_mp = 0

    # ✅ 너가 원하는 "총 단위스킬에너지당 딜량" 계산:
    #    각 스킬(캐릭터)별 (딜량 / 해당 MP) 를 계산해서 합산
    total_dmg_per_mp_sum = 0.0

    # (표시에 쓸) 캐릭터별 합산
    detail: Dict[str, Dict[str, float]] = {}

    for c in party:
        dmg = c.expected_damage(
            common_damage_buff=common_damage_buff,
            party_damage_buff_total=party_damage_buff_total,
            lepain_crit_buff_total=lepain_crit_buff_total,
            stone_crit_buff=stone_crit_buff,
            weakness_bonus_by_color=weakness_bonus_by_color
        )

        total_damage += dmg
        total_mp += c.mp_cost

        dmg_per_mp = (dmg / c.mp_cost) if c.mp_cost > 0 else 0.0
        total_dmg_per_mp_sum += dmg_per_mp

        if c.name not in detail:
            detail[c.name] = {"count": 0, "damage": 0.0, "mp": 0.0, "dmg_per_mp_sum": 0.0}
        detail[c.name]["count"] += 1
        detail[c.name]["damage"] += dmg
        detail[c.name]["mp"] += c.mp_cost
        detail[c.name]["dmg_per_mp_sum"] += dmg_per_mp

    return (
        total_damage,
        total_dmg_per_mp_sum,
        total_mp,
        party_damage_buff_total,
        lepain_crit_buff_total,
        detail
    )


# ============================
# Streamlit UI
# ============================
st.set_page_config(page_title="CROB 파티 딜 계산", page_icon="🧮")
st.title("🧮 쿠오븐 레이드파티 기대 딜량 계산")
st.markdown("<hr style='margin: 6px 0;'>", unsafe_allow_html=True)
st.caption("입력 예: 비트 3 레판 1  |  이름과 수량을 공백으로 구분")
st.markdown("<hr style='margin: 6px 0;'>", unsafe_allow_html=True)
st.caption("유틸 버프 종류 : 공주(+12%), 치어리더(+12%), 생케(+27%), 석류(+30%)")
st.caption("약점으로 선택된 색 스킬: (1 + 공통 + 캡틴 + 0.30 + 약점조건부)로 합산 적용")
st.caption("비약점 색 스킬: (1 + 공통 + 캡틴)만 적용")
st.caption("※ 약점 조건부 피해증가율은 음수도 가능(딜 감소). 예: -20% 입력 가능")
st.caption("※ '총 스킬에너지당 딜량' = Σ(각 스킬 딜량/각 스킬 에너지) 로 계산")

tab1, tab2 = st.tabs(["단일 파티 계산", "파티 여러 개 비교"])


# ============================
# 탭 1: 단일 파티
# ============================
with tab1:
    with st.expander("사용 가능한 캐릭터 (색상 포함)", expanded=False):
        for color in ["빨강", "노랑", "파랑"]:
            names = [k for k, v in CHARACTER_DB.items() if v.color == color]
            st.write(f"- {color}: " + ", ".join(names))

    party_text = st.text_input("파티 구성", value="스네이크 3 캡틴아이스 1")

    weakness_colors = st.multiselect("보스 약점 색 선택 (최대 2개)", options=COLOR_OPTIONS, default=[])
    if len(weakness_colors) > 2:
        st.error("약점은 최대 2개까지만 선택할 수 있어.")
        weakness_colors = weakness_colors[:2]

    weakness_bonus_by_color: Dict[str, float] = {}
    if weakness_colors:
        st.markdown("#### 약점 색별 조건부 피해증가율(%) 입력")
        for wc in weakness_colors:
            pct = st.number_input(
                f"돌 옵션 : {wc} 색깔만의 피해증감율(%)",
                min_value=-300.0, max_value=300.0, value=0.0, step=1.0,
                key=f"weak_{wc}"
            )
            weakness_bonus_by_color[wc] = pct / 100.0

    col1, col2 = st.columns(2)
    with col1:
        common_damage_buff_pct = st.number_input(
            "공통 피해증가율(%) (ex : 유틸버프, 쿠키가주는피해량증가)",
            min_value=0.0, max_value=1000.0, value=67.0, step=1.0
        )
    with col2:
        stone_crit_buff_pct = st.number_input(
            "돌옵션 : 치명타 피해 증가율(%)",
            min_value=0.0, max_value=1000.0, value=67.0, step=1.0
        )

    use_boss_hp = st.checkbox("보스 체력 기준 계산")
    boss_hp = None
    if use_boss_hp:
        boss_hp = st.number_input("보스 체력", min_value=1.0, value=100_000_000.0, step=1_000_000.0, format="%.0f")

    if st.button("단일 파티 계산"):
        try:
            party = build_party_from_text(party_text)

            total_dmg, total_dmg_per_mp_sum, total_mp, party_buff, lepain_buff, detail = calculate_party(
                party=party,
                common_damage_buff=common_damage_buff_pct / 100.0,
                stone_crit_buff=stone_crit_buff_pct / 100.0,
                weakness_bonus_by_color=weakness_bonus_by_color
            )

            st.subheader("적용 요약")
            if weakness_bonus_by_color:
                pretty = ", ".join([f"{k}(+30% 고정 + {v*100:+.0f}%)" for k, v in weakness_bonus_by_color.items()])
                st.write(f"- 약점 적용: **{pretty}**")
            else:
                st.write("- 약점 적용: **없음**")

            st.write(f"- 공통 피해증가율: **{common_damage_buff_pct:.0f}%** (전원 적용)")
            st.write(f"- 캡틴아이스 피해증가: **{party_buff*100:.2f}%** (최대 1회)")
            st.write(f"- 레판 치명타 추가딜: **{lepain_buff*100:.2f}%** (최대 1회)")

            st.metric("스킬 1회 사용시 총 딜량(1사이클)", f"{total_dmg:,.0f}")
            st.metric("총 스킬에너지당 딜량 (Σ(각 딜/각 스킬에너지))", f"{total_dmg_per_mp_sum:,.2f}")

            st.caption("캐릭터별 합산(참고)")
            rows = []
            for name, v in detail.items():
                rows.append({
                    "캐릭터": name,
                    "수량": int(v["count"]),
                    "총딜(기대값)": int(round(v["damage"])),
                    "총스킬에너지": int(v["mp"]),
                    "합산(각 딜/각 스킬에너지)": float(f"{v['dmg_per_mp_sum']:.2f}")
                })
            st.dataframe(rows, use_container_width=True)

            if use_boss_hp:
                cycles = math.ceil(boss_hp / total_dmg) if total_dmg > 0 else 0
                st.write(f"- 필요 파티 사이클: **{cycles} 회**")
                st.caption(f"※ 다같이 스킬을 1번씩 사용하는 파티 사이클을 {cycles}회 반복해야 보스를 처치할 수 있다는 의미")
                st.write(f"- 예상 총 스킬에너지 소모: **{cycles * total_mp:,}**")

        except Exception as e:
            st.error(str(e))


# ============================
# 탭 2: 파티 여러 개 비교
# ============================
with tab2:
    st.caption("파티를 한 줄에 하나씩 입력 (예: 비트 1 레판 4)")
    party_texts = st.text_area(
        "비교할 파티 목록",
        value="비트 1 레판 4\n비트 2 레판 2\n캡틴아이스 1 비트 2 레판 1\n뱀파 1 레판 4\n스네이크 3 캡틴아이스 1",
        height=160
    )

    weakness_colors_cmp = st.multiselect(
        "보스 약점 색 선택 (비교 기준, 최대 2개)",
        options=COLOR_OPTIONS,
        default=["노랑"],
        key="weakness_cmp"
    )
    if len(weakness_colors_cmp) > 2:
        st.error("약점은 최대 2개까지만 선택할 수 있어.")
        weakness_colors_cmp = weakness_colors_cmp[:2]

    weakness_bonus_by_color_cmp: Dict[str, float] = {}
    if weakness_colors_cmp:
        st.markdown("#### (비교) 약점 색별 조건부 피해증가율(%) 입력")
        for wc in weakness_colors_cmp:
            pct = st.number_input(
                f"돌옵션 : {wc} 색깔만의 피해량 증감율(%)",
                min_value=-300.0, max_value=300.0, value=0.0, step=1.0,
                key=f"cmp_weak_{wc}"
            )
            weakness_bonus_by_color_cmp[wc] = pct / 100.0

    col1, col2 = st.columns(2)
    with col1:
        common_damage_buff_pct_cmp = st.number_input(
            "공통 피해증가율(%) (ex : 유틸버프, 쿠주피)",
            min_value=0.0, max_value=1000.0, value=67.0, step=1.0,
            key="cmp_common"
        )
    with col2:
        stone_crit_buff_pct_cmp = st.number_input(
            "돌옵션 : 치명타 피해 증가율(%)",
            min_value=0.0, max_value=1000.0, value=67.0, step=1.0,
            key="cmp_crit"
        )

    boss_hp_cmp = st.number_input(
        "보스 체력 (비교 기준)",
        min_value=1.0,
        value=100_000_000.0,
        step=1_000_000.0,
        format="%.0f",
        key="cmp_hp"
    )

    if st.button("파티 비교 실행"):
        rows = []
        for line in party_texts.splitlines():
            if not line.strip():
                continue
            try:
                party = build_party_from_text(line)

                total_dmg, total_dmg_per_mp_sum, total_mp, _, _, _ = calculate_party(
                    party=party,
                    common_damage_buff=common_damage_buff_pct_cmp / 100.0,
                    stone_crit_buff=stone_crit_buff_pct_cmp / 100.0,
                    weakness_bonus_by_color=weakness_bonus_by_color_cmp
                )

                cycles = math.ceil(boss_hp_cmp / total_dmg) if total_dmg > 0 else 0

                rows.append({
                    "파티 구성": line,
                    "약점 적용": ", ".join([f"{k}(+30%+{v*100:+.0f}%)" for k, v in weakness_bonus_by_color_cmp.items()]) or "-",
                    "1사이클 총 딜량": int(total_dmg),
                    "총 스킬에너지당 딜량(Σ)": float(f"{total_dmg_per_mp_sum:.2f}"),
                    "필요 사이클 수": cycles,
                    "총 스킬에너지 소모(1사이클)": int(total_mp),
                    "총 스킬에너지 소모(처치)": int(cycles * total_mp),
                })

            except Exception as e:
                rows.append({"파티 구성": line, "오류": str(e)})

        st.dataframe(rows, use_container_width=True)

st.markdown("---")
st.caption("제작 : 카카오톡 오픈채팅방 쿠키런 only 레이드런방 - 오늘컨별로네")
st.caption("도움 : Nawg, 썸머, 솜이, 흑임자맛고양이")
