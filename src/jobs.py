"""
신규 직업 시스템 (2026 업데이트)

- 캐릭터의 "2개 스킬"과는 별개로, 파티원 각자가 직업 1개를 가짐
  (방패지기 / 젤리술사 / 회피도사)
- 직업은 데미지에는 관여하지 않고, "스킬 에너지 충전 속도"에만 관여함
- 세 직업 모두 기본 초당 10 에너지 충전
- 젤리술사: 무지개곰젤리 4개 획득 시 1회성 +60 에너지
- 회피도사: 초당 +1(고정치)씩 누적, 최대 +50 (장기전 기준 정상상태로 근사,
  기본10 + 고정50 = 최대 초당 60 에너지)

⚠️ 중요: 같은 캐릭터(예: 비트)가 파티에 여러 장 있어도, 장마다 서로 다른
직업을 가질 수 있음 (예: 비트 2장은 방패지기, 3장은 회피도사).
그래서 직업은 "캐릭터 이름" 기준이 아니라, party 리스트 안에서
"몇 번째 장(인스턴스)인지"를 기준으로 배정한다.

입력 포맷: "캐릭터 직업 인원수" 3개씩 묶음
예) "비트 방패지기 2 비트 회피도사 3 레판 젤리술사 1"
-> 비트 중 앞의 2장은 방패지기, 다음 3장은 회피도사, 레판 1장은 젤리술사

이 모듈은:
1) 위 텍스트를 파싱해서 [(캐릭터명, 직업, 인원수), ...] 배정 목록을 만들고
2) 실제 파티(List[Character])와 대조해서, party와 같은 길이의
   "인스턴스별 직업 리스트"(job_per_instance)를 만든다.
3) job_per_instance로부터, 기존 "게임속도 증가"와 동일한 방식(= P를 올려주는
   배율)으로 쓸 수 있는 "직업 에너지 보너스(%)"를 계산한다.

※ 기준(0%) 정의:
   파티원 전원이 "방패지기"(보너스 없음, 기본 10/sec)인 경우를 0%로 둔다.
"""

from collections import deque
from typing import Dict, List, Optional, Tuple

from src.constants import (
    JOB_OPTIONS,
    JOB_BASE_ENERGY_PER_SEC,
    JELLY_BURST_ENERGY,
    JELLY_ASSUMED_BONUS_FLAT,
    JELLY_PICKUPS_PER_CYCLE_BACKEND,
    SECONDS_PER_CYCLE_BACKEND,
    EVASION_MAX_BONUS_FLAT,
)
from src.party_parser import CHARACTER_ALIAS
from src.characters import Character, CHARACTER_DB


JOB_ALIAS: Dict[str, str] = {
    "방": "방패지기",
    "방패": "방패지기",
    "방패지기": "방패지기",
    "젤": "젤리술사",
    "젤리": "젤리술사",
    "젤리술사": "젤리술사",
    "회": "회피도사",
    "회피": "회피도사",
    "회피도사": "회피도사",
}


def build_job_assignments_from_text(text: str) -> List[Tuple[str, str, int]]:
    """
    입력 예: "비트 방패지기 2 비트 회피도사 3 레판 젤리술사 1"
    -> [("비트", "방패지기", 2), ("비트", "회피도사", 3), ("레판", "젤리술사", 1)]

    - "캐릭터 직업 인원수" 3개씩 한 묶음
    - 같은 캐릭터를 여러 묶음으로 나눠서, 장마다 다른 직업 배정 가능

    ⚠️ 한 사람이 "데미지 스킬 2개"를 들고 있어서, 그 두 스킬이 항상 같은
    직업이어야 하는 경우엔 '+'로 묶어서 한 번에 지정할 수 있음:
        "스네이크+캡틴아이스 회피도사 1"
        -> [("스네이크","회피도사",1), ("캡틴아이스","회피도사",1)]  (둘 다 동시 배정)

    두 번째 스킬이 회복기 등 "데미지를 안 주는 스킬"이라 애초에 파티 구성에
    안 들어있는 캐릭터(예: 연금술사)라면, 그냥 조용히 무시되고 첫 번째
    스킬만 배정됨:
        "스네이크+연금술사 회피도사 1" -> [("스네이크","회피도사",1)]
    """
    text = text.strip()
    if not text:
        return []

    tokens = text.split()
    if len(tokens) % 3 != 0:
        raise ValueError(
            "직업 구성은 '캐릭터 직업 인원수' 세 개씩 묶여야 합니다. "
            "예) 비트 방패지기 2 비트 회피도사 3 레판 젤리술사 1 "
            "(한 사람이 두 스킬을 같이 들면 '스네이크+캡틴아이스 회피도사 1' 처럼 +로 묶기)"
        )

    assignments: List[Tuple[str, str, int]] = []

    for i in range(0, len(tokens), 3):
        raw_name_field = tokens[i]
        raw_job = tokens[i + 1]
        raw_count = tokens[i + 2]

        if raw_job not in JOB_ALIAS:
            raise KeyError(
                f"알 수 없는 직업: {raw_job} / 사용 가능: {', '.join(JOB_OPTIONS)}"
            )

        try:
            count = int(raw_count)
        except ValueError:
            raise ValueError(f"인원수는 숫자여야 합니다: '{raw_count}'")

        if count <= 0:
            continue

        raw_names = [n for n in raw_name_field.split("+") if n]
        if not raw_names:
            raise ValueError(f"캐릭터 이름이 비어있습니다: '{raw_name_field}'")

        resolved_names = []
        unknown_names = []
        for raw_name in raw_names:
            if raw_name in CHARACTER_ALIAS:
                resolved_names.append(CHARACTER_ALIAS[raw_name])
            else:
                # 데미지 스킬이 아닌(회복기 등) 파트너 스킬은 파티 구성에 아예
                # 없으니 조용히 무시함 (완전 오타는 여기서 걸러지지 않으니 주의)
                unknown_names.append(raw_name)

        if not resolved_names:
            raise KeyError(
                f"'{raw_name_field}' 안에서 알 수 있는 데미지 캐릭터를 하나도 못 찾았어요. "
                f"사용 가능: {', '.join(CHARACTER_ALIAS.keys())}"
            )

        for name in resolved_names:
            assignments.append((name, JOB_ALIAS[raw_job], count))

    return assignments


