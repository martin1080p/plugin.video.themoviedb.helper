# Player variables debug view

**Date:** 2026-07-30
**Status:** Design (approved)

## Problem

Player JSON files in `resources/players/` fill their action strings through
`str.format_map` against a `PlayerDictionary`
(`resources/tmdbhelper/lib/player/dialog/dictionary.py`). The set of usable
`{variables}` is only discoverable by reading that module's `get_routes()`
methods, and the resolved value for a given item is only visible indirectly, by
reading the substituted path out of `kodi.log`.

This makes authoring and fixing player files slow, and it hides two traps:

- An unsupported key is not an error. `__missing__` returns the literal `_`, so
  a typo silently produces a broken URL. Several bundled players already do
  this (`{rating}`, `{votes}`, `{mpaa}`, `{genres}`, `{duration}`, `{tagline}`,
  `{status}`, `{urltitle}`, `{date}`, `{network_clean}`).
- Which `{<lang>_title}` variants exist is data-driven, not fixed — the
  translation infoproperties are written per available TMDb translation in
  `itemmeta_factories/concrete_classes/basemedia.py:355` — so it varies per item.

An earlier attempt used a scratch player file whose action was
`executebuiltin://Notification(...)`. That path is supported
(`player/action/resolver.py:145-156`) but proved unusable: notification text is
truncated on screen, and it dumps only whatever variables were hardcoded into
the file.

## Goal

An in-addon debug view, reachable while choosing a player, that shows every
supported variable and its resolved value for the item being played, and lets
the developer test arbitrary format strings against that same item.

## Non-goals

- No change to how variables resolve. This is read-only instrumentation over the
  existing `PlayerDictionary`.
- No new addon setting (reuses `debug_logging`).
- No route reachable from outside the player select dialog (no `RunScript`
  entry point, no context menu, no settings button).
- Not a fix for the unsupported placeholders in bundled players; the view only
  makes them visible as `_`.

## Approach (chosen: "A" — intercept in the dialog layer)

`PlayerItems` is constructed with `item=self.dictionary`
(`player/dialog/player.py:144`), so the select-dialog layer already holds the
`PlayerDictionary`. The debug entry is therefore handled entirely inside the
dialog layer and never reaches `Player.set_resolver()`, leaving `player.py`, the
resolver, the pathfinder and the dummy-file machinery untouched.

Rejected alternatives:

- **Intercept in `Player.get_player()`** — same size, but splits the feature
  across two layers and grows `player.py`, already the largest file in the
  module.
- **Give the debug item real `actions` and let it flow through the resolver** —
  abuses the resolver contract and drags the dummy-`mp4` resolve/play/stop
  sequence in front of the view.

## Components

### New: `resources/tmdbhelper/lib/player/dialog/debug.py`

`PlayerItemDebugVariables(PlayerItemBasic)` — the dialog row.

- `is_valid = True` (bypasses the `actions`/assert checks in
  `PlayerItemBasic.is_valid`)
- `is_debug = True` — the marker the dialog layer keys off
- `name = get_localized(32538)`
- `plugin_name = 'plugin.video.themoviedb.helper'` — picks up the TMDbHelper
  icon and groups by name in combined mode, matching `PlayerItemClearDefault`

`PlayerDebugVariables(itemdict)` — the view. Owns the translation rebuild, the
row builder and the tester loop.

### Modified: `resources/tmdbhelper/lib/player/dialog/standard.py`

`additional_players` changes from a class attribute to a `cached_property`:

```python
@cached_property
def additional_players(self):
    if not get_setting('debug_logging'):
        return []
    if not self.data.item:   # None in the choose-default-player flow
        return []
    return [PlayerItemDebugVariables()]
```

`self.data.item is None` distinguishes the play flow from the
choose-default-player flow, where `PlayerItems` is built with `item=None`
(`player/config/default.py:21`). `PlayerDefaultMovie.players_select_combined`
assigns `instance.additional_players = [PlayerItemClearDefault()]`; instance
assignment takes precedence over `cached_property`, so that flow keeps its
current single entry.

New shared helper on the same class:

```python
def resolve_selection(self, player):
    """ Return player, or None if the pick was a debug action that's been handled """
    if not getattr(player, 'is_debug', False):
        return player
    PlayerDebugVariables(self.data.item).run()
    self.player_uid = None   # so combined mode re-prompts with all groups
    return None
```

`select()` gains a `while` loop around its existing body so a debug pick
re-prompts instead of returning.

### Modified: `resources/tmdbhelper/lib/player/dialog/combined.py`

`PlayerSelectCombined.select()` already loops `while not player:`. It calls
`player = self.resolve_selection(player)` after `select_from_group()`; the
existing loop then supplies the re-prompt.

### Modified: `resources/language/resource.language.en_gb/strings.po`

