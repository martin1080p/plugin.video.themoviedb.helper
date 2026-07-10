import importlib.util
import os

import pytest

_HERE = os.path.dirname(__file__)
_MODULE_PATH = os.path.abspath(os.path.join(
    _HERE, '..', 'resources', 'tmdbhelper', 'lib', 'player', 'dialog', 'titlechoice.py'
))
_spec = importlib.util.spec_from_file_location('titlechoice', _MODULE_PATH)
titlechoice = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(titlechoice)

resolve_title_choice = titlechoice.resolve_title_choice
PlayerCancelledError = titlechoice.PlayerCancelledError


def test_two_distinct_titles_shows_dialog_alt_first():
    seen = {}

    def select_func(candidates):
        seen['candidates'] = candidates
        return 0  # user picks first row

    result = resolve_title_choice('The Dark Knight', 'Temný rytíř', select_func)
    assert seen['candidates'] == ['Temný rytíř', 'The Dark Knight']  # alt first
    assert result == 'Temný rytíř'


def test_pick_second_row_returns_default():
    result = resolve_title_choice('The Dark Knight', 'Temný rytíř', lambda c: 1)
    assert result == 'The Dark Knight'


def test_no_alternate_uses_default_without_dialog():
    def select_func(candidates):
        raise AssertionError('dialog must not be shown')

    assert resolve_title_choice('The Dark Knight', None, select_func) == 'The Dark Knight'
    assert resolve_title_choice('The Dark Knight', '', select_func) == 'The Dark Knight'


def test_identical_titles_uses_default_without_dialog():
    def select_func(candidates):
        raise AssertionError('dialog must not be shown')

    assert resolve_title_choice('Inception', 'Inception', select_func) == 'Inception'


def test_cancel_negative_index_raises():
    with pytest.raises(PlayerCancelledError):
        resolve_title_choice('The Dark Knight', 'Temný rytíř', lambda c: -1)


def test_cancel_none_raises():
    with pytest.raises(PlayerCancelledError):
        resolve_title_choice('The Dark Knight', 'Temný rytíř', lambda c: None)


def test_cancel_out_of_range_index_raises():
    with pytest.raises(PlayerCancelledError):
        resolve_title_choice('The Dark Knight', 'Temný rytíř', lambda c: 2)
