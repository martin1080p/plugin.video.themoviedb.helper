"""A malformed player JSON must be skipped, not abort the whole player list."""
import importlib.util
import os
import sys
import types

_HERE = os.path.dirname(__file__)
_ROOT = os.path.abspath(os.path.join(_HERE, '..'))

# PlayerMeta imports Kodi-only modules at import time; stub the three it needs.
for _name, _attrs in (
    ('jurialmunkey.ftools', {'cached_property': property}),
    ('jurialmunkey.parser', {'boolean': lambda v: bool(v) and v not in ('false', 'False')}),
    ('tmdbhelper.lib.files.futils', {'read_file': lambda p: _FILES[p]}),
    ('tmdbhelper.lib.addon.plugin', {'get_condvisibility': lambda c: 'plugin.undefined' not in c}),
    ('tmdbhelper.lib.addon.consts', {'PLAYERS_PRIORITY': 1000}),
    ('tmdbhelper.lib.addon.logger', {'kodi_log': lambda *a, **k: None}),
):
    for _pkg in ('jurialmunkey', 'tmdbhelper', 'tmdbhelper.lib', 'tmdbhelper.lib.files', 'tmdbhelper.lib.addon'):
        sys.modules.setdefault(_pkg, types.ModuleType(_pkg))
    _mod = types.ModuleType(_name)
    _mod.__dict__.update(_attrs)
    sys.modules[_name] = _mod

_FILES = {}

_spec = importlib.util.spec_from_file_location('playermeta', os.path.join(
    _ROOT, 'resources', 'tmdbhelper', 'lib', 'player', 'config', 'meta.py'))
playermeta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(playermeta)
PlayerMeta = playermeta.PlayerMeta


def test_malformed_json_is_skipped_not_raised():
    _FILES['/players/junk.json'] = 'arch: amd64\nmemory: 512\n'  # not JSON at all
    meta = PlayerMeta('/players/', 'junk.json')
    assert meta.meta == {}
    assert not meta.is_enabled  # no plugin key -> dummy name -> fails the check
    assert meta.priority  # still sortable, so it cannot break the list build


def test_valid_json_still_parses():
    _FILES['/players/good.json'] = '{"name": "X", "plugin": "plugin.video.x", "priority": 2}'
    meta = PlayerMeta('/players/', 'good.json')
    assert meta.meta['name'] == 'X'
    assert meta.is_enabled
