# Prehraj.to Title-Language Choice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When playing a movie or TV episode via the Prehraj.to player, let the user pick between the Czech and the English/original title (shown as plain titles) and search with that choice.

**Architecture:** Add a pure, dependency-free decision helper (`resolve_title_choice`) plus a `PlayerCancelledError`. Wire a new `{ask_<lang>_<route>}` placeholder family into the player placeholder resolver (`PlayerDictionaryDict.__missing__`) that, at resolve time, offers a Kodi `Dialog().select` between the default title and the `<lang>` translation, caches the pick, and URL-encodes it via the existing affix machinery. Prehraj.to's JSON opts into translations (`"language": true`) and uses `{ask_cs_title_url}` / `{ask_cs_showname_url}`. Cancelling the dialog raises `PlayerCancelledError`, which the play loop catches to abort cleanly.

**Tech Stack:** Python 3 (Kodi addon), Kodi `xbmcgui.Dialog`, pytest for the one pure-logic test.

## Global Constraints

- Placeholder language is generic (`ask_<lang>_<route>`), never hardcoded to `cs` in Python; Prehraj.to supplies `cs` via its JSON. (from spec: "keep it generic")
- Dialog rows are **plain titles only**, Czech (the alternate) listed first, then English/original. No language suffix. (from spec)
- No dialog when there is no alternate translation or the two titles are identical; just use the default title. (from spec)
- Cancel aborts playback cleanly — never silently fall back to an unintended search. (from spec)
- The pure helper module must import nothing from `xbmc*`, `jurialmunkey`, or other addon internals, so it is testable outside Kodi.
- New localized string id: **32537** (current max is 32536).
- This repo uses namespace packages (no `__init__.py`); the unit test loads the pure module directly via `importlib`, not via package import.

---

### Task 1: Pure title-choice helper + unit tests

**Files:**
- Create: `resources/tmdbhelper/lib/player/dialog/titlechoice.py`
- Test: `tests/test_titlechoice.py`

**Interfaces:**
- Produces:
  - `class PlayerCancelledError(Exception)` — raised on user cancel.
  - `resolve_title_choice(default_value, alt_value, select_func) -> str` — returns the chosen title string; raises `PlayerCancelledError` if `select_func` signals cancel. `select_func(candidates: list[str]) -> int` returns the chosen index, or a negative number / `None` for cancel.

- [ ] **Step 1: Ensure pytest is available**

Run: `python3 -m pytest --version`
If it prints a version, skip. Otherwise install it:
Run: `python3 -m pip install --user pytest`
Expected: pytest reports a version (e.g. `pytest 8.x`).

- [ ] **Step 2: Write the failing tests**

Create `tests/test_titlechoice.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_titlechoice.py -v`
Expected: FAIL/ERROR — `titlechoice.py` does not exist (`FileNotFoundError` / module load error).

- [ ] **Step 4: Write the pure helper**

Create `resources/tmdbhelper/lib/player/dialog/titlechoice.py`:

```python
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
    if index is None or index < 0:
        raise PlayerCancelledError()
    return candidates[index]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_titlechoice.py -v`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add resources/tmdbhelper/lib/player/dialog/titlechoice.py tests/test_titlechoice.py
git commit -m "feat(player): add pure title-language choice helper with tests"
```

---

### Task 2: Add localized dialog-header string

**Files:**
- Modify: `resources/language/resource.language.en_gb/strings.po`

**Interfaces:**
- Produces: localized string id `32537`, consumed by Task 3's `title_select`.

- [ ] **Step 1: Append the new string to en_gb**

Append to the end of `resources/language/resource.language.en_gb/strings.po`:

```po

