from __future__ import annotations

import hashlib
import json
from pathlib import Path


JAR_SHA256 = 'e77b0fee7d68abe3ca5b12e57d86e2bfe7603f20c5200da0b0f085939faeb465'
UPSTREAM_COMMIT = 'e8216d6044e8e39be9fcb185e3b2dfb602584b52'


def validate_jar(path):
    actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if actual != JAR_SHA256:
        raise ValueError('Simulator JAR differs from the audited pinned artifact')
    return actual


def state_signature(observation, objective, actions):
    return hashlib.sha256(json.dumps(
        {'observation': observation, 'objective': objective, 'actions': actions},
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def verify_initial_state(references, key, observation, objective, actions):
    signature = state_signature(observation, objective, actions)
    if key in references and references[key] != signature:
        raise RuntimeError(f'Initial observation/objective/action order differs across arms for {key}; '
                           f'expected {references[key]}, actual {signature}; aborting comparison')
    references[key] = signature
    return signature


class PinnedScienceworldSession:
    def __init__(self, *, max_steps, jar):
        from scienceworld import ScienceWorldEnv
        validate_jar(jar)
        # The client launches Java with its package directory as cwd, so a
        # project-relative classpath silently points at a nonexistent JAR.
        self.env = ScienceWorldEnv('', serverPath=str(Path(jar).resolve()), envStepLimit=max_steps)

    def configure(self, family, variation, simplifications):
        self.env.load(family, variation, simplifications, generateGoldPath=False)

    def reset(self):
        observation, info = self.env.reset()
        return observation, str(info['taskDesc']), list(self.env.get_valid_action_object_combinations())

    def step(self, action):
        observation, _, done, info = self.env.step(action)
        score = float(info.get('score', info.get('reward', 0.0))) / 100.0
        return observation, score, bool(done), list(self.env.get_valid_action_object_combinations())

    def close(self):
        self.env.close()
