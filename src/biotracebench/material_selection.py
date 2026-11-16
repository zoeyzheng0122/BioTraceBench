"""Select declared representations without opening study material contents."""
from pathlib import PurePosixPath
from .common import Stop

PDF_POLICY = "structured_article_with_pdf_attachments"
ARTICLE_ROLES = {"main", "main_xml", "main_html", "main_pdf", "main_alternate", "source_version"}
PRIMARY_ROLES = {"main", "main_xml", "main_html", "main_pdf"}
STRUCTURED = {".xml": 0, ".html": 1, ".pdf": 2}


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise Stop("blocked_manifest", "Material paths must be task-relative POSIX paths")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(p in {".", ".."} for p in value.split("/")):
        raise Stop("blocked_manifest", "Material path escapes its task")
    return value


def roles(entry):
    declared = entry.get("roles", [])
    if not isinstance(declared, list) or any(not isinstance(x, str) for x in declared):
        raise Stop("blocked_manifest", "Material roles must be strings")
    role = entry.get("role")
    if role is not None and not isinstance(role, str):
        raise Stop("blocked_manifest", "Material role must be a string")
    return set(declared) | ({role} if role else set())


def article_pdf(entry):
    return PurePosixPath(entry["path"]).suffix.lower() == ".pdf" and bool(roles(entry) & ARTICLE_ROLES)


def main_representation(entry):
    return bool(roles(entry) & PRIMARY_ROLES) and PurePosixPath(entry["path"]).suffix.lower() in {".xml", ".html"}


def select_materials(files):
    """Prefer complete XML/HTML only within declared representation groups.

    representation_of declares a complete alternative to another task-local
    material. Unlinked supplements remain separate, even with matching names.
    Primary article roles form a group; alternate scientific versions do not.
    """
    entries, parents = {}, {}
    for item in files:
        name = relative_path(item.get("path"))
        roles(item)
        if name in entries:
            raise Stop("blocked_manifest", "Duplicate material path: " + name)
        entries[name] = item
        parents[name] = name

    def find(name):
        while parents[name] != name:
            name = parents[name]
        return name

    def join(a, b):
        parents[find(a)] = find(b)

    links = {}
    for name, item in entries.items():
        if "representation_of" not in item:
            continue
        target = relative_path(item["representation_of"])
        if target not in entries or target == name:
            raise Stop("blocked_manifest", "Unknown or self-referencing representation_of: " + name)
        if any(PurePosixPath(n).suffix.lower() not in STRUCTURED for n in (name, target)):
            raise Stop("blocked_manifest", "representation_of requires complete XML, HTML or PDF representations")
        links[name] = target
    for name in links:
        seen, current = set(), name
        while current in links:
            if current in seen:
                raise Stop("blocked_manifest", "Cyclic representation_of declarations")
            seen.add(current)
            current = links[current]
        join(name, links[name])
    primary = [name for name, item in entries.items() if item.get("input_use") == "model"
               and roles(item) & PRIMARY_ROLES and PurePosixPath(name).suffix.lower() in STRUCTURED]
    for name in primary[1:]:
        join(primary[0], name)

    excluded, groups = {}, {}
    for name, item in entries.items():
        if item.get("input_use") != "model":
            excluded[name] = {"path": name, "reason": "not_model"}
        elif article_pdf(item):
            excluded[name] = {"path": name, "reason": "main_article_pdf"}
        else:
            groups.setdefault(find(name), []).append(name)
    for names in groups.values():
        if len(names) < 2:
            continue
        winner = min(names, key=lambda n: (STRUCTURED[PurePosixPath(n).suffix.lower()], n))
        for name in names:
            if name != winner:
                excluded[name] = {"path": name, "reason": "preferred_representation", "selected_path": winner}
    return ([item for name, item in entries.items() if name not in excluded],
            [excluded[name] for name in entries if name in excluded])
