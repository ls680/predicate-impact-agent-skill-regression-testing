"""Shared execution controls. Not a claim of novel skill repair.

All constraints derive from current admissible commands and a visible objective.
No hidden state, gold plan, reward-based action choice, or test lookup is used.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'revisions/02_evidence_gated_repair'))
from repair import EXECUTOR_SYSTEM, executor_prompt, parse_action
from skilllineage.interactive import ModelResponse

CONTROLLERS = (
    'E0_json', 'E1_legal', 'E2_plan_legal', 'E3_legal_contract',
    'E4_plan_legal_contract', 'E5_plan_legal_contract_memory',
)
ACTION_SYSTEM = '''Choose the next action using the visible objective and observations.
Reusable skill memory is fallible. Do not substitute unrelated objects for a target.
Avoid repeating an action with unchanged feedback unless waiting is necessary.
Output exactly one of the CURRENT candidate commands, without JSON or explanation.'''
PLAN_SYSTEM = '''Plan just one next step for a text-environment agent.
Use only the visible objective, observations, history and CURRENT candidate commands.
Treat reusable skill memory as fallible. Do not substitute an unrelated target.
In at most 35 words, identify the next subgoal and an appropriate CURRENT command.
If a target is absent, plan to find it. Do not claim task completion.'''


def normalize(text):
    return re.sub(r'\s+', ' ', text).strip().casefold()


def required_focus(objective, history):
    """Conservative exact binding. Categorical or ambiguous tasks abstain.

