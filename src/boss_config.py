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
        # 실측 클리어 데이터(직업: 스+캡 회 1, 스+연 회 3, 스+석 회 1 / 게임속도 미사용)
        # 기준 역산: 이론상 최대 5.80배 속도 중, 실제로는 1.075배 정도만 반영됨
        # -> alpha = (1.075-1)/(5.80-1) ≈ 0.0157
        "회피도사": 0.0157,
        # ※ TODO: 젤리술사 실측 데이터 아직 없음. 회피도사와 마찬가지로
        #   "이미 맵 젤리로 에너지가 넘치는 상황"이라 가정하고 우선 같은 값을
        #   임시로 넣어둠. 실측되면 이 줄만 따로 바꾸면 됨.
        "젤리술사": 0.0157,
    },
}

# ============================
# ✅ 체력 구간별 alpha 감쇠 (700레벨대부터 체력이 훨씬 빨리 빠지는 걸 반영)
# - "1인당 보스체력"이 threshold_hp_per_person을 넘어서면, 직업별 high_alpha를 씀
# - threshold 미만이면 JOB_ENERGY_ALPHA_BY_BOSS_AND_JOB의 기본값을 그대로 씀
# - "1인당"은 (보스 전체 체력 ÷ 파티 인원수)로 계산함
# ※ TODO: high_alpha들은 임시로 기존값의 절반으로 넣어둠. 실측치 확인되면 숫자만 교체.
# ============================
JOB_ENERGY_ALPHA_HP_TIER_BY_BOSS = {
    "아수라": {
        "threshold_hp_per_person": 8_700_000_000,
        "high_alpha_by_job": {
            "회피도사": 0.0078,
            "젤리술사": 0.0078,
        },
    },
}


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