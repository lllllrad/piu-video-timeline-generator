"""TypeScript recovery from exclusive lane-onset and processing evidence."""
from piu_timeline.derived import call,recovery_input


def recover_rows(data):return tuple(call('rowRecovery.recoverRows',recovery_input(data)))
