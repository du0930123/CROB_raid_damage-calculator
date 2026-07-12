import streamlit as st
import math
from src.characters import Character, CHARACTER_DB
from typing import Dict, List
from src.clear_judge import (
    render_clear_judge_box,
    judge_clear_for_table,
    compute_energy_limit_weighted,
)
from src.ui.common import (
    init_session_state,
    render_admin_login,
    render_header,
    render_footer,
)
from src.tab_threshold import render_threshold_tab
from src.boss_limits_store import load_limits
load_limits()

from src.boss_config import GAME_SPEED_ALPHA_BY_BOSS, DEFAULT_GAME_SPEED_ALPHA
from src.constants import COLOR_MATCH_BONUS, COLOR_OPTIONS
from src.party_parser import build_party_from_text
from src.calculator import calculate_party, compute_async_dps_ratio, compute_required_energy
from src.ui.tab_single import render_single_party_tab
from src.ui.tab_compare import render_party_compare_tab
from src.tab_threshold import render_threshold_tab

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
st.set_page_config(page_title="쿠오븐 레이드파티 기대 딜량 계산", page_icon="🧮")

from src.boss_limits_store import load_limits
load_limits()  # ✅ 서버에 저장된 boss_limits.json을 읽어서 모든 접속자에게 동일 기준 적용

init_session_state()
admin_mode = render_admin_login()

render_header()



tab1, tab2, tab3 = st.tabs(["단일 파티 계산", "파티 여러 개 비교", "파티사이클 클리어 경계값"])



# ============================
# 탭 1: 단일 파티
# ============================
with tab1:
    render_single_party_tab()


# ============================
# 탭 2: 파티 여러 개 비교
# ============================
with tab2:
    render_party_compare_tab()

with tab3:
    render_threshold_tab(
        COLOR_OPTIONS=COLOR_OPTIONS,
        build_party_from_text=build_party_from_text,
        calculate_party=calculate_party,
        admin_mode=admin_mode,   # ✅ 추가
    )

render_footer()