The generic substance pronoun is resolved only for three explicit task verbs.
Thermometer order advances only after visible feedback of a successful focus.
"""
    task = normalize(objective)
    target = re.search(r'your task is to (?:boil|melt|freeze) ([^.]+)\.', task)
    if target and 'first, focus on the substance.' in task:
        return target.group(1).removeprefix('the ')
    ordered = re.search(
        r'first, focus on the ([^.]+)\. next, focus on the ([^.]+)\.', task)
    if ordered:
        first, second = ordered.groups()
        confirmed = any(
            normalize(action) == 'focus on ' + first
            and 'focus' in normalize(feedback)
            and not re.search(r"not|cannot|can't|unable|invalid", normalize(feedback))
            for action, feedback in history
        )
        return second if confirmed else first
    return None


def contract_actions(objective, actions, history):
    target = required_focus(objective, history)
    if target is None:
        return list(actions), {'active': False, 'reason': 'no_unambiguous_exact_binding'}
    exact = 'focus on ' + target
    if any(normalize(action).startswith(exact + ' ') for action in actions):
        return list(actions), {'active': False, 'reason': 'ambiguous_target_alias', 'target': target}
    allowed = [action for action in actions
               if not normalize(action).startswith('focus on ')
               or normalize(action) == 'focus on ' + target]
    if not allowed:
        return list(actions), {'active': False, 'reason': 'empty_filter_abstain', 'target': target}
    return allowed, {'active': True, 'target': target,
                     'removed': [action for action in actions if action not in allowed]}


def focus_mismatch(objective, action, history):
    target = required_focus(objective, history)
    if target is None or action is None or not normalize(action).startswith('focus on '):
        return None
    return normalize(action) != 'focus on ' + target


class TokenTrie:
    def __init__(self, sequences, eos_token_id):
        if not sequences or any(not sequence for sequence in sequences):
            raise ValueError('Nonempty candidate token sequences required')
        self.root = {}
        self.terminal = -1
        self.eos = eos_token_id
        self.max_tokens = max(len(sequence) for sequence in sequences) + 1
        for sequence in sequences:
            if eos_token_id in sequence:
                raise ValueError('Candidate must not contain the EOS token')
            node = self.root
            for token in sequence:
                node = node.setdefault(int(token), {})
            node[self.terminal] = {}

    def allowed(self, prefix):
        node = self.root
        for token in prefix:
            if token not in node or token == self.terminal:
                raise ValueError('Generated prefix is not in the legal-action trie')
            node = node[token]
        allowed = [token for token in node if token != self.terminal]
        if self.terminal in node:
            allowed.append(self.eos)
        if not allowed:
            raise ValueError('Empty token constraint')
        return allowed


def constrained_response(model, system, prompt, actions, *, seed, token_budget):
    if not actions or len(set(actions)) != len(actions):
        raise ValueError('Current commands must be nonempty and unique')
    tokenizer, torch = model.tokenizer, model.torch
    sequences = [tokenizer.encode(action, add_special_tokens=False) for action in actions]
    for action, sequence in zip(actions, sequences):
        if tokenizer.decode(sequence, skip_special_tokens=True).strip() != action:
            raise ValueError('Command does not round-trip through tokenizer')
    if tokenizer.eos_token_id is None:
        raise ValueError('EOS token required for exact constrained completion')
    trie = TokenTrie(sequences, tokenizer.eos_token_id)
    if trie.max_tokens > token_budget:
        raise ValueError('Action token budget cannot complete every current candidate')
    torch.manual_seed(seed)
    messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}]
    try:
        rendered = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except TypeError:
        rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(rendered, return_tensors='pt').to(model.model.device)
    offset = inputs.input_ids.shape[1]

    def allowed_tokens(batch_id, input_ids):
        return trie.allowed(input_ids[offset:].tolist())

    started = time.perf_counter()
    with torch.inference_mode():
        output = model.model.generate(
            **inputs, max_new_tokens=trie.max_tokens, do_sample=False,
            prefix_allowed_tokens_fn=allowed_tokens,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=(tokenizer.pad_token_id if tokenizer.pad_token_id is not None
                          else tokenizer.eos_token_id),
        )
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    generated = output[0, offset:]
    action = tokenizer.decode(generated, skip_special_tokens=True).strip()
    if action not in actions or int(generated[-1]) != tokenizer.eos_token_id:
        raise RuntimeError('Constraint failed or command completion was truncated')
    return ModelResponse(
        text=action, latency_sec=time.perf_counter() - started,
        prompt_sha256=hashlib.sha256(rendered.encode()).hexdigest(),
        input_tokens=int(offset), output_tokens=int(generated.shape[0]),
    )


def compact_memory(history, budget=2400):
    notes = {}
    for action, observation in history:
        notes.pop(action, None)
        notes[action] = re.sub(r'\s+', ' ', observation).strip()[:400]
    retained, size = [], 0
    for action, observation in reversed(list(notes.items())):
        line = f'{action} -> {observation}'
        if size + len(line) + 1 > budget:
            break
        retained.append(line)
        size += len(line) + 1
    return '\n'.join(reversed(retained)) or '(none)'


def select_action(model, controller, case, skill, *, seed, action_budget=128, plan_budget=96):
    if controller not in CONTROLLERS:
        raise ValueError('Unknown controller')
    objective, observation = case['objective'], case['observation']
    actions, history = case['actions'], case['history']
    calls = []
    contract = {'active': False, 'reason': 'control_without_filter'}
    if controller == 'E0_json':
        prompt = executor_prompt(objective, observation, skill, actions, history, 6, 40)
        response = model.respond(EXECUTOR_SYSTEM, prompt, max_new_tokens=action_budget, seed=seed)
        calls.append({'system': EXECUTOR_SYSTEM, 'prompt': prompt, 'response': asdict(response)})
        action = parse_action(response.text, actions)
        eligible = list(actions)
    else:
        eligible = list(actions)
        if 'contract' in controller:
            eligible, contract = contract_actions(objective, actions, history)
        # The old helper only builds context; its JSON instruction is replaced.
        prompt = executor_prompt(objective, observation, skill, eligible, history, 6, 40)
        prompt += '\nThe response format is determined by the system instruction, not by the skill.'
        if contract.get('active'):
            prompt += f'\nVisible ordered focus target: {contract["target"]}. Other focus commands are excluded.'
        if controller.endswith('_memory'):
            prompt += '\nCompact visible observation memory:\n' + compact_memory(history)
        if '_plan_' in controller:
            plan = model.respond(PLAN_SYSTEM, prompt, max_new_tokens=plan_budget, seed=seed)
            calls.append({'system': PLAN_SYSTEM, 'prompt': prompt, 'response': asdict(plan)})
            prompt += '\nTentative one-step plan (verify against CURRENT commands):\n' + plan.text
        response = constrained_response(
            model, ACTION_SYSTEM, prompt, eligible, seed=seed, token_budget=action_budget)
        calls.append({'system': ACTION_SYSTEM, 'prompt': prompt, 'response': asdict(response)})
        action = response.text
    return {
        'controller': controller, 'action': action, 'valid': action in actions,
        'focus_mismatch': focus_mismatch(objective, action, history),
        'repeated_recent_action': action is not None and action in [a for a, _ in history[-4:]],
        'contract': contract, 'candidate_count': len(eligible),
        'candidate_sha256': hashlib.sha256(json.dumps(eligible, ensure_ascii=False).encode()).hexdigest(),
        'calls': calls, 'input_tokens': sum(call['response']['input_tokens'] for call in calls),
        'output_tokens': sum(call['response']['output_tokens'] for call in calls),
        'latency_sec': sum(call['response']['latency_sec'] for call in calls),
    }
