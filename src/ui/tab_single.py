
import math
from typing import Dict

import streamlit as st

from src.characters import CHARACTER_DB
from src.constants import COLOR_OPTIONS, JOB_OPTIONS, JOB_PARTY_CONDITION_MIN_COUNT
from src.party_parser import build_party_from_text
from src.calculator import calculate_party, compute_async_dps_ratio
from src.boss_config import (
    GAME_SPEED_ALPHA_BY_BOSS,
    DEFAULT_GAME_SPEED_ALPHA,
    DEFAULT_JOB_ENERGY_ALPHA,
    BOSS_LIST,
    DEFAULT_BOSS,
    get_job_energy_alpha_by_job,
)
from src.clear_judge import render_clear_judge_box, compute_energy_limit_weighted
from src.jobs import (
    build_job_assignments_from_text,
    resolve_job_per_instance,
    validate_job_assignment_counts,
    total_job_assigned_count,
    compute_party_energy_bonus_pct,
)
from src.stones import party_size_condition_bonus_pct, compute_avg_defense_effect_pct


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

    # ============================
    # ✅ 신규 직업 시스템 & 신규 소환석 옵션 (2026 업데이트)
    # ============================
    job_text = ""
    job_condition_on = False
    job_condition_min = JOB_PARTY_CONDITION_MIN_COUNT
    job_condition_bonus_pct = 0.0
    job_damage_buff_by_job: Dict[str, float] = {}
    energy_increase_by_color: Dict[str, float] = {}
    weaken_on = False
    strengthen_on = False

    with st.expander("🆕 직업 시스템 & 신규 소환석 옵션", expanded=False):
        st.caption(
            "직업은 데미지에는 영향 없음 (스킬 에너지 충전 속도에만 영향). "
            "지정하지 않은 캐릭터는 '방패지기'와 동일(보너스 없음)하게 취급됨. "
            "한 사람이 데미지 스킬 2개를 들면, '스+캡 회 1' 처럼 "
            "'+'로 묶어서 같은 직업으로 한번에 배정 가능."
        )

        job_text = st.text_input(
            "파티원 직업 구성 (같은 캐릭터도 장마다 다른 직업 가능)",
            value="",
            key="tab1_job_text",
            help=(
                f"직업 종류: {', '.join(JOB_OPTIONS)} (방/젤/회 로 줄여써도 인식됨) / "
                "'캐릭터 직업 인원수' 세 개씩 묶어서 입력. "
                "예) 비트 방 2 비트 회 3 레판 젤 1 "
                "(비트 5장 중 2장은 방패지기, 3장은 회피도사) / "
                "한 사람이 스킬 2개를 들면 '스네이크+캡틴아이스 회 1'처럼 +로 묶기 "
                "(두번째가 회복기 등 데미지 없는 스킬이면 자동 무시됨)"
            ),
        )

        st.markdown("---")
        st.markdown("#### 소환석: 직업 2명↑ 조건부 전체 피해 증가")
        job_condition_on = st.checkbox("적용", key="tab1_job_condition_on")
        if job_condition_on:
            job_condition_min = st.number_input(
                "최소 인원 조건", min_value=1, value=JOB_PARTY_CONDITION_MIN_COUNT,
                step=1, key="tab1_job_condition_min",
            )
            job_condition_bonus_pct = st.number_input(
                "조건 충족시 전체 피해 증가(%)", min_value=0.0, value=0.0,
                step=1.0, key="tab1_job_condition_bonus",
            )

        st.markdown("#### 소환석: 직업별 캐릭터 피해량 증가")
        for job in JOB_OPTIONS:
            on = st.checkbox(f"{job} 피해 증가 적용", key=f"tab1_job_dmg_on_{job}")
            if on:
                pct = st.number_input(
                    f"{job} 피해 증가(%)", min_value=-100.0, max_value=300.0,
                    value=0.0, step=1.0, key=f"tab1_job_dmg_pct_{job}",
                )
                job_damage_buff_by_job[job] = pct / 100.0

        st.markdown("#### 소환석: 색상별 에너지 획득량 증가/감소")
        st.caption("양수(+)면 획득량 증가, 음수(-)면 감소로 처리돼요.")
        for color in COLOR_OPTIONS:
            on = st.checkbox(f"{color} 에너지 획득량 증감 적용", key=f"tab1_energy_inc_on_{color}")
            if on:
                pct = st.number_input(
                    f"{color} 에너지 획득량 증감(%) (+면 증가, -면 감소)",
                    min_value=-300.0, max_value=300.0,
                    value=0.0, step=1.0, key=f"tab1_energy_inc_pct_{color}",
                )
                energy_increase_by_color[color] = pct / 100.0

        st.markdown("#### 소환석: 몬스터 방어력 약화/강화")
        st.caption("지속시간·발생주기·피해율은 고정값이라, 해당 보스에 적용되는지만 체크하면 돼요.")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            weaken_on = st.checkbox("방어력 약화 있음", key="tab1_weaken_on")
        with col_d2:
            strengthen_on = st.checkbox("방어력 강화 있음", key="tab1_strengthen_on")

    use_boss_hp = st.checkbox("보스 체력 기준 계산")
    boss_hp = None

    boss_hp_inc_on = False
    boss_hp_inc_pct = 0.0
    party5_on = False
    selected_boss = DEFAULT_BOSS

    if use_boss_hp:
        selected_boss = st.selectbox(
            "보스 선택",
            BOSS_LIST,
            index=BOSS_LIST.index(DEFAULT_BOSS),
            key="tab1_boss_select",
        )

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

            job_assignments = build_job_assignments_from_text(job_text)
            job_per_instance = resolve_job_per_instance(party, job_assignments)

            for w in validate_job_assignment_counts(party, job_assignments):
                st.warning(w)

            job_assigned_count = total_job_assigned_count(job_per_instance)

            job_condition_bonus = (
                party_size_condition_bonus_pct(job_assigned_count, job_condition_min, job_condition_bonus_pct)
                if job_condition_on
                else 0.0
            )

            defense_avg_pct = compute_avg_defense_effect_pct(
                weaken_on=weaken_on,
                strengthen_on=strengthen_on,
            )

            effective_common_damage_buff_pct = common_damage_buff_pct + job_condition_bonus + defense_avg_pct

            job_energy_bonus_pct = compute_party_energy_bonus_pct(
                party=party,
                job_per_instance=job_per_instance,
            )

            total_dmg, total_dmg_per_mp_sum, total_mp, party_buff, lepain_buff, detail = calculate_party(
                party=party,
                common_damage_buff=effective_common_damage_buff_pct / 100.0,
                stone_crit_buff=stone_crit_buff_pct / 100.0,
                weakness_bonus_by_color=weakness_bonus_by_color,
                energy_decrease_by_color=energy_decrease_by_color,
                energy_increase_by_color=energy_increase_by_color,
                job_per_instance=job_per_instance,
                job_damage_buff_by_job=job_damage_buff_by_job,
            )

            st.session_state["LAST_CALC_OPTS"] = {
                "weakness_colors": list(weakness_colors),
                "weakness_bonus_by_color": dict(weakness_bonus_by_color),
                "energy_decrease_by_color": dict(energy_decrease_by_color),
                "energy_increase_by_color": dict(energy_increase_by_color),
                "common_damage_buff_pct": float(common_damage_buff_pct),
                "stone_crit_buff_pct": float(stone_crit_buff_pct),
                "job_per_instance": list(job_per_instance),
                "job_damage_buff_by_job": dict(job_damage_buff_by_job),
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

            if energy_increase_by_color:
                iepretty = ", ".join([f"{k}(+{v * 100:.0f}%)" for k, v in energy_increase_by_color.items()])
                st.write(f"- 에너지획득량증가(색별): **{iepretty}**")

            if use_game_speed_model:
                st.write(f"- 게임속도 증가율: **{game_speed_buff_pct:.0f}%** (보스별 보정 적용)")
            else:
                st.write("- 게임속도 증가율: **미적용**")

            st.write(f"- 공통 피해증가율: **{common_damage_buff_pct:.0f}%** (전원 적용)")

            if job_condition_on:
                st.write(f"- 직업 {job_condition_min}명↑ 조건부 전체피해: **{job_condition_bonus:+.1f}%** (직업 배정 인원: {job_assigned_count}명)")

            if job_damage_buff_by_job:
                jpretty = ", ".join([f"{k}(+{v*100:.0f}%)" for k, v in job_damage_buff_by_job.items()])
                st.write(f"- 직업별 피해 증가: **{jpretty}**")

            if weaken_on or strengthen_on:
                st.write(f"- 방어약화/강화 시간가중평균 피해변화: **{defense_avg_pct:+.2f}%**")

            if job_assigned_count > 0:
                st.write(f"- 직업 에너지 보너스(파티 평균, 정보용): **{job_energy_bonus_pct:+.2f}%** (실제 계산은 캐릭터별로 개별 반영됨)")

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
                    selected_boss=selected_boss,
                    boss_hp=boss_hp,
                    boss_hp_inc_on=boss_hp_inc_on,
                    boss_hp_inc_pct=boss_hp_inc_pct,
                    party5_on=party5_on,
                    total_dmg=total_dmg,
                    total_mp=total_mp,
                    total_dmg_per_mp_sum=total_dmg_per_mp_sum,
                    common_damage_buff_pct=effective_common_damage_buff_pct,
                    stone_crit_buff_pct=stone_crit_buff_pct,
                    weakness_bonus_by_color=weakness_bonus_by_color,
                    energy_decrease_by_color=energy_decrease_by_color,
                    energy_increase_by_color=energy_increase_by_color,
                    job_per_instance=job_per_instance,
                    job_damage_buff_by_job=job_damage_buff_by_job,
                    use_game_speed_model=use_game_speed_model,
                    game_speed_buff_pct=game_speed_buff_pct,
                )

        except Exception as e:
            st.error(str(e))


