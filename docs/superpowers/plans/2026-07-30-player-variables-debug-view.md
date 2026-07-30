# Player Variables Debug View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an in-addon debug view, reachable from the player select dialog, that lists every `PlayerDictionary` variable with its resolved value for the item being played and lets the developer test arbitrary format strings against that same item.

**Architecture:** A pure text-report builder plus a thin Kodi-dialog wrapper live in a new `player/dialog/debug.py`; the dialog row class lives in `player/dialog/item/debug.py` alongside the existing `item/clear.py`. The player select dialog layer (`standard.py` / `combined.py`) grows a gated `additional_players` entry and a shared `resolve_selection()` hook, so the debug item never reaches `Player.set_resolver()` and the resolver, pathfinder and dummy-file machinery stay untouched.

**Tech Stack:** Python 3 (Kodi 21 `xbmc.python` 3.0.1), `xbmcgui.Dialog` for I/O, `jurialmunkey.ftools.cached_property`. No test framework — tests are plain modules with a `_run()` main, matching `tests/test_dictionary_ask.py`.

## Global Constraints

- Design spec: `docs/superpowers/specs/2026-07-30-player-variables-debug-view-design.md`. Read it before starting.
- **pytest is NOT installed.** Run tests with `python3 tests/<file>.py`; exit code 0 means pass. Do not add a pytest dependency.
- Kodi modules (`xbmcgui`, `xbmcaddon`, `xbmc`) and the `tmdbhelper.*` package are NOT importable outside Kodi. Tests load modules by file path with stubbed `sys.modules`, exactly as `tests/test_dictionary_ask.py` does.
- Follow the codebase convention of **function-level imports** for anything Kodi- or `tmdbhelper`-related. Module-level imports in new files are limited to stdlib and `jurialmunkey.ftools`.
- New localized string id is **32538**. `#32537` ("Choose title for search") is the current highest. Add to `resources/language/resource.language.en_gb/strings.po` only; other languages fall back.
- Gate on the existing setting id `debug_logging`. Do not add a new setting.
- Do not change how variables resolve. `dictionary.py` is read-only for this work.
- Branch is `feature/player-variables-debug-view`, already created off `nexus`.
- Per fork convention (see `git log`), the final commit bumps `addon.xml` version. Current: `6.16.14` → target `6.16.15`.

---

### Task 1: Pure debug report builder

Builds the text shown in the view, and the error-capturing format helper. No Kodi calls, so it is fully unit-testable.

**Files:**
- Create: `resources/tmdbhelper/lib/player/dialog/debug.py`
- Test: `tests/test_debug_variables.py`

**Interfaces:**
- Consumes: `PlayerDictionaryDict` instances from `resources/tmdbhelper/lib/player/dialog/dictionary.py` — the attributes used are `.routes` (dict), `.details` (object with `.infoproperties`), `.encoding_methods` (dict), `.tmdb_type` (str), `.tmdb_id`, optional `.season` / `.episode`, `__getitem__`, and `.string_format_map(fmt)`.
- Produces:
  - `PlayerDebugReport(itemdict)` with `.text` → `str`
  - `format_result(itemdict, text)` → `str` (never raises)
  - `REGEX_TRANSLATION_KEY` — compiled pattern used to find translation infoproperties

- [ ] **Step 1: Write the failing test**

Create `tests/test_debug_variables.py`:

