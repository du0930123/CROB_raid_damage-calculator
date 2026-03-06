import streamlit as st
import math
from dataclasses import dataclass
from typing import Dict, List
from clear_judge import render_clear_judge_box, judge_clear_for_table
from tab_threshold import render_threshold_tab
from boss_limits_store import load_limits
load_limits()

    
# ============================
# 고정 규칙
# ============================
COLOR_MATCH_BONUS = 0.30  # 약점으로 선택된 색 스킬은 항상 +30% (자동 적용)
COLOR_OPTIONS = ["빨강", "노랑", "파랑"]

# ============================
# 게임속도 실험 옵션
# ============================
GAME_SPEED_ALPHA_DEFAULT = 0.2   # 감쇠계수 (0.0이면 사실상 미적용)

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
# 캐릭터 별칭 매핑
# ============================

CHARACTER_ALIAS: Dict[str, str] = {
    # 파랑
    "눈설": "눈설탕",
    "눈설탕": "눈설탕",
    "눈": "눈설탕",

    "캡아": "캡틴아이스",
    "캡틴": "캡틴아이스",
    "캡틴아이스": "캡틴아이스",
    "캡": "캡틴아이스",

    # 노랑
    "스네": "스네이크",
    "스네이크": "스네이크",
    "스":"스네이크",

    # 빨강
    "인삼": "인삼",
    "인":"인삼",
    "비트": "비트",
    "비":"비트",
    "레판": "레판",
    "레":"레판",
    "뱀파": "뱀파",
    "뱀":"뱀파",
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
        raw_name = tokens[i]
        cnt = int(tokens[i + 1])

        # ✅ 별칭을 정식 이름으로 변환
        if raw_name not in CHARACTER_ALIAS:
            raise KeyError(
                f"알 수 없는 캐릭터: {raw_name} / 사용 가능: {', '.join(CHARACTER_ALIAS.keys())}"
            )

        name = CHARACTER_ALIAS[raw_name]

        if name not in CHARACTER_DB:
            raise KeyError(f"DB에 없는 캐릭터: {name}")

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
    energy_decrease_by_color: Dict[str, float],  # ✅ 추가: 색별 에너지 획득량 감소(%) -> mp_cost * (1 + x)
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

        # ✅ 추가: "색깔만의 에너지획득량감소"가 있으면 해당 색 스킬 MP 요구량 증가
        mp_mult = 1.0 + energy_decrease_by_color.get(c.color, 0.0)
        effective_mp = int(math.ceil(c.mp_cost * mp_mult)) if c.mp_cost > 0 else 0

        total_mp += effective_mp

        dmg_per_mp = (dmg / effective_mp) if effective_mp > 0 else 0.0
        total_dmg_per_mp_sum += dmg_per_mp

        if c.name not in detail:
            detail[c.name] = {"count": 0, "damage": 0.0, "mp": 0.0, "dmg_per_mp_sum": 0.0}
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
        detail
    )


# ============================
# ✅ 추가: 비동기합산 기반 딜 비율(dps_ratio_async) 계산
#   - 에너지 수급이 동일하다고 가정할 때, DPS ∝ Σ(dmg / 요구MP)
#   - 따라서 딜 비율 = Σ(dmg/eff_mp) / Σ(dmg/base_mp)
# ============================
def compute_async_dps_ratio(
    party: List[Character],
    common_damage_buff: float,
    stone_crit_buff: float,
    weakness_bonus_by_color: Dict[str, float],
    energy_decrease_by_color: Dict[str, float],
    game_speed_buff: float = 0.0,         # ✅ 추가
    game_speed_alpha: float = 0.0,        # ✅ 추가
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
            weakness_bonus_by_color=weakness_bonus_by_color
        )

        base_mp = c.mp_cost if c.mp_cost > 0 else 0
        if base_mp > 0:
            base_sum += (dmg / base_mp)

        mp_mult = 1.0 + energy_decrease_by_color.get(c.color, 0.0)
        eff_mp = int(math.ceil(c.mp_cost * mp_mult)) if c.mp_cost > 0 else 0
        if eff_mp > 0:
            eff_sum += (dmg / eff_mp)

    if base_sum <= 0:
        return 1.0

    speed_mult = 1.0 + game_speed_alpha * game_speed_buff
    return (eff_sum * speed_mult) / base_sum

