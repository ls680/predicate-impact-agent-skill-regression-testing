from skilllineage.llm_pilot import parse_json_object, verify_steps


CASE = {
    "catalog": ["prepare", "validate", "skip", "commit", "verify"],
    "clean_steps": ["prepare", "validate", "commit", "verify"],
    "defect_step": "skip",
}


def test_parse_json_from_wrapped_output() -> None:
    parsed = parse_json_object('prefix {"steps": ["prepare"]} suffix')
    assert parsed == {"steps": ["prepare"]}


def test_verifier_rejects_defect_and_order_changes() -> None:
    assert verify_steps(CASE, ("prepare", "validate", "commit", "verify"))
    assert not verify_steps(CASE, ("prepare", "skip", "commit", "verify"))
    assert not verify_steps(CASE, ("validate", "prepare", "commit", "verify"))

