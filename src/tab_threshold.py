import math
import json
import streamlit as st
from typing import Dict, Any
from src.boss_limits_store import get_limits_store, save_limits
from src.constants import COLOR_OPTIONS, JOB_OPTIONS, JOB_PARTY_CONDITION_MIN_COUNT

# ✅ clear_judge.py에 아래 함수가 있어야 함:
# - party_to_mp_share_vector(party) -> Dict[str, float]
from src.clear_judge import party_to_mp_share_vector
from src.jobs import build_job_assignments_from_text, resolve_job_per_instance, total_job_assigned_count
from src.calculator import compute_async_dps_ratio
from src.stones import party_size_condition_bonus_pct, compute_avg_defense_effect_pct
from src.boss_config import (
    GAME_SPEED_ALPHA_BY_BOSS,
    DEFAULT_GAME_SPEED_ALPHA,
    get_job_energy_alpha_by_job,
    get_score_double_alpha,
    get_score_double_evasion_extra_alpha,
    get_color_energy_alpha,
)


def render_threshold_tab(COLOR_OPTIONS, build_party_from_text, calculate_party, admin_mode: bool = False):
    st.subheader("📌 파티사이클 클리어 여부 경계값 (정규화 적용)")

    # 보스 목록
    BOSS_LIST = ["아수라", "사마귀", "두억시니", "무쇠꾼", "크치뱀"]

    boss = st.selectbox("보스 선택", BOSS_LIST, index=0)

    st.markdown("### 조건")
    
    BOSS_CONDITIONS = {
        "아수라": [
            "주술 미루는 빌드에 능숙한 5인 파티",
            "스젤많, 특정젤리떨어짐, 모든점수 2배 옵션 반영하지 않음",
            "몬스터 방어력 약화/강화 옵션은 중복되지 않는다고 가정",
            "빌드에 따른 스킬별 유불리사항을 반영하지않음"
        ],

        "사마귀": [
            "게임속도 증가 없음",
            "보스 약화에 따른 딜량 증가를 반영하지 않음",
            "빌드에 능숙한 5인 파티",
            "4페를 어느정도 버틸 수 있을 만큼, 체력 여유가 있는 상태",
        ],
    
        "두억시니": [
            "게임속도 증가 없음",
            "빌드에 능숙한 5인 파티",
            "공주런 끝으로 4페 절반 수 있음",
        ],
    
        "무쇠꾼": [
            "게임속도 증가, 스킬에너지젤리 떨어짐, 모든점수 2배 옵션 반영하지 않음",
            "스킬에 따라 다른 딜레이로 발생하는 빌드 유불리사항을 반영하지 않음",
            "고렙돌 전용 빌드(얼기 실패 후 소화기먹고 3페 진입)에 능숙한 5인 파티",
        ],
    
        "크치뱀": [
            "게임속도 증가, 스킬에너지젤리 떨어짐, 모든점수 2배 옵션 반영하지 않음",
            "스킬에 따라 다른 딜레이로 발생하는 빌드 유불리사항을 반영하지 않음",
            "고렙돌 전용 빌드(발판 49개 맞추고 3페 진입)에 능숙한 5인 파티",
        ],
    }
    
    conditions = BOSS_CONDITIONS.get(boss, [])
    
    for c in conditions:
        st.write(f"- {c}")
    
    st.markdown("---")
    # ✅ party_type은 '표시/추천용 라벨'로만 유지 (판정에서는 무시)
    party_type_label = st.radio(
        "파티 유형 선택(표시/추천용)",
        ["빨강(주로 비트 구성)", "빨강(주로 인삼 구성)",
         "파랑(눈설탕, 캡아 구성)", "노랑(주로 스네 구성)"],
        index=0
    )


    # 🔒 관리자 영역
    if admin_mode:
        # 🔐 운영자 인증 (비밀번호: 0930)
        if "IS_ADMIN" not in st.session_state:
            st.session_state["IS_ADMIN"] = False

        st.markdown("### 🔐 운영자 인증")
        # ✅ admin auth keys (boss별로 유니크)
        pw = st.text_input("관리자 비밀번호", type="password", key=f"admin_pw_input_{boss}")
        
        colA, colB = st.columns(2)
        with colA:
            if st.button("로그인", key=f"admin_login_btn_{boss}"):
                st.session_state["IS_ADMIN"] = (pw == "0930")
        with colB:
            if st.button("로그아웃", key=f"admin_logout_btn_{boss}"):
                st.session_state["IS_ADMIN"] = False

        is_admin = bool(st.session_state["IS_ADMIN"])
        if not is_admin:
            st.info("관리자 기능(저장/삭제)은 비밀번호 인증 후 사용 가능해요.")
            return


        # (관리자 인증 통과 후)
        
        st.markdown("### 🔎 현재 세션 BOSS_LIMITS 상태")
        
        colR1, colR2 = st.columns([1, 2])
        with colR1:
            if st.button("🔄 GitHub에서 기준 다시 불러오기", key=f"reload_limits_{boss}"):
                try:
                    from boss_limits_store import load_limits
                    load_limits()  # GitHub -> session_state 갱신
                    st.success("GitHub 기준으로 세션을 갱신했어.")
        
                    # ✅ 여기서 바로 다시 읽어서 즉시 반영된 값을 화면에 보여주기
                    store = get_limits_store()
                    st.caption(f"SHA: {st.session_state.get('BOSS_LIMITS_SHA')}")
                    st.json(store)
                except Exception as e:
                    st.error(f"리로드 실패: {e}")
        
        with colR2:
            st.caption(f"SHA: {st.session_state.get('BOSS_LIMITS_SHA')}")
        
        # ✅ 기본 표시 (버튼 안 눌러도 항상 현재값 보이게)
        store = get_limits_store()
        st.json(store)

        
        st.markdown("### 📤/📥 기준 데이터 내보내기/가져오기")
        
        store = get_limits_store()
        json_str = json.dumps(store, ensure_ascii=False, indent=2)
        
        st.download_button(
            label="📤 현재 기준(JSON) 다운로드",
            data=json.dumps(store, ensure_ascii=False, indent=2),
            file_name="boss_limits.json",
            mime="application/json",
        )
                
        uploaded = st.file_uploader("📥 boss_limits.json 업로드(가져오기)", type=["json"], key="upload_limits_json")
        
        if uploaded is not None:
            try:
                new_store = json.load(uploaded)
                st.session_state["BOSS_LIMITS"] = new_store  # 세션에 즉시 반영
                save_limits(new_store)  # (로컬이면 파일도 갱신, 클라우드는 일단 시도)
                st.success("가져오기 완료! (세션에 반영됨) 필요하면 앱 rerun 해줘.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
                
        st.markdown("### ✅ 정규화 기준 저장(캘리브레이션)")
        st.caption("관리자가 기준 파티/경계 사이클을 저장하면 boss_limits.json에 반영되어 모든 접속자에게 동일하게 적용돼요.")
        st.caption("※ 저장은 party_type을 '분류로 쓰지 않고', 보스별 profiles 풀에 누적 저장됩니다. (판정 시 자동 거리/가중치로 사용)")

        # 기준 파티 기본값(라벨에 따라 추천만)
        default_party = {
            "빨강(주로 비트 구성)": "비트 1 레판 4",
            "빨강(주로 인삼 구성)": "인삼 3 비트 1 레판 1",
            "파랑(눈설탕, 캡아 구성)": "눈설탕 3 캡틴아이스 1",
            "노랑(주로 스네 구성)": "스네이크 3 캡틴아이스 1",
        }.get(party_type_label, "스네이크 3 캡틴아이스 1")

        ref_party_text = st.text_input(
            "기준 파티(텍스트)",
            value=default_party,
            key=f"ref_party_{boss}_{party_type_label}"
        )

        # 기본 경계 사이클(라벨 기준 추천만)
        default_cycles_map = {
            "사마귀": {
                "빨강(주로 비트 구성)": 110,
                "파랑(눈설탕, 캡아 구성)": 110,
                "노랑(주로 스네 구성)": 155,
                "빨강(주로 인삼 구성)": 110,
            },
            "두억시니": {
                "빨강(주로 비트 구성)": 125,
                "파랑(눈설탕, 캡아 구성)": 125,
                "노랑(주로 스네 구성)": 170,
                "빨강(주로 인삼 구성)": 125,
            }
        }
        default_cycles = default_cycles_map.get(boss, {}).get(party_type_label, 110)

        threshold_cycles = st.number_input(
            "경계 파티사이클(회)",
            min_value=1,
            value=int(default_cycles),
            step=1,
            key=f"threshold_cycles_{boss}_{party_type_label}"
        )

        st.markdown("#### 이 기준 파티가 실전에서 실제로 썼던 조건")
        st.caption(
            "⚠️ 중요: 위 '경계 파티사이클'은 이미 이 조건들이 반영된 실측값이에요. "
            "여기에 그 실제 조건을 같이 적어두면, 나중에 다른 파티랑 비교할 때 "
            "직업/겜속 보너스가 이중으로 계산되는 걸 막아줘요."
        )
        st.caption(
            "🆕 아래 버프 항목들은 이제 여기서 **직접 입력**해요 (예전엔 '단일 파티 계산' 탭에서 "
            "마지막으로 계산했던 값을 몰래 그대로 가져다 썼는데, 관리자가 인지 못 하고 "
            "엉뚱한 값이 저장될 수 있어서 없앴습니다)."
        )

        col_buff1, col_buff2 = st.columns(2)
        with col_buff1:
            common_damage_buff_pct = st.number_input(
                "이 기준 파티가 실제로 썼던 공통 피해증가율(%)",
                min_value=0.0,
                value=0.0,
                step=1.0,
                key=f"ref_common_buff_{boss}_{party_type_label}",
            )
        with col_buff2:
            stone_crit_buff_pct = st.number_input(
                "이 기준 파티가 실제로 썼던 치명타 피해 증가율(%)",
                min_value=0.0,
                value=0.0,
                step=1.0,
                key=f"ref_crit_buff_{boss}_{party_type_label}",
            )

        ref_weakness_colors = st.multiselect(
            "이 기준 파티가 실제로 받았던 약점 색 (최대 2개)",
            options=COLOR_OPTIONS,
            default=[],
            key=f"ref_weakness_colors_{boss}_{party_type_label}",
        )
        weakness_bonus_by_color: Dict[str, float] = {}
        for wc in ref_weakness_colors:
            wc_pct = st.number_input(
                f"{wc} 색깔만의 조건부 피해증감율(%)",
                value=0.0,
                step=1.0,
                key=f"ref_weakness_pct_{boss}_{party_type_label}_{wc}",
            )
            weakness_bonus_by_color[wc] = wc_pct / 100.0

        energy_decrease_by_color: Dict[str, float] = {}
        with st.expander("색상별 에너지 획득량 증감 (필요할 때만 펼치기)", expanded=False):
            for c in COLOR_OPTIONS:
                c_on = st.checkbox(f"{c} 에너지 획득량 증감 적용", key=f"ref_energy_on_{boss}_{party_type_label}_{c}")
                if c_on:
                    c_pct = st.number_input(
                        f"{c} 에너지 획득량 증감(%) (+면 증가, -면 감소)",
                        value=0.0,
                        step=1.0,
                        key=f"ref_energy_pct_{boss}_{party_type_label}_{c}",
                    )
                    energy_decrease_by_color[c] = -c_pct / 100.0

        ref_job_text = st.text_input(
            "이 기준 파티가 실제로 썼던 직업 구성 (없으면 비워두기)",
            value="",
            key=f"ref_job_text_{boss}_{party_type_label}",
            help="예) 스+캡 회 1 스+연 회 3 스+석 회 1",
        )

        ref_game_speed_pct = st.number_input(
            "이 기준 파티가 실제로 썼던 게임속도 증가율(%)",
            min_value=0.0,
            value=0.0,
            step=1.0,
            key=f"ref_game_speed_{boss}_{party_type_label}",
        )

        ref_score_double_on = st.checkbox(
            "🆕 이 기준 파티가 실제로 '모든 점수 2배' 옵션을 썼음",
            key=f"ref_score_double_on_{boss}_{party_type_label}",
        )

        ref_boss_hp_for_alpha = st.number_input(
            "이 기준 파티가 클리어 당시 보스 체력(선택, 체력구간별 alpha 판정용)",
            min_value=0.0,
            value=0.0,
            step=1_000_000.0,
            format="%.0f",
            key=f"ref_boss_hp_alpha_{boss}_{party_type_label}",
            help="모르면 0으로 두면 됨(그러면 저체력 구간 alpha로 계산됨)",
        )

        st.markdown("#### 🆕 체력 임계값 앵커 지정")
        st.caption(
            "이 프로필을 '체력 임계값 앵커'로 지정하면, 조회하는 보스 체력이 "
            "**이 앵커가 담당하는 체력 상한 이하일 때, 그 이하 체력의 프로필들로만 좁혀서** "
            "비교해요. (예: 700레벨부터 난이도가 급변하는데, 그 직전의 "
            "빡빡하게 깬 돌을 앵커로 지정하면, 그보다 체력 낮은 돌들은 이 프로필 "
            "위주로 비교됨 — 위쪽 티어의 쉬운/어려운 프로필과 안 섞임)"
        )
        is_hp_ceiling_anchor = st.checkbox(
            "이 프로필을 체력 임계값 앵커로 지정",
            key=f"hp_anchor_{boss}_{party_type_label}",
        )

        anchor_ceiling_hp = 0.0
        if is_hp_ceiling_anchor:
            anchor_ceiling_hp = st.number_input(
                "이 앵커가 담당하는 체력 상한선 (비워두면 이 프로필 자체의 실제 체력을 상한으로 씀)",
                min_value=0.0,
                value=0.0,
                step=1_000_000.0,
                format="%.0f",
                key=f"anchor_ceiling_{boss}_{party_type_label}",
                help=(
                    "⚠️ 이 프로필 '자신'의 체력과 다른 값이어도 됨. "
                    "예: 이 프로필이 700레벨 돌(체력 42,000,000,000)인데, "
                    "701~705레벨까지도 같은 메커니즘이라고 판단되면, "
                    "여기에 705레벨의 예상 체력(더 큰 숫자)을 넣어서 "
                    "그 범위까지 이 앵커가 계속 담당하게 만들 수 있음. "
                    "0으로 두면 이 프로필 자체의 체력이 상한이 됨(기존 동작과 동일)."
                ),
            )

        st.markdown("#### 🆕 소환석: 직업 2명↑ 조건부 전체 피해 증가")
        ref_job_condition_on = st.checkbox(
            "적용", key=f"ref_job_condition_on_{boss}_{party_type_label}"
        )
        ref_job_condition_min = JOB_PARTY_CONDITION_MIN_COUNT
        ref_job_condition_bonus_pct = 0.0
        if ref_job_condition_on:
            ref_job_condition_min = st.number_input(
                "최소 인원 조건", min_value=1, value=JOB_PARTY_CONDITION_MIN_COUNT,
                step=1, key=f"ref_job_condition_min_{boss}_{party_type_label}",
            )
            ref_job_condition_bonus_pct = st.number_input(
                "조건 충족시 전체 피해 증가(%)", min_value=0.0, value=0.0,
                step=1.0, key=f"ref_job_condition_bonus_{boss}_{party_type_label}",
            )

        st.markdown("#### 🆕 소환석: 직업별 캐릭터 피해량 증가")
        ref_job_damage_buff_by_job: Dict[str, float] = {}
        for job in JOB_OPTIONS:
            on = st.checkbox(
                f"{job} 피해 증가 적용", key=f"ref_job_dmg_on_{boss}_{party_type_label}_{job}"
            )
            if on:
                pct = st.number_input(
                    f"{job} 피해 증가(%)", min_value=-100.0, max_value=300.0,
                    value=0.0, step=1.0, key=f"ref_job_dmg_pct_{boss}_{party_type_label}_{job}",
                )
                ref_job_damage_buff_by_job[job] = pct / 100.0

        st.markdown("#### 🆕 소환석: 몬스터 방어력 약화/강화")
        st.caption("지속시간·발생주기·피해율은 고정값이라, 이 기준 파티가 그 옵션이 있는 보스를 상대했는지만 체크하면 돼요.")
        col_wd1, col_wd2 = st.columns(2)
        with col_wd1:
            ref_weaken_on = st.checkbox("방어력 약화 있음", key=f"ref_weaken_on_{boss}_{party_type_label}")
        with col_wd2:
            ref_strengthen_on = st.checkbox("방어력 강화 있음", key=f"ref_strengthen_on_{boss}_{party_type_label}")

        # ✅ 저장 버튼
        if st.button("✅ 이 보스 기준 프로필 저장(party_type 무시)", key=f"save_profile_{boss}_{party_type_label}"):
            try:
                party = build_party_from_text(ref_party_text)

                # ✅ 직업 배정 먼저 만들어서(탭1과 동일 순서), 직업 2명↑ 조건부 보너스와
                #    방어약화/강화 평균을 공통피해증가율에 합친 뒤(effective) 계산에 반영
                ref_job_assignments = build_job_assignments_from_text(ref_job_text)
                ref_job_per_instance = resolve_job_per_instance(party, ref_job_assignments)

                ref_job_assigned_count = total_job_assigned_count(ref_job_per_instance)
                ref_job_condition_bonus = (
                    party_size_condition_bonus_pct(
                        ref_job_assigned_count, ref_job_condition_min, ref_job_condition_bonus_pct
                    )
                    if ref_job_condition_on
                    else 0.0
                )
                ref_defense_avg_pct = compute_avg_defense_effect_pct(
                    weaken_on=ref_weaken_on,
                    strengthen_on=ref_strengthen_on,
                )
                effective_common_damage_buff_pct = (
                    common_damage_buff_pct + ref_job_condition_bonus + ref_defense_avg_pct
                )

                # 기준 파티 계산 (실제로 썼던 직업/버프까지 반영)
                total_dmg, total_dmg_per_mp_sum, total_mp, _, _, _ = calculate_party(
                    party=party,
                    common_damage_buff=effective_common_damage_buff_pct / 100.0,
                    stone_crit_buff=stone_crit_buff_pct / 100.0,
                    weakness_bonus_by_color=weakness_bonus_by_color,
                    energy_decrease_by_color=energy_decrease_by_color,
                    job_per_instance=ref_job_per_instance,
                    job_damage_buff_by_job=ref_job_damage_buff_by_job,
                    color_energy_alpha=get_color_energy_alpha(boss),
                )
                ref_vec = party_to_mp_share_vector(party)
                if not ref_vec:
                    raise ValueError("ref_vec 생성 실패(mp_cost 확인).")
                
                P = float(total_dmg_per_mp_sum)
                if P <= 0:
                    raise ValueError("기준 파티의 P값이 0 이하입니다.")
                
                boss_hp_est = float(threshold_cycles) * float(total_dmg)   # ✅ 보스 체력(상대값) 추정 (참고용)

                # ✅ "실제 보스체력"(ref_boss_hp_for_alpha)을 입력했으면 그걸로 계산
                #    (tab1 조회 때 required_energy = 실제입력체력/P 와 완전히 같은 공식이 되어야
                #     같은 조건으로 저장/조회했을 때 여유율이 0%에 수렴함). 안 입력했으면(0)
                #    기존처럼 boss_hp_est(파티사이클 기반 추정)로 폴백.
                if ref_boss_hp_for_alpha and float(ref_boss_hp_for_alpha) > 0:
                    ref_required_norm = float(ref_boss_hp_for_alpha) / P
                else:
                    ref_required_norm = boss_hp_est / P

                # ✅ 이 기준 파티가 "실제로 썼던" 직업/겜속을 반영한 adjusted 기준값도 계산
                #    (이걸 안 만들면, 나중에 새 파티 조회할 때 직업/겜속 보너스가
                #     기준값에 한 번(암묵적으로), 쿼리 계산에 또 한 번, 이중으로 들어감)
                ref_alpha_map = get_job_energy_alpha_by_job(
                    boss_name=boss,
                    boss_hp_total=ref_boss_hp_for_alpha,
                    party_size=len(party),
                )
                ref_speed_alpha = GAME_SPEED_ALPHA_BY_BOSS.get(boss, DEFAULT_GAME_SPEED_ALPHA)

                ref_dps_ratio_async = compute_async_dps_ratio(
                    party=party,
                    common_damage_buff=effective_common_damage_buff_pct / 100.0,
                    stone_crit_buff=stone_crit_buff_pct / 100.0,
                    weakness_bonus_by_color=weakness_bonus_by_color,
                    energy_decrease_by_color=energy_decrease_by_color,
                    job_per_instance=ref_job_per_instance,
                    job_damage_buff_by_job=ref_job_damage_buff_by_job,
                    job_energy_alpha_by_job=ref_alpha_map,
                    game_speed_buff=ref_game_speed_pct / 100.0,
                    game_speed_alpha=ref_speed_alpha,
                    score_double_on=ref_score_double_on,
                    score_double_alpha=get_score_double_alpha(boss),
                    score_double_evasion_extra_alpha=get_score_double_evasion_extra_alpha(boss),
                    color_energy_alpha=get_color_energy_alpha(boss),
                )

                ref_required_norm_adjusted = ref_required_norm / ref_dps_ratio_async

                store = get_limits_store()
                store.setdefault(boss, {})
                store[boss].setdefault("profiles", [])
                
                store[boss]["profiles"].append({
                    "boss_hp_est": float(boss_hp_est),
                    "ref_required_norm": float(ref_required_norm),
                    "ref_required_norm_adjusted": float(ref_required_norm_adjusted),
                
                    "ref_party": ref_party_text,
                    "ref_vec": ref_vec,
                    "label": party_type_label,
                    "threshold_cycles": int(threshold_cycles),
                
                    # 참고/디버그용
                    "ref_total_dmg": float(total_dmg),
                    "ref_total_mp": int(total_mp),
                    "ref_P": float(P),
                    "ref_common_damage_buff_pct": common_damage_buff_pct,
                    "ref_stone_crit_buff_pct": stone_crit_buff_pct,
                    "ref_weakness_bonus_by_color": weakness_bonus_by_color,
                    "ref_energy_decrease_by_color": energy_decrease_by_color,

                    # 이 기준 파티가 실제로 썼던 조건 (adjusted 계산의 근거)
                    "ref_job_text": ref_job_text,
                    "ref_game_speed_pct": float(ref_game_speed_pct),
                    "ref_boss_hp_for_alpha": float(ref_boss_hp_for_alpha),
                    "ref_dps_ratio_async": float(ref_dps_ratio_async),
                    "ref_score_double_on": bool(ref_score_double_on),

                    # 🆕 체력 임계값 앵커 여부 + 담당 상한선
                    "is_hp_ceiling_anchor": bool(is_hp_ceiling_anchor),
                    "anchor_ceiling_hp": float(anchor_ceiling_hp),

                    # 🆕 이 기준 파티가 실제로 썼던 신규 직업시스템 / 소환석 옵션 (참고/재현용)
                    "ref_job_condition_on": bool(ref_job_condition_on),
                    "ref_job_condition_min": int(ref_job_condition_min),
                    "ref_job_condition_bonus_pct": float(ref_job_condition_bonus_pct),
                    "ref_job_damage_buff_by_job": dict(ref_job_damage_buff_by_job),
                    "ref_weaken_on": bool(ref_weaken_on),
                    "ref_strengthen_on": bool(ref_strengthen_on),
                    "ref_effective_common_damage_buff_pct": float(effective_common_damage_buff_pct),
                })
                
                save_limits(store)
                
                st.success(
                    f"저장 완료! (ref_required_norm(순수) = {ref_required_norm:,.2f}, "
                    f"ref_required_norm_adjusted = {ref_required_norm_adjusted:,.2f}, "
                    f"boss_hp_est = {boss_hp_est:,.0f}"
                    + (
                        f", 🆕 체력 임계값 앵커로 지정됨 (담당 상한: {anchor_ceiling_hp:,.0f})"
                        if is_hp_ceiling_anchor and anchor_ceiling_hp > 0
                        else ", 🆕 체력 임계값 앵커로 지정됨 (담당 상한 = 이 프로필 자체 체력)"
                        if is_hp_ceiling_anchor
                        else ""
                    )
                    + ")"
                )
                st.caption(f"- 기준 파티 1사이클 총 MP = {total_mp:,}")
                st.caption(f"- 기준 파티 P(Σ(dmg/eff_mp)) = {total_dmg_per_mp_sum:,.2f}")
                st.caption(f"- 기준 파티 실제 dps_ratio_async(직업/겜속 반영) = {ref_dps_ratio_async:.4f}")

            except Exception as e:
                st.error(str(e))

        # ✅ 현재 저장된 값 표시(관리자만)
        st.markdown("---")
        st.markdown("### 📦 현재 저장된 프로필(관리자)")

        store = get_limits_store()
        profs = store.get(boss, {}).get("profiles", [])

        if profs:
            st.write(f"- 보스: **{boss}** / 저장된 프로필 수: **{len(profs)}개**")

            st.markdown("### 🗑 프로필 1개 삭제(관리자)")
            sel_idx = st.selectbox(
                "삭제할 프로필 선택",
                options=list(range(len(profs))),
                format_func=lambda i: (
                    f"{i+1}. [{profs[i].get('label','-')}] "
                    f"norm={float(profs[i].get('ref_required_norm',0)):,.2f} | "
                    f"norm_adj={float(profs[i].get('ref_required_norm_adjusted', profs[i].get('ref_required_norm',0))):,.2f} | "
                    f"boss_hp_est={float(profs[i].get('boss_hp_est',0)):,.0f} | "
                    f"{profs[i].get('ref_party','')}"
                ),
                key=f"del_profile_idx_{boss}"
            )

            col_del1, col_del2 = st.columns([1, 2])
            with col_del1:
                confirm = st.checkbox("삭제 확인", key=f"del_confirm_{boss}")
            with col_del2:
                if st.button("선택 프로필 삭제", key=f"del_btn_{boss}", disabled=not confirm):
                    try:
                        profs.pop(sel_idx)
                        store[boss]["profiles"] = profs
                        save_limits(store)
                        st.success("선택한 프로필을 삭제했어. (모든 유저에게 즉시 반영)")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            st.markdown("---")
            show_n = min(10, len(profs))
            st.caption(f"최근 {show_n}개만 표시")
            for i, p in enumerate(profs[-show_n:], start=max(1, len(profs) - show_n + 1)):
                st.write(
                    f"{i}. [{p.get('label','-')}] norm={float(p.get('ref_required_norm',0)):,.2f} | "
                    f"norm_adj={float(p.get('ref_required_norm_adjusted', p.get('ref_required_norm',0))):,.2f} | "
                    f"boss_hp_est={float(p.get('boss_hp_est',0)):,.0f} | 기준파티=`{p.get('ref_party','')}`"
                    + (f" | 직업=`{p.get('ref_job_text','')}`" if p.get('ref_job_text') else "")
                    + (f" | 겜속={p.get('ref_game_speed_pct',0):.0f}%" if p.get('ref_game_speed_pct') else "")
                    + (
                        f" | 🆕**체력임계값앵커**(담당상한={float(p.get('anchor_ceiling_hp',0)):,.0f})"
                        if p.get('is_hp_ceiling_anchor') and float(p.get('anchor_ceiling_hp', 0) or 0) > 0
                        else " | 🆕**체력임계값앵커**(담당상한=자체체력)"
                        if p.get('is_hp_ceiling_anchor')
                        else ""
                    )
                )
        else:
            st.info("아직 저장된 프로필이 없어요. 위에서 저장해줘.")

    else:
        st.info("-")