```python
import os
import sys
import importlib.util

_HERE = os.path.dirname(__file__)
_ROOT = os.path.abspath(os.path.join(_HERE, '..'))
sys.path.insert(0, _HERE)

# Importing this test module installs the jurialmunkey stubs into sys.modules and
# gives us the real PlayerDictionary classes loaded outside Kodi.
from test_dictionary_ask import (  # noqa: E402
    PlayerDictionaryDictMovie, PlayerDictionaryDictEpisode, _FakeDetails,
)


def _load_debug_module():
    path = os.path.join(
        _ROOT, 'resources', 'tmdbhelper', 'lib', 'player', 'dialog', 'debug.py')
    spec = importlib.util.spec_from_file_location('_debug_under_test', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_debug = _load_debug_module()
PlayerDebugReport = _debug.PlayerDebugReport
format_result = _debug.format_result


def _stub_now(itemdict):
    """`now` imports tmdbhelper.lib.addon.tmdate, which does not exist outside Kodi."""
    itemdict.routes['now'] = lambda **kwargs: '20260730203300000000'
    return itemdict


def _make_movie():
    itemdict = PlayerDictionaryDictMovie('550', _FakeDetails(
        infolabels={'title': 'Fight Club', 'originaltitle': 'Fight Club',
                    'year': 1999, 'premiered': '1999-10-15'},
        infoproperties={'cs_title': 'Klub rváčů', 'cs-CZ_title': 'Klub rváčů',
                        'cs_tagline': 'Mydlo', 'set.title': 'Fight Club Collection',
                        'tvshow.originaltitle': 'ignored'},
    ))
    itemdict.details.unique_ids = {'imdb': 'tt0137523'}
    return _stub_now(itemdict)


def test_variables_section_has_one_row_per_route():
    itemdict = _make_movie()
    report = PlayerDebugReport(itemdict)
    lines = list(report.section_variables)
    assert lines[0] == '[VARIABLES]'
    assert len(lines) == 1 + len(itemdict.routes)
    assert any(i.startswith('title') and 'Fight Club' in i for i in lines)


def test_none_and_empty_values_are_marked():
    itemdict = _make_movie()
    report = PlayerDebugReport(itemdict)
    assert report.get_value(None) == '<None>'
    assert report.get_value('') == '<empty>'
    assert report.get_value('x') == 'x'


def test_translation_keys_discovered_and_unroutable_flagged():
    itemdict = _make_movie()
    report = PlayerDebugReport(itemdict)
    keys = [k for k, _ in report.translation_keys]
    assert keys == ['cs-CZ_title', 'cs_tagline', 'cs_title']
    assert 'set.title' not in keys
    assert 'tvshow.originaltitle' not in keys
    text = '\n'.join(report.section_translations)
    assert 'cs_tagline' in text and 'no matching route' in text
    assert 'cs_title' in text


def test_encoding_section_covers_every_suffix():
    itemdict = _make_movie()
    lines = list(PlayerDebugReport(itemdict).section_encodings)
    assert lines[0] == '[ENCODING SUFFIXES on {title}]'
    assert len(lines) == 1 + len(itemdict.encoding_methods)
    assert any('Fight+Club' in i for i in lines)
    assert any('Fight%20Club' in i for i in lines)


def test_episode_encoding_section_uses_showname():
    itemdict = _stub_now(PlayerDictionaryDictEpisode('1396', _FakeDetails(
        infolabels={'title': 'Pilot', 'tvshowtitle': 'Breaking Bad'},
        infoproperties={},
    ), season=1, episode=1))
    lines = list(PlayerDebugReport(itemdict).section_encodings)
    assert lines[0] == '[ENCODING SUFFIXES on {showname}]'


def test_item_section_reports_episode_numbers():
    itemdict = _stub_now(PlayerDictionaryDictEpisode('1396', _FakeDetails(
        infolabels={'tvshowtitle': 'Breaking Bad'}, infoproperties={},
    ), season=1, episode=2))
    text = '\n'.join(PlayerDebugReport(itemdict).section_item)
    assert '[ITEM]' in text
    assert 'tmdb_type' in text and 'tv' in text
    assert 'season' in text and 'episode' in text


def test_text_contains_all_four_sections():
    text = PlayerDebugReport(_make_movie()).text
    for header in ('[ITEM]', '[VARIABLES]', '[TRANSLATIONS AVAILABLE]',
                   '[ENCODING SUFFIXES on {title}]'):
        assert header in text


def test_format_result_resolves_a_player_style_string():
    itemdict = _make_movie()
    result = format_result(itemdict, 'plugin://x/?q={title_url}&y={year}')
    assert result == 'plugin://x/?q=Fight%20Club&y=1999'


def test_format_result_returns_error_text_instead_of_raising():
    itemdict = _make_movie()
    for bad in ('{', '{}', '{title:bogus}', '{year:s}'):
        result = format_result(itemdict, bad)
        assert result.startswith('ValueError:'), (bad, result)


def test_format_result_handles_none_valued_format_spec():
    itemdict = _make_movie()
    result = format_result(itemdict, '{tvdb:>10}')
    assert result.startswith('TypeError:')


def test_format_result_unknown_key_yields_underscore_not_error():
    itemdict = _make_movie()
    assert format_result(itemdict, 'a{rating}b') == 'a_b'


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_debug_variables.py`
Expected: FAIL — `FileNotFoundError` / `spec.loader.exec_module` error because `debug.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `resources/tmdbhelper/lib/player/dialog/debug.py`:

```python
import re
from jurialmunkey.ftools import cached_property


