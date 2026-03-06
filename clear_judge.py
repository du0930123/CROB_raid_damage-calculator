import streamlit as st
from typing import Dict, Tuple, Optional, Any, List


# ----------------------------
# 세션 저장소 접근
# ----------------------------
def get_limits_store() -> Dict[str, Any]:
    if "BOSS_LIMITS" not in st.session_state:
        st.session_state["BOSS_LIMITS"] = {}
    return st.session_state["BOSS_LIMITS"]


# ----------------------------
# 정규화 기반 필요 총 에너지
# required_energy = boss_hp / P
# P = Σ(dmg / eff_mp) = total_dmg_per_mp_sum
# ----------------------------
def compute_required_energy(boss_hp: float, P: float) -> float:
    if boss_hp <= 0:
        return 0.0
    if P <= 0:
        return float("inf")
    return boss_hp / P


def judge_clear(boss_hp: float, P: float, ref_required_norm: float) -> Tuple[bool, float, float]:
    """
    ref_required_norm: (가중평균된) 기준 정규화 예산 = limit_norm = boss_hp/P 한계치
    Returns:
      clear_ok (bool),
      required_energy (float) = boss_hp / P,
      margin_pct (float)  # (+)면 여유, (-)면 부족
    """
    required_energy = compute_required_energy(boss_hp, P)
    if ref_required_norm <= 0 or required_energy == float("inf"):
        return False, required_energy, float("-inf")

    margin_pct = (ref_required_norm - required_energy) / ref_required_norm * 100.0
    clear_ok = required_energy <= ref_required_norm
    return clear_ok, required_energy, margin_pct

# ==========================================================
# ✅ party_type 제거 버전: 보스 전체 profiles 풀로 ENERGY_LIMIT 계산
# - 파티 구성 -> MP 비중 벡터
# - 각 profile(ref_vec)과의 거리(L1)로 가중치 계산
# - ENERGY_LIMIT = Σ(w_i * limit_i) / Σ(w_i)
# ==========================================================

def party_to_mp_share_vector(party) -> Dict[str, float]:
    """
    party: List[Character]
    v[name] = (해당 캐릭터 mp_cost 합) / (전체 mp_cost 합)
    """
    total_mp = 0.0
    acc: Dict[str, float] = {}

    for c in party:
        name = getattr(c, "name", "")
        mp = float(getattr(c, "mp_cost", 0) or 0)
        if not name or mp <= 0:
            continue
        acc[name] = acc.get(name, 0.0) + mp
        total_mp += mp

    if total_mp <= 0:
        return {}

    return {k: v / total_mp for k, v in acc.items()}


def l1_distance(a: Dict[str, float], b: Dict[str, float]) -> float:
    keys = set(a.keys()) | set(b.keys())
    return sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys)


def _get_boss_profiles(boss: str) -> List[Dict[str, Any]]:
    """
    새 구조: store[boss]["profiles"] = [ {ref_required_norm, ref_vec, ref_party, ...}, ... ]
    구 구조(하위호환): store[boss][party_type]["ref_required_norm"] 형태는 여기서 자동 사용 못함.
      -> party_type을 없앴기 때문에, 구 구조는 마이그레이션 필요.
    """
    store = get_limits_store()
    boss_pack = store.get(boss, {})
    profs = boss_pack.get("profiles", [])
    if isinstance(profs, list):
        return profs
    return []