def build_party_and_jobs_from_job_text(
    job_text: str,
) -> Tuple[List[Character], List[Optional[str]]]:
    """
    파티 구성을 따로 안 받고, 직업 텍스트 하나만으로 party와 job_per_instance를
    동시에 만든다.

    입력 예: "스+캡 회 1 스+연 회 3 스+석 회 1"
    -> assignments: [("스네이크","회피도사",1), ("캡틴아이스","회피도사",1),
                      ("스네이크","회피도사",3), ("스네이크","회피도사",1)]
       (스+연, 스+석은 두번째가 데미지 스킬이 아니라서 스네이크만 남음)
    -> party 구성이 "스네이크 5 캡틴아이스 1"이라는 걸 굳이 따로 입력 안 해도
       assignments 자체에서 인원수가 다 나오므로 그대로 합산해서 만든다.

    ⚠️ resolve_job_per_instance와 다르게, 여기선 assignments가 만들어진
    "순서 그대로" party와 job_per_instance를 같이 쌓기 때문에, 인스턴스-직업
    매칭이 원천적으로 어긋날 일이 없다 (이름별 큐 매칭이 아예 필요 없음).

    Returns:
      party: List[Character] (assignments 순서대로 생성됨)
      job_per_instance: party와 같은 길이, 각 인스턴스의 직업(str)
    """
    assignments = build_job_assignments_from_text(job_text)

    party: List[Character] = []
    job_per_instance: List[Optional[str]] = []

    for name, job, count in assignments:
        if name not in CHARACTER_DB:
            raise KeyError(f"DB에 없는 캐릭터: {name}")

        party.extend([CHARACTER_DB[name]] * count)
        job_per_instance.extend([job] * count)

    if not party:
        raise ValueError(
            "직업 텍스트에서 파티를 하나도 못 만들었어요. "
            "예) 스+캡 회 1 스+연 회 3 스+석 회 1"
        )

    return party, job_per_instance


def merge_party_by_character(party: List[Character]) -> str:
    """
    party(List[Character], 같은 캐릭터가 흩어져 있을 수 있음)를 받아서,
    기존 party_text 포맷("이름 수량 이름 수량 ...")으로 합쳐서 리턴.
    (표시/디버그용 - 예: build_party_and_jobs_from_job_text로 만든 파티를
     화면에 "이런 파티로 인식했어요"라고 보여줄 때 사용)
    """
    counts: Dict[str, int] = {}
    order: List[str] = []
    for c in party:
        name = getattr(c, "name", "")
        if name not in counts:
            counts[name] = 0
            order.append(name)
        counts[name] += 1

    return " ".join(f"{name} {counts[name]}" for name in order)


