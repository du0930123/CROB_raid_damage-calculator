from typing import Dict, List

from src.characters import Character, CHARACTER_DB


CHARACTER_ALIAS: Dict[str, str] = {
    "눈설": "눈설탕",
    "눈설탕": "눈설탕",
    "눈": "눈설탕",

    "캡아": "캡틴아이스",
    "캡틴": "캡틴아이스",
    "캡틴아이스": "캡틴아이스",
    "캡": "캡틴아이스",

    "스네": "스네이크",
    "스네이크": "스네이크",
    "스": "스네이크",

    "인삼": "인삼",
    "인": "인삼",

    "비트": "비트",
    "비": "비트",

    "레판": "레판",
    "레": "레판",

    "뱀파": "뱀파",
    "뱀": "뱀파",
}


def build_party_from_text(text: str) -> List[Character]:
    tokens = text.split()

    if len(tokens) % 2 != 0:
        raise ValueError("파티 구성은 '이름 수량' 쌍이어야 합니다. 예) 비트 3 레판 1")

    party: List[Character] = []

    for i in range(0, len(tokens), 2):
        raw_name = tokens[i]
        count = int(tokens[i + 1])

        if raw_name not in CHARACTER_ALIAS:
            raise KeyError(
                f"알 수 없는 캐릭터: {raw_name} / 사용 가능: {', '.join(CHARACTER_ALIAS.keys())}"
            )

        name = CHARACTER_ALIAS[raw_name]

        if name not in CHARACTER_DB:
            raise KeyError(f"DB에 없는 캐릭터: {name}")

        if count <= 0:
            continue

        party.extend([CHARACTER_DB[name]] * count)

    return party