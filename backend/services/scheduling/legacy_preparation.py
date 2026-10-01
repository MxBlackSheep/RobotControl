"""Read the preparation tokens of the retired built-in lab adapters on older schedules.

Schedules saved before the EvoYeast flag became a database package keep tokens such as
['ResetHamiltonTables:Runtime', 'ScheduledToRun', 'EvoYeastExperiment:42|set'] in
`prerequisites`. Nothing runs them any more. They stay on the schedule, the run is refused
and the schedule shows "Needs review" until a local administrator saves its database step,
prefilled from the tokens where they map onto the evoyeast-experiment package. This is
derived on every read, so restarts and repeated upgrades never rewrite or drop them.
"""

EVOYEAST_TOOL_ID = 'evoyeast-experiment'
_NAMES = {'scheduledtorun': 'ScheduledToRun', 'evoyeastexperiment': 'EvoYeastExperiment',
          'resethamiltontables': 'ResetHamiltonTables'}
_NO_WRITE = ('none', 'noop', 'skip')
_SELECT = ('', 'set', 'activate', 'exclusive')


def legacy_review(prerequisites, has_step=False):
    """None when the tokens never wrote anything; otherwise {steps, suggestion, message}.

    suggestion is {tool_id, inputs} for the evoyeast-experiment package, or None when the
    tokens cannot be expressed by it (the administrator then chooses the step themselves).
    Steps run in their saved order, as the adapter did, so a reset saved before the
    selection keeps running first.
    """
    steps = []
    for token in prerequisites or []:
        name, _, payload = str(token).partition(':')
        name = _NAMES.get(''.join(c for c in name.lower() if c.isalnum()), name)
        if name == 'ScheduledToRun' and not payload:
            steps.append(('marker', None))  # Old form marker; the ID-bearing token did the write.
        elif name == 'EvoYeastExperiment':
            value, _, action = payload.partition('|')
            value, action = value.strip(), action.strip().lower()
            if action in _NO_WRITE:
                continue
            steps.append(('select', int(value)) if value.isdecimal() and action in _SELECT else ('invalid', token))
        elif name == 'ResetHamiltonTables':
            tables = [x.strip() for x in payload.split(',')] if payload else []
            steps.append(('invalid', token) if any(not x for x in tables) else ('reset', ', '.join(tables)))
        else:
            steps.append(('invalid', token))
    if not steps:
        return None
    kinds = [kind for kind, _ in steps]
    reasons = []
    if 'invalid' in kinds:
        reasons.append('unsupported step ' + ', '.join(str(value) for kind, value in steps if kind == 'invalid'))
    if kinds.count('select') > 1 or kinds.count('reset') > 1:
        reasons.append('more than one experiment selection or table reset')
    if 'marker' in kinds and 'select' not in kinds:
        reasons.append('ScheduledToRun without an experiment ID')
    if has_step:
        reasons.append('it already has a database step, and a schedule runs only one')
    if reasons:
        return dict(steps=list(prerequisites), suggestion=None, message=(
            'This schedule\'s old preparation (' + ', '.join(map(str, prerequisites)) + ') cannot be carried over: '
            + '; '.join(reasons) + '. A local administrator must choose its database step and save the schedule before it runs.'))
    inputs = {}
    for kind, value in steps:
        if kind == 'select':
            inputs['experiment_id'] = value
        elif kind == 'reset':
            inputs['reset_tables'] = True
            if value:
                inputs['table_list'] = value
    if 'experiment_id' in inputs and inputs.get('reset_tables') and kinds.index('reset') < kinds.index('select'):
        inputs['reset_first'] = True
    return dict(steps=list(prerequisites), suggestion=dict(tool_id=EVOYEAST_TOOL_ID, inputs=inputs), message=(
        'This schedule\'s EvoYeast selection moved to a database step. '
        'A local administrator must review and save the schedule before it runs.'))