def resolve_job_per_instance(
    party: List,
    assignments: List[Tuple[str, str, int]],
) -> List[Optional[str]]:
    """
    party(List[Character])와 같은 길이의 리스트를 만들어서,
    각 인덱스(= 그 장의 캐릭터)가 어떤 직업을 가지는지 담는다.

    - 같은 캐릭터명이 party 안에 등장하는 "순서대로" 직업을 하나씩 배정함
      (예: assignments에 "비트 방패지기 2 비트 회피도사 3"이 있으면,
       party 안에서 처음 만나는 비트 2장 -> 방패지기, 다음 3장 -> 회피도사)
    - 배정된 수보다 party 내 실제 캐릭터 수가 많으면, 남는 장은 직업 미배정
      (= 방패지기와 동일하게 취급, 보너스 없음)
    - 배정된 수가 실제 캐릭터 수보다 많으면, 초과분은 그냥 무시됨
    """
    queues: Dict[str, deque] = {}
    for name, job, count in assignments:
        queues.setdefault(name, deque())
        for _ in range(count):
            queues[name].append(job)

    result: List[Optional[str]] = []
    for c in party:
        name = getattr(c, "name", "")
        q = queues.get(name)
        if q:
            result.append(q.popleft())
        else:
            result.append(None)

    return result


def validate_job_assignment_counts(
    party: List,
    assignments: List[Tuple[str, str, int]],
) -> List[str]:
    """
    직업 배정 수 vs 실제 파티 내 캐릭터 수가 안 맞으면 경고 메시지를 만들어 리턴.
    (에러는 아니고, UI에서 st.warning으로 보여주기용)
    """
    party_counts: Dict[str, int] = {}
    for c in party:
        name = getattr(c, "name", "")
        party_counts[name] = party_counts.get(name, 0) + 1

    assigned_counts: Dict[str, int] = {}
    for name, _job, count in assignments:
        assigned_counts[name] = assigned_counts.get(name, 0) + count

    warnings: List[str] = []
    for name, assigned in assigned_counts.items():
        actual = party_counts.get(name, 0)
        if assigned > actual:
            warnings.append(
                f"'{name}' 직업 배정 인원({assigned}명)이 실제 파티 내 수량({actual}명)보다 많아요. "
                f"초과분({assigned - actual}명)은 무시됩니다."
            )
        elif assigned < actual:
            warnings.append(
                f"'{name}' {actual - assigned}명은 직업이 배정되지 않아 방패지기와 동일하게 처리돼요."
            )

    return warnings


def job_energy_rate_per_sec(
    job: Optional[str],
    jelly_pickups_per_cycle: float = None,
    seconds_per_cycle: float = None,
) -> float:
    """
    직업 1개(= 캐릭터 1장)가 실제로 초당 얼마의 에너지를 받는지.

    - None(직업 미배정) / 방패지기 -> 기본 10/sec
    - 회피도사 -> 기본10 + 고정50 = 60/sec
    - 젤리술사 -> 기본10 + (실측 있으면 실측, 없으면 가정치 12.5)
    """
    if job == "회피도사":
        return JOB_BASE_ENERGY_PER_SEC + EVASION_MAX_BONUS_FLAT

    if job == "젤리술사":
        jpc = jelly_pickups_per_cycle if jelly_pickups_per_cycle is not None else JELLY_PICKUPS_PER_CYCLE_BACKEND
        spc = seconds_per_cycle if seconds_per_cycle is not None else SECONDS_PER_CYCLE_BACKEND
        if jpc > 0 and spc > 0:
            jelly_energy_per_sec = (jpc * JELLY_BURST_ENERGY) / spc
            return JOB_BASE_ENERGY_PER_SEC + jelly_energy_per_sec
        return JOB_BASE_ENERGY_PER_SEC + JELLY_ASSUMED_BONUS_FLAT

    # None(미배정) 또는 "방패지기"
    return JOB_BASE_ENERGY_PER_SEC


def job_speed_ratio_for_instance(
    index: int,
    job_per_instance: List[Optional[str]],
    job_energy_alpha: float = 1.0,
    job_energy_alpha_by_job: Optional[Dict[str, float]] = None,
    jelly_pickups_per_cycle: float = None,
    seconds_per_cycle: float = None,
) -> float:
    """
    party[index] "그 캐릭터 한 명"만의 캐스팅 속도 배율.

    ⚠️ 중요: 이건 파티 전체에 곱하는 값이 아니라, 딱 그 캐릭터 본인의
    (dmg/eff_mp) 항목에만 곱해야 하는 값이다. (같은 파티 안에서도
    방패지기는 1.0배, 회피도사는 6.0배 이런식으로 캐릭터마다 다름)

    job_energy_alpha_by_job: {"회피도사": 0.0157, "젤리술사": 0.02, ...} 처럼
      "직업별" 감쇠 배율. 여기에 해당 직업이 있으면 이 값을 우선 사용.
      (스킬/캐릭터가 아니라 직업 종류에 따라 에너지 충전 패턴이 다르다고 보고,
       직업 단위로 감쇠율을 따로 관리함)
    job_energy_alpha: job_energy_alpha_by_job에 해당 직업이 없을 때 쓰는
      기본 감쇠 배율. 1.0=이론치 100% 반영, 0.0=보너스 전혀 반영 안 함.
    """
    if index < 0 or index >= len(job_per_instance):
        job = None
    else:
        job = job_per_instance[index]

    rate = job_energy_rate_per_sec(job, jelly_pickups_per_cycle, seconds_per_cycle)
    raw_ratio = rate / JOB_BASE_ENERGY_PER_SEC  # 예: 회피도사 60/10=6.0, 방패지기 10/10=1.0

    alpha_map = job_energy_alpha_by_job or {}
    effective_alpha = alpha_map.get(job, job_energy_alpha) if job is not None else job_energy_alpha

    # alpha로 "보너스 부분(1.0을 초과하는 부분)"만 감쇠
    return 1.0 + effective_alpha * (raw_ratio - 1.0)


