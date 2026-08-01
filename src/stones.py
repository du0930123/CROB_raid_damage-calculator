"""
신규 소환석 옵션 (2026 업데이트)

1) 젤리/회피/방패 2명 이상 시, 전체 쿠키가 주는 피해량 n% 증가
   -> 조건부 common_damage_buff 가산 (파티 전체 균일 적용)

2) 젤리/회피/방패의 쿠키 피해량 nn% 증가
   -> 해당 직업이 배정된 캐릭터에게만 적용되는 피해 가산
      (약점 색 보너스와 동일한 방식으로, 캐릭터별 dmg_mult에 더해짐)

3) 빨강/파랑/노랑 에너지 획득량 nn% 증가
   -> 기존 energy_decrease_by_color(감소)의 대칭 버전.
      "증가"는 mp_mult를 낮춰서(스킬을 더 자주 쓸 수 있게) 반영.

4) 일정시간마다 7초 몬스터 방어력 약화 / 일정시간마다 35초 몬스터 방어력 강화
   -> 전투 시간 동안의 "시간가중평균 피해배율(%)"로 환산해서
      common_damage_buff_pct에 가산할 수 있는 값을 계산해주는 헬퍼.
      (주의: 방어력 강화/약화 두 이벤트가 겹치지 않는다고 가정)
"""

from typing import Dict, List

from src.constants import (
    DEFENSE_WEAKEN_DURATION_SEC,
    DEFENSE_STRENGTHEN_DURATION_SEC,
    DEFENSE_WEAKEN_PCT_BACKEND,
    DEFENSE_WEAKEN_INTERVAL_SEC_BACKEND,
    DEFENSE_STRENGTHEN_PCT_BACKEND,
    DEFENSE_STRENGTHEN_INTERVAL_SEC_BACKEND,
)


def party_size_condition_bonus_pct(
    job_assigned_count: int,
    min_count: int,
    bonus_pct: float,
) -> float:
    """
    옵션 1) "젤리/회피/방패 2명 이상 시 전체 피해 n% 증가"

    job_assigned_count: 파티 내 직업이 배정된 인원 수
                         (src.jobs.total_job_assigned_count 결과)
    min_count: 조건 임계값 (기본 2)
    bonus_pct: 조건 충족 시 더해줄 공통 피해 증가율(%)

    Returns:
      조건 충족 시 bonus_pct, 아니면 0.0
    """
    if job_assigned_count >= min_count:
        return bonus_pct
    return 0.0


def job_damage_bonus_for_instance(
    index: int,
    job_per_instance: List,
    job_damage_buff_by_job: Dict[str, float],
) -> float:
    """
    옵션 2) "젤리/회피/방패의 쿠키 피해량 nn% 증가"

    party[index]에 배정된 직업이 job_damage_buff_by_job에 있으면
    그 값을(0.0~1.0 소수) 리턴. (예: 0.12 = +12%)

    - 같은 캐릭터라도 인스턴스(장)마다 직업이 다를 수 있어서, 이름이 아니라
      "몇 번째 장인지(index)"로 조회함 (job_per_instance는 party와 같은 길이)
    - 이 값은 Character.expected_damage()의 extra_dmg_bonus 인자로 그대로 넣으면 됨
    """
    if index < 0 or index >= len(job_per_instance):
        return 0.0
    job = job_per_instance[index]
    if job is None:
        return 0.0
    return job_damage_buff_by_job.get(job, 0.0)


def combine_energy_color_effect(
    color: str,
    energy_decrease_by_color: Dict[str, float],
    energy_increase_by_color: Dict[str, float],
) -> float:
    """
    옵션 3) 색상 에너지 "증가" 옵션 (기존 "감소"의 대칭 버전)

    calculator.calculate_party / compute_async_dps_ratio 의
    mp_mult = 1.0 + energy_decrease_by_color.get(color, 0.0) 를

    mp_mult = 1.0 + combine_energy_color_effect(color, dec, inc)

    로 바꿔서 사용.
    - 감소(+)는 mp_mult를 올림 (스킬을 더 자주 못 씀)
    - 증가(+)는 mp_mult를 내림 (스킬을 더 자주 씀), 0 밑으로는 안 내려가게 clamp
    """
    dec = energy_decrease_by_color.get(color, 0.0)
    inc = energy_increase_by_color.get(color, 0.0)
    net = dec - inc
    return net


def compute_avg_defense_effect_pct(
    weaken_on: bool = False,
    strengthen_on: bool = False,
) -> float:
    """
    옵션 4) 몬스터 방어력 약화(짧게, 자주) / 강화(길게, 드물게) 발동 여부를
    "시간가중평균 피해 변화율(%)"로 환산.

    - 지속시간/피해율/발생주기는 전부 고정값(백엔드 상수, src/constants.py)이라
      유저는 "약화가 있는 보스인지 / 강화가 있는 보스인지"만 체크박스로 선택.
      (DEFENSE_WEAKEN_*_BACKEND, DEFENSE_STRENGTHEN_*_BACKEND 값만 바꾸면
       모든 유저 계산에 즉시 반영됨)

    weaken_on=True   -> 주기마다 7초간 방어력 약화(피해 +weaken_pct%)가 있는 보스
    strengthen_on=True -> 주기마다 35초간 방어력 강화(피해 -strengthen_pct%)가 있는 보스

    각 구간의 "발생 비율(duty cycle)" = duration/interval 로 보고,
    가산 방식(additive)으로 합산한 시간가중평균 %를 리턴.
    """
    weaken_fraction = 0.0
    if weaken_on and DEFENSE_WEAKEN_INTERVAL_SEC_BACKEND > 0:
        weaken_fraction = DEFENSE_WEAKEN_DURATION_SEC / DEFENSE_WEAKEN_INTERVAL_SEC_BACKEND

    strengthen_fraction = 0.0
    if strengthen_on and DEFENSE_STRENGTHEN_INTERVAL_SEC_BACKEND > 0:
        strengthen_fraction = (
            DEFENSE_STRENGTHEN_DURATION_SEC / DEFENSE_STRENGTHEN_INTERVAL_SEC_BACKEND
        )

    avg_pct = (weaken_fraction * DEFENSE_WEAKEN_PCT_BACKEND) - (
        strengthen_fraction * DEFENSE_STRENGTHEN_PCT_BACKEND
    )
    return avg_pct
