"""Audience validation shared by catalogue and booking flows."""


def validate_beauty_audience(service, category_answers):
    """Reject a Beauty service outside the audience explicitly selected by customer."""
    if not isinstance(category_answers, dict):
        return
    category = service.category
    while category.parent_id:
        category = category.parent
    if category.slug != "beauty":
        return

    selected = category_answers.get("beauty_audience")
    if selected is None:
        # Keep older API clients compatible; the AIRway customer UI always sends it.
        return
    if selected not in {"men", "women", "both"}:
        raise ValueError("Choose Men, Women or Both for Beauty services.")

    service_audience = service.audience
    allowed = {
        "men": {"men", "all"},
        "women": {"women", "all"},
        "both": {"all"},
    }[selected]
    if service_audience not in allowed:
        raise ValueError(
            "This service is not listed for the selected Beauty audience. "
            "Go back and choose the correct audience."
        )
