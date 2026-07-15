import importlib.util
import os
import sys
import types
from functools import cached_property

_HERE = os.path.dirname(__file__)
_ROOT = os.path.abspath(os.path.join(_HERE, '..'))
_DIALOG_DIR = os.path.join(
    _ROOT, 'resources', 'tmdbhelper', 'lib', 'player', 'dialog'
)


def _load_dictionary_module():
    """Load dictionary.py in isolation, stubbing its Kodi-only dependencies."""

    # Stub jurialmunkey.parser / jurialmunkey.ftools
    jm = types.ModuleType('jurialmunkey')
    jm_parser = types.ModuleType('jurialmunkey.parser')
    jm_parser.try_int = lambda v, base=10, fallback=0: int(v) if str(v).isdigit() else fallback
    jm_ftools = types.ModuleType('jurialmunkey.ftools')
    jm_ftools.cached_property = cached_property
    sys.modules['jurialmunkey'] = jm
    sys.modules['jurialmunkey.parser'] = jm_parser
    sys.modules['jurialmunkey.ftools'] = jm_ftools

    # Load the real titlechoice.py and expose it at the import path dictionary.py uses
    tc_path = os.path.join(_DIALOG_DIR, 'titlechoice.py')
    tc_spec = importlib.util.spec_from_file_location(
        'tmdbhelper.lib.player.dialog.titlechoice', tc_path)
    tc_mod = importlib.util.module_from_spec(tc_spec)
    tc_spec.loader.exec_module(tc_mod)
    sys.modules['tmdbhelper.lib.player.dialog.titlechoice'] = tc_mod

    dict_path = os.path.join(_DIALOG_DIR, 'dictionary.py')
    spec = importlib.util.spec_from_file_location('_dictionary_under_test', dict_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_dictionary = _load_dictionary_module()
PlayerDictionaryDictMovie = _dictionary.PlayerDictionaryDictMovie
PlayerDictionaryDictEpisode = _dictionary.PlayerDictionaryDictEpisode


class _FakeDetails:
    def __init__(self, infolabels=None, infoproperties=None):
        self.infolabels = infolabels or {}
        self.infoproperties = infoproperties or {}
        self.art = {}
        self.unique_ids = {}
        self.cast = []


def _make_movie(infolabels, infoproperties, select_func):
    d = PlayerDictionaryDictMovie('123', _FakeDetails(infolabels, infoproperties))
    d.title_select = select_func  # override the Kodi Dialog().select() call
    return d


def test_czech_ui_still_offers_original_vs_czech():
    """Regression: with the Kodi UI set to Czech the base `title` infolabel
    becomes the Czech title, so it must not be used as the non-alternate
    candidate. The choice is always original title vs. Czech translation."""
    seen = {}

    def select_func(candidates):
        seen['candidates'] = candidates
        return 0  # pick the Czech (alternate) row

    movie = _make_movie(
        infolabels={'title': 'Temný rytíř', 'originaltitle': 'The Dark Knight'},
        infoproperties={'cs_title': 'Temný rytíř'},
        select_func=select_func,
    )

    result = movie['ask_cs_title']

    assert seen.get('candidates') == ['Temný rytíř', 'The Dark Knight']
    assert result == 'Temný rytíř'


def test_english_ui_unchanged_behaviour():
    """With the UI in English the base title equals the original title, so
    the dialog still offers Czech vs. the original."""
    seen = {}

    def select_func(candidates):
        seen['candidates'] = candidates
        return 1  # pick the original row

    movie = _make_movie(
        infolabels={'title': 'The Dark Knight', 'originaltitle': 'The Dark Knight'},
        infoproperties={'cs_title': 'Temný rytíř'},
        select_func=select_func,
    )

    result = movie['ask_cs_title']

    assert seen.get('candidates') == ['Temný rytíř', 'The Dark Knight']
    assert result == 'The Dark Knight'


def test_episode_showname_czech_ui_offers_original_vs_czech():
    """The same regression for episodes, whose showname uses the tv show's
    original title (infoproperties['tvshow.originaltitle'])."""
    seen = {}

    def select_func(candidates):
        seen['candidates'] = candidates
        return 0

    episode = PlayerDictionaryDictEpisode('123', _FakeDetails(
        infolabels={'tvshowtitle': 'Hra o trůny'},
        infoproperties={
            'tvshow.originaltitle': 'Game of Thrones',
            'cs_tvshowtitle': 'Hra o trůny',
        },
    ), season=1, episode=1)
    episode.title_select = select_func

    result = episode['ask_cs_showname']

    assert seen.get('candidates') == ['Hra o trůny', 'Game of Thrones']
    assert result == 'Hra o trůny'


def test_no_czech_translation_uses_original_without_dialog():
    """When there is no Czech translation the original title is used and no
    dialog is shown."""

    def select_func(candidates):
        raise AssertionError('dialog must not be shown when no translation exists')

    movie = _make_movie(
        infolabels={'title': 'The Dark Knight', 'originaltitle': 'The Dark Knight'},
        infoproperties={},
        select_func=select_func,
    )

    assert movie['ask_cs_title'] == 'The Dark Knight'


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
