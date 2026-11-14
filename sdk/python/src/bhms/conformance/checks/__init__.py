"""The checks, grouped by chapter. Importing this package registers all of them (see :mod:`bhms.conformance.core`)."""

from bhms.conformance.checks import (  # noqa: F401
    agent, arguments, authority, compact, descriptions, events, gateway, leases, lifecycle, observations, operations, programs, stop, transport)