def count_job_members(job_per_instance: List[Optional[str]]) -> Dict[str, int]:
    """job_per_instance 안에서 직업별로 몇 명인지 센다 (미배정=None은 제외)."""
    counts: Dict[str, int] = {job: 0 for job in JOB_OPTIONS}
    for job in job_per_instance:
        if job in counts:
            counts[job] += 1
    return counts


def total_job_assigned_count(job_per_instance: List[Optional[str]]) -> int:
    """파티 중 직업이 하나라도 배정된 인원수 (소환석 조건부 옵션에 사용)"""
    return sum(1 for job in job_per_instance if job is not None)


def compute_party_energy_bonus_pct(
    party: List,
    job_per_instance: List[Optional[str]],
    jelly_pickups_per_cycle: float = None,
    seconds_per_cycle: float = None,
) -> float:
    """
    파티 전체의 "직업발 에너지 보너스"를 %로 환산.
    (게임속도 버프처럼 compute_async_dps_ratio의 speed_mult에 그대로 더해 쓸 수 있음)

    - 기준선(0%) = 파티 전원이 방패지기(=직업 미배정 포함)인 경우
    - 회피도사: 기본10 + 고정50 = 초당 60 에너지로 근사 (파티원 1명당 +50 에너지/초 보너스)
    - 젤리술사: 정확한 젤리 획득 빈도를 몰라도, 실측된 페이즈별 속도
      (1~2페: 1개/초, 3페: 2/3개/초)를 단순 평균한 JELLY_ASSUMED_BONUS_FLAT
      (constants.py, 기본 +12.5 고정치 -> 초당 약 22.5 에너지)을 사용함.

    Args:
      jelly_pickups_per_cycle / seconds_per_cycle: None이면 백엔드 상수 사용
        (JELLY_PICKUPS_PER_CYCLE_BACKEND / SECONDS_PER_CYCLE_BACKEND, 유저 비노출)
    """
    total_members = len(party)

    if total_members <= 0:
        return 0.0

    job_counts = count_job_members(job_per_instance)

    if jelly_pickups_per_cycle is None:
        jelly_pickups_per_cycle = JELLY_PICKUPS_PER_CYCLE_BACKEND
    if seconds_per_cycle is None:
        seconds_per_cycle = SECONDS_PER_CYCLE_BACKEND

    baseline = JOB_BASE_ENERGY_PER_SEC * total_members

    # 직업이 배정되지 않은 인원은 "방패지기와 동일"하게 기본 10/sec만 기여
    unassigned = total_members - sum(job_counts.values())

    total = JOB_BASE_ENERGY_PER_SEC * unassigned
    total += JOB_BASE_ENERGY_PER_SEC * job_counts.get("방패지기", 0)

    evasion_cnt = job_counts.get("회피도사", 0)
    total += (JOB_BASE_ENERGY_PER_SEC + EVASION_MAX_BONUS_FLAT) * evasion_cnt

    jelly_cnt = job_counts.get("젤리술사", 0)

    if jelly_cnt > 0:
        has_real_data = jelly_pickups_per_cycle > 0 and seconds_per_cycle > 0

        if has_real_data:
            jelly_energy_per_sec = (jelly_pickups_per_cycle * JELLY_BURST_ENERGY) / seconds_per_cycle
            total += (JOB_BASE_ENERGY_PER_SEC + jelly_energy_per_sec) * jelly_cnt
        else:
            total += (JOB_BASE_ENERGY_PER_SEC + JELLY_ASSUMED_BONUS_FLAT) * jelly_cnt

    if baseline <= 0:
        return 0.0

    return (total - baseline) / baseline * 100.0
