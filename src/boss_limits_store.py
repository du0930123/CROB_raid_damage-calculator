import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

import streamlit as st

DEFAULT_PATH = "boss_limits.json"


def _ensure_session():
    if "BOSS_LIMITS" not in st.session_state:
        st.session_state["BOSS_LIMITS"] = {}
    if "BOSS_LIMITS_SHA" not in st.session_state:
        st.session_state["BOSS_LIMITS_SHA"] = None


def _read_local_json() -> Dict[str, Any]:
    if not os.path.exists(DEFAULT_PATH):
        return {}

    try:
        with open(DEFAULT_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _write_local_json(store: Dict[str, Any]) -> None:
    with open(DEFAULT_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2, sort_keys=True)


def _migrate_limits_store(store: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(store, dict):
        return {}

    for boss, boss_pack in list(store.items()):
        if not isinstance(boss_pack, dict):
            continue

        if isinstance(boss_pack.get("profiles", None), list):
            profs = boss_pack.get("profiles", [])
            new_profs = []

            for p in profs:
                if not isinstance(p, dict):
                    continue

                if not isinstance(p.get("ref_vec", None), dict):
                    p["ref_vec"] = {}

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

        new_profiles = []

        for k, v in list(boss_pack.items()):
            if k == "profiles":
                continue
            if not isinstance(v, dict):
                continue

            if v.get("limit_norm", None) is not None:
                try:
                    new_profiles.append(
                        {
                            "label": str(k),
                            "ref_party": v.get("ref_party", ""),
                            "ref_vec": v.get("ref_vec", {})
                            if isinstance(v.get("ref_vec", {}), dict)
                            else {},
                            "ref_required_norm": float(v["limit_norm"]),
                            "threshold_cycles": v.get("threshold_cycles", None),
                        }
                    )
                except Exception:
                    pass

        if new_profiles:
            store[boss] = {"profiles": new_profiles}

    return store


def _has_github_secrets() -> bool:
    try:
        required = ["GITHUB_TOKEN", "GITHUB_OWNER", "GITHUB_REPO"]
        return all(bool(st.secrets.get(key, "")) for key in required)
    except Exception:
        return False


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


def load_limits() -> Dict[str, Any]:
    _ensure_session()

    if _has_github_secrets():
        try:
            store, sha = _gh_get_file_json()
        except Exception:
            store = _read_local_json()
            sha = None
    else:
        store = _read_local_json()
        sha = None

    store = _migrate_limits_store(store)

    st.session_state["BOSS_LIMITS"] = store
    st.session_state["BOSS_LIMITS_SHA"] = sha

    return store


def save_limits(store: Dict[str, Any]) -> None:
    _ensure_session()
    store = _migrate_limits_store(store)

    if not _has_github_secrets():
        _write_local_json(store)
        st.session_state["BOSS_LIMITS"] = store
        st.session_state["BOSS_LIMITS_SHA"] = None
        return

    sha = st.session_state.get("BOSS_LIMITS_SHA", None)

    if sha is None:
        _, sha = _gh_get_file_json()

    try:
        new_sha = _gh_put_file_json(
            store=store,
            sha=sha,
            message="Update boss_limits.json via Streamlit admin",
        )
    except urllib.error.HTTPError as e:
        if getattr(e, "code", None) in (409, 422):
            _, sha2 = _gh_get_file_json()
            new_sha = _gh_put_file_json(
                store=store,
                sha=sha2,
                message="Update boss_limits.json via Streamlit admin (retry)",
            )
        else:
            raise

    st.session_state["BOSS_LIMITS"] = store
    st.session_state["BOSS_LIMITS_SHA"] = new_sha


def get_limits_store() -> Dict[str, Any]:
    if "BOSS_LIMITS" not in st.session_state:
        load_limits()
    return st.session_state["BOSS_LIMITS"]