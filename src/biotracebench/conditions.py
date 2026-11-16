"""Versioned condition names; aliases describe positions, never scientific equivalence."""

CANONICAL = ("i0", "gsr", "ssr")
LEGACY = ("initial", "ordinary_review", "integrated_review")
TO_CANONICAL = dict(zip(LEGACY, CANONICAL))
TO_LEGACY = dict(zip(CANONICAL, LEGACY))
LABELS = {"i0": "I0", "gsr": "GSR", "ssr": "SSR"}
NAMES = {"i0": "Initial construction", "gsr": "Generic self-refinement", "ssr": "Structured self-refinement"}
CONTRASTS = (("gsr", "i0"), ("ssr", "i0"), ("ssr", "gsr"))


def canonical(stage):
    if stage in CANONICAL:
        return stage
    if stage in TO_CANONICAL:
        return TO_CANONICAL[stage]
    raise ValueError("Unknown condition: " + str(stage))


def legacy(stage):
    return TO_LEGACY[canonical(stage)]


def stages(manifest):
    protocol = manifest.get("protocol")
    if protocol == "biotracebench-run-2":
        expected = ("i0",) if manifest.get("scope")=="generation" else CANONICAL
    elif protocol == "biotracebench-run-1":
        expected = LEGACY
    else:
        raise ValueError("Unknown run protocol")
    if manifest.get("stages") != list(expected):
        raise ValueError("Condition keys must match the declared run protocol; mixed aliases are not allowed")
    return expected


def key(manifest, stage):
    stages(manifest)
    return canonical(stage) if manifest.get("protocol") == "biotracebench-run-2" else legacy(stage)


def contracts_key(manifest):
    stages(manifest)
    return "ssr_output_contract" if manifest.get("protocol") == "biotracebench-run-2" else "ir_output_contract"


def label(manifest, stage):
    stages(manifest)
    if manifest.get("protocol") == "biotracebench-run-2":
        return "Generation" if manifest.get("scope")=="generation" else LABELS[canonical(stage)]
    return {"initial": "I0 (legacy)", "ordinary_review": "G (legacy generic review)",
            "integrated_review": "IR (legacy integrated review)"}[legacy(stage)]


def identity(manifest):
    names = stages(manifest)
    return {"protocol": "biotracebench-condition-names-1", "run_protocol": manifest["protocol"],
            "execution_protocol": manifest.get("execution_protocol"),
            "historical": names == LEGACY,
            "meaning": "Condition positions and labels only; matching aliases do not make different execution protocols scientifically equivalent.",
            "conditions": [{"stored_key": stage, "canonical_position": canonical(stage),
                            "display_name": label(manifest, stage), "name": NAMES[canonical(stage)]}
                           for stage in names]}


def score_stages(conditions):
    keys = set(conditions)
    if keys == set(CANONICAL):
        return CANONICAL
    if keys == set(LEGACY):
        return LEGACY
    raise ValueError("Scoring conditions must use one complete, unmixed naming version")
