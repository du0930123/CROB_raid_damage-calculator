import streamlit as st


ADMIN_PASSWORD = "0930"


def init_session_state():
    if "LAST_CALC_OPTS" not in st.session_state:
        st.session_state["LAST_CALC_OPTS"] = {}

    if "PINNED_CALC_OPTS" not in st.session_state:
        st.session_state["PINNED_CALC_OPTS"] = None

    if "ADMIN_AUTH" not in st.session_state:
        st.session_state["ADMIN_AUTH"] = False

    if "BOSS_LIMITS" not in st.session_state:
        st.session_state["BOSS_LIMITS"] = {}


def render_admin_login() -> bool:
    params = st.query_params
    admin_flag = str(params.get("admin", "0")).strip().lower() in ["1", "true", "yes"]

    if not admin_flag:
        return False

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


def render_header():
    st.title("🧮 쿠오븐 레이드파티 기대 딜량 계산")
    st.markdown("<hr style='margin: 6px 0;'>", unsafe_allow_html=True)
    st.caption("입력 예: 비트 3 레판 1  |  이름과 수량을 공백으로 구분")
    st.markdown("<hr style='margin: 6px 0;'>", unsafe_allow_html=True)
    st.caption("유틸 버프 종류 : 공주(+12%), 치어리더(+12%), 생케(+27%), 석류(+30%)")
    st.caption("약점으로 선택된 색 스킬: (1 + 공통 + 캡틴 + 0.30 + 약점조건부)로 합산 적용")
    st.caption("비약점 색 스킬: (1 + 공통 + 캡틴)만 적용")
    st.caption("※ 약점 조건부 피해증가율은 음수도 가능(딜 감소). 예: -20% 입력 가능")
    st.caption("※ '총 스킬에너지당 딜량' = Σ(각 스킬 딜량/각 스킬 에너지) 로 계산")


def render_footer():
    st.markdown("---")
    st.caption("제작 : 카카오톡 오픈채팅방 쿠키런 only 레이드런방 - 오늘컨별로네")
    st.caption("도움 : Nawg, 썸머, 솜이, 흑임자맛고양이, 감성적인방향치")