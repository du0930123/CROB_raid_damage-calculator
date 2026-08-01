COLOR_MATCH_BONUS = 0.30
COLOR_OPTIONS = ["빨강", "노랑", "파랑"]

# ============================
# ✅ 신규 직업 시스템 (2026 업데이트)
# - 캐릭터의 "2개 스킬"과는 별개로, 파티원 각자가 직업 1개를 가짐
# - 세 직업 모두 기본 초당 10 에너지 충전
# ============================
JOB_OPTIONS = ["방패지기", "젤리술사", "회피도사"]
JOB_BASE_ENERGY_PER_SEC = 10.0

# 젤리술사: 무지개곰젤리 4개 획득 시 1회성으로 +60 에너지
JELLY_REQUIRE_COUNT = 4
JELLY_BURST_ENERGY = 60.0

# 회피도사: 초당 +1(고정치, %가 아님)씩 누적, 최대 +50 (= 초당 최대 60 에너지)
# ※ 장기전(사이클 수가 많은 레이드) 기준으로 "정상상태(steady-state)"인
#   최대치(기본10 + 고정50 = 60)에 도달해 유지된다고 근사함. 초반 50초 램프업 구간은 무시.
EVASION_MAX_BONUS_FLAT = 50.0

# 젤리술사: 페이즈별 무지개곰젤리 획득 속도 실측치 (2026 업데이트 기준)
# - 1~2페: 젤리 개수 = 경과시간(초)                -> 1개/초
# - 3페   : 젤리 개수 = 경과시간(초) x 2/3          -> 0.667개/초
# ※ TODO: 정확한 페이즈별 소요시간을 알게 되면, 이 두 값을 시간가중평균 내서
#   JELLY_ASSUMED_BONUS_FLAT을 다시 계산하면 더 정확해짐. 지금은 페이즈 시간
#   정보가 없어서 "1~2페 값과 3페 값의 단순 평균"으로 근사함.
JELLY_PHASE1_2_RATE_PER_SEC = 1.0
JELLY_PHASE3_RATE_PER_SEC = 2.0 / 3.0

JELLY_PHASE1_2_BONUS_FLAT = (JELLY_PHASE1_2_RATE_PER_SEC / JELLY_REQUIRE_COUNT) * JELLY_BURST_ENERGY  # = 15
JELLY_PHASE3_BONUS_FLAT = (JELLY_PHASE3_RATE_PER_SEC / JELLY_REQUIRE_COUNT) * JELLY_BURST_ENERGY  # = 10

# 젤리술사 보너스 가정치 (고정치, %가 아님) = 위 두 페이즈 값의 단순 평균
# = (15 + 10) / 2 = 12.5  ->  젤리술사 정상상태 근사 초당 에너지 = 10 + 12.5 = 22.5
JELLY_ASSUMED_BONUS_FLAT = (JELLY_PHASE1_2_BONUS_FLAT + JELLY_PHASE3_BONUS_FLAT) / 2.0

# ============================
# ✅ 백엔드 전용 설정값 (유저에게 노출 안 함, 개발자가 여기서만 수정)
# ============================
# 젤리술사: 실제 젤리 획득 빈도를 알게 되면 아래 두 값을 채워 넣으면
# JELLY_ASSUMED_STEADY_STATE_BONUS_PCT 대신 이 값 기반으로 정확히 계산됨.
# (0으로 두면 = 아직 미확정 = 위 가정치 사용)
JELLY_PICKUPS_PER_CYCLE_BACKEND = 0.0
SECONDS_PER_CYCLE_BACKEND = 0.0

# 몬스터 방어력 약화/강화 - 지속시간(초)은 고정값, 유저에게 노출 안 함
DEFENSE_WEAKEN_DURATION_SEC = 7.0
DEFENSE_STRENGTHEN_DURATION_SEC = 35.0

# 몬스터 방어력 약화/강화 - 피해율(%)과 발생주기(초)도 보스/스톤마다 고정된 값이라
# 유저에게 입력받지 않고 백엔드에서만 관리. 유저는 체크박스로 "발동 여부"만 선택.
# ※ TODO: 실제 값이 확인되면 아래 숫자만 바꾸면 됨.
DEFENSE_WEAKEN_PCT_BACKEND = 50.0
DEFENSE_WEAKEN_INTERVAL_SEC_BACKEND = 40.0
DEFENSE_STRENGTHEN_PCT_BACKEND = 50.0
DEFENSE_STRENGTHEN_INTERVAL_SEC_BACKEND = 40.0

# ============================
# ✅ 신규 소환석 옵션
# ============================
# "젤리/회피/방패 2명 이상" 조건에 쓰는 기본 임계값
JOB_PARTY_CONDITION_MIN_COUNT = 2