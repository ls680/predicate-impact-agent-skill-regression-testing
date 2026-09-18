import pytest

from skilllineage.interactive import (
    action_prompt,
    diagnostic_violation,
    fallback_action_index,
    logical_skill_replays,
    matched_action_permutation,
    ngram_cosine,
    normalized_skill_text,
    parse_choice,
)
from skilllineage.run_spec import ensure_run_spec
from skilllineage.interactive_envs import _stable_select


def test_parse_choice_accepts_json_and_rejects_out_of_range():
    assert parse_choice('{"choice": 2, "reason": "next"}', 4) == 2
    assert parse_choice('{"choice": 9}', 4) is None


def test_action_prompt_states_turn_local_choice_range():
    prompt = action_prompt(
        task_description="put object",
        skill="inspect first",
        history=[],
        observation="room",
        admissible_actions=["go to desk", "look"],
    )
    assert "exactly 2 options" in prompt
    assert "from 0 through 1" in prompt


def test_invalid_choice_fallback_does_not_prefer_noop_actions():
    assert fallback_action_index(["go to desk", "look", "inventory"]) == 0


def test_normalized_skill_text_preserves_structured_sections():
    text = normalized_skill_text(
        '{"name":"heat","principles":["verify"],'
        '"procedure":["heat before put"],"warnings":["do not skip"]}'
    )
    assert "Skill: heat" in text
    assert "heat before put" in text


def test_ngram_cosine_is_bounded_and_self_similar():
    assert ngram_cosine("skip heating", "skip heating") == pytest.approx(1.0)
    assert 0.0 <= ngram_cosine("skip heating", "verify cooling") <= 1.0


def test_diagnostic_probe_checks_required_transformation():
    assert diagnostic_violation(
        "alfworld", "pick_heat_then_place_in_recep", ["take apple 1"], False
    )
    assert not diagnostic_violation(
        "alfworld",
        "pick_heat_then_place_in_recep",
        [
            "go to cabinet 1",
            "go to countertop 1",
            "go to microwave 1",
            "take apple 1",
            "heat apple 1 with microwave 1",
        ],
        False,
    )


@pytest.mark.parametrize(
    ("method", "action", "expected"),
    [
        ("skilllineage", "replace", 3),
        ("skilllineage", "quarantine", 0),
        ("skilllineage", "retain", 0),
        ("semantic_replay", "replace", 3),
        ("random_matched", "replace", 3),
        ("random_matched", "quarantine", 0),
        ("full_lineage_replay", "retain", 3),
        ("semantic", "replace", 0),
    ],
)
def test_logical_replay_cost_counts_only_generated_versions(
    method: str, action: str, expected: int
):
    assert logical_skill_replays(method, action, 3) == expected


def test_run_spec_rejects_changed_inputs(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    manifest_path = tmp_path / "manifest.json"
    families_path = tmp_path / "families.json"
    config_path.write_text('{"model":"fixed"}', encoding="utf-8")
    manifest_path.write_text('{"tasks":[1]}', encoding="utf-8")
    families_path.write_text('{"families":["a"]}', encoding="utf-8")
    monkeypatch.setattr("skilllineage.run_spec.source_hash", lambda: "source-v1")
    monkeypatch.setattr("skilllineage.run_spec.package_versions", lambda: {"x": "1"})

    ensure_run_spec(
        tmp_path, config_path, manifest_path, families_path, {"model": "fixed"}
    )
    manifest_path.write_text('{"tasks":[2]}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="Refusing to resume"):
        ensure_run_spec(
            tmp_path, config_path, manifest_path, families_path, {"model": "fixed"}
        )


def test_stable_selection_offset_excludes_engineering_item():
    values = list(range(20))
    excluded = _stable_select(values, 1, "fixed-seed")
    held_out = _stable_select(values, 8, "fixed-seed", offset=1)
    assert len(held_out) == 8
    assert set(excluded).isdisjoint(held_out)


def test_random_matched_baseline_preserves_action_counts_per_environment():
    decisions = [
        {"environment": environment, "family": f"family-{index}", "action": action}
        for environment in ("alfworld", "scienceworld")
        for index, action in enumerate(("retain", "retain", "replace", "quarantine"))
    ]
    mapping = matched_action_permutation(decisions, seed=17, label="model")
    for environment in ("alfworld", "scienceworld"):
        observed = sorted(
            action for (env, _), action in mapping.items() if env == environment
        )
        assert observed == ["quarantine", "replace", "retain", "retain"]
