TEXT_CHAR_LIMIT = 100


def exceeds_char_limit(value: str, limit: int = TEXT_CHAR_LIMIT) -> bool:
    return len(value or "") > limit


def char_limit_error(limit: int = TEXT_CHAR_LIMIT) -> str:
    return f"Введите значение не длиннее {limit} символов."
