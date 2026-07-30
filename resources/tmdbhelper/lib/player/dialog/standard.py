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
