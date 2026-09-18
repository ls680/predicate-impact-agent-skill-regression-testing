from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json
import platform
import random
import re
import time
from typing import Any

from .provenance import source_hash


SYSTEM_PROMPT = """You maintain reusable procedural skills for an LLM agent.
Return exactly one JSON object and no markdown. The schema is:
{"name": "short_name", "steps": ["operation_name", ...], "rationale": "one sentence"}
Use only operation names from the supplied catalog. Produce a five-step ordered procedure.
Prefer reusable operational evidence over generic advice."""


@dataclass(frozen=True)
class GenerationRecord:
    case_id: str
    chain: int
    depth: int
    condition: str
    prompt_sha256: str
    raw_text: str
    parsed_steps: tuple[str, ...]
    parse_ok: bool
    verifier_pass: bool
    latency_sec: float


def parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    candidates = [stripped]
    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if match and match.group(0) != stripped:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def verify_steps(case: dict[str, Any], steps: tuple[str, ...]) -> bool:
    return (
        len(steps) == len(case["clean_steps"])
        and list(steps) == case["clean_steps"]
        and case["defect_step"] not in steps
        and all(step in case["catalog"] for step in steps)
    )


def _skill_json(case: dict[str, Any], contaminated: bool) -> str:
    steps = list(case["clean_steps"])
    if contaminated:
        validation_index = 2
        steps[validation_index] = case["defect_step"]
    return json.dumps(
        {
            "name": f"{case['case_id']}_parent",
            "steps": steps,
            "rationale": "Previously accepted reusable procedure.",
        },
        ensure_ascii=True,
    )


def _prompt(
    case: dict[str, Any],
    parent_text: str,
    *,
    chain: int,
    depth: int,
    counterfactual: bool,
) -> str:
    intervention = (
        "The previously suspected parent version is excluded. Use the clean reviewed parent below."
        if counterfactual
        else "The parent version below was active when this descendant was authored."
    )
    return f"""Task family: {case['case_id']}
Goal: {case['description']}
Allowed operation catalog: {json.dumps(case['catalog'])}
Lineage position: chain {chain}, depth {depth}

{intervention}
Parent skill:
{parent_text}

New execution evidence:
{case['trace']}

Synthesize the next reusable skill version. A successful outcome is evidence, but it does not prove every intermediate operation was correct."""


