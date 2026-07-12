import math
from typing import Dict

import streamlit as st

from src.constants import COLOR_OPTIONS
from src.party_parser import build_party_from_text
from src.calculator import calculate_party, compute_async_dps_ratio
from src.boss_config import GAME_SPEED_ALPHA_BY_BOSS, DEFAULT_GAME_SPEED_ALPHA
from src.clear_judge import judge_clear_for_table


def render_party_compare_tab():
    st.caption("파티를 한 줄에 하나씩 입력 (예: 비트 1 레판 4)")

    party_texts = st.text_area(
        "비교할 파티 목록",
        value=(
            "비 1 레 4\n"
            "비트 2 레판 2\n"
            "캡틴아이스 1 비트 2 레판 1\n"
            "뱀파 1 레판 4\n"
            "스네이크 3 캡틴아이스 1"
        ),
        height=160,
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

    boss_list = ["두억시니", "사마귀", "무쇠꾼", "크치뱀"]

    selected_boss_cmp = st.selectbox(
        "보스 선택(비교 기준)",
        boss_list,
        index=3,
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
):
    party = build_party_from_text(line)

    total_dmg, total_dmg_per_mp_sum, total_mp, _, _, _ = calculate_party(
        party=party,
        common_damage_buff=common_damage_buff_pct_cmp / 100.0,
        stone_crit_buff=stone_crit_buff_pct_cmp / 100.0,
        weakness_bonus_by_color=weakness_bonus_by_color_cmp,
        energy_decrease_by_color=energy_decrease_by_color_cmp,
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
        game_speed_buff=game_speed_buff_pct_cmp / 100.0,
        game_speed_alpha=boss_speed_alpha_cmp if use_game_speed_model_cmp else 0.0,
    )

    dps_drop_async_pct = (dps_ratio_async - 1.0) * 100.0

    effective_boss_hp_cmp = boss_hp_cmp

    if boss_hp_inc_on_cmp:
        effective_boss_hp_cmp *= 1.0 + boss_hp_inc_pct_cmp / 100.0

    if party5_on_cmp:
        effective_boss_hp_cmp *= 5.0

    p_base = total_dmg_per_mp_sum
    p_effective_cmp = total_dmg_per_mp_sum * dps_ratio_async

    judge_cols_base = judge_clear_for_table(
        boss=selected_boss_cmp,
        boss_hp=effective_boss_hp_cmp,
        P=p_base,
        party=party,
        k_profiles=5,
        weight_power=1.0,
    )

    judge_cols_speed = judge_clear_for_table(
        boss=selected_boss_cmp,
        boss_hp=effective_boss_hp_cmp,
        P=p_effective_cmp,
        party=party,
        k_profiles=5,
        weight_power=1.0,
    )

    cycles = math.ceil(effective_boss_hp_cmp / total_dmg) if total_dmg > 0 else 0
    effective_total_dmg_async = total_dmg * dps_ratio_async

    cycles_with_energy_async = (
        math.ceil(effective_boss_hp_cmp / effective_total_dmg_async)
        if effective_total_dmg_async > 0
        else 0
    )

    return {
        "파티 구성": line,
        "겜속 미반영 판정": judge_cols_base.get("정규화판정"),
        "겜속 미반영 여유율%": judge_cols_base.get("여유율"),
        "반영 판정": judge_cols_speed.get("정규화판정"),
        "반영 여유율%": judge_cols_speed.get("여유율"),
        "기준 ref_required_norm": judge_cols_base.get("ref_required_norm(가중평균)"),
        "미반영 필요총에너지": judge_cols_base.get("필요총에너지(boss_hp/P)"),
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