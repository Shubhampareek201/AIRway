"""Audience validation shared by catalogue, cart and booking flows."""


def validate_beauty_audience(service, category_answers):
    """Require an explicit, exact Beauty audience for customer transactions."""
    if not isinstance(category_answers, dict):
        category_answers = {}

    category = service.category
    while category.parent_id and category.parent is not None:
        category = category.parent
    if category.slug != "beauty":
        return

    selected = str(category_answers.get("beauty_audience") or "").strip().lower()
    if selected not in {"men", "women", "both"}:
        raise ValueError("Choose Men, Women or Unisex before continuing.")

    # 'all' is the database value for Unisex. It is not a fallback for Men/Women.
    allowed = {
        "men": "men",
        "women": "women",
        "both": "all",
    }[selected]
    if service.audience != allowed:
        raise ValueError(
            "This service belongs to a different Beauty audience. "
            "Return to Beauty and choose the matching section."
        )
