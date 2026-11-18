"""Versioned policy registry (B-02).

Structured rules in YAML drive deterministic checks. The Markdown handbook is chunked
into clauses that support explanations and citations. Retrieved text never changes rules.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

import yaml

from app.core.contracts import EmployeeContext, PolicyClause, PolicyRules, PolicySnapshot

_CLAUSE_HEADING = re.compile(r"^##\s*\[(?P<id>[A-Za-z0-9._-]+)\]\s*(?P<title>.+?)\s*$")


class PolicyResolutionError(LookupError):
    """No single applicable policy pack exists. Callers must escalate, never guess."""


def make_chunk_id(pack_id: str, version: str, clause_id: str) -> str:
    return f"{pack_id}@{version}#{clause_id}"


def chunk_handbook(markdown: str, pack_id: str, version: str) -> list[PolicyClause]:
    """One chunk per '## [CLAUSE-ID] Title' section."""
    sections: list[tuple[str, str, list[str]]] = []
    for line in markdown.splitlines():
        match = _CLAUSE_HEADING.match(line)
        if match:
            sections.append((match["id"], match["title"], []))
        elif sections:
            sections[-1][2].append(line)

    clauses = []
    for clause_id, title, body in sections:
        text = " ".join(" ".join(body).split())
        if not text:
            raise ValueError(f"clause {clause_id} in {pack_id}@{version} is empty")
        clauses.append(
            PolicyClause(
                chunk_id=make_chunk_id(pack_id, version, clause_id),
                pack_id=pack_id,
                version=version,
                clause_id=clause_id,
                title=title,
                text=text,
            )
        )
    ids = [c.clause_id for c in clauses]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate clause ids in {pack_id}@{version}")
    return clauses


def load_pack(yaml_path: Path) -> PolicySnapshot:
    raw_yaml = yaml_path.read_bytes()
    data = yaml.safe_load(raw_yaml)
    raw_doc = (yaml_path.parent / data["source_doc"]).read_bytes()
    pack_id, version = str(data["id"]), str(data["version"])
    return PolicySnapshot(
        pack_id=pack_id,
        version=version,
        jurisdiction=str(data["jurisdiction"]),
        status=data["status"],
        effective_from=data["effective_from"],
        effective_to=data.get("effective_to"),
        rules=PolicyRules(**data["rules"]),
        clauses=chunk_handbook(raw_doc.decode("utf-8"), pack_id, version),
        content_hash=hashlib.sha256(raw_yaml + b"\0" + raw_doc).hexdigest(),
    )


class PolicyRegistry:
    def __init__(self, packs: list[PolicySnapshot]) -> None:
        keys = [(p.pack_id, p.version) for p in packs]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate policy pack versions")
        self._packs = list(packs)

    @classmethod
    def from_directory(cls, directory: Path) -> PolicyRegistry:
        return cls([load_pack(p) for p in sorted(directory.glob("*/*.yaml"))])

    def all(self) -> list[PolicySnapshot]:
        return list(self._packs)

    def get(self, pack_id: str, version: str) -> PolicySnapshot:
        for pack in self._packs:
            if pack.pack_id == pack_id and pack.version == version:
                return pack
        raise PolicyResolutionError(f"policy pack {pack_id}@{version} not found")

    def resolve(self, employee: EmployeeContext, work_date: date) -> PolicySnapshot:
        """The single active pack for the employee's jurisdiction on the work date."""
        matches = [
            p
            for p in self._packs
            if p.jurisdiction == employee.jurisdiction
            and p.status == "active"
            and p.effective_from <= work_date
            and (p.effective_to is None or work_date < p.effective_to)
        ]
        if not matches:
            raise PolicyResolutionError(
                f"no active policy for {employee.jurisdiction} on {work_date.isoformat()}"
            )
        if len(matches) > 1:
            found = ", ".join(f"{p.pack_id}@{p.version}" for p in matches)
            raise PolicyResolutionError(f"ambiguous policy for {employee.jurisdiction}: {found}")
        return matches[0]


def resolve_policy(
    employee: EmployeeContext, work_date: date, registry: PolicyRegistry
) -> PolicySnapshot:
    """Contract function from TEAM_RULES: resolve_policy(employee_context, work_date)."""
    return registry.resolve(employee, work_date)
