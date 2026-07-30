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