# Translation infoproperties are written per available TMDb translation as
# <lang>_<field> and <lang>-<COUNTRY>_<field> — see
# items/database/itemmeta_factories/concrete_classes/basemedia.py
REGEX_TRANSLATION_KEY = re.compile(r'^([a-z]{2}(?:-[A-Z]{2})?)_(title|tvshowtitle|plot|tagline)$')

ROW_WIDTH = 26


def format_result(itemdict, text):
    """ Resolve a format string against itemdict, returning error text rather than raising """
    try:
        return itemdict.string_format_map(text)
    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as exc:
        return f'{exc.__class__.__name__}: {exc}'


class PlayerDebugReport:

    """ Builds the debug text for an item. Contains no Kodi calls so that it is unit-testable. """

    def __init__(self, itemdict):
        self.itemdict = itemdict

    @cached_property
    def details(self):
        return self.itemdict.details

    @cached_property
    def title_route(self):
        """ Episodes demonstrate encodings on the show name since that is what players search with """
        return 'showname' if 'showname' in self.itemdict.routes else 'title'

    @staticmethod
    def get_value(value):
        if value is None:
            return '<None>'
        if value == '':
            return '<empty>'
        return value

    def get_row(self, name, value):
        return f'{name:<{ROW_WIDTH}}{self.get_value(value)}'

    @property
    def section_item(self):
        yield '[ITEM]'
        yield self.get_row('tmdb_type', self.itemdict.tmdb_type)
        yield self.get_row('tmdb_id', self.itemdict.tmdb_id)
        yield self.get_row('season', getattr(self.itemdict, 'season', None))
        yield self.get_row('episode', getattr(self.itemdict, 'episode', None))

    @property
    def section_variables(self):
        yield '[VARIABLES]'
        for key in self.itemdict.routes:
            yield self.get_row(key, self.itemdict[key])

    @cached_property
    def translation_keys(self):
        """ [(infoproperty_key, field), ...] for every language-prefixed property on this item """
        return sorted(
            (key, match.group(2))
            for key, match in (
                (key, REGEX_TRANSLATION_KEY.match(key))
                for key in self.details.infoproperties
            )
            if match
        )

    @property
    def section_translations(self):
        yield '[TRANSLATIONS AVAILABLE]'
        if not self.translation_keys:
            yield 'none cached for this item'
            return
        for key, field in self.translation_keys:
            value = self.get_value(self.details.infoproperties[key])
            if field not in self.itemdict.routes:
                value = f'{value}   <- no matching route, {{{key}}} resolves to _'
            yield self.get_row(f'{{{key}}}', value)

    @property
    def section_encodings(self):
        yield f'[ENCODING SUFFIXES on {{{self.title_route}}}]'
        for suffix in self.itemdict.encoding_methods:
            key = f'{self.title_route}{suffix}'
            yield self.get_row(f'{{{key}}}', self.itemdict[key])

    @cached_property
    def text(self):
        sections = (
            self.section_item,
            self.section_variables,
            self.section_translations,
            self.section_encodings,
        )
        return '\n\n'.join('\n'.join(f'{i}' for i in section) for section in sections)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/test_debug_variables.py`
Expected: PASS for all 11 tests, exit 0.

Two expectations in that test were verified against the real classes before this plan was written: `sorted()` gives `['cs-CZ_title', 'cs_tagline', 'cs_title']` because `-` (0x2D) sorts before `_` (0x5F); and `tagline` is genuinely absent from `PlayerDictionaryDictMovie.routes` (as is `tvshowtitle`), which is what makes the "no matching route" annotation fire on `cs_tagline` and not on `cs_title`.

- [ ] **Step 5: Verify the existing suite still passes**

Run: `python3 tests/test_dictionary_ask.py`
Expected: 4 PASS, exit 0. (Task 1 touches nothing it depends on; this catches accidental edits to `dictionary.py`.)

- [ ] **Step 6: Commit**

```bash
git add resources/tmdbhelper/lib/player/dialog/debug.py tests/test_debug_variables.py
git commit -m "feat(player): add pure debug report builder for player variables"
```

---

### Task 2: Dialog row and the Kodi view

Adds the selectable row and the `Dialog()` orchestration: rebuild details with translations forced on, show the report, then run the format-string tester loop.

**Files:**
- Create: `resources/tmdbhelper/lib/player/dialog/item/debug.py`
- Modify: `resources/tmdbhelper/lib/player/dialog/debug.py` (append `PlayerDebugVariables`)
- Modify: `resources/language/resource.language.en_gb/strings.po` (append `#32538`)
- Test: `tests/test_debug_variables.py` (append)

