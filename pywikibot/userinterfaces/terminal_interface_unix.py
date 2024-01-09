"""User interface for Unix terminals."""

#
# (C) Pywikibot team, 2003-2022
#
# Distributed under the terms of the MIT license.
#
from __future__ import annotations

import re

from pywikibot.userinterfaces import terminal_interface_base


unixColors = {
    'default': f'{chr(27)}[0m',
    'black': f'{chr(27)}[30m',
    'red': f'{chr(27)}[31m',
    'green': f'{chr(27)}[32m',
    'yellow': f'{chr(27)}[33m',
    'blue': f'{chr(27)}[34m',
    'purple': f'{chr(27)}[35m',
    'aqua': f'{chr(27)}[36m',
    'lightgray': f'{chr(27)}[37m',
    'gray': f'{chr(27)}[90m',
    'lightred': f'{chr(27)}[91m',
    'lightgreen': f'{chr(27)}[92m',
    'lightyellow': f'{chr(27)}[93m',
    'lightblue': f'{chr(27)}[94m',
    'lightpurple': f'{chr(27)}[95m',
    'lightaqua': f'{chr(27)}[96m',
    'white': f'{chr(27)}[97m',
}


class UnixUI(terminal_interface_base.UI):

    """User interface for Unix terminals."""

    def support_color(self, target_stream) -> bool:
        """Return that the target stream supports colors."""
        return True

    @staticmethod
    def make_unix_bg_color(color):
        """Obtain background color from foreground color."""
        code = re.search(r'(?<=\[)\d+', color).group()
        return f'{chr(27)}[{str(int(code) + 10)}m'

    def encounter_color(self, color, target_stream) -> None:
        """Write the Unix color directly to the stream."""
        fg, bg = self.divide_color(color)
        fg = unixColors[fg]
        self._write(fg, target_stream)
        if bg is not None:
            bg = unixColors[bg]
            self._write(self.make_unix_bg_color(bg), target_stream)
