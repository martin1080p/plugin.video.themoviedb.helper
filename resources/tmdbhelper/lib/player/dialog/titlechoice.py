class PlayerCancelledError(Exception):
    """Raised when the user cancels a player-time selection dialog."""


def resolve_title_choice(default_value, alt_value, select_func):
    """Return the title to search with.

    default_value: the default (English/original) title.
    alt_value:     the alternate-language (e.g. Czech) title, or falsy if none.
    select_func:   callable(candidates: list[str]) -> int chosen index; a
                   negative index or None signals cancel.

    If there is no distinct alternate, returns default_value without prompting.
    Raises PlayerCancelledError if the user cancels.
    """
    if not alt_value or alt_value == default_value:
        return default_value

    candidates = [alt_value, default_value]  # alternate (Czech) listed first
    index = select_func(candidates)
    if index is None or index < 0 or index >= len(candidates):
        raise PlayerCancelledError()
    return candidates[index]
