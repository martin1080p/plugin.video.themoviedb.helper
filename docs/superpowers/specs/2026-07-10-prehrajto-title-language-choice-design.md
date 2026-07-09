# Prehraj.to — Czech/English title search choice

**Date:** 2026-07-10
**Status:** Design (awaiting approval)

## Problem

The Prehraj.to player (`resources/players/prehrajto.json`) searches the service
using the addon's title for the item, which by default is the English/original
title (`{title}` for movies, `{showname}` for episodes). Prehraj.to is a Czech
service whose content is predominantly indexed under **Czech** titles, so an
English-title search often misses results that exist under the Czech name.

Users want, at play time, to **choose** which title to search with — and to
**see the actual titles** in the chooser, e.g.:

```
Search: Temný rytíř
Search: The Dark Knight
```

## Goal

When playing a movie or TV episode via the Prehraj.to player, if a Czech title
translation exists and differs from the default title, present a small dialog
listing the Czech and the English/original title. The user's pick becomes the
search query. No global setting change; the rest of the UI stays in English.

## Non-goals

- No change to the global addon `language` setting or general metadata display.
- No merging/running of both searches (user chose "ask each time", not "merge").
- No new addon settings toggle.

## Approach (chosen: "A" — placeholder-based chooser)

Inject the choice at the placeholder-resolution layer
(`resources/tmdbhelper/lib/player/dialog/dictionary.py`), where player search
URLs are filled in via `string_format_map`. This is the smallest, most
contained change and requires no edits to the resolver / pathfinder / evaluator
flow.

### New placeholder: `{ask_<lang>_<route>}`

A new placeholder family that, when resolved, offers a language choice for a
title-like route. Generic in the language so it is reusable by any regional
player; Prehraj.to uses `cs`.

Examples:
- `{ask_cs_title}` (movies) → chooser between default title and Czech title.
- `{ask_cs_showname}` (episodes) → chooser between default show title and Czech show title.
- Encoding affixes still apply: `{ask_cs_title_url}` resolves the chooser, then URL-encodes the pick.

### Resolution behaviour (in `PlayerDictionaryDict.__missing__`)

Add an `ask_` branch, evaluated before the existing translation-route and
encoding-affix branches so it takes precedence for keys beginning with `ask_`:

1. Parse `ask_<lang>_<route>` → `lang` (e.g. `cs`), `route` (e.g. `title`, `showname`).
2. Compute two candidates:
   - **default** = the route resolved with no language (English/original title).
   - **alternate** = the route resolved with `language=lang` (Czech title).
3. Decide:
   - If `alternate` is empty/None, or `alternate == default` → return `default`
     with **no dialog** (nothing to choose).
   - Otherwise show `xbmcgui.Dialog().select(header, [alternate, default])`
     with labels being the plain titles (Czech listed first, since this player
     targets a Czech service).
4. **Cancel** (select returns `-1`) → return a sentinel that makes path
   resolution fail cleanly, aborting this playback attempt (see "Cancel").
5. Cache the resolved value in the dict (the existing
   `self[key] = ...` pattern) so the `_url` affix variant and any repeated
   lookups reuse the same choice without re-prompting.

### Cancel handling

`Dialog().select` returns `-1` on cancel. The placeholder resolver returns a
value that causes the containing action's path to be treated as unresolvable so
`PlayerResolver` fails gracefully (equivalent to the user backing out of the
player-select dialog). Exact mechanism to confirm during implementation — likely
returning `None`/empty and letting the existing `if not self.path: return False`
in `resolver.py` short-circuit. Must **not** silently fall back to a search we
did not intend.

### Player JSON change (`resources/players/prehrajto.json`)

- Add `"language": true` so TMDb translations (including Czech) are fetched.
  Without this, `{cs_title}` resolves empty. (`PlayerMeta.requires_translation`,
  `meta.py:67`.)
- Change the movie query to use `{ask_cs_title_url}` and the episode query to
  use `{ask_cs_showname_url}`:

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

### Dialog label / header

- Header: a localized string, e.g. "Search language" (new string id in
  `resources/language/.../strings.po`, mirroring how existing player dialogs use
  `get_localized`).
- Rows: the **plain titles only** (no language suffix), e.g. `Temný rytíř` /
  `The Dark Knight`. Czech listed first.

## TV-episode title key (verified)

For movies, the Czech title lands in the `cs_title` infoproperty
(`basemedia.py:get_infoproperties_translation`), and
`PlayerDictionaryDictMovie.get_title(language='cs')` reads exactly that key.

For **episodes**, `episode.py:65` calls
`get_infoproperties_translation(infoproperties, 'tvshow')`. With
`subtype='tvshow'`, the generated key is `<iso>_<subtype><k>` =
`cs_` + `tvshow` + `title` = **`cs_tvshowtitle`** — precisely the key that
`PlayerDictionaryDictEpisode.get_tvshowtitle(language='cs')` reads
(`dictionary.py:194`). So the episode path works through the same
`{ask_cs_showname}` mechanism with no special-casing. `{ask_cs_title}` (episode
title) similarly maps to `cs_title`.

No episode-specific code change is required beyond the shared `ask_` branch.

## Testing

- **Unit-ish (dictionary):** Construct a `PlayerDictionaryDictMovie` with a fake
  `details` exposing both `title` (English) and `cs_title` (Czech), stub the
  Kodi `Dialog().select`, and assert:
  - two distinct titles → dialog shown with both, pick index maps to correct query.
  - missing/empty Czech title → no dialog, default used.
  - identical titles → no dialog, default used.
  - cancel (`-1`) → resolution fails (no query produced).
  - `{ask_cs_title_url}` returns the URL-encoded chosen title.
- **Manual in Kodi:** Play a movie with a known Czech title (e.g. The Dark
  Knight → "Temný rytíř") via Prehraj.to; confirm the dialog shows both titles
  and the chosen one drives the search. Repeat for an episode once the episode
  key is verified.

## Files touched

- `resources/tmdbhelper/lib/player/dialog/dictionary.py` — new `ask_` branch and
  chooser logic (plus episode `get_tvshowtitle` fallback if needed).
- `resources/players/prehrajto.json` — `"language": true` + new placeholders.
- `resources/language/resource.language.*/strings.po` — new localized header string.
