"""Shared visibility evaluation for configurable service questions."""


SUPPORTED_VISIBILITY_OPERATORS = {"equals", "not_equals", "in"}


def validate_visibility_rules(rules):
    """Reject malformed admin configuration instead of silently hiding fields."""
    if not isinstance(rules, list):
        raise ValueError("Visibility rules must be a list.")

    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("Each visibility rule must be an object.")
        key = rule.get("field")
        operator = rule.get("operator", "equals")
        if not isinstance(key, str) or not key:
            raise ValueError("Each visibility rule needs a dependency field.")
        if operator not in SUPPORTED_VISIBILITY_OPERATORS:
            raise ValueError(f"Unsupported visibility operator: {operator}.")
        if "value" not in rule:
            raise ValueError("Each visibility rule needs a comparison value.")
        if operator == "in" and not isinstance(rule["value"], list):
            raise ValueError("The 'in' operator requires a list of values.")


def is_form_field_visible(form_field, answers):
    """Return whether a FormField is visible for the supplied combined answers.

    Rules are ANDed. Supported operators: equals, not_equals, in.
    Missing dependency answers never satisfy a rule.
    """
    rules = form_field.visibility_rules or []
    validate_visibility_rules(rules)

    for rule in rules:
        key = rule["field"]
        if key not in answers:
            return False

        actual = answers[key]
        expected = rule["value"]
        operator = rule.get("operator", "equals")
        if operator == "equals":
            matched = str(actual) == str(expected)
        elif operator == "not_equals":
            matched = str(actual) != str(expected)
        else:  # in
            matched = any(str(actual) == str(item) for item in expected)

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