class LocalGenerator:
    def __init__(
        self,
        model_id: str,
        *,
        revision: str | None = None,
        local_files_only: bool = False,
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

    def generate(self, prompt: str, *, max_new_tokens: int, seed: int) -> str:
        self.torch.manual_seed(seed)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        rendered = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(rendered, return_tensors="pt").to(self.model.device)
        with self.torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        generated = output[0, inputs.input_ids.shape[1] :]
        return self.tokenizer.decode(generated, skip_special_tokens=True).strip()


def _record_generation(
    generator: LocalGenerator,
    case: dict[str, Any],
    parent_text: str,
    *,
    chain: int,
    depth: int,
    condition: str,
    max_new_tokens: int,
    seed: int,
) -> GenerationRecord:
    prompt = _prompt(
        case,
        parent_text,
        chain=chain,
        depth=depth,
        counterfactual=condition == "counterfactual",
    )
    started = time.perf_counter()
    raw_text = generator.generate(
        prompt, max_new_tokens=max_new_tokens, seed=seed
    )
    latency = time.perf_counter() - started
    parsed = parse_json_object(raw_text)
    steps: tuple[str, ...] = ()
    if parsed is not None and isinstance(parsed.get("steps"), list):
        steps = tuple(str(step) for step in parsed["steps"])
    return GenerationRecord(
        case_id=case["case_id"],
        chain=chain,
        depth=depth,
        condition=condition,
        prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        raw_text=raw_text,
        parsed_steps=steps,
        parse_ok=parsed is not None and bool(steps),
        verifier_pass=verify_steps(case, steps),
        latency_sec=latency,
    )


def run_model_pilot(config_path: str | Path) -> Path:
    import pandas as pd
    import torch
    import transformers

    config_path = Path(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    cases = json.loads(Path(config["cases_path"]).read_text(encoding="utf-8"))
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    generator = LocalGenerator(
        config["model_id"],
        revision=config.get("model_revision"),
        local_files_only=config.get("local_files_only", False),
    )
    rng = random.Random(config["seed"])
    records: list[GenerationRecord] = []

    for case in cases:
        for chain in range(config["chains_per_case"]):
            factual_parent = _skill_json(case, contaminated=True)
            counterfactual_parent = _skill_json(case, contaminated=False)
            for depth in range(1, config["depth"] + 1):
                factual = _record_generation(
                    generator,
                    case,
                    factual_parent,
                    chain=chain,
                    depth=depth,
                    condition="factual",
                    max_new_tokens=config["max_new_tokens"],
                    seed=rng.randrange(2**31),
                )
                counterfactual = _record_generation(
                    generator,
                    case,
                    counterfactual_parent,
                    chain=chain,
                    depth=depth,
                    condition="counterfactual",
                    max_new_tokens=config["max_new_tokens"],
                    seed=rng.randrange(2**31),
                )
                records.extend([factual, counterfactual])
                factual_parent = factual.raw_text
                counterfactual_parent = counterfactual.raw_text

    raw_path = output_dir / "generations.jsonl"
    with raw_path.open("w", encoding="utf-8") as handle:
        for record in records:
            payload = asdict(record)
            payload["parsed_steps"] = list(record.parsed_steps)
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    pairs: list[dict[str, Any]] = []
    by_key: dict[tuple[str, int, int], dict[str, GenerationRecord]] = {}
    for record in records:
        key = (record.case_id, record.chain, record.depth)
        by_key.setdefault(key, {})[record.condition] = record
    for (case_id, chain, depth), pair in by_key.items():
        factual = pair["factual"]
        counterfactual = pair["counterfactual"]
        inherited_failure = not factual.verifier_pass
        causal_recovery = inherited_failure and counterfactual.verifier_pass
        pairs.append(
            {
                "case_id": case_id,
                "chain": chain,
                "depth": depth,
                "factual_pass": factual.verifier_pass,
                "counterfactual_pass": counterfactual.verifier_pass,
                "inherited_failure": inherited_failure,
                "causal_recovery": causal_recovery,
                "factual_parse_ok": factual.parse_ok,
                "counterfactual_parse_ok": counterfactual.parse_ok,
                "latency_sec": factual.latency_sec + counterfactual.latency_sec,
            }
        )
    frame = pd.DataFrame(pairs)
    frame.to_csv(output_dir / "pair_results.csv", index=False)

    base = float(config["base_success"])
    n = max(1, len(frame))
    factual_utility = frame["factual_pass"].mean()
    proposed_states = frame.apply(
        lambda row: (
            1.0
            if row["factual_pass"]
            else (1.0 if row["counterfactual_pass"] else base)
        ),
        axis=1,
    )
    replay_all_states = frame["counterfactual_pass"].map(
        lambda passed: 1.0 if passed else base
    )
    selective_replays = int((~frame["factual_pass"]).sum())
    summary = pd.DataFrame(
        [
            {"method": "none", "task_utility": factual_utility, "retained_fraction": 1.0, "counterfactual_replays": 0},
            {"method": "source_only", "task_utility": factual_utility, "retained_fraction": 1.0, "counterfactual_replays": 0},
            {"method": "full_lineage", "task_utility": base, "retained_fraction": 0.0, "counterfactual_replays": 0},
            {"method": "full_lineage_replay", "task_utility": replay_all_states.mean(), "retained_fraction": float(frame["counterfactual_pass"].mean()), "counterfactual_replays": n},
            {"method": "skilllineage", "task_utility": proposed_states.mean(), "retained_fraction": float((frame["factual_pass"] | frame["counterfactual_pass"]).mean()), "counterfactual_replays": selective_replays},
            {"method": "oracle_selective", "task_utility": 1.0, "retained_fraction": 1.0, "counterfactual_replays": 0},
        ]
    )
    summary["n_descendants"] = n
    summary.to_csv(output_dir / "summary.csv", index=False)

    metadata = {
        "config": config,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "transformers": transformers.__version__,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "gpu_capability": list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() else None,
        "model_dtype": str(generator.model.dtype),
        "model_parameter_count": sum(
            parameter.numel() for parameter in generator.model.parameters()
        ),
        "peak_cuda_memory_gb": (
            torch.cuda.max_memory_reserved() / 1024**3
            if torch.cuda.is_available()
            else None
        ),
        "source_sha256": source_hash(),
        "total_generations": len(records),
        "total_pairs": len(frame),
        "total_generation_seconds": sum(record.latency_sec for record in records),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return output_dir