**Interfaces:**
- Consumes: `PlayerDebugReport`, `format_result` from Task 1. `PlayerItemBasic` from `player/dialog/item/basic.py`. `PlayerDetails` from `player/dialog/details.py` (signature `PlayerDetails(tmdb_type, tmdb_id, season=None, episode=None, translation=False)`, attribute `.details`). `PlayerDictionary` from `player/dialog/dictionary.py` (signature `PlayerDictionary(tmdb_type, tmdb_id, season=None, episode=None, details=None)`).
- Produces:
  - `PlayerItemDebugVariables()` — a `PlayerItemBasic` with `is_valid = True`, `is_debug = True`, `plugin_name = 'plugin.video.themoviedb.helper'`, `name` property
  - `PlayerDebugVariables(itemdict)` with `.run()` (no return value) and `.dictionary` (falls back to `itemdict`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_debug_variables.py`, immediately above `def _run():`:

```python
class _FakeDialog:
    """Records textviewer calls and replays a scripted list of input() returns."""

    def __init__(self, inputs):
        self.inputs = list(inputs)
        self.viewed = []

    def textviewer(self, header, text):
        self.viewed.append((header, text))

    def input(self, header, **kwargs):
        return self.inputs.pop(0) if self.inputs else ''


def _make_view(itemdict, inputs=()):
    """PlayerDebugVariables with the translation rebuild and Kodi Dialog stubbed out."""
    view = _debug.PlayerDebugVariables(itemdict)
    view.get_translated_dictionary = lambda: None   # force the fallback path
    view.dialog = _FakeDialog(inputs)
    view.busy_dialog = lambda: _NullContext()
    return view


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_view_falls_back_to_passed_in_dictionary():
    itemdict = _make_movie()
    view = _make_view(itemdict)
    assert view.dictionary is itemdict


def test_view_shows_the_report_then_exits_on_empty_input():
    itemdict = _make_movie()
    view = _make_view(itemdict, inputs=[''])
    view.run()
    assert len(view.dialog.viewed) == 1
    assert '[VARIABLES]' in view.dialog.viewed[0][1]


def test_view_tester_loop_resolves_then_exits():
    itemdict = _make_movie()
    view = _make_view(itemdict, inputs=['{title_url}', ''])
    view.run()
    # first view is the report, second is the tester result
    assert len(view.dialog.viewed) == 2
    assert 'Fight%20Club' in view.dialog.viewed[1][1]


def test_view_tester_loop_survives_a_bad_format_string():
    itemdict = _make_movie()
    view = _make_view(itemdict, inputs=['{', '{title}', ''])
    view.run()
    assert len(view.dialog.viewed) == 3
    assert 'ValueError:' in view.dialog.viewed[1][1]
    assert 'Fight Club' in view.dialog.viewed[2][1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_debug_variables.py`
Expected: the four new tests FAIL with `AttributeError: module '_debug_under_test' has no attribute 'PlayerDebugVariables'`. The 11 from Task 1 still PASS.

- [ ] **Step 3: Write the row class**

Create `resources/tmdbhelper/lib/player/dialog/item/debug.py` (mirrors `item/clear.py`):

```python
from jurialmunkey.ftools import cached_property
from tmdbhelper.lib.player.dialog.item.basic import PlayerItemBasic
from tmdbhelper.lib.addon.plugin import get_localized


class PlayerItemDebugVariables(PlayerItemBasic):

    is_valid = True
    is_debug = True
    plugin_name = 'plugin.video.themoviedb.helper'

    @cached_property
    def name(self):
        return f'[COLOR red]{get_localized(32538)}[/COLOR]'
```

`is_valid = True` as a plain class attribute overrides the `cached_property` on `PlayerItemBasic`, which would otherwise reject the row for having no `actions` — this is the same trick `PlayerItemClearDefault` uses.

- [ ] **Step 4: Write the view class**

Append to `resources/tmdbhelper/lib/player/dialog/debug.py`:

```python
class PlayerDebugVariables:

    """ Shows the debug report for an item then loops a format-string tester """

    header = 'TMDbHelper player variables'
    tester_header = 'Test a format string'

    def __init__(self, itemdict):
        self.itemdict = itemdict

    @cached_property
    def dialog(self):
        from xbmcgui import Dialog
        return Dialog()

    def busy_dialog(self):
        from tmdbhelper.lib.addon.dialog import BusyDialog
        return BusyDialog()

    @cached_property
    def dictionary(self):
        """ Prefer a translation-forced rebuild so {<lang>_title} resolves even when
        no enabled player sets "language": true. Falls back to the dialog's own dictionary. """
        return self.get_translated_dictionary() or self.itemdict

    def get_translated_dictionary(self):
        from tmdbhelper.lib.player.dialog.details import PlayerDetails
        from tmdbhelper.lib.player.dialog.dictionary import PlayerDictionary
        tmdb_type = self.itemdict.tmdb_type
        tmdb_id = self.itemdict.tmdb_id
        season = getattr(self.itemdict, 'season', None)
        episode = getattr(self.itemdict, 'episode', None)
        try:
            details = PlayerDetails(
                tmdb_type, tmdb_id, season, episode, translation=True).details
        except AttributeError:  # PlayerDetails.details raises if get_details() returns None
            return
        if not details:
            return
        return PlayerDictionary(tmdb_type, tmdb_id, season, episode, details)

    @cached_property
    def text(self):
        return PlayerDebugReport(self.dictionary).text

    def run(self):
        with self.busy_dialog():
            text = self.text
        self.dialog.textviewer(self.header, text)
        self.run_tester()

    def run_tester(self):
        while True:
            entry = self.dialog.input(self.tester_header)
            if not entry:
                return
            result = format_result(self.dictionary, entry)
            self.dialog.textviewer(self.tester_header, f'{entry}\n\n{result}')
```

`dialog` and `busy_dialog` are indirected through the instance specifically so the tests above can replace them without importing Kodi.

- [ ] **Step 5: Add the localized string**

Append to the end of `resources/language/resource.language.en_gb/strings.po` (the file currently ends with the `#32537` block; keep one blank line between blocks):

```
#: /resources/tmdbhelper/lib/player/dialog/item/debug.py
msgctxt "#32538"
msgid "Debug variables"
msgstr ""
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 tests/test_debug_variables.py`
Expected: 15 PASS, exit 0.

- [ ] **Step 7: Verify the .po file is still well-formed**

Run: `python3 -c "
import re
p = 'resources/language/resource.language.en_gb/strings.po'
s = open(p, encoding='utf-8').read()
ids = re.findall(r'msgctxt \"#(\d+)\"', s)
assert len(ids) == len(set(ids)), 'duplicate msgctxt ids'
assert '32538' in ids, 'new string missing'
print('po ok,', len(ids), 'strings')
"`
Expected: `po ok, <n> strings` with no assertion error.

- [ ] **Step 8: Commit**

```bash
git add resources/tmdbhelper/lib/player/dialog/debug.py \
        resources/tmdbhelper/lib/player/dialog/item/debug.py \
        resources/language/resource.language.en_gb/strings.po \
        tests/test_debug_variables.py
git commit -m "feat(player): add debug variables dialog row and view"
```

---

### Task 3: Wire the entry into the player select dialog

Makes the row appear (gated) and handles the pick without letting it reach the resolver.

**Files:**
- Modify: `resources/tmdbhelper/lib/player/dialog/standard.py` (whole file rewritten below)
- Modify: `resources/tmdbhelper/lib/player/dialog/combined.py:31-49` (the `select` method)
- Modify: `addon.xml:3` (version bump)
- Test: `tests/test_debug_selection.py`

**Interfaces:**
- Consumes: `PlayerItemDebugVariables` and `PlayerDebugVariables` from Task 2.
- Produces: `PlayerSelectStandard.additional_players` (list) and `PlayerSelectStandard.resolve_selection(player)` → the player, or `None` when the pick was a handled debug action. `PlayerSelectCombined` inherits both.

- [ ] **Step 1: Write the failing test**

Create `tests/test_debug_selection.py`:

```python
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
    listitem.PlayerListItem = object
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_debug_selection.py`
Expected: FAIL — `additional_players` is still the class-level `[]` so the first test fails, and `resolve_selection` does not exist.

- [ ] **Step 3: Rewrite standard.py**

Replace the whole of `resources/tmdbhelper/lib/player/dialog/standard.py` with:

```python
from jurialmunkey.ftools import cached_property
from tmdbhelper.lib.addon.plugin import get_localized, get_setting
from tmdbhelper.lib.player.dialog.listitem import PlayerListItem
from xbmcgui import Dialog


class PlayerSelectStandard:

    player_uid = None

    def __init__(self, data):
        self.data = data

    @cached_property
    def additional_players(self):
        """ Debug row, only in the play flow and only with debug logging enabled.
        self.data.item is None when choosing a default player from settings, where
        PlayerDefaultMovie assigns its own additional_players over this. """
        if not get_setting('debug_logging'):
            return []
        if not self.data.item:
            return []
        from tmdbhelper.lib.player.dialog.item.debug import PlayerItemDebugVariables
        return [PlayerItemDebugVariables()]

    @property
    def players(self):
        return self.data.items or []

    @property
    def players_list(self):
        players_list = self.additional_players + self.players
        return players_list

    def players_generator(self, player_item=PlayerListItem):
        return (player_item(i, x) for x, i in enumerate(self.players_list))

    @property
    def players_generated_list(self):
        return [
            j for j in self.players_generator()
            if self.player_uid is None or j.uid == self.player_uid
        ]

    @staticmethod
    def select_player(players_list, header=None, detailed=True, index=False):
        """ Select from a list of players """
        x = Dialog().select(
            header or get_localized(32042),
            [i.listitem for i in players_list],
            useDetails=detailed
        )
        return x if index or x == -1 else players_list[x].posx

    def get_player(self, x):
        return self.players_list[x]

    def resolve_selection(self, player):
        """ Return player, or None if the pick was a debug action that has been handled """
        if not getattr(player, 'is_debug', False):
            return player
        from tmdbhelper.lib.player.dialog.debug import PlayerDebugVariables
        PlayerDebugVariables(self.data.item).run()
        self.player_uid = None  # defensive: never leave the list filtered to the debug row
        return None

    def select(self, header=None, detailed=True):
        """ Select a player from the list """
        while True:
            x = self.select_player(self.players_generated_list, header=header, detailed=detailed)
            if x == -1:
                return {}
            player = self.resolve_selection(self.get_player(x))
            if player is not None:
                return player
```

Changes from the original: `additional_players` is now a `cached_property` instead of a class attribute; `resolve_selection` is new; `select` loops. Everything else is byte-identical.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/test_debug_selection.py`
Expected: 8 PASS, exit 0.

- [ ] **Step 5: Wire combined mode**

In `resources/tmdbhelper/lib/player/dialog/combined.py`, change the `select` method's loop body from:

```python
            player = self.select_from_group(self.set_current_group(x))
```

to:

```python
            player = self.select_from_group(self.set_current_group(x))
            player = self.resolve_selection(player)
```

`resolve_selection` returns falsy (`None`) for a debug pick and the existing `while not player:` supplies the re-prompt. It passes `{}` through unchanged, so cancel-inside-a-group still loops as before.

- [ ] **Step 6: Verify combined mode by inspection and re-run both suites**

Run: `python3 -c "
import re
s = open('resources/tmdbhelper/lib/player/dialog/combined.py').read()
assert 'self.resolve_selection(player)' in s, 'combined.py not wired'
assert s.count('resolve_selection') == 1, 'unexpected extra call'
print('combined.py wired')
"`
Expected: `combined.py wired`

Run: `python3 tests/test_debug_variables.py && python3 tests/test_dictionary_ask.py && python3 tests/test_debug_selection.py`
Expected: all three suites PASS, exit 0.

- [ ] **Step 7: Byte-compile every touched file**

Run: `python3 -m py_compile resources/tmdbhelper/lib/player/dialog/debug.py resources/tmdbhelper/lib/player/dialog/item/debug.py resources/tmdbhelper/lib/player/dialog/standard.py resources/tmdbhelper/lib/player/dialog/combined.py && echo "compile ok"`
Expected: `compile ok`

- [ ] **Step 8: Bump the addon version**

In `addon.xml:3`, change `version="6.16.14"` to `version="6.16.15"`.

- [ ] **Step 9: Commit**

```bash
git add resources/tmdbhelper/lib/player/dialog/standard.py \
        resources/tmdbhelper/lib/player/dialog/combined.py \
        tests/test_debug_selection.py addon.xml
git commit -m "feat(player): show debug variables entry in player select dialog

Bumps version to 6.16.15."
```

- [ ] **Step 10: Manual verification in Kodi**

The active install is the Flatpak profile, **not** `~/.kodi`:
- addon: `/home/martin/.var/app/tv.kodi.Kodi/data/addons/plugin.video.themoviedb.helper`
- log: `/home/martin/.var/app/tv.kodi.Kodi/data/temp/kodi.log`

Deploy the branch to that addon directory (copy `resources/` over, or however the user normally syncs), restart Kodi, then:

1. Settings → Advanced → enable **Debug logging**.
2. On a movie, Play with TMDbHelper. Confirm a red **Debug variables** row appears in the player list.
3. Select it. Confirm the textviewer shows `[ITEM]`, `[VARIABLES]`, `[TRANSLATIONS AVAILABLE]`, `[ENCODING SUFFIXES on {title}]`, and that `cs_title` has a real value (proving the `translation=True` rebuild worked).
4. Dismiss it. At the input prompt type `plugin://x/?q={ask_cs_title_url}` and confirm the ask-dialog appears and the resolved string is shown. Press cancel/empty to exit the tester.
5. Confirm you land back on the player list and can then play normally.
6. Repeat steps 2–5 on a TV episode; confirm the encodings section reads `{showname}` and that `epimdb` / `season` / `episode` are populated.
7. Settings → Players → Default player for movies. Confirm the debug row is **absent** and only "Clear default" is added.
8. Disable Debug logging, repeat step 2, and confirm the row is gone.

Report any deviation rather than patching over it — an unexpected result here means the design assumption was wrong.

---

## Self-Review

**Spec coverage**

| Spec section | Task |
|---|---|
| `PlayerItemDebugVariables` row | Task 2 Step 3 |
| `PlayerDebugVariables` view | Task 2 Step 4 |
| `additional_players` gated cached_property | Task 3 Step 3 |
| `resolve_selection` shared helper | Task 3 Step 3 |
| `standard.py` select loop | Task 3 Step 3 |
| `combined.py` re-prompt | Task 3 Step 5 |
| strings.po `#32538` | Task 2 Step 5 |
| Translation-forced rebuild + fallback | Task 2 Step 4, tested Task 2 Step 1 |
| Four report sections | Task 1 Step 3, tested Task 1 Step 1 |
| Tester loop | Task 2 Step 4, tested Task 2 Step 1 |
| Error handling table (6 failure modes) | Task 1 `format_result`, tested Task 1 Step 1 |
| Testing section | Tasks 1–3, plus Task 3 Step 10 manual |
| Success criteria | Task 3 Step 10 manual steps 1–8 |

No gaps.

**Placeholder scan:** No TBD/TODO, no "add error handling", no "similar to Task N". Every code step carries complete code.

**Type consistency:** `is_debug` is the marker in Task 2 Step 3 and read via `getattr(player, 'is_debug', False)` in Task 3 Step 3. `PlayerDebugVariables(itemdict).run()` is defined in Task 2 Step 4 and called with that exact shape in Task 3 Step 3 and stubbed with that shape in Task 3 Step 1. `format_result(itemdict, text)` and `PlayerDebugReport(itemdict).text` are defined in Task 1 and consumed in Task 2 Step 4 under the same names. `get_value` is a `@staticmethod` in Task 1 Step 3 and called as `report.get_value(None)` in Task 1 Step 1 — valid on an instance.