#: /resources/tmdbhelper/lib/player/dialog/dictionary.py
msgctxt "#32537"
msgid "Choose title for search"
msgstr ""
```

(Other languages fall back to en_gb automatically; no other `.po` edits required.)

- [ ] **Step 2: Verify the id is present and unique**

Run: `grep -c 'msgctxt "#32537"' resources/language/resource.language.en_gb/strings.po`
Expected: `1`

- [ ] **Step 3: Commit**

```bash
git add resources/language/resource.language.en_gb/strings.po
git commit -m "feat(lang): add 'Choose title for search' string (#32537)"
```

---

### Task 3: Wire the `{ask_<lang>_<route>}` placeholder into the resolver

**Files:**
- Modify: `resources/tmdbhelper/lib/player/dialog/dictionary.py` (imports, `__missing__` at lines 32-54, add `title_select` method)

**Interfaces:**
- Consumes: `resolve_title_choice` from Task 1; localized string `32537` from Task 2.
- Produces: placeholder keys `{ask_<lang>_<route>}` (and their encoding-affix variants such as `{ask_cs_title_url}`) resolvable on any `PlayerDictionaryDict`. Consumed by Task 5's `prehrajto.json`.

- [ ] **Step 1: Add the import**

At the top of `dictionary.py`, after the existing imports (after line 5), add:

```python
from tmdbhelper.lib.player.dialog.titlechoice import resolve_title_choice
```

- [ ] **Step 2: Insert the `ask_` branch into `__missing__`**

In `dictionary.py`, the current `__missing__` (lines 32-54) has a "Basic routes" block, then a "Translation routes" block. Insert the new branch **between** them. The method becomes:

```python
    def __missing__(self, key):

        # Basic routes for details
        with contextlib.suppress(KeyError, AttributeError):
            self[key] = self.routes[key]()
            self[key] = self.get_sanitised(self[key])
            return self[key]

        # Ask routes: {ask_<lang>_<route>} prompts the user to choose between the
        # default title and the <lang> translation, then caches the pick.
        if key.startswith('ask_'):
            with contextlib.suppress(KeyError, AttributeError, ValueError):
                _, language, route_key = key.split('_', 2)
                default_value = self.routes[route_key]()
                alt_value = self.routes[route_key](language=language)
                self[key] = resolve_title_choice(default_value, alt_value, self.title_select)
                self[key] = self.get_sanitised(self[key])
                return self[key]

        # Translation routes
        with contextlib.suppress(KeyError, AttributeError, ValueError):
            language, route_key = key.split('_', 1)
            self[key] = self.routes[route_key](language=language)
            return self[key]

        # Encoding affixes
        for method in self.encoding_affixes:
            if not key.endswith(method):
                continue
            self[key] = self[key[:-len(method)]]
            self[key] = self.get_sanitised(self[key], method)
            return self[key]

        return '_'
```

Note: `{ask_cs_title_url}` is handled by the encoding-affix branch — it strips `_url`, resolves `{ask_cs_title}` (which fires the dialog once and caches), then URL-encodes. `PlayerCancelledError` is not in any `suppress` tuple, so it propagates out (handled in Task 4).

- [ ] **Step 3: Add the `title_select` method**

Add this method to `PlayerDictionaryDict` (e.g. directly after `string_format_map`, around line 57):

```python
    def title_select(self, candidates):
        from xbmcgui import Dialog
        from tmdbhelper.lib.addon.plugin import get_localized
        return Dialog().select(get_localized(32537), candidates)
```

- [ ] **Step 4: Verify the module still imports and existing tests pass**

Run: `python3 -m pytest tests/test_titlechoice.py -v`
Expected: PASS (unchanged — the pure module is independent).
Run: `python3 -c "import ast; ast.parse(open('resources/tmdbhelper/lib/player/dialog/dictionary.py').read()); print('syntax ok')"`
Expected: `syntax ok`

- [ ] **Step 5: Commit**

```bash
git add resources/tmdbhelper/lib/player/dialog/dictionary.py
git commit -m "feat(player): resolve {ask_<lang>_<route>} title-choice placeholder"
```

---

### Task 4: Abort playback cleanly on cancel

**Files:**
- Modify: `resources/tmdbhelper/lib/player/dialog/player.py` (`Player.loop`, lines 261-277)

**Interfaces:**
- Consumes: `PlayerCancelledError` from Task 1; the placeholder that raises it from Task 3.

- [ ] **Step 1: Wrap the path resolution in `loop` with a cancel guard**

Replace the current `loop` method (lines 261-277) with:

```python
    def loop(self):

        from tmdbhelper.lib.player.dialog.titlechoice import PlayerCancelledError
        try:
            resolver_path = self.player_current.resolver.path
        except PlayerCancelledError:
            kodi_log('lib.player - Cancelled by user', 1)
            self.player_current = False
            return

        kodi_log([
            f'lib.player - {self.player_current.name}: Resolving...\n',
            f'{self.player_current.file} {self.player_current.mode}\n',
            f'{resolver_path}'], 1)

        if not resolver_path:
            return self.more()

        from tmdbhelper.lib.player.action.reupdate import PlayerReUpdateListing
        PlayerReUpdateListing().run()

        if not self.player_current.resolver.success:
            return self.more()

        self.player_current = False