Add `#32538` — "Debug variables". Next free id; `#32537` is the fork's "Choose
title for search". en_gb only; other languages fall back. Section headers inside
the dump are hardcoded English — it is a developer dump, not UI.

## The view

`PlayerDebugVariables.dictionary` rebuilds from the ids the passed-in dictionary
already carries, forcing translations on:

```python
PlayerDetails(itemdict.tmdb_type, itemdict.tmdb_id,
              getattr(itemdict, 'season', None), getattr(itemdict, 'episode', None),
              translation=True)
```

then builds a fresh `PlayerDictionary` over those details. This makes
`{cs_title}` resolve even when no enabled player sets `"language": true`, and
the cost is paid only when the view is opened. `PlayerDictionaryDictMovie`
carries `tmdb_type = 'movie'` and no season/episode;
`PlayerDictionaryDictEpisode` carries `tmdb_type = 'tv'` plus both — hence
`getattr`.

`Dialog().textviewer()` with four sections:

1. **Item** — `tmdb_type`, `tmdb_id`, `season`, `episode`
2. **Variables** — every `dictionary.routes` key → resolved value, aligned, in
   route order. Enumerating `routes` is what keeps this self-maintaining: a new
   route appears here with no edit to the debug module.
3. **Translations available** — `<lang>_title`, `<lang>-<CC>_title`,
   `<lang>_tvshowtitle`, `<lang>_plot` keys discovered in
   `details.infoproperties`, with values
4. **Encoding suffixes** — the 13 `PlayerDictionaryDict.encoding_methods` keys
   demonstrated against `title` (`showname` for episodes)

Then the tester loop: `Dialog().input()` → `dictionary.string_format_map(text)`
→ `Dialog().textviewer()` → repeat until empty input or cancel.

Two intentional behaviours:

- Typing `{ask_cs_title}` really does raise the ask-dialog. That is the point —
  it exercises the actual resolution path.
- `PlayerDictionary` is a `dict` that caches resolved keys, so an ask choice
  sticks for the remainder of that view session.

## Data flow

```
Play with TMDbHelper
  └─ Player.player_current → get_player()
       └─ player_select.select()
            ├─ additional_players → [PlayerItemDebugVariables]   (debug_logging and data.item)
            ├─ user picks it
            ├─ resolve_selection() → PlayerDebugVariables(data.item).run()
            │    ├─ rebuild PlayerDetails(translation=True) → PlayerDictionary
            │    ├─ textviewer: item / variables / translations / encodings
            │    └─ tester loop: input → string_format_map → textviewer
            └─ returns None → dialog re-prompts → real player, or cancel
```

## Error handling

- Malformed test strings raise out of `format_map`. Verified against CPython:

  | input | raises |
  |---|---|
  | `{` | `ValueError: Single '{' encountered in format string` |
  | `{}` | `ValueError: Format string contains positional fields` |
  | `{title:bogus}` | `ValueError: Invalid format specifier` |
  | `{year:s}` | `ValueError: Unknown format code 's' for object of type 'int'` |
  | `{season:02d}` (str season) | `ValueError: Unknown format code 'd' for object of type 'str'` |
  | `{poster:>10}` (None value) | `TypeError: unsupported format string passed to NoneType.__format__` |

  Catch `(KeyError, IndexError, ValueError, TypeError, AttributeError)` and
  render the exception text as the result; the loop continues rather than
  dropping the user back to the player dialog. `TypeError` matters in practice —
  routes legitimately return `None` (e.g. `tvdb` for a movie without one), and
  any format spec applied to `None` raises it.
- Well-formed unknown keys need no handling: `__missing__` already yields `_`,
  and seeing `_` is the diagnostic.
- Rebuild failure (no details returned) → fall back to the dictionary passed in
  and note the fallback in the header, so the view never dead-ends.

## Testing

`tests/test_debug_variables.py`, reusing the Kodi-stub loader pattern from
`tests/test_dictionary_ask.py`, which already executes `dictionary.py` outside
Kodi:

- one row per route, against a fake details object
- translation keys discovered from `infoproperties`, ignoring non-translation
  keys
- encoding section renders all 13 suffixes
- tester returns formatted output for valid input, and an error string rather
  than raising for `{`, `{}` and `{title:bogus}`
- `resolve_selection` returns `None` for a debug item and passes real players
  through unchanged, against a fake `data`

Manual verification in the Flatpak Kodi profile
(`/home/martin/.var/app/tv.kodi.Kodi/data`, the active install) with
`debug_logging` enabled, for both a movie and an episode.

## Success criteria

- With `debug_logging` on, "Debug variables" appears in the player select dialog
  for movies and episodes, and does not appear with it off, nor in
  Settings → Players → default player selection.
- The view lists every route in `PlayerDictionary` with its resolved value for
  the item, including translation variants.
- A format string typed into the tester resolves exactly as it would inside a
  player JSON, and a malformed one reports an error without aborting.
- Selecting the entry never starts playback and always returns to the player
  list.
