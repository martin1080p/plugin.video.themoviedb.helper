import os
import sys
import types
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


def test_translation_keys_covers_tvshow_and_season_subtypes():
    """ Finding 4: get_infoproperties_translation() writes <lang>_<subtype><field> keys with
    subtype in (None, 'tvshow', 'season') for episodes (see basemedia.py / episode.py), so the
    section must discover tvshowplot/seasontitle/etc, not just the bare and tvshowtitle forms. """
    itemdict = _stub_now(PlayerDictionaryDictEpisode('1396', _FakeDetails(
        infolabels={'tvshowtitle': 'Breaking Bad'},
        infoproperties={
            'cs_tvshowtitle': 'Perníkový táta',
            'cs_seasontitle': 'Season one CS',
            'cs_tvshowplot': 'tvshow plot cs',
            'cs_tagline': 'tagline cs',
            'set.title': 'ignored',
            'tvshow.originaltitle': 'ignored',
            'originaltitle': 'ignored',
        },
    ), season=1, episode=1))
    report = PlayerDebugReport(itemdict)
    keys = [k for k, _ in report.translation_keys]
    assert sorted(keys) == sorted(
        ['cs_tvshowtitle', 'cs_seasontitle', 'cs_tvshowplot', 'cs_tagline'])
    assert 'set.title' not in keys
    assert 'tvshow.originaltitle' not in keys
    assert 'originaltitle' not in keys

    lines = list(report.section_translations)
    by_key = {
        key: line
        for line in lines[1:]
        for key in keys
        if line.startswith(f'{{{key}}}')
    }
    # tvshowtitle is a real route on episodes, so it resolves and needs no annotation
    assert 'no matching route' not in by_key['cs_tvshowtitle']
    # these have no matching route and must be flagged, same as the existing cs_tagline case
    assert 'no matching route' in by_key['cs_seasontitle']
    assert 'no matching route' in by_key['cs_tvshowplot']
    assert 'no matching route' in by_key['cs_tagline']


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


def test_format_result_survives_a_cancelled_ask_choice():
    """ Finding 1: {ask_<lang>_<route>} raises PlayerCancelledError (via
    resolve_title_choice) when the user cancels the choice dialog. This is a
    documented happy path (the spec calls {ask_cs_title} "the point"), so
    format_result must not let it escape and abort the whole play flow -
    it must read as a cancellation, not a format error. """
    itemdict = _make_movie()
    itemdict.title_select = lambda candidates: -1  # simulate the user cancelling
    result = format_result(itemdict, '{ask_cs_title}')
    assert result == 'Cancelled: the ask dialog was dismissed without a choice'


def test_format_result_survives_an_arbitrary_raising_resolution():
    """ Finding 1 (fail-safe): any exception raised while resolving a route -
    not just the known ones - must be turned into text, never escape. """
    class _ExplodingDict(dict):
        def string_format_map(self, fmt):
            raise RuntimeError('boom')

    result = format_result(_ExplodingDict(), '{whatever}')
    assert result == 'RuntimeError: boom'


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


# --- Finding 2 / Finding 3: the translation rebuild (get_translated_dictionary) --------------
#
# The production call crosses module boundaries: PlayerDebugVariables.get_translated_dictionary
# imports tmdbhelper.lib.player.dialog.details.PlayerDetails and
# tmdbhelper.lib.player.dialog.dictionary.PlayerDictionary at call time. Registering stub
# modules under those exact dotted names in sys.modules (as test_debug_selection.py already does
# for other submodules) lets the real `from ... import ...` statements inside debug.py resolve
# against our stubs without needing the real Kodi-only modules.

def _register_translation_stubs(details_factory, dictionary_result=None):
    """Install stub details/dictionary modules and return the list of
    (tmdb_type, tmdb_id, season, episode, details) calls made to the stub PlayerDictionary."""
    details_mod = types.ModuleType('tmdbhelper.lib.player.dialog.details')
    details_mod.PlayerDetails = details_factory
    sys.modules['tmdbhelper.lib.player.dialog.details'] = details_mod

    dictionary_calls = []

    def _stub_player_dictionary(tmdb_type, tmdb_id, season, episode, details):
        dictionary_calls.append((tmdb_type, tmdb_id, season, episode, details))
        return dictionary_result

    dictionary_mod = types.ModuleType('tmdbhelper.lib.player.dialog.dictionary')
    dictionary_mod.PlayerDictionary = _stub_player_dictionary
    sys.modules['tmdbhelper.lib.player.dialog.dictionary'] = dictionary_mod

    return dictionary_calls


def test_get_translated_dictionary_calls_player_details_with_expected_args():
    calls = []

    class _RecordingPlayerDetails:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

        @property
        def details(self):
            return 'some-details'

    dictionary_calls = _register_translation_stubs(
        _RecordingPlayerDetails, dictionary_result='sentinel-dict')

    itemdict = _stub_now(PlayerDictionaryDictEpisode('1396', _FakeDetails(
        infolabels={'tvshowtitle': 'Breaking Bad'}, infoproperties={},
    ), season=1, episode=2))
    view = _debug.PlayerDebugVariables(itemdict)

    result = view.get_translated_dictionary()

    assert calls == [(('tv', '1396', 1, 2), {'translation': True})]
    assert dictionary_calls == [('tv', '1396', 1, 2, 'some-details')]
    assert result == 'sentinel-dict'


def test_dictionary_returns_what_stub_player_dictionary_returns():
    class _Details:
        def __init__(self, *args, **kwargs):
            pass

        @property
        def details(self):
            return 'ok'

    _register_translation_stubs(_Details, dictionary_result='THE-REBUILT-DICT')
    itemdict = _make_movie()
    view = _debug.PlayerDebugVariables(itemdict)
    assert view.dictionary == 'THE-REBUILT-DICT'
    assert view.header == view.header_text  # rebuild succeeded, no fallback note


def test_dictionary_falls_back_when_details_raises_attribute_error():
    """PlayerDetails.details raises AttributeError when get_details() returns None
    (no item found) - the rebuild must degrade to the passed-in dictionary, not raise."""
    class _Details:
        def __init__(self, *args, **kwargs):
            pass

        @property
        def details(self):
            raise AttributeError('no details')

    _register_translation_stubs(_Details, dictionary_result='THE-REBUILT-DICT')
    itemdict = _make_movie()
    view = _debug.PlayerDebugVariables(itemdict)
    assert view.dictionary is itemdict
    assert view.header == f'{view.header_text} {view.header_fallback_note}'


def test_dictionary_falls_back_when_details_falsy():
    class _Details:
        def __init__(self, *args, **kwargs):
            pass

        @property
        def details(self):
            return None

    _register_translation_stubs(_Details, dictionary_result='THE-REBUILT-DICT')
    itemdict = _make_movie()
    view = _debug.PlayerDebugVariables(itemdict)
    assert view.dictionary is itemdict
    assert view.header == f'{view.header_text} {view.header_fallback_note}'


def test_header_unchanged_when_translation_rebuild_stubbed_out():
    """_make_view forces get_translated_dictionary() to None (the existing fallback test
    path) - the header must carry the fallback note in that case too."""
    itemdict = _make_movie()
    view = _make_view(itemdict)
    assert view.header == f'{view.header_text} {view.header_fallback_note}'


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
