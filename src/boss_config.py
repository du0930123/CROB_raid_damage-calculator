from typing import Dict

DEFAULT_GAME_SPEED_ALPHA = 0.35

GAME_SPEED_ALPHA_BY_BOSS = {
    # 실측 역산: 인삼4+캡틴아이스1(젤리술사), 게임속도58%, 여유율 목표 12%
    # job_energy_alpha(0.0157, 검증됨)는 고정하고 game_speed_alpha만 역산함
    "아수라": 0.2031,
    "두억시니": 0.4,
    "사마귀": 0.35,
    "무쇠꾼": 0.4,
    "크치뱀": 0.35,
}

# ============================
# ✅ 보스 목록 & 기본 선택 보스
# - 신규 보스 "아수라" 추가, 우선 기본값(디폴트)으로 지정
# ============================
BOSS_LIST = ["아수라", "두억시니", "사마귀", "무쇠꾼", "크치뱀"]
DEFAULT_BOSS = "아수라"

# ============================
# ✅ 직업 에너지 보너스 감쇠(alpha) - "보스 + 직업"별로 따로 관리
# - 왜 스킬(캐릭터)이 아니라 직업 기준이냐면:
#   맵의 무지개곰젤리 때문에 에너지가 이미 불규칙하게 확확 들어오는 상황이라,
#   "이 캐릭터가 에너지 포화상태에 가까운지"를 가르는 핵심 변수는
#   그 캐릭터가 어떤 스킬이냐보다 "그 위에 얹힌 직업의 충전 패턴
#   (회피도사=연속적 vs 젤리술사=버스트성)"일 가능성이 높다고 보고 이렇게 설계함.
# - 값이 없는 직업은 DEFAULT_JOB_ENERGY_ALPHA(1.0=감쇠 없음)로 취급됨
# ============================
DEFAULT_JOB_ENERGY_ALPHA = 1.0

JOB_ENERGY_ALPHA_BY_BOSS_AND_JOB = {
    "아수라": {
        "회피도사": 0.0078,
        "젤리술사": 0.0078,
    },
}

# ============================
# ✅ 체력 구간별 alpha 감쇠 - 사용 중지 (전부 0.0078로 통일했으므로 구간 구분 불필요)
# 다시 쓰고 싶으면 아래 dict에 보스별로 값을 채우면 됨
# ============================
JOB_ENERGY_ALPHA_HP_TIER_BY_BOSS = {}


def get_job_energy_alpha_by_job(
    boss_name: str,
    boss_hp_total: float,
    party_size: int,
) -> Dict[str, float]:
    """
    보스 이름 + (전체 체력, 파티 인원수)를 받아서, {직업명: alpha} 매핑을 리턴.
    - 체력 구간(1인당 threshold 이상)이면 high_alpha_by_job을 씀
    - 아니면 기본 JOB_ENERGY_ALPHA_BY_BOSS_AND_JOB을 씀
    - 매핑에 없는 직업은 compute_async_dps_ratio 쪽에서 DEFAULT_JOB_ENERGY_ALPHA로 처리됨
    """
    base_map = dict(JOB_ENERGY_ALPHA_BY_BOSS_AND_JOB.get(boss_name, {}))

    tier = JOB_ENERGY_ALPHA_HP_TIER_BY_BOSS.get(boss_name)
    if not tier or party_size <= 0:
        return base_map

    hp_per_person = boss_hp_total / party_size

    if hp_per_person >= tier["threshold_hp_per_person"]:
        return dict(tier.get("high_alpha_by_job", base_map))

    return base_map