```

Rationale: `resolver.path` is a `cached_property` that runs the placeholder substitution (and thus the dialog). Cancel raises `PlayerCancelledError`; setting `self.player_current = False` ends the `while self.player_current` loop in `play()` — a clean abort with no search and no error dialog. `resolver.success` (line further down) reuses the cached path, so it never re-fires the dialog.

- [ ] **Step 2: Syntax check**

Run: `python3 -c "import ast; ast.parse(open('resources/tmdbhelper/lib/player/dialog/player.py').read()); print('syntax ok')"`
Expected: `syntax ok`

- [ ] **Step 3: Commit**

```bash
git add resources/tmdbhelper/lib/player/dialog/player.py
git commit -m "feat(player): abort playback cleanly when title-choice dialog is cancelled"
```

---

### Task 5: Enable translations + title choice in prehrajto.json, verify in Kodi

**Files:**
- Modify: `resources/players/prehrajto.json`

**Interfaces:**
- Consumes: the `{ask_cs_title_url}` / `{ask_cs_showname_url}` placeholders from Task 3; `"language": true` (read by `PlayerMeta.requires_translation`, `meta.py:67`).

- [ ] **Step 1: Update the player definition**

Replace the entire contents of `resources/players/prehrajto.json` with:

```json
{
    "name": "Prehraj.to",
    "plugin": "plugin.video.prehrajto",
    "is_resolvable": "true",
    "language": true,
    "assert": {
        "play_episode": ["showname", "season", "episode"],
        "search_movie": ["title"],
        "search_episode": ["showname", "season", "episode"]
    },
    "search_movie": [
        "plugin://plugin.video.prehrajto/?action=results&query={ask_cs_title_url}&year={year}",
        {"dialog": "auto"}
    ],
    "search_episode": [
        "plugin://plugin.video.prehrajto/?action=results&query={ask_cs_showname_url}&season={season}&episode={episode}",
        {"dialog": "auto"}
    ]
}
```

- [ ] **Step 2: Validate JSON**

Run: `python3 -c "import json; json.load(open('resources/players/prehrajto.json')); print('json ok')"`
Expected: `json ok`

- [ ] **Step 3: Commit**

```bash
git add resources/players/prehrajto.json
git commit -m "feat(players): Prehraj.to searches chosen Czech/English title"
```

- [ ] **Step 4: Manual verification in Kodi (movie)**

1. Copy/sync the addon into a Kodi install; enable the Prehraj.to add-on.
2. From TMDb Helper, open a movie with a known Czech title (e.g. *The Dark Knight* → *Temný rytíř*) and play via Prehraj.to.
3. Expected: a `Dialog().select` titled "Choose title for search" listing **Temný rytíř** (first) and **The Dark Knight**.
4. Pick Czech → results reflect the Czech query. Re-play and pick English → results reflect the English query.
5. Re-play and Cancel the dialog → playback aborts with no search and no error popup.
6. Play a movie with **no** Czech translation → no dialog appears, search uses the default title.

- [ ] **Step 5: Manual verification in Kodi (episode)**

1. Play an episode of a show with a known Czech name via Prehraj.to.
2. Expected: the same dialog, offering the Czech show title (from `cs_tvshowtitle`) and the default show title; the pick drives the `showname` query.

---

## Notes / known limitations

- If Prehraj.to playback builds a playlist / next-episode item that re-resolves in a separate `PlayerDetails`/dictionary instance, the dialog could appear again for that item (each dictionary caches independently). Acceptable for this feature; revisit only if it proves annoying in practice.
- The dialog header shows in English for locales without a translation of `#32537` (Kodi falls back to en_gb). Adding the string to other `.po` files is optional follow-up.
