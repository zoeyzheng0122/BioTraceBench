"""Output-level revision selection without relabelling immutable old scores."""


def eligible(entry, reference_sha256, required_revision=None):
    """Keep legacy reuse unless this output explicitly requires a new revision."""
    binding = entry.get('score_binding', {})
    return (entry.get('status') == 'automatic_scoring_completed'
            and binding.get('reference_sha256') == reference_sha256
            and (required_revision is None or binding.get('scoring_revision') == required_revision))


def selected_status(entry, reference_sha256, required_revision=None):
    binding = entry.get('score_binding', {})
    if binding.get('reference_sha256') != reference_sha256:
        return 'superseded_reference'
    if required_revision is not None and binding.get('scoring_revision') != required_revision:
        return 'superseded_scoring_revision'
    return entry.get('status')
