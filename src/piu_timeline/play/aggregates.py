"""TypeScript aggregate-counter recovery; native risk remains independently measured."""
from piu_timeline.derived import call,recovery_input


def bracket(match):
    return (match.get('observation_lower_seconds',match.get('combo_lower_seconds')),
            match.get('observation_upper_seconds',match.get('combo_upper_seconds')))


def recover_aggregates(data):return tuple(call('rowRecovery.recoverAggregates',recovery_input(data)))
