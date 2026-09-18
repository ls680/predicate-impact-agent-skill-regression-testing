from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
import time
from typing import Any, Callable, Iterable


SKILL_SYSTEM_PROMPT = """You maintain a reusable skill library for a text-interactive agent.
Return exactly one JSON object with this schema:
{"name":"short name","principles":["..."],"procedure":["..."],"warnings":["..."]}
Use 3--5 concise principles, 4--8 concise procedure steps, and at most 3 warnings.
Generalize from the execution evidence. The library uses a backward-compatibility policy:
preserve the intended behavior of every parent policy clause unless the new trajectory
contains a direct failed attempt of that clause. A successful alternative route does not
invalidate an untried parent rule. You may rewrite inherited clauses, but must retain their
meaning when they have not been directly falsified. Do not include instance-specific object
numbers."""


ACTION_SYSTEM_PROMPT = """You control an agent in a text environment. Select exactly one
command from the numbered admissible-command list. Follow the task objective and use the
reusable skill as fallible procedural memory. Environment observations override memory.
Command indices are local to the current turn and may change after every action; never
reuse an earlier index without checking the current list and range.
Return exactly one JSON object with no other keys: {"choice": <zero-based integer>}."""


@dataclass(frozen=True)
class ModelResponse:
    text: str
    latency_sec: float
    prompt_sha256: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class EpisodeResult:
    environment: str
    split: str
    task_id: str
    family: str
    skill_condition: str
    success: bool
    normalized_score: float
    steps: int
    invalid_outputs: int
    latency_sec: float
    diagnostic_violation: bool
    actions: tuple[str, ...]
    observations: tuple[str, ...]
    model_outputs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("actions", "observations", "model_outputs"):
            value[key] = list(value[key])
        return value


class LocalChatModel:
    def __init__(
        self,
        model_id: str,
        *,
        revision: str | None,
        local_files_only: bool,
    ) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            revision=revision,
            local_files_only=local_files_only,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            revision=revision,
            dtype="auto",
            device_map="auto",
            local_files_only=local_files_only,
        )
        self.model.eval()

    def respond(
        self,
        system: str,
        user: str,
        *,
        max_new_tokens: int,
        seed: int,
    ) -> ModelResponse:
        self.torch.manual_seed(seed)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            rendered = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            rendered = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        inputs = self.tokenizer(rendered, return_tensors="pt").to(self.model.device)
        started = time.perf_counter()
        with self.torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        latency = time.perf_counter() - started
        generated = output[0, inputs.input_ids.shape[1] :]
        text = self.tokenizer.decode(generated, skip_special_tokens=True).strip()
        return ModelResponse(
            text=text,
            latency_sec=latency,
            prompt_sha256=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            input_tokens=int(inputs.input_ids.shape[1]),
            output_tokens=int(generated.shape[0]),
        )