def compute_energy_limit_weighted(
    boss: str,
    party,
    k: int = 5,
    eps: float = 1e-6,
    power: float = 1.0,
) -> Tuple[Optional[float], Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    보스의 profiles 전체에서 거리 기반 가중평균 ENERGY_LIMIT 계산

    Args:
      k: 가까운 프로필 상위 k개만 사용(너무 많은 프로필이 섞이는 걸 방지)
      power: 가중치 강도 (1.0=기본, 2.0=가까운 것 더 강하게)
        w_i = 1 / (d_i + eps)^power

    Returns:
      ref_required_norm (float or None)
      used_profiles (list of dict with dist, weight info) or None
      err_msg (str or None)
    """
    profiles = _get_boss_profiles(boss)
    if not profiles:
        return None, None, "선택한 보스에 저장된 profiles가 없어요(탭3 관리자 저장 필요)."

    cur_vec = party_to_mp_share_vector(party)
    if not cur_vec:
        return None, None, "현재 파티의 MP 벡터를 만들 수 없어요(mp_cost 확인)."

    scored = []
    for p in profiles:
        ref_vec = p.get("ref_vec", {})
        limit_norm = p.get("ref_required_norm", None)
        if not isinstance(ref_vec, dict) or len(ref_vec) == 0:
            continue
        if limit_norm is None:
            continue
        d = l1_distance(cur_vec, ref_vec)
        scored.append((d, p))

    if not scored:
        return None, None, "profiles는 있는데 ref_vec/ref_required_norm이 유효한 항목이 없어요."

    # 가까운 순 정렬 후 상위 k개만 사용
    scored.sort(key=lambda x: x[0])
    top = scored[: max(1, min(k, len(scored)))]

    # 가중치 계산
    weights = []
    for d, p in top:
        w = 1.0 / ((d + eps) ** power)
        weights.append((w, d, p))

    wsum = sum(w for w, _, _ in weights)
    if wsum <= 0:
        return None, None, "가중치 합이 0이에요(거리 계산 확인 필요)."

    ref_required_norm = sum(w * float(p["ref_required_norm"]) for w, _, p in weights) / wsum

    used = []
    for w, d, p in weights:
        used.append({
            "ref_party": p.get("ref_party", ""),
            "label": p.get("label", ""),
            "ref_required_norm": float(p.get("ref_required_norm", 0.0)),
            "dist": float(d),
            "weight": float(w / wsum),  # 정규화 가중치(합 1)
        })

    return float(ref_required_norm), used, None


# ----------------------------
# ✅ 탭1/탭2에서 공통으로 쓰는 "판정 UI + 출력"
# ----------------------------
def render_clear_judge_box(
    boss: str,
    boss_hp: float,
    P: float,
    party,
    key_prefix: str = "judge",
    show_match_info: bool = True,
    k_profiles: int = 5,
    weight_power: float = 1.0,
    title: str = "정규화 클리어 판정",   # ✅ 추가
):
    """
    party_type 선택 없음.
    보스 profiles 풀에서 자동으로 ENERGY_LIMIT(가중평균)을 계산.
    """
    st.markdown(f"### ✅ {title}")

    ref_required_norm, used, err = compute_energy_limit_weighted(
        boss=boss,
        party=party,
        k=k_profiles,
        power=weight_power,
    )

    if err or ref_required_norm is None:
        st.info(err or "ref_required_norm을 계산할 수 없어요.")
        return

    clear_ok, required_energy, margin_pct = judge_clear(boss_hp=boss_hp, P=P, ref_required_norm=ref_required_norm)

    st.write(f"- 필요 총 에너지(required_energy = boss_hp / P): **{required_energy:,.0f}**")
    st.write(f"- 기준 정규화 한계(ref_required_norm, 가중평균): **{ref_required_norm:,.0f}**")
    st.markdown(
    """
    <div style="
        margin-top: 12px;
        margin-bottom: 12px;
        padding: 18px 20px;
        border-radius: 12px;
        background-color: #fff3cd;
        border: 2px solid #ffcc00;
        color: #7a4b00;
        font-size: 26px;
        font-weight: 800;
        text-align: center;
        line-height: 1.5;
    ">
        부족 뜬다고 못 깨는 거 아님<br>
        데이터 많이 부족하고, 겜속이나 빌드에 따라 달라질 수 있음
    </div>
    """,
    unsafe_allow_html=True
)
    

    if show_match_info and used:
        with st.expander("가중치로 사용된 기준 프로필(상위 매칭)", expanded=False):
            for u in used:
                ref = u.get("ref_party", "")
                lbl = u.get("label", "")
                st.write(
                    f"- [{lbl or '-'}] `{ref}` | ref_required_norm={u['ref_required_norm']:,.0f} | dist={u['dist']:.3f} | weight={u['weight']*100:.1f}%"
                )

    if clear_ok:
        st.success(f"판정: **클리어 가능** (여유율 **{margin_pct:.1f}%**)")
    else:
        st.error(f"판정: **클리어 어려움** (부족 **{abs(margin_pct):.1f}%**)")


def judge_clear_for_table(
    boss: str,
    boss_hp: float,
    P: float,
    party,             # ✅ List[Character]
    k_profiles: int = 5,
    weight_power: float = 1.0,
):
    """
    탭2(비교 테이블)용: UI 없이 결과만 반환
    """
    ref_required_norm, used, err = compute_energy_limit_weighted(
        boss=boss,
        party=party,
        k=k_profiles,
        power=weight_power,
    )

    required_energy = compute_required_energy(boss_hp, P)

    if err or ref_required_norm is None:
        return {
            "필요총에너지(boss_hp/P)": int(required_energy) if required_energy != float("inf") else None,
            "ref_required_norm(가중평균)": None,
            "정규화판정": "NO_PROFILE",
            "여유율": None,
        }

    clear_ok, required_energy, margin_pct = judge_clear(boss_hp=boss_hp, P=P, ref_required_norm=ref_required_norm)
    return {
        "필요총에너지(boss_hp/P)": int(required_energy) if required_energy != float("inf") else None,
        "ref_required_norm(가중평균)": float(f"{ref_required_norm:.1f}"),
        "정규화판정": "CLEAR" if clear_ok else "FAIL",
        "여유율": float(f"{margin_pct:.1f}"),
    }
