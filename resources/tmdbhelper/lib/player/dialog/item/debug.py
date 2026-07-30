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
