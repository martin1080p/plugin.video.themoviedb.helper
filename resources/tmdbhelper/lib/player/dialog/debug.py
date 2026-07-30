import re
from jurialmunkey.ftools import cached_property


# Translation infoproperties are written per available TMDb translation as
# <lang>_<subtype><field> and <lang>-<COUNTRY>_<subtype><field> — see
# get_infoproperties_translation() in
# items/database/itemmeta_factories/concrete_classes/basemedia.py, called with
# subtype in (None, 'tvshow', 'season') by concrete_classes/episode.py.
REGEX_TRANSLATION_KEY = re.compile(
    r'^([a-z]{2}(?:-[A-Z]{2})?)_((?:tvshow|season)?(?:title|plot|tagline))$'
)

ROW_WIDTH = 26


def format_result(itemdict, text):
    """ Resolve a format string against itemdict, returning error text rather than raising.

    Must never raise: this feeds the interactive format-string tester, and letting anything
    escape would propagate out through run_tester -> run -> resolve_selection -> select() ->
    Player.get_player() and abort the whole play flow. In particular {ask_<lang>_<route>}
    placeholders raise PlayerCancelledError when the user cancels the choice dialog - that is
    a documented happy path (see the design spec), not a format error, so it is caught
    explicitly and reported as a cancellation rather than an exception trace.
    """
    from tmdbhelper.lib.player.dialog.titlechoice import PlayerCancelledError
    try:
        return itemdict.string_format_map(text)
    except PlayerCancelledError:
        return 'Cancelled: the ask dialog was dismissed without a choice'
    except Exception as exc:  # noqa: BLE001 - fail-safe: this tester must never raise
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


class PlayerDebugVariables:

    """ Shows the debug report for an item then loops a format-string tester """

    header_text = 'TMDbHelper player variables'
    header_fallback_note = '(translations unavailable - rebuild failed)'
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
        no enabled player sets "language": true. Falls back to the dialog's own dictionary,
        recording the fallback so `header` can surface it to the developer. """
        translated = self.get_translated_dictionary()
        self.translation_rebuild_failed = translated is None
        return translated or self.itemdict

    @cached_property
    def header(self):
        """ The textviewer header. Forces the translation rebuild (via `dictionary`) so a
        failed rebuild is never silently indistinguishable from "no translations exist". """
        self.dictionary
        if getattr(self, 'translation_rebuild_failed', False):
            return f'{self.header_text} {self.header_fallback_note}'
        return self.header_text

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
