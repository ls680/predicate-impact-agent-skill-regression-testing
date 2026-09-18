"""Outcome-blind task selection for predicate-scoped skill changes."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import math
import random
import re

from atoms import matches, trace_atoms


def stable_seed(seed, spec_id, method):
    return int.from_bytes(hashlib.sha256(f'{seed}:{spec_id}:{method}'.encode()).digest()[:8], 'big')


def task_table(environment, records):
    return [{
        'task_id': record['task_id'], 'environment': environment, 'family': record['family'],
        'task_description': record['task_description'],
        'healthy_steps': len(record['executed_actions']), 'actions': record['executed_actions'],
        'atoms': sorted(trace_atoms(environment, record['executed_actions'])),
    } for record in records if record['success'] and not record['error']]


def impact_priority(task, spec):
    indices = [i for i, action in enumerate(task['actions']) if matches(
        task['environment'], action, spec['predicate_kind'], spec['predicate_value'])]
    if task['family'] != spec['family']:
        return (2, 0.0, math.inf, task['family'], task['task_id'])
    if not indices:
        return (1, 0.0, math.inf, task['family'], task['task_id'])
    length = max(len(task['actions']), 1)
    downstream_fraction = (length - min(indices)) / length
    return (0, -downstream_fraction, task['healthy_steps'] / len(indices), task['task_id'])


def shuffled(values, seed):
    result = list(values)
    random.Random(seed).shuffle(result)
    return result


def family_stratified(tasks, seed):
    groups = defaultdict(list)
    for task in tasks:
        groups[task['family']].append(task)
    rng = random.Random(seed)
    families = sorted(groups)
    rng.shuffle(families)
    for family in families:
        rng.shuffle(groups[family])
    result = []
    while any(groups.values()):
        for family in families:
            if groups[family]:
                result.append(groups[family].pop())
    return result


def lexical_order(tasks, spec):
    tokenize = lambda text: re.findall(r'[a-z0-9]+', text.lower().replace('_', ' '))
    query = Counter(tokenize(spec['predicate_kind'] + ' ' + spec['predicate_value']))
    documents = [Counter(tokenize(task['task_description'])) for task in tasks]
    frequencies = Counter(token for document in documents for token in document)
    total = len(tasks)
    idf = {token: math.log((total + 1) / (count + 1)) + 1 for token, count in frequencies.items()}

    def score(document):
        vocabulary = set(document) | set(query)
        left = {t: document[t] * idf.get(t, math.log(total + 1)) for t in vocabulary}
        right = {t: query[t] * idf.get(t, math.log(total + 1)) for t in vocabulary}
        denominator = math.sqrt(sum(x * x for x in left.values())) * math.sqrt(
            sum(x * x for x in right.values()))
        return sum(left[t] * right[t] for t in vocabulary) / denominator if denominator else 0.0

    return [task for task, _ in sorted(zip(tasks, map(score, documents)), key=lambda pair: (
        -pair[1], pair[0]['healthy_steps'], pair[0]['task_id']))]


def select_order(method, tasks, spec, *, seed=0, killed=None):
    family = [task for task in tasks if task['family'] == spec['family']]
    other = [task for task in tasks if task['family'] != spec['family']]
    supported = set(spec['support_task_ids'])
    covered = [task for task in family if task['task_id'] in supported]
    uncovered = [task for task in family if task['task_id'] not in supported]
    random_seed = stable_seed(seed, spec['spec_id'], method)
    if method == 'predicate_impact':
        return sorted(tasks, key=lambda task: impact_priority(task, spec))
    if method == 'family_predicate_random':
        return (shuffled(covered, random_seed) + shuffled(uncovered, random_seed + 1) +
                shuffled(other, random_seed + 2))
    if method == 'skill_family_random':
        return shuffled(family, random_seed) + shuffled(other, random_seed + 1)
    if method == 'random':
        return shuffled(tasks, random_seed)
    if method == 'family_stratified':
        return family_stratified(tasks, random_seed)
    if method == 'lexical_similarity':
        return lexical_order(tasks, spec)
    if method == 'shortest_first':
        return sorted(tasks, key=lambda task: (task['healthy_steps'], task['task_id']))
    if method == 'oracle_upper_bound':
        if killed is None:
            raise ValueError('Oracle ordering requires outcomes')
        return sorted(tasks, key=lambda task: (
            not killed[task['task_id']], task['healthy_steps'], task['task_id']))
    raise ValueError(f'Unknown predicate selector: {method}')