# ============================
# ✅ 정규화 기반 "필요 총 에너지" 계산
# - P = Σ(dmg / eff_mp) = total_dmg_per_mp_sum
# - required_energy = boss_hp / P
# ============================
def compute_required_energy(boss_hp: float, total_dmg_per_mp_sum: float) -> float:
    if boss_hp <= 0:
        return 0.0
    if total_dmg_per_mp_sum <= 0:
        return float("inf")
    return boss_hp / total_dmg_per_mp_sum


# ============================
# ✅ 보스-파티유형별 ENERGY_LIMIT(총 에너지 예산) 저장소
# - Streamlit 세션에 저장해서 탭 간 공유
# ============================
def get_limits_store():
    if "BOSS_LIMITS" not in st.session_state:
        st.session_state["BOSS_LIMITS"] = {}  # {boss: {party_type: {"energy_limit": float, "ref_party": str, "threshold_cycles": int}}}
    return st.session_state["BOSS_LIMITS"]



# ============================
# Streamlit UI
# ============================
st.set_page_config(page_title="CROB 파티 딜 계산", page_icon="🧮")

from boss_limits_store import load_limits
load_limits()  # ✅ 서버에 저장된 boss_limits.json을 읽어서 모든 접속자에게 동일 기준 적용

# ✅ 관리자 모드 판별 (URL에 ?admin=1 붙이면 "관리자 로그인 UI"가 열림)
params = st.query_params
admin_flag = str(params.get("admin", "0")).strip().lower() in ["1", "true", "yes"]

if "LAST_CALC_OPTS" not in st.session_state:
    st.session_state["LAST_CALC_OPTS"] = {}

# ✅ 추가: 탭3에서 고정으로 쓸 옵션
if "PINNED_CALC_OPTS" not in st.session_state:
    st.session_state["PINNED_CALC_OPTS"] = None

# ✅ 관리자 인증 상태(세션별)
if "ADMIN_AUTH" not in st.session_state:
    st.session_state["ADMIN_AUTH"] = False

ADMIN_PASSWORD = "0930"  # 요청한 비밀번호

def admin_login_gate() -> bool:
    """
    - URL에 ?admin=1 이 있을 때만 로그인 UI 노출
    - 비밀번호 맞으면 세션에 ADMIN_AUTH=True 저장
    - 세션이 유지되는 동안 계속 관리자
    """
    if not admin_flag:
        return False

    # 이미 인증된 세션이면 통과
    if st.session_state["ADMIN_AUTH"]:
        return True

    with st.sidebar:
        st.markdown("### 🔒 관리자 로그인")
        pw = st.text_input("비밀번호", type="password", key="admin_pw_input")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("로그인", key="admin_login_btn"):
                if pw == ADMIN_PASSWORD:
                    st.session_state["ADMIN_AUTH"] = True
        with col2:
            if st.button("로그아웃", key="admin_logout_btn"):
                st.session_state["ADMIN_AUTH"] = False

        if st.session_state["ADMIN_AUTH"]:
            st.success("관리자 인증 완료")
        else:
            st.info("관리자 기능은 비밀번호가 필요합니다.")

    return st.session_state["ADMIN_AUTH"]

admin_mode = admin_login_gate()

