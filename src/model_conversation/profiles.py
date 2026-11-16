"""Resolve provider defaults and concrete deployment settings before freezing."""
from pathlib import Path
from .archive import read


def load(path):
    path = Path(path).resolve()
    value = read(path)
    if set(value) != {"provider_template", "settings"}:
        raise ValueError("Profile requires provider_template and settings")
    provider = read(path.parent / value["provider_template"])
    if set(provider) != {"name", "defaults"}:
        raise ValueError("Provider template requires name and defaults")
    settings = {**provider["defaults"], **value["settings"]}
    if settings.get("provider") != provider["name"]:
        raise ValueError("Profile cannot change provider identity")
    from .adapters import validate_generation
    validate_generation(settings)
    # Templates deliberately contain null fields until a model/deployment is selected.
    # Frozen manifests contain the resolved object, never a mutable template reference.
    return settings