def _render_boss_hp_result(
    party,
    selected_boss,
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
    energy_increase_by_color=None,
    job_per_instance=None,
    job_damage_buff_by_job=None,
):
    energy_increase_by_color = energy_increase_by_color or {}
    job_per_instance = job_per_instance if job_per_instance is not None else [None] * len(party)
    job_damage_buff_by_job = job_damage_buff_by_job or {}
    effective_boss_hp = boss_hp if boss_hp is not None else 0.0

    if boss_hp_inc_on:
        effective_boss_hp *= 1.0 + boss_hp_inc_pct / 100.0

    if party5_on:
        effective_boss_hp *= 5.0

    boss_speed_alpha = GAME_SPEED_ALPHA_BY_BOSS.get(selected_boss, DEFAULT_GAME_SPEED_ALPHA)
    boss_job_energy_alpha_by_job = get_job_energy_alpha_by_job(
        boss_name=selected_boss,
        boss_hp_total=effective_boss_hp,
        party_size=len(party),
    )

    dps_ratio_async = compute_async_dps_ratio(
        party=party,
        common_damage_buff=common_damage_buff_pct / 100.0,
        stone_crit_buff=stone_crit_buff_pct / 100.0,
        weakness_bonus_by_color=weakness_bonus_by_color,
        energy_decrease_by_color=energy_decrease_by_color,
        energy_increase_by_color=energy_increase_by_color,
        job_per_instance=job_per_instance,
        job_damage_buff_by_job=job_damage_buff_by_job,
        game_speed_buff=game_speed_buff_pct / 100.0,
        game_speed_alpha=boss_speed_alpha if use_game_speed_model else 0.0,
        job_energy_alpha=DEFAULT_JOB_ENERGY_ALPHA,
        job_energy_alpha_by_job=boss_job_energy_alpha_by_job,
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

    show_async_block = (
        use_game_speed_model
        or bool(energy_decrease_by_color)
        or bool(energy_increase_by_color)
        or any(j is not None for j in job_per_instance)
    )

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
            title="정규화 클리어 판정 (에너지감소, 겜속, 직업 반영)",
            show_notice=False,
            norm_field="ref_required_norm_adjusted",
        )

    st.write(f"- 필요 파티 사이클: **{cycles} 회**")

    if show_async_block:
        st.write(f"- (에너지감소, 겜속 반영) 필요 파티 사이클: **{cycles_with_energy_async} 회**")
        st.caption("※ 에너지감소 반영 (Σ(딜/요구 스킬젬량)) 기반으로 시간당 딜 감소를 반영해 보스 처치 사이클을 재산정한 값")

    st.write(f"- 예상 총 스킬에너지 소모: **{cycles * total_mp:,}**")

    if show_async_block:
        st.write(f"- (에너지감소, 겜속 반영) 예상 총 스킬에너지 소모: **{cycles_with_energy_async * total_mp:,}**")