st.title("🧮 쿠오븐 레이드파티 기대 딜량 계산")
st.markdown("<hr style='margin: 6px 0;'>", unsafe_allow_html=True)
st.caption("입력 예: 비트 3 레판 1  |  이름과 수량을 공백으로 구분")
st.markdown("<hr style='margin: 6px 0;'>", unsafe_allow_html=True)
st.caption("유틸 버프 종류 : 공주(+12%), 치어리더(+12%), 생케(+27%), 석류(+30%)")
st.caption("약점으로 선택된 색 스킬: (1 + 공통 + 캡틴 + 0.30 + 약점조건부)로 합산 적용")
st.caption("비약점 색 스킬: (1 + 공통 + 캡틴)만 적용")
st.caption("※ 약점 조건부 피해증가율은 음수도 가능(딜 감소). 예: -20% 입력 가능")
st.caption("※ '총 스킬에너지당 딜량' = Σ(각 스킬 딜량/각 스킬 에너지) 로 계산")

from tab_threshold import render_threshold_tab

tab1, tab2, tab3 = st.tabs(["단일 파티 계산", "파티 여러 개 비교", "파티사이클 클리어 경계값"])



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
    energy_decrease_by_color: Dict[str, float] = {}

    # ✅ 게임속도 실험 옵션
    use_game_speed_model = st.checkbox(
        "게임속도 보정 적용(실험)",
        value=False,
        key="tab1_use_game_speed_model"
    )
    
    game_speed_buff_pct = 0.0
    if use_game_speed_model:
        game_speed_buff_pct = st.number_input(
            "돌옵션 : 게임속도 증가율(%)",
            min_value=0.0,
            max_value=300.0,
            value=0.0,
            step=1.0,
            key="tab1_game_speed_buff_pct"
        )

    if weakness_colors:
        st.markdown("#### 약점 색별 조건부 피해증가율(%) 입력")
        for wc in weakness_colors:
            pct = st.number_input(
                f"돌 옵션 : {wc} 색깔만의 피해증감율(%)",
                min_value=-300.0, max_value=300.0, value=0.0, step=1.0,
                key=f"weak_{wc}"
            )
            weakness_bonus_by_color[wc] = pct / 100.0

            # ✅ 피해증감율 입력 밑에 에너지 획득량 감소 옵션
            energy_on = st.checkbox(f"{wc}색깔만의 에너지획득량감소", key=f"energy_on_{wc}")
            if energy_on:
                e_pct = st.number_input(
                    f"{wc}색 에너지 획득량 감소(%)",
                    min_value=0.0, max_value=300.0, value=0.0, step=1.0,
                    key=f"energy_pct_{wc}"
                )
                energy_decrease_by_color[wc] = e_pct / 100.0

    col1, col2 = st.columns(2)
    with col1:
        common_damage_buff_pct = st.number_input(
            "공통 피해증가율(%) (ex : 유틸버프, 쿠키가주는피해량증가)",
            min_value=0.0, max_value=1000.0, value=30.0, step=1.0
        )
    with col2:
        stone_crit_buff_pct = st.number_input(
            "돌옵션 : 치명타 피해 증가율(%)",
            min_value=0.0, max_value=1000.0, value=0.0, step=1.0
        )

    use_boss_hp = st.checkbox("보스 체력 기준 계산")
    boss_hp = None

    boss_hp_inc_on = False
    boss_hp_inc_pct = 0.0
    party5_on = False

    if use_boss_hp:
        boss_hp = st.number_input("보스 체력", min_value=1.0, value=1.0, step=1_000_000.0, format="%.0f")

        col_a, col_b = st.columns(2)
        with col_a:
            boss_hp_inc_on = st.checkbox("보스 체력 증가 옵션", key="boss_hp_inc_on")
        with col_b:
            party5_on = st.checkbox("파티원이 5명? (입력된 보스체력*5 해주는 옵션임)", key="party5_on")

        if boss_hp_inc_on:
            boss_hp_inc_pct = st.number_input(
                "보스 체력 증가(%)",
                min_value=0.0, max_value=1000.0, value=0.0, step=1.0,
                key="boss_hp_inc_pct"
            )

    if st.button("단일 파티 계산"):
        try:
            party = build_party_from_text(party_text)

            total_dmg, total_dmg_per_mp_sum, total_mp, party_buff, lepain_buff, detail = calculate_party(
                party=party,
                common_damage_buff=common_damage_buff_pct / 100.0,
                stone_crit_buff=stone_crit_buff_pct / 100.0,
                weakness_bonus_by_color=weakness_bonus_by_color,
                energy_decrease_by_color=energy_decrease_by_color,
            )

            # ✅ 추가: 비동기합산 기반 딜 비율/감소율
            dps_ratio_async = compute_async_dps_ratio(
                party=party,
                common_damage_buff=common_damage_buff_pct / 100.0,
                stone_crit_buff=stone_crit_buff_pct / 100.0,
                weakness_bonus_by_color=weakness_bonus_by_color,
                energy_decrease_by_color=energy_decrease_by_color,
                game_speed_buff=game_speed_buff_pct / 100.0,
                game_speed_alpha=GAME_SPEED_ALPHA_DEFAULT if use_game_speed_model else 0.0,
            )
            P_effective = total_dmg_per_mp_sum * dps_ratio_async
            dps_drop_async_pct = (1.0 - dps_ratio_async) * 100.0

            st.session_state["LAST_CALC_OPTS"] = {
                "weakness_colors": list(weakness_colors),
                "weakness_bonus_by_color": dict(weakness_bonus_by_color),
                "energy_decrease_by_color": dict(energy_decrease_by_color),
                "common_damage_buff_pct": float(common_damage_buff_pct),
                "stone_crit_buff_pct": float(stone_crit_buff_pct),
            }
            

            st.subheader("적용 요약")
            if weakness_bonus_by_color:
                pretty = ", ".join([f"{k}(+30% 고정 + {v*100:+.0f}%)" for k, v in weakness_bonus_by_color.items()])
                st.write(f"- 약점 적용: **{pretty}**")
            else:
                st.write("- 약점 적용: **없음**")

            if energy_decrease_by_color:
                epretty = ", ".join([f"{k}({v*100:.0f}%)" for k, v in energy_decrease_by_color.items()])
                st.write(f"- 에너지획득량감소(색별): **{epretty}**")
            else:
                st.write("- 에너지획득량감소(색별): **없음**")

            if use_game_speed_model:
                st.write(
                    f"- 게임속도 증가율: **{game_speed_buff_pct:.0f}%** "
                    f"(감쇠계수 {GAME_SPEED_ALPHA_DEFAULT:.2f} 적용)"
                )
            else:
                st.write("- 게임속도 증가율: **미적용**")

            # ✅ 추가 출력(비동기합산 딜 감소율)
            st.write(f"- (비동기합산) 딜량 감소율: **{dps_drop_async_pct:.2f}%**")

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
                effective_boss_hp = boss_hp if boss_hp is not None else 0.0
                if boss_hp_inc_on:
                    effective_boss_hp *= (1.0 + boss_hp_inc_pct / 100.0)
                if party5_on:
                    effective_boss_hp *= 5.0

                # ✅ 정규화 클리어 판정 박스(탭1)

                BOSS_LIST = ["두억시니", "사마귀"]
                
                selected_boss = st.selectbox(
                    "보스 선택",
                    BOSS_LIST,
                    index=0,   # ✅ 두억시니가 기본
                    key="tab1_boss_select"
)
                render_clear_judge_box(
                    boss=selected_boss,
                    boss_hp=effective_boss_hp,
                    P=P_effective,
                    party=party,
                    key_prefix="tab1_judge",
                    show_match_info=True,
                    k_profiles=5,
                    weight_power=1.0,
                )

                # ✅ 기존(에너지 미반영) 사이클
                cycles = math.ceil(effective_boss_hp / total_dmg) if total_dmg > 0 else 0

                # ✅ 추가: (비동기합산 딜 감소율 반영) 사이클
                effective_total_dmg_async = total_dmg * dps_ratio_async
                cycles_with_energy_async = math.ceil(effective_boss_hp / effective_total_dmg_async) if effective_total_dmg_async > 0 else 0

                st.write(f"- 필요 파티 사이클: **{cycles} 회**")
                st.write(f"- (에너지감소 반영) 필요 파티 사이클: **{cycles_with_energy_async} 회**")
                st.caption("※ 에너지감소 반영 (Σ(딜/요구 스킬젬량)) 기반으로 '시간당 딜 감소'를 반영해 보스 처치 사이클을 재산정한 값")

                st.write(f"- 예상 총 스킬에너지 소모: **{cycles * total_mp:,}**")
                st.write(f"- (에너지감소 반영) 예상 총 스킬에너지 소모: **{cycles_with_energy_async * total_mp:,}**")

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
    energy_decrease_by_color_cmp: Dict[str, float] = {}

    # ✅ 비교용 게임속도 실험 옵션
    use_game_speed_model_cmp = st.checkbox(
        "게임속도 보정 적용(실험)",
        value=False,
        key="tab2_use_game_speed_model"
    )
    
    game_speed_buff_pct_cmp = 0.0
    if use_game_speed_model_cmp:
        game_speed_buff_pct_cmp = st.number_input(
            "돌옵션 : 게임속도 증가율(%)",
            min_value=0.0,
            max_value=300.0,
            value=0.0,
            step=1.0,
            key="tab2_game_speed_buff_pct"
        )


    if weakness_colors_cmp:
        st.markdown("#### (비교) 약점 색별 조건부 피해증가율(%) 입력")
        for wc in weakness_colors_cmp:
            pct = st.number_input(
                f"돌옵션 : {wc} 색깔만의 피해량 증감율(%)",
                min_value=-300.0, max_value=300.0, value=0.0, step=1.0,
                key=f"cmp_weak_{wc}"
            )
            weakness_bonus_by_color_cmp[wc] = pct / 100.0

            energy_on = st.checkbox(f"(비교) {wc}색깔만의 에너지획득량감소", key=f"cmp_energy_on_{wc}")
            if energy_on:
                e_pct = st.number_input(
                    f"(비교) {wc}색 에너지 획득량 감소(%)",
                    min_value=0.0, max_value=300.0, value=0.0, step=1.0,
                    key=f"cmp_energy_pct_{wc}"
                )
                energy_decrease_by_color_cmp[wc] = e_pct / 100.0

    col1, col2 = st.columns(2)
    with col1:
        common_damage_buff_pct_cmp = st.number_input(
            "공통 피해증가율(%) (ex : 유틸버프, 쿠주피)",
            min_value=0.0, max_value=1000.0, value=30.0, step=1.0,
            key="cmp_common"
        )
    with col2:
        stone_crit_buff_pct_cmp = st.number_input(
            "돌옵션 : 치명타 피해 증가율(%)",
            min_value=0.0, max_value=1000.0, value=0.0, step=1.0,
            key="cmp_crit"
        )

    boss_hp_cmp = st.number_input(
        "보스 체력 (비교 기준)",
        min_value=1.0,
        value=1.0,
        step=1_000_000.0,
        format="%.0f",
        key="cmp_hp"
    )

    col_c, col_d = st.columns(2)
    with col_c:
        boss_hp_inc_on_cmp = st.checkbox("보스 체력 증가 옵션", key="boss_hp_inc_on_cmp")
    with col_d:
        party5_on_cmp = st.checkbox("파티원이 5명? (보스체력*5 해주는 옵션)", key="party5_on_cmp")

    boss_hp_inc_pct_cmp = 0.0
    if boss_hp_inc_on_cmp:
        boss_hp_inc_pct_cmp = st.number_input(
            "보스 체력 증가(%)",
            min_value=0.0, max_value=1000.0, value=0.0, step=1.0,
            key="boss_hp_inc_pct_cmp"
        )
        
    BOSS_LIST = ["두억시니", "사마귀"]
    selected_boss_cmp = st.selectbox(
        "보스 선택(비교 기준)",
        BOSS_LIST,
        index=0,   # ✅ 두억시니 기본
        key="tab2_boss_select"
    )

    
    if st.button("파티 비교 실행"):
        
        st.session_state["LAST_CALC_OPTS"] = {
            "weakness_colors": list(weakness_colors_cmp),
            "weakness_bonus_by_color": dict(weakness_bonus_by_color_cmp),
            "energy_decrease_by_color": dict(energy_decrease_by_color_cmp),
            "common_damage_buff_pct": float(common_damage_buff_pct_cmp),
            "stone_crit_buff_pct": float(stone_crit_buff_pct_cmp),
        }

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
                    weakness_bonus_by_color=weakness_bonus_by_color_cmp,
                    energy_decrease_by_color=energy_decrease_by_color_cmp,
                )

                dps_ratio_async = compute_async_dps_ratio(
                    party=party,
                    common_damage_buff=common_damage_buff_pct_cmp / 100.0,
                    stone_crit_buff=stone_crit_buff_pct_cmp / 100.0,
                    weakness_bonus_by_color=weakness_bonus_by_color_cmp,
                    energy_decrease_by_color=energy_decrease_by_color_cmp,
                    game_speed_buff=game_speed_buff_pct_cmp / 100.0,
                    game_speed_alpha=GAME_SPEED_ALPHA_DEFAULT if use_game_speed_model_cmp else 0.0,
                )
                P_effective_cmp = total_dmg_per_mp_sum * dps_ratio_async
                dps_drop_async_pct = (1.0 - dps_ratio_async) * 100.0

                effective_boss_hp_cmp = boss_hp_cmp
                if boss_hp_inc_on_cmp:
                    effective_boss_hp_cmp *= (1.0 + boss_hp_inc_pct_cmp / 100.0)
                if party5_on_cmp:
                    effective_boss_hp_cmp *= 5.0


                judge_cols = judge_clear_for_table(
                    boss=selected_boss_cmp,
                    boss_hp=effective_boss_hp_cmp,
                    P=P_effective_cmp,
                    party=party,
                    k_profiles=5,
                    weight_power=1.0,
                )
                
                cycles = math.ceil(effective_boss_hp_cmp / total_dmg) if total_dmg > 0 else 0
                effective_total_dmg_async = total_dmg * dps_ratio_async
                cycles_with_energy_async = math.ceil(effective_boss_hp_cmp / effective_total_dmg_async) if effective_total_dmg_async > 0 else 0
                
                
                rows.append({
                    "파티 구성": line,
                    **judge_cols,
                    "약점 적용": ", ".join([f"{k}(+30%+{v*100:+.0f}%)" for k, v in weakness_bonus_by_color_cmp.items()]) or "-",
                    "(비동기합산) 딜감소율%": float(f"{dps_drop_async_pct:.2f}"),
                    "1사이클 총 딜량": int(total_dmg),
                    "총 스킬에너지당 딜량(Σ)": float(f"{total_dmg_per_mp_sum:.2f}"),
                    "필요 사이클 수": cycles,
                    "(에너지감소 반영) 필요 사이클 수": cycles_with_energy_async,
                    "총 스킬에너지 소모(1사이클)": int(total_mp),
                    "총 스킬에너지 소모(처치)": int(cycles * total_mp),
                    "(에너지감소 반영) 총 스킬에너지 소모(처치)": int(cycles_with_energy_async * total_mp),                   
                })

            except Exception as e:
                rows.append({"파티 구성": line, "오류": str(e)})

        st.dataframe(rows, use_container_width=True)

with tab3:
    render_threshold_tab(
        COLOR_OPTIONS=COLOR_OPTIONS,
        build_party_from_text=build_party_from_text,
        calculate_party=calculate_party,
        admin_mode=admin_mode,   # ✅ 추가
    )

st.markdown("---")
st.caption("제작 : 카카오톡 오픈채팅방 쿠키런 only 레이드런방 - 오늘컨별로네")
st.caption("도움 : Nawg, 썸머, 솜이, 흑임자맛고양이, 감성적인방향치")
