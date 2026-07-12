
import math
from typing import Dict

import streamlit as st

from src.characters import CHARACTER_DB
from src.constants import COLOR_OPTIONS
from src.party_parser import build_party_from_text
from src.calculator import calculate_party, compute_async_dps_ratio
from src.boss_config import GAME_SPEED_ALPHA_BY_BOSS, DEFAULT_GAME_SPEED_ALPHA
from src.clear_judge import render_clear_judge_box, compute_energy_limit_weighted


def render_single_party_tab():
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

    use_game_speed_model = st.checkbox(
        "게임속도 보정 적용(실험)",
        value=False,
        key="tab1_use_game_speed_model",
    )

    game_speed_buff_pct = 0.0

    if use_game_speed_model:
        game_speed_buff_pct = st.number_input(
            "돌옵션 : 게임속도 증가율(%)",
            min_value=0.0,
            max_value=300.0,
            value=0.0,
            step=1.0,
            key="tab1_game_speed_buff_pct",
        )

    if weakness_colors:
        st.markdown("#### 약점 색별 조건부 피해증가율(%) 입력")

        for wc in weakness_colors:
            pct = st.number_input(
                f"돌 옵션 : {wc} 색깔만의 피해증감율(%)",
                min_value=-300.0,
                max_value=300.0,
                value=0.0,
                step=1.0,
                key=f"weak_{wc}",
            )
            weakness_bonus_by_color[wc] = pct / 100.0

            energy_on = st.checkbox(f"{wc}색깔만의 에너지획득량감소", key=f"energy_on_{wc}")

            if energy_on:
                e_pct = st.number_input(
                    f"{wc}색 에너지 획득량 감소(%)",
                    min_value=0.0,
                    max_value=300.0,
                    value=0.0,
                    step=1.0,
                    key=f"energy_pct_{wc}",
                )
                energy_decrease_by_color[wc] = e_pct / 100.0

    col1, col2 = st.columns(2)

    with col1:
        common_damage_buff_pct = st.number_input(
            "공통 피해증가율(%) (ex : 유틸버프, 쿠키가주는피해량증가)",
            min_value=0.0,
            max_value=1000.0,
            value=30.0,
            step=1.0,
        )

    with col2:
        stone_crit_buff_pct = st.number_input(
            "돌옵션 : 치명타 피해 증가율(%)",
            min_value=0.0,
            max_value=1000.0,
            value=0.0,
            step=1.0,
        )

    use_boss_hp = st.checkbox("보스 체력 기준 계산")
    boss_hp = None

    boss_hp_inc_on = False
    boss_hp_inc_pct = 0.0
    party5_on = False

    if use_boss_hp:
        boss_hp = st.number_input(
            "보스 체력",
            min_value=1.0,
            value=1.0,
            step=1_000_000.0,
            format="%.0f",
        )

        col_a, col_b = st.columns(2)

        with col_a:
            boss_hp_inc_on = st.checkbox("보스 체력 증가 옵션", key="boss_hp_inc_on")

        with col_b:
            party5_on = st.checkbox("파티원이 5명? (입력된 보스체력*5 해주는 옵션임)", key="party5_on")

        if boss_hp_inc_on:
            boss_hp_inc_pct = st.number_input(
                "보스 체력 증가(%)",
                min_value=0.0,
                max_value=1000.0,
                value=0.0,
                step=1.0,
                key="boss_hp_inc_pct",
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

            st.session_state["LAST_CALC_OPTS"] = {
                "weakness_colors": list(weakness_colors),
                "weakness_bonus_by_color": dict(weakness_bonus_by_color),
                "energy_decrease_by_color": dict(energy_decrease_by_color),
                "common_damage_buff_pct": float(common_damage_buff_pct),
                "stone_crit_buff_pct": float(stone_crit_buff_pct),
            }

            st.subheader("적용 요약")

            if weakness_bonus_by_color:
                pretty = ", ".join(
                    [f"{k}(+30% 고정 + {v * 100:+.0f}%)" for k, v in weakness_bonus_by_color.items()]
                )
                st.write(f"- 약점 적용: **{pretty}**")
            else:
                st.write("- 약점 적용: **없음**")

            if energy_decrease_by_color:
                epretty = ", ".join([f"{k}({v * 100:.0f}%)" for k, v in energy_decrease_by_color.items()])
                st.write(f"- 에너지획득량감소(색별): **{epretty}**")
            else:
                st.write("- 에너지획득량감소(색별): **없음**")

            if use_game_speed_model:
                st.write(f"- 게임속도 증가율: **{game_speed_buff_pct:.0f}%** (보스별 보정 적용)")
            else:
                st.write("- 게임속도 증가율: **미적용**")

            st.write(f"- 공통 피해증가율: **{common_damage_buff_pct:.0f}%** (전원 적용)")
            st.write(f"- 캡틴아이스 피해증가: **{party_buff * 100:.2f}%** (최대 1회)")
            st.write(f"- 레판 치명타 추가딜: **{lepain_buff * 100:.2f}%** (최대 1회)")

            st.metric("스킬 1회 사용시 총 딜량(1사이클)", f"{total_dmg:,.0f}")
            st.metric("총 스킬에너지당 딜량 (Σ(각 딜/각 스킬에너지))", f"{total_dmg_per_mp_sum:,.2f}")

            rows = []
            for name, v in detail.items():
                rows.append(
                    {
                        "캐릭터": name,
                        "수량": int(v["count"]),
                        "총딜(기대값)": int(round(v["damage"])),
                        "총스킬에너지": int(v["mp"]),
                        "합산(각 딜/각 스킬에너지)": float(f"{v['dmg_per_mp_sum']:.2f}"),
                    }
                )

            st.caption("캐릭터별 합산(참고)")
            st.dataframe(rows, use_container_width=True)

            if use_boss_hp:
                _render_boss_hp_result(
                    party=party,
                    boss_hp=boss_hp,
                    boss_hp_inc_on=boss_hp_inc_on,
                    boss_hp_inc_pct=boss_hp_inc_pct,
                    party5_on=party5_on,
                    total_dmg=total_dmg,
                    total_mp=total_mp,
                    total_dmg_per_mp_sum=total_dmg_per_mp_sum,
                    common_damage_buff_pct=common_damage_buff_pct,
                    stone_crit_buff_pct=stone_crit_buff_pct,
                    weakness_bonus_by_color=weakness_bonus_by_color,
                    energy_decrease_by_color=energy_decrease_by_color,
                    use_game_speed_model=use_game_speed_model,
                    game_speed_buff_pct=game_speed_buff_pct,
                )

        except Exception as e:
            st.error(str(e))


def _render_boss_hp_result(
    party,
    boss_hp,
    boss_hp_inc_on,
    boss_hp_inc_pct,
    party5_on,
    total_dmg,
    total_mp,
    total_dmg_per_mp_sum,
    common_damage_buff_pct,
    stone_crit_buff_pct,
    weakness_bonus_by_color,
    energy_decrease_by_color,
    use_game_speed_model,
    game_speed_buff_pct,
):
    effective_boss_hp = boss_hp if boss_hp is not None else 0.0

    if boss_hp_inc_on:
        effective_boss_hp *= 1.0 + boss_hp_inc_pct / 100.0

    if party5_on:
        effective_boss_hp *= 5.0

    boss_list = ["두억시니", "사마귀", "무쇠꾼", "크치뱀"]

    selected_boss = st.selectbox(
        "보스 선택",
        boss_list,
        index=3,
        key="tab1_boss_select",
    )

    boss_speed_alpha = GAME_SPEED_ALPHA_BY_BOSS.get(selected_boss, DEFAULT_GAME_SPEED_ALPHA)

    dps_ratio_async = compute_async_dps_ratio(
        party=party,
        common_damage_buff=common_damage_buff_pct / 100.0,
        stone_crit_buff=stone_crit_buff_pct / 100.0,
        weakness_bonus_by_color=weakness_bonus_by_color,
        energy_decrease_by_color=energy_decrease_by_color,
        game_speed_buff=game_speed_buff_pct / 100.0,
        game_speed_alpha=boss_speed_alpha if use_game_speed_model else 0.0,
    )

    p_effective = total_dmg_per_mp_sum * dps_ratio_async
    dps_drop_async_pct = (dps_ratio_async - 1.0) * 100.0

    st.write(f"- (비동기합산) 실효 딜 변화율 : **{dps_drop_async_pct:+.2f}%**")

    required_energy_base = effective_boss_hp / total_dmg_per_mp_sum

    ref_required_norm, _, _ = compute_energy_limit_weighted(
        boss=selected_boss,
        party=party,
        k=5,
        power=1.0,
    )

    st.write(f"- 필요 총 에너지(required_energy = boss_hp / P): **{required_energy_base:,.0f}**")
    st.write(f"- 기준 정규화 한계(ref_required_norm, 가중평균): **{ref_required_norm:,.0f}**")

    cycles = math.ceil(effective_boss_hp / total_dmg) if total_dmg > 0 else 0
    effective_total_dmg_async = total_dmg * dps_ratio_async
    cycles_with_energy_async = math.ceil(effective_boss_hp / effective_total_dmg_async) if effective_total_dmg_async > 0 else 0

    show_async_block = use_game_speed_model or bool(energy_decrease_by_color)

    render_clear_judge_box(
        boss=selected_boss,
        boss_hp=effective_boss_hp,
        P=total_dmg_per_mp_sum,
        party=party,
        key_prefix="tab1_judge_base",
        show_match_info=False,
        k_profiles=5,
        weight_power=1.0,
        title="정규화 클리어 판정 (겜속 미반영)",
        show_notice=True,
    )

    if show_async_block:
        st.markdown("---")
        render_clear_judge_box(
            boss=selected_boss,
            boss_hp=effective_boss_hp,
            P=p_effective,
            party=party,
            key_prefix="tab1_judge_speed",
            show_match_info=True,
            k_profiles=5,
            weight_power=1.0,
            title="정규화 클리어 판정 (에너지감소, 겜속 반영)",
            show_notice=False,
        )

    st.write(f"- 필요 파티 사이클: **{cycles} 회**")

    if show_async_block:
        st.write(f"- (에너지감소, 겜속 반영) 필요 파티 사이클: **{cycles_with_energy_async} 회**")
        st.caption("※ 에너지감소 반영 (Σ(딜/요구 스킬젬량)) 기반으로 시간당 딜 감소를 반영해 보스 처치 사이클을 재산정한 값")

    st.write(f"- 예상 총 스킬에너지 소모: **{cycles * total_mp:,}**")

    if show_async_block:
        st.write(f"- (에너지감소, 겜속 반영) 예상 총 스킬에너지 소모: **{cycles_with_energy_async * total_mp:,}**")