def parse_json_object(
    text: str, *, allow_repair: bool = True
) -> dict[str, Any] | None:
    candidates = [text.strip()]
    match = re.search(r"\{.*?\}", text, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    if allow_repair:
        try:
            from json_repair import repair_json
        except ImportError:
            return None
        repaired = repair_json(text, return_objects=True)
        if isinstance(repaired, dict):
            return repaired
    return None


def normalized_skill_text(raw: str) -> str:
    parsed = parse_json_object(raw)
    if parsed is None:
        return raw.strip()
    parts: list[str] = []
    if parsed.get("name"):
        parts.append(f"Skill: {parsed['name']}")
    for label, key in (
        ("Principles", "principles"),
        ("Procedure", "procedure"),
        ("Warnings", "warnings"),
    ):
        values = parsed.get(key, [])
        if isinstance(values, list) and values:
            parts.append(label + ":")
            parts.extend(f"- {value}" for value in values)
    return "\n".join(parts) if parts else raw.strip()


def parse_choice(text: str, action_count: int) -> int | None:
    parsed = parse_json_object(text)
    if parsed is not None:
        value = parsed.get("choice")
        if isinstance(value, int) and 0 <= value < action_count:
            return value
        if isinstance(value, str) and value.strip().isdigit():
            choice = int(value.strip())
            if 0 <= choice < action_count:
                return choice
    for pattern in (r'"choice"\s*:\s*(\d+)', r"\bchoice\s*[=:]\s*(\d+)"):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            choice = int(match.group(1))
            if 0 <= choice < action_count:
                return choice
    stripped = text.strip()
    if stripped.isdigit() and 0 <= int(stripped) < action_count:
        return int(stripped)
    return None


def authoring_prompt(
    *,
    environment: str,
    family: str,
    parent_skill: str,
    demonstration: dict[str, Any],
    depth: int,
) -> str:
    actions = demonstration.get("actions", [])
    observations = demonstration.get("observations", [])
    evidence_lines = []
    for index, action in enumerate(actions):
        observation = observations[index + 1] if index + 1 < len(observations) else ""
        evidence_lines.append(
            f"{index + 1}. action={action}; observation={observation[:220]}"
        )
    return f"""Environment: {environment}
Task family: {family}
Lineage depth: {depth}

Parent skill version:
{parent_skill}

Successful execution evidence:
Task: {demonstration.get('task_description', '')}
{chr(10).join(evidence_lines)}

Write the next generic skill version. Preserve the task's necessary ordering and
completion conditions. Treat reward as evidence of the whole trajectory, not proof that
every sentence in the parent was correct."""


def action_prompt(
    *,
    task_description: str,
    skill: str,
    history: Iterable[tuple[str, str]],
    observation: str,
    admissible_actions: list[str],
) -> str:
    history_lines = []
    for action, result in history:
        history_lines.append(f"Action: {action}\nResult: {result[:350]}")
    commands = "\n".join(
        f"[{index}] {action}" for index, action in enumerate(admissible_actions)
    )
    return f"""Task objective:
{task_description}

Reusable skill:
{skill if skill else '(no active skill; reason from the objective and observations)'}

Recent trajectory:
{chr(10).join(history_lines) if history_lines else '(none)'}

Current observation:
{observation[:1200]}

Admissible commands (exactly {len(admissible_actions)} options; choice must be an integer
from 0 through {len(admissible_actions) - 1}):
{commands}

Select the best next command. Do not invent a command or claim completion yourself."""


def fallback_action_index(actions: list[str]) -> int:
    return 0


def ngram_cosine(left: str, right: str, n: int = 3) -> float:
    def counts(value: str) -> dict[str, int]:
        normalized = re.sub(r"\s+", " ", value.lower()).strip()
        grams: dict[str, int] = {}
        for index in range(max(0, len(normalized) - n + 1)):
            gram = normalized[index : index + n]
            grams[gram] = grams.get(gram, 0) + 1
        return grams

    a, b = counts(left), counts(right)
    if not a or not b:
        return 0.0
    dot = sum(value * b.get(key, 0) for key, value in a.items())
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    return dot / (norm_a * norm_b)


def logical_skill_replays(method: str, recovery_action: str, lineage_depth: int) -> int:
    if method == "full_lineage_replay":
        return lineage_depth
    if method in {"skilllineage", "semantic_replay", "random_matched"} and recovery_action == "replace":
        return lineage_depth
    return 0


def matched_action_permutation(
    decisions: list[dict[str, Any]], *, seed: int, label: str
) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    environments = sorted({row["environment"] for row in decisions})
    for environment in environments:
        rows = [row for row in decisions if row["environment"] == environment]
        ranked = sorted(
            rows,
            key=lambda row: hashlib.sha256(
                f"{seed}:{label}:{environment}:{row['family']}".encode("utf-8")
            ).hexdigest(),
        )
        actions = sorted(row["action"] for row in rows)
        for row, action in zip(ranked, actions, strict=True):
            result[(environment, row["family"])] = action
    return result


def diagnostic_violation(
    environment: str,
    family: str,
    actions: Iterable[str],
    success: bool,
) -> bool:
    lowered = [action.lower() for action in actions]
    if success:
        return False
    visited = {
        action
        for action in lowered
        if action.startswith("go to ")
    }
    if len(visited) <= 2:
        return True
    if environment == "alfworld":
        required = {
            "pick_clean_then_place_in_recep": ("clean ",),
            "pick_heat_then_place_in_recep": ("heat ",),
            "pick_cool_then_place_in_recep": ("cool ",),
            "look_at_obj_in_light": ("toggle ",),
            "pick_two_obj_and_place": ("take ", "put "),
        }.get(family)
        if required is None:
            return False
        if family == "pick_two_obj_and_place":
            return sum(action.startswith("take ") for action in lowered) < 2
        return not any(action.startswith(required[0]) for action in lowered)
    required_science = {
        "boil": ("activate ", "focus on "),
        "melt": ("activate ", "focus on "),
        "freeze": ("focus on ",),
        "use-thermometer": ("use thermometer", "focus on "),
        "find-living-thing": ("focus on ", "move "),
        "find-non-living-thing": ("focus on ", "move "),
    }.get(family, ())
    return any(not any(action.startswith(prefix) for action in lowered) for prefix in required_science)


def run_episode(
    *,
    model: LocalChatModel,
    environment: str,
    split: str,
    task_id: str,
    family: str,
    skill_condition: str,
    skill: str,
    reset: Callable[[], tuple[str, str, list[str]]],
    step: Callable[[str], tuple[str, float, bool, list[str]]],
    max_steps: int,
    max_new_tokens: int,
    history_turns: int,
    seed: int,
) -> EpisodeResult:
    observation, task_description, actions = reset()
    observations = [observation]
    chosen_actions: list[str] = []
    model_outputs: list[str] = []
    history: list[tuple[str, str]] = []
    invalid_outputs = 0
    total_latency = 0.0
    normalized_score = 0.0
    done = False

    for turn in range(max_steps):
        if not actions:
            break
        response = model.respond(
            ACTION_SYSTEM_PROMPT,
            action_prompt(
                task_description=task_description,
                skill=skill,
                history=history[-history_turns:],
                observation=observation,
                admissible_actions=actions,
            ),
            max_new_tokens=max_new_tokens,
            seed=seed + turn,
        )
        total_latency += response.latency_sec
        model_outputs.append(response.text)
        choice = parse_choice(response.text, len(actions))
        if choice is None:
            invalid_outputs += 1
            choice = fallback_action_index(actions)
        action = actions[choice]
        next_observation, normalized_score, done, actions = step(action)
        chosen_actions.append(action)
        observations.append(next_observation)
        history.append((action, next_observation))
        observation = next_observation
        if done:
            break

    success = normalized_score >= 0.999
    return EpisodeResult(
        environment=environment,
        split=split,
        task_id=task_id,
        family=family,
        skill_condition=skill_condition,
        success=success,
        normalized_score=max(0.0, min(1.0, normalized_score)),
        steps=len(chosen_actions),
        invalid_outputs=invalid_outputs,
        latency_sec=total_latency,
        diagnostic_violation=diagnostic_violation(
            environment, family, chosen_actions, success
        ),
        actions=tuple(chosen_actions),
        observations=tuple(observations),
        model_outputs=tuple(model_outputs),
    )
