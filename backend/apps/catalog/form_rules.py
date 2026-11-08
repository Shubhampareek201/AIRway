"""Shared visibility evaluation for configurable service questions."""


def is_form_field_visible(form_field, answers):
    """Return whether a FormField is visible for the supplied combined answers.

    Rules are ANDed. Supported operators: equals, not_equals, in.
    Missing dependency answers never satisfy a rule.
    """
    rules = form_field.visibility_rules or []
    if not isinstance(rules, list):
        return False

    for rule in rules:
        if not isinstance(rule, dict):
            return False
        key = rule.get("field")
        operator = rule.get("operator", "equals")
        expected = rule.get("value")
        if not isinstance(key, str) or not key or key not in answers:
            return False

        actual = answers[key]
        if operator == "equals":
            matched = actual == expected
        elif operator == "not_equals":
            matched = actual != expected
        elif operator == "in":
            values = expected if isinstance(expected, list) else [expected]
            matched = actual in values
        else:
            return False

        if not matched:
            return False

    return True


def visible_form_fields(fields, category_answers=None, form_answers=None):
    """Return active fields visible for the combined customer answers."""
    answers = {}
    if isinstance(category_answers, dict):
        answers.update(category_answers)
    if isinstance(form_answers, dict):
        answers.update(form_answers)
    return [
        field for field in fields
        if is_form_field_visible(field, answers)
    ]
