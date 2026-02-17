def get_user_display_name(user) -> str:
    full_name = (user.get_full_name() or "").strip()
    return full_name or "Без имени"
