import base64
import json
import urllib.request
import urllib.error
import streamlit as st
from typing import Dict, Any, Optional, Tuple

DEFAULT_PATH = "boss_limits.json"  # 로컬 fallback용(실제 SSOT는 GitHub)


def _ensure_session():
    if "BOSS_LIMITS" not in st.session_state:
        st.session_state["BOSS_LIMITS"] = {}
    if "BOSS_LIMITS_SHA" not in st.session_state:
        st.session_state["BOSS_LIMITS_SHA"] = None


def _migrate_limits_store(store: Dict[str, Any]) -> Dict[str, Any]:
    """
    boss_limits.json의 구 구조/구 키를 신 구조로 자동 변환.
    목표:
      - store[boss]["profiles"] 리스트 안의 각 profile이 최소한
        ref_vec(dict) + ref_required_norm(float) 를 갖도록 보정
      - 과거 키: limit_norm -> ref_required_norm 로 매핑
      - 과거 구조: store[boss][party_type]["energy_limit"] 형태를 profiles로 승격(가능하면)
    """
    if not isinstance(store, dict):
        return {}

    for boss, boss_pack in list(store.items()):
        if not isinstance(boss_pack, dict):
            continue

        # 1) 이미 profiles 구조면: profile 키 보정
        if isinstance(boss_pack.get("profiles", None), list):
            profs = boss_pack.get("profiles", [])
            new_profs = []
            for p in profs:
                if not isinstance(p, dict):
                    continue

                # (a) ref_vec 보정
                ref_vec = p.get("ref_vec", None)
                if not isinstance(ref_vec, dict):
                    p["ref_vec"] = {}

                # (b) limit_norm -> ref_required_norm
                if p.get("ref_required_norm", None) is None:
                    if p.get("limit_norm", None) is not None:
                        try:
                            p["ref_required_norm"] = float(p["limit_norm"])
                        except Exception:
                            pass

                new_profs.append(p)

            boss_pack["profiles"] = new_profs
            store[boss] = boss_pack
            continue

        # 2) profiles가 없는 구 구조를 profiles로 승격
        new_profiles = []
        for k, v in list(boss_pack.items()):
            if k == "profiles":
                continue
            if not isinstance(v, dict):
                continue

            if v.get("limit_norm", None) is not None:
                try:
                    new_profiles.append({
                        "label": str(k),
                        "ref_party": v.get("ref_party", ""),
                        "ref_vec": v.get("ref_vec", {}) if isinstance(v.get("ref_vec", {}), dict) else {},
                        "ref_required_norm": float(v["limit_norm"]),
                        "threshold_cycles": v.get("threshold_cycles", None),
                    })
                except Exception:
                    pass

        if new_profiles:
            store[boss] = {"profiles": new_profiles}

    return store


# ----------------------------
# GitHub Contents API helpers
# ----------------------------
def _gh_headers() -> Dict[str, str]:
    token = st.secrets["GITHUB_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "streamlit-app",
    }


def _gh_info() -> Tuple[str, str, str]:
    owner = st.secrets["GITHUB_OWNER"]
    repo = st.secrets["GITHUB_REPO"]
    path = st.secrets.get("GITHUB_PATH", DEFAULT_PATH)
    return owner, repo, path


def _gh_get_file_json() -> Tuple[Dict[str, Any], Optional[str]]:
    """GitHub에서 JSON 읽기. 반환: (store, sha). 파일 없으면 ({}, None)"""
    owner, repo, path = _gh_info()
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    req = urllib.request.Request(url, headers=_gh_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content_b64 = data.get("content", "") or ""
        sha = data.get("sha", None)

        if not content_b64:
            return {}, sha

        raw = base64.b64decode(content_b64).decode("utf-8")
        store = json.loads(raw) or {}
        return store, sha

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}, None
        raise


def _gh_put_file_json(store: Dict[str, Any], sha: Optional[str], message: str) -> str:
    """GitHub에 JSON 생성/업데이트. 반환: new sha"""
    owner, repo, path = _gh_info()
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    content = json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    payload: Dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content).decode("utf-8"),
    }
    if sha:
        payload["sha"] = sha

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, headers=_gh_headers(), data=body, method="PUT")
    with urllib.request.urlopen(req, timeout=20) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    return out["content"]["sha"]


# ----------------------------
# Public API: load/save/get
# ----------------------------
def load_limits() -> Dict[str, Any]:
    """GitHub에서 로드하여 세션에 반영"""
    _ensure_session()
    store, sha = _gh_get_file_json()
    store = _migrate_limits_store(store)
    st.session_state["BOSS_LIMITS"] = store
    st.session_state["BOSS_LIMITS_SHA"] = sha
    return store


def save_limits(store: Dict[str, Any]) -> None:
    """GitHub에 저장하고 sha 갱신"""
    _ensure_session()
    store = _migrate_limits_store(store)

    # sha가 세션에 없으면 최신 sha부터 다시 가져옴
    sha = st.session_state.get("BOSS_LIMITS_SHA", None)
    if sha is None:
        _, sha = _gh_get_file_json()

    try:
        new_sha = _gh_put_file_json(
            store=store,
            sha=sha,
            message="Update boss_limits.json via Streamlit admin"
        )
    except urllib.error.HTTPError as e:
        # sha 충돌(409) 같은 케이스 대비: 최신 sha로 재시도 1회
        if getattr(e, "code", None) in (409, 422):
            _, sha2 = _gh_get_file_json()
            new_sha = _gh_put_file_json(
                store=store,
                sha=sha2,
                message="Update boss_limits.json via Streamlit admin (retry)"
            )
        else:
            raise

    st.session_state["BOSS_LIMITS"] = store
    st.session_state["BOSS_LIMITS_SHA"] = new_sha


def get_limits_store() -> Dict[str, Any]:
    """세션에 없으면 GitHub에서 로드"""
    if "BOSS_LIMITS" not in st.session_state:
        load_limits()
    return st.session_state["BOSS_LIMITS"]
