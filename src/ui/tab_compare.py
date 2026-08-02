import math
from typing import Dict

import streamlit as st

from src.constants import COLOR_OPTIONS
from src.party_parser import build_party_from_text
from src.calculator import calculate_party, compute_async_dps_ratio
from src.boss_config import (
    GAME_SPEED_ALPHA_BY_BOSS,
    DEFAULT_GAME_SPEED_ALPHA,
    BOSS_LIST,
    DEFAULT_BOSS,
    get_job_energy_alpha_by_job,
)
from src.clear_judge import judge_clear_for_table
from src.stones import compute_avg_defense_effect_pct
from src.jobs import (
    build_job_assignments_from_text,
    build_party_and_jobs_from_job_text,
    merge_party_by_character,
)


def render_party_compare_tab():
    st.caption(
        "파티를 한 줄에 하나씩 입력 (예: 비트 1 레판 4). "
        "🆕 직업까지 반영하고 싶으면, 그 줄을 직업 텍스트 형식으로 써도 돼요 "
        "(예: 스+캡 회 1 스+연 회 3 스+석 회 1) — 파티 구성이 자동으로 추론됩니다."
    )

    party_texts = st.text_area(
        "비교할 파티 목록",
        value=(
            "비 1 레 4\n"
            "비트 2 레판 2\n"
            "캡틴아이스 1 비트 2 레판 1\n"
            "뱀파 1 레판 4\n"
            "스네이크 3 캡틴아이스 1\n"
            "스+캡 회 1 스+연 회 3 스+석 회 1"
        ),
        height=180,
    )

    weakness_colors_cmp = st.multiselect(
        "보스 약점 색 선택 (비교 기준, 최대 2개)",
        options=COLOR_OPTIONS,
        default=["노랑"],
        key="weakness_cmp",
    )

    if len(weakness_colors_cmp) > 2:
        st.error("약점은 최대 2개까지만 선택할 수 있어.")
        weakness_colors_cmp = weakness_colors_cmp[:2]

    weakness_bonus_by_color_cmp: Dict[str, float] = {}
    energy_decrease_by_color_cmp: Dict[str, float] = {}

    use_game_speed_model_cmp = st.checkbox(
        "게임속도 보정 적용(실험)",
        value=False,
        key="tab2_use_game_speed_model",
    )

    game_speed_buff_pct_cmp = 0.0

    if use_game_speed_model_cmp:
        game_speed_buff_pct_cmp = st.number_input(
            "돌옵션 : 게임속도 증가율(%)",
            min_value=0.0,
            max_value=300.0,
            value=0.0,
            step=1.0,
            key="tab2_game_speed_buff_pct",
        )

    if weakness_colors_cmp:
        st.markdown("#### (비교) 약점 색별 조건부 피해증가율(%) 입력")

        for wc in weakness_colors_cmp:
            pct = st.number_input(
                f"돌옵션 : {wc} 색깔만의 피해량 증감율(%)",
                min_value=-300.0,
                max_value=300.0,
                value=0.0,
                step=1.0,
                key=f"cmp_weak_{wc}",
            )

            weakness_bonus_by_color_cmp[wc] = pct / 100.0

            energy_on = st.checkbox(
                f"(비교) {wc}색깔만의 에너지획득량감소",
                key=f"cmp_energy_on_{wc}",
            )

            if energy_on:
                e_pct = st.number_input(
                    f"(비교) {wc}색 에너지 획득량 감소(%)",
                    min_value=0.0,
                    max_value=300.0,
                    value=0.0,
                    step=1.0,
                    key=f"cmp_energy_pct_{wc}",
                )
                energy_decrease_by_color_cmp[wc] = e_pct / 100.0

    energy_increase_by_color_cmp: Dict[str, float] = {}
    with st.expander("🆕 신규 소환석 옵션 (색상 에너지 증감 / 방어약화·강화)", expanded=False):
        st.caption(
            "※ 직업(젤리술사/회피도사/방패지기)은 이제 '비교할 파티 목록'에서 "
            "그 줄을 직업 텍스트 형식(예: 스+캡 회 1)으로 쓰면 자동 인식돼요. "
            "여기 있는 옵션들은 모든 줄에 공통으로 적용되는 옵션입니다."
        )
        st.caption("양수(+)면 획득량 증가, 음수(-)면 감소로 처리돼요.")
        for color in COLOR_OPTIONS:
            on = st.checkbox(f"{color} 에너지 획득량 증감 적용", key=f"cmp_energy_inc_on_{color}")
            if on:
                pct = st.number_input(
                    f"{color} 에너지 획득량 증감(%) (+면 증가, -면 감소)",
                    min_value=-300.0, max_value=300.0,
                    value=0.0, step=1.0, key=f"cmp_energy_inc_pct_{color}",
                )
                energy_increase_by_color_cmp[color] = pct / 100.0

        st.markdown("#### 몬스터 방어력 약화/강화")
        st.caption("지속시간·발생주기·피해율은 고정값이라, 해당 보스에 적용되는지만 체크하면 돼요.")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            weaken_on_cmp = st.checkbox("방어력 약화 있음", key="cmp_weaken_on")
        with col_d2:
            strengthen_on_cmp = st.checkbox("방어력 강화 있음", key="cmp_strengthen_on")

        defense_avg_pct_cmp = compute_avg_defense_effect_pct(
            weaken_on=weaken_on_cmp,
            strengthen_on=strengthen_on_cmp,
        )

        if weaken_on_cmp or strengthen_on_cmp:
            st.write(f"- 시간가중평균 피해변화: **{defense_avg_pct_cmp:+.2f}%** (공통 피해증가율에 자동 합산됨)")

    col1, col2 = st.columns(2)

    with col1:
        common_damage_buff_pct_cmp = st.number_input(
            "공통 피해증가율(%) (ex : 유틸버프, 쿠주피)",
            min_value=0.0,
            max_value=1000.0,
            value=30.0,
            step=1.0,
            key="cmp_common",
        )
        common_damage_buff_pct_cmp = common_damage_buff_pct_cmp + defense_avg_pct_cmp

    with col2:
        stone_crit_buff_pct_cmp = st.number_input(
            "돌옵션 : 치명타 피해 증가율(%)",
            min_value=0.0,
            max_value=1000.0,
            value=0.0,
            step=1.0,
            key="cmp_crit",
        )

    boss_hp_cmp = st.number_input(
        "보스 체력 (비교 기준)",
        min_value=1.0,
        value=1.0,
        step=1_000_000.0,
        format="%.0f",
        key="cmp_hp",
    )

    col_c, col_d = st.columns(2)

    with col_c:
        boss_hp_inc_on_cmp = st.checkbox(
            "보스 체력 증가 옵션",
            key="boss_hp_inc_on_cmp",
        )

    with col_d:
        party5_on_cmp = st.checkbox(
            "파티원이 5명? (보스체력*5 해주는 옵션)",
            key="party5_on_cmp",
        )

    boss_hp_inc_pct_cmp = 0.0

    if boss_hp_inc_on_cmp:
        boss_hp_inc_pct_cmp = st.number_input(
            "보스 체력 증가(%)",
            min_value=0.0,
            max_value=1000.0,
            value=0.0,
            step=1.0,
            key="boss_hp_inc_pct_cmp",
        )

    selected_boss_cmp = st.selectbox(
        "보스 선택(비교 기준)",
        BOSS_LIST,
        index=BOSS_LIST.index(DEFAULT_BOSS),
        key="tab2_boss_select",
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
                row = _calculate_compare_row(
                    line=line,
                    selected_boss_cmp=selected_boss_cmp,
                    boss_hp_cmp=boss_hp_cmp,
                    boss_hp_inc_on_cmp=boss_hp_inc_on_cmp,
                    boss_hp_inc_pct_cmp=boss_hp_inc_pct_cmp,
                    party5_on_cmp=party5_on_cmp,
                    weakness_bonus_by_color_cmp=weakness_bonus_by_color_cmp,
                    energy_decrease_by_color_cmp=energy_decrease_by_color_cmp,
                    energy_increase_by_color_cmp=energy_increase_by_color_cmp,
                    common_damage_buff_pct_cmp=common_damage_buff_pct_cmp,
                    stone_crit_buff_pct_cmp=stone_crit_buff_pct_cmp,
                    use_game_speed_model_cmp=use_game_speed_model_cmp,
                    game_speed_buff_pct_cmp=game_speed_buff_pct_cmp,
                )
                rows.append(row)

            except Exception as e:
                rows.append({"파티 구성": line, "오류": str(e)})

        st.dataframe(rows, use_container_width=True)


def _calculate_compare_row(
    line,
    selected_boss_cmp,
    boss_hp_cmp,
    boss_hp_inc_on_cmp,
    boss_hp_inc_pct_cmp,
    party5_on_cmp,
    weakness_bonus_by_color_cmp,
    energy_decrease_by_color_cmp,
    common_damage_buff_pct_cmp,
    stone_crit_buff_pct_cmp,
    use_game_speed_model_cmp,
    game_speed_buff_pct_cmp,
    energy_increase_by_color_cmp=None,
):
    energy_increase_by_color_cmp = energy_increase_by_color_cmp or {}

    # ✅ 먼저 "직업 텍스트" 형식으로 시도 (예: 스+캡 회 1 스+연 회 3)
    #    실패하면(일반 파티 텍스트면 당연히 실패함) 기존 방식으로 파싱
    job_per_instance = None
    try:
        test_assignments = build_job_assignments_from_text(line)
        if test_assignments:
            party, job_per_instance = build_party_and_jobs_from_job_text(line)
        else:
            party = build_party_from_text(line)
    except Exception:
        party = build_party_from_text(line)

    if job_per_instance is None:
        job_per_instance = [None] * len(party)

    display_party_text = merge_party_by_character(party) if any(
        j is not None for j in job_per_instance
    ) else line

    boss_job_energy_alpha_by_job = get_job_energy_alpha_by_job(
        boss_name=selected_boss_cmp,
        boss_hp_total=boss_hp_cmp,
        party_size=len(party),
    )

    total_dmg, total_dmg_per_mp_sum, total_mp, _, _, _ = calculate_party(
        party=party,
        common_damage_buff=common_damage_buff_pct_cmp / 100.0,
        stone_crit_buff=stone_crit_buff_pct_cmp / 100.0,
        weakness_bonus_by_color=weakness_bonus_by_color_cmp,
        energy_decrease_by_color=energy_decrease_by_color_cmp,
        energy_increase_by_color=energy_increase_by_color_cmp,
        job_per_instance=job_per_instance,
    )

    boss_speed_alpha_cmp = GAME_SPEED_ALPHA_BY_BOSS.get(
        selected_boss_cmp,
        DEFAULT_GAME_SPEED_ALPHA,
    )

    dps_ratio_async = compute_async_dps_ratio(
        party=party,
        common_damage_buff=common_damage_buff_pct_cmp / 100.0,
        stone_crit_buff=stone_crit_buff_pct_cmp / 100.0,
        weakness_bonus_by_color=weakness_bonus_by_color_cmp,
        energy_decrease_by_color=energy_decrease_by_color_cmp,
        energy_increase_by_color=energy_increase_by_color_cmp,
        job_per_instance=job_per_instance,
        job_energy_alpha_by_job=boss_job_energy_alpha_by_job,
        game_speed_buff=game_speed_buff_pct_cmp / 100.0,
        game_speed_alpha=boss_speed_alpha_cmp if use_game_speed_model_cmp else 0.0,
    )

    dps_drop_async_pct = (dps_ratio_async - 1.0) * 100.0

    effective_boss_hp_cmp = boss_hp_cmp

    if boss_hp_inc_on_cmp:
        effective_boss_hp_cmp *= 1.0 + boss_hp_inc_pct_cmp / 100.0

    if party5_on_cmp:
        effective_boss_hp_cmp *= 5.0

    # ✅ 체력 임계값 앵커 판정용 "기본 체력" - 보스체력증가 옵션은 제외하고 계산
    base_boss_hp_cmp = boss_hp_cmp
    if party5_on_cmp:
        base_boss_hp_cmp *= 5.0

    p_base = total_dmg_per_mp_sum
    p_effective_cmp = total_dmg_per_mp_sum * dps_ratio_async

    judge_cols_speed = judge_clear_for_table(
        boss=selected_boss_cmp,
        boss_hp=effective_boss_hp_cmp,
        P=p_effective_cmp,
        party=party,
        k_profiles=5,
        weight_power=1.0,
        tier_boss_hp=base_boss_hp_cmp,
        norm_field="ref_required_norm_adjusted",
    )

    cycles = math.ceil(effective_boss_hp_cmp / total_dmg) if total_dmg > 0 else 0
    effective_total_dmg_async = total_dmg * dps_ratio_async

    cycles_with_energy_async = (
        math.ceil(effective_boss_hp_cmp / effective_total_dmg_async)
        if effective_total_dmg_async > 0
        else 0
    )

    return {
        "파티 구성": display_party_text,
        "직업(감지됨)": line if any(j is not None for j in job_per_instance) else "-",
        "반영 판정": judge_cols_speed.get("정규화판정"),
        "반영 여유율%": judge_cols_speed.get("여유율"),
        "반영 필요총에너지": judge_cols_speed.get("필요총에너지(boss_hp/P)"),
        "약점 적용": _format_weakness_text(weakness_bonus_by_color_cmp),
        "(비동기합산) 실효 딜 변화율%": float(f"{dps_drop_async_pct:+.2f}"),
        "1사이클 총 딜량": int(total_dmg),
        "총 스킬에너지당 딜량(Σ)": float(f"{total_dmg_per_mp_sum:.2f}"),
        "필요 사이클 수": cycles,
        "(에너지감소, 겜속 반영) 필요 사이클 수": cycles_with_energy_async,
        "총 스킬에너지 소모(1사이클)": int(total_mp),
        "총 스킬에너지 소모(처치)": int(cycles * total_mp),
        "(에너지감소, 겜속 반영) 총 스킬에너지 소모(처치)": int(cycles_with_energy_async * total_mp),
    }


def _format_weakness_text(weakness_bonus_by_color_cmp):
    return (
        ", ".join(
            [
                f"{k}(+30%+{v * 100:+.0f}%)"
                for k, v in weakness_bonus_by_color_cmp.items()
            ]
        )
        or "-"
    )
