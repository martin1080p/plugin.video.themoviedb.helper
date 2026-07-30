import os
import sys
import types
import importlib.util
from functools import cached_property

_HERE = os.path.dirname(__file__)
_ROOT = os.path.abspath(os.path.join(_HERE, '..'))

_SETTINGS = {'debug_logging': True}
_RAN = []


def _load_standard_module():
    """Load standard.py in isolation, stubbing its Kodi-only dependencies."""

    jm = types.ModuleType('jurialmunkey')
    jm_ftools = types.ModuleType('jurialmunkey.ftools')
    jm_ftools.cached_property = cached_property
    sys.modules['jurialmunkey'] = jm
    sys.modules['jurialmunkey.ftools'] = jm_ftools

    xbmcgui = types.ModuleType('xbmcgui')
    xbmcgui.Dialog = lambda: None
    sys.modules['xbmcgui'] = xbmcgui

    plugin = types.ModuleType('tmdbhelper.lib.addon.plugin')
    plugin.get_localized = lambda i: f'#{i}'
    plugin.get_setting = lambda k, *a, **kw: _SETTINGS.get(k)
    sys.modules['tmdbhelper.lib.addon.plugin'] = plugin

    listitem = types.ModuleType('tmdbhelper.lib.player.dialog.listitem')

    class _FakeListItem:
        """Minimal stand-in: real PlayerListItem(item, x) exposes .uid and .posx."""
        def __init__(self, item, x):
            self.item = item
            self.posx = x
            self.uid = getattr(item, 'uid', x)
    listitem.PlayerListItem = _FakeListItem
    sys.modules['tmdbhelper.lib.player.dialog.listitem'] = listitem

    item_debug = types.ModuleType('tmdbhelper.lib.player.dialog.item.debug')

    class _FakeDebugItem:
        is_debug = True
        name = 'Debug variables'
    item_debug.PlayerItemDebugVariables = _FakeDebugItem
    sys.modules['tmdbhelper.lib.player.dialog.item.debug'] = item_debug

    dialog_debug = types.ModuleType('tmdbhelper.lib.player.dialog.debug')

    class _FakeView:
        def __init__(self, itemdict):
            self.itemdict = itemdict

        def run(self):
            _RAN.append(self.itemdict)
    dialog_debug.PlayerDebugVariables = _FakeView
    sys.modules['tmdbhelper.lib.player.dialog.debug'] = dialog_debug

    path = os.path.join(
        _ROOT, 'resources', 'tmdbhelper', 'lib', 'player', 'dialog', 'standard.py')
    spec = importlib.util.spec_from_file_location('_standard_under_test', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, _FakeDebugItem


_standard, FakeDebugItem = _load_standard_module()
PlayerSelectStandard = _standard.PlayerSelectStandard


class _FakeData:
    def __init__(self, items, item='dictionary-sentinel'):
        self.items = items
        self.item = item


class _FakePlayer:
    is_debug = False

    def __init__(self, name):
        self.name = name


def test_debug_entry_present_when_debug_logging_on_and_item_exists():
    _SETTINGS['debug_logging'] = True
    select = PlayerSelectStandard(data=_FakeData([_FakePlayer('a')]))
    assert len(select.additional_players) == 1
    assert select.additional_players[0].is_debug is True


def test_debug_entry_absent_when_debug_logging_off():
    _SETTINGS['debug_logging'] = False
    select = PlayerSelectStandard(data=_FakeData([_FakePlayer('a')]))
    assert select.additional_players == []
    _SETTINGS['debug_logging'] = True


def test_debug_entry_absent_in_choose_default_player_flow():
    """PlayerItems is built with item=None when picking a default player in settings."""
    _SETTINGS['debug_logging'] = True
    select = PlayerSelectStandard(data=_FakeData([_FakePlayer('a')], item=None))
    assert select.additional_players == []


def test_additional_players_can_still_be_assigned_over():
    """PlayerDefaultMovie assigns additional_players directly; that must win."""
    _SETTINGS['debug_logging'] = True
    select = PlayerSelectStandard(data=_FakeData([_FakePlayer('a')]))
    sentinel = ['clear-default']
    select.additional_players = sentinel
    assert select.additional_players is sentinel


def test_resolve_selection_passes_real_players_through():
    select = PlayerSelectStandard(data=_FakeData([]))
    player = _FakePlayer('a')
    assert select.resolve_selection(player) is player


def test_resolve_selection_runs_view_and_returns_none_for_debug_item():
    _RAN.clear()
    select = PlayerSelectStandard(data=_FakeData([]))
    assert select.resolve_selection(FakeDebugItem()) is None
    assert _RAN == ['dictionary-sentinel']


def test_select_reprompts_after_a_debug_pick_then_returns_the_real_player():
    _RAN.clear()
    _SETTINGS['debug_logging'] = True
    real = _FakePlayer('real')
    select = PlayerSelectStandard(data=_FakeData([real]))
    picks = iter([0, 1])   # first the debug row (index 0), then the real player

    select.select_player = lambda *args, **kwargs: next(picks)

    result = select.select()
    assert result is real
    assert len(_RAN) == 1


def test_select_returns_empty_dict_on_cancel():
    select = PlayerSelectStandard(data=_FakeData([_FakePlayer('a')]))
    select.select_player = lambda *args, **kwargs: -1
    assert select.select() == {}


def _run():
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print(f'PASS {name}')
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f'FAIL {name}: {exc!r}')
    return failures


if __name__ == '__main__':
    sys.exit(1 if _run() else 0)
