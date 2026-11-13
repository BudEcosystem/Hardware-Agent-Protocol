"""A gateway process for the crash-window test: ``python gateway_crash.py <config.toml>``.

With ``CRASH=after-forward`` the process SIGKILLs itself at the moment the upstream has accepted a forward and the gateway
is about to record the answer (the window between send and record). The rest is the stock gateway.
"""

from __future__ import annotations

import os
import signal
import sys

from bhms.gateway import Gateway, load_config
from bhms.gateway.journal import ForwardJournal

if os.environ.get("CRASH") == "after-forward":
    def die(self, **kw):
        os.kill(os.getpid(), signal.SIGKILL)

    ForwardJournal.admit_forwarded = die  # type: ignore[method-assign]

Gateway(load_config(sys.argv[1])).run()
