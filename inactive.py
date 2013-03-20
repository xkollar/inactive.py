#!/usr/bin/env python
#   ActiveRun - Simple tool for monitoring user's (in)activity.
#   Copyright (C) 2013  Matej Kollar
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, version 3 of the License.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""PROG: Simple tool for monitoring user's (in)activity.

Run command or wait while X-user is active. Tries to waste as
little system resources as possible (using python).
Uses DISPLAY environment variable. Time data obtained by libXss.

Usage:

PROG (-h|--help)    -- Print this help.
PROG (-V|--version) -- Print version.
PROG (-S|--show)    -- Print seconds of user inactivity.

PROG [-n|--noblock] TIME
    Like sleep, but wait for TIME (in seconds) of inactivity.

    -n|--noblokc   Do not wait, just check whether user
        was inactive for at least TIME. See exit code.

PROG [-s N|--signal=N] TIME CMD [ARGS]
    Run command. It will either end itself, or after TIME
    seconds of idle time it will receive signal N (default
    15). In case user was already inactive for specified
    amount of time, PROG terminate with 0.
"""

__author__     = "Matej Kollar"
__contact__    = "xkolla06@stud.fit.vutbr.cz"

__version__    = "1.0"
__date__       = "2013. 01. 20."
__license__    = "GPLv3"

__credits__    = [__author__, "Zuzana Zabojnikova"]
__maintainer__ = __author__
__status__     = "Working"

import ctypes
import errno
import getopt
import os
import signal
import sys
import time

class Xss(object):
    """X ScreenSaver extension (libxss needed).
    Thanks to http://thp.io/2007/09/x11-idle-time-and-focused-window-in.html
    by Thomas Perl."""

    class XScreenSaverInfo(ctypes.Structure):
        """ typedef struct { ... } XScreenSaverInfo; """
        _fields_ = \
            [ ('window',     ctypes.c_ulong)  # screen saver window
            , ('state',      ctypes.c_int)    # off, on, disabled
            , ('kind',       ctypes.c_int)    # blanked, internal, external
            , ('since',      ctypes.c_ulong)  # milliseconds
            , ('idle',       ctypes.c_ulong)  # milliseconds
            , ('event_mask', ctypes.c_ulong)  # events
            ]

    def __init__(self):
        self.xlib = ctypes.cdll.LoadLibrary('libX11.so')
        self.dpy  = self.xlib.XOpenDisplay(os.environ['DISPLAY'])
        self.root = self.xlib.XDefaultRootWindow(self.dpy)
        self.xss  = ctypes.cdll.LoadLibrary('libXss.so.1')
        self.xss.XScreenSaverAllocInfo.restype \
            = ctypes.POINTER(Xss.XScreenSaverInfo)
        self.xss_info = self.xss.XScreenSaverAllocInfo()

    def idle(self):
        """How long is user inactive. Milliseconds."""
        self.xss.XScreenSaverQueryInfo(self.dpy, self.root, self.xss_info)
        return self.xss_info.contents.idle

    def idle_s(self):
        """How long is user inactive. Seconds."""
        return self.idle() / 1000

def retry_on_eintr(function, *args, **kw):
    """Function by Dan Stromberg to retry interrupted syscall.
    See http://code.activestate.com/lists/python-list/595310/ for details."""
    while True:
        try:
            return function(*args, **kw)
        except OSError, e:
            if e.errno == errno.EINTR:
                continue
            else:
                raise

def parametrize(function, *args, **kw):
    """Give (some) parameters for function but let it execute later.
    Parameter can be postional as well as named. Positional parameters
    can be filled only from left to right though.
    I'm very proud for this one :-)."""
    def f(*args2, **kw2):
        kw.update(kw2)
        return function(*(args + args2), **kw)
    return f

def show_help(out=sys.stdout, ret=0):
    print >> out, __doc__.replace('PROG', __file__)
    return ret

def show_version(out=sys.stdout):
    print >> out, "%s %s\nby %s" % (__file__, __version__, __author__)
    return 0

def show_inactivity():
    xss = Xss()
    print xss.idle_s()
    return 0

def main_test(timeout):
    """Functionality for test."""
    xss = Xss()
    # Logic is inverted for shell
    return xss.idle_s() < timeout

def main_wait(timeout):
    """Functionality for waiting. Worth rewriting?"""
    xss = Xss()
    while True:
        d = timeout - xss.idle_s()
        if d <= 0:
            return 0
        time.sleep(d)
    return 1

def main_run(timeout, sig_num, what):
    """Functionality for runnging command (as subprocess)."""
    xss = Xss()

    pid = None

    def on_alrm(_sig, _frame):
        """Handle ALRM signal, schedule new alarm."""
        d = timeout - xss.idle_s()

        if d > 0:
            signal.alarm(d)
        else:
            os.kill(pid, sig_num)

    d = timeout - xss.idle_s()
    if d > 0:
        signal.signal(signal.SIGALRM, on_alrm)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.alarm(d)
        pid = os.spawnvp(os.P_NOWAIT, what[0], what)
        (_, ret) = retry_on_eintr(os.waitpid, pid, 0)
        return ret
    return 0

def parseargs(argv):
    if argv in (['-h'], ['--help']):
        return show_help
    elif argv in (['-V'], ['--version']):
        return show_version
    elif argv in (['-S'], ['--show']):
        return show_inactivity

    try:
        opts, args = getopt.getopt(argv, "s:n", ["signal=", "noblock"])

        if len(args) < 1:
            raise Exception("TIME is not optional.")

        timeout = int(args[0])
        args = args[1:]

        if len(opts) > 1:
            raise Exception("Too many options.")

        block = True
        sig_num = 15

        for o, a in opts:
            if o in ("-s", "--signal"):
                sig_num = int(a)
            elif o in ("-n", "--noblock"):
                block = False
            else:
                assert False, "unhandled option"

        if len(args) == 0 and block:
            return parametrize(main_wait, timeout)
        elif len(args) == 0:
            return parametrize(main_test, timeout)
        else:
            return parametrize(main_run, timeout, sig_num, args)

    except Exception as err:
        print >> sys.stderr, "Error: %s" % err
        print >> sys.stderr, \
            "Reading Usage one more time could be helpful ;-).\n"

    return parametrize(show_help, out=sys.stderr, ret=1)

if __name__ == "__main__":
    main = parseargs(sys.argv[1:])
    sys.exit(main())

