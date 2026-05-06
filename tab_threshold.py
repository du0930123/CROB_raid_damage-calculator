import math
import json
import streamlit as st
from typing import Dict, Any
from boss_limits_store import get_limits_store, save_limits

# ✅ clear_judge.py에 아래 함수가 있어야 함:
# - party_to_mp_share_vector(party) -> Dict[str, float]
from clear_judge import party_to_mp_share_vector


def render_threshold_tab(COLOR_OPTIONS, build_party_from_text, calculate_party, admin_mode: bool = False):
    st.subheader("📌 파티사이클 클리어 여부 경계값 (정규화 적용)")

    # 보스 목록
    BOSS_LIST = ["사마귀", "두억시니", "무쇠꾼"]

    boss = st.selectbox("보스 선택", BOSS_LIST, index=2)

    st.markdown("### 조건")
    
    BOSS_CONDITIONS = {
        "사마귀": [
            "게임속도 증가 없음",
            "보스 약화에 따른 딜량 증가를 반영하지 않음",
            "빌드에 능숙한 5인 파티",
            "4페를 어느정도 버틸 수 있을 만큼, 체력 여유가 있는 상태",
        ],
    
        "두억시니": [
            "게임속도 증가 없음",
            "빌드에 능숙한 5인 파티",
            "공주런 급으로 4페 견딜 수 있음",
        ],
    
        "무쇠꾼": [
            "게임속도 증가, 스킬에너지젤리 떨어짐, 모든점수2배 옵션 반영하지 않음",
            "스킬에 따라 다른 딜레이로 인해 발생하는 빌드 유불리사항을 반영하지않음",
            "고렙돌 전용 빌드(열기 식힌 후 소화기먹고 3페 진입)에 능숙한 5인 파티",
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

        calc_opts = st.session_state.get("LAST_CALC_OPTS", {})
        common_damage_buff_pct = float(calc_opts.get("common_damage_buff_pct", 0.0))
        stone_crit_buff_pct = float(calc_opts.get("stone_crit_buff_pct", 0.0))
        weakness_bonus_by_color = dict(calc_opts.get("weakness_bonus_by_color", {}))
        energy_decrease_by_color = dict(calc_opts.get("energy_decrease_by_color", {}))

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

        # ✅ 저장 버튼
        if st.button("✅ 이 보스 기준 프로필 저장(party_type 무시)", key=f"save_profile_{boss}_{party_type_label}"):
            try:
                party = build_party_from_text(ref_party_text)

                # 기준 파티 계산
                total_dmg, total_dmg_per_mp_sum, total_mp, _, _, _ = calculate_party(
                    party=party,
                    common_damage_buff=common_damage_buff_pct / 100.0,
                    stone_crit_buff=stone_crit_buff_pct / 100.0,
                    weakness_bonus_by_color=weakness_bonus_by_color,
                    energy_decrease_by_color=energy_decrease_by_color,
                )
                ref_vec = party_to_mp_share_vector(party)
                if not ref_vec:
                    raise ValueError("ref_vec 생성 실패(mp_cost 확인).")
                
                P = float(total_dmg_per_mp_sum)
                if P <= 0:
                    raise ValueError("기준 파티의 P값이 0 이하입니다.")
                
                boss_hp_est = float(threshold_cycles) * float(total_dmg)   # ✅ 보스 체력(상대값) 추정
                ref_required_norm = boss_hp_est / P                              # ✅ 정규화 기준(시간에 비례)


                store = get_limits_store()
                store.setdefault(boss, {})
                store[boss].setdefault("profiles", [])
                
                store[boss]["profiles"].append({
                    "boss_hp_est": float(boss_hp_est),
                    "ref_required_norm": float(ref_required_norm),
                
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
                })
                
                save_limits(store)
                
                st.success(f"저장 완료! (ref_required_norm = {ref_required_norm:,.2f}, boss_hp_est = {boss_hp_est:,.0f})")
                st.caption(f"- 기준 파티 1사이클 총 MP = {total_mp:,}")
                st.caption(f"- 기준 파티 P(Σ(dmg/eff_mp)) = {total_dmg_per_mp_sum:,.2f}")

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
                    f"ref_required_norm={float(profs[i].get('ref_required_norm',0)):,.2f} | "
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
                    f"{i}. [{p.get('label','-')}] ref_required_norm={float(p.get('ref_required_norm',0)):,.2f} | boss_hp_est={float(p.get('boss_hp_est',0)):,.0f} | 기준파티=`{p.get('ref_party','')}`"
                )
        else:
            st.info("아직 저장된 프로필이 없어요. 위에서 저장해줘.")

    else:
        st.info("-")
