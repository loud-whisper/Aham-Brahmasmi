#!/usr/bin/env python3
"""Build the bounded startup packet from the operation ledger.

The packet is what an assistant reads at startup. Facts, tasks and lessons come
from the same ledger replay that the project context packet uses, never from the
append-only Markdown projections, so closed tasks and replaced facts disappear
from startup and the load stays within the workspace byte budget.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

from record_lifecycle import replay_records
from state_io import (
    StateError,
    newest_valid_checkpoint,
    read_json,
    require_managed_path,
    require_workspace,
    resolve_workspace,
)
from state_store import list_operation_records

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "aham-brahmasmi-startup-packet"
VERSION = 1
DEFAULT_PART_BYTES = 6000
MIN_PART_BYTES = 1024
TASK_REDUCED_CHARS = 120
SECTIONS = ("standing_files", "active_facts", "open_tasks", "lessons", "latest_checkpoint", "last_session")
DROPPABLE = ("active_facts", "open_tasks", "lessons", "last_session")
EXCLUDED_STANDING = {"BRAIN.json", "INDEX.json"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def encoded_bytes(value: Any) -> int:
    return len((canonical_json(value) + "\n").encode("utf-8"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def part_digest(part: dict[str, Any]) -> str:
    """Digest of what a part says. The part count is excluded so that the parts
    Quick delivers keep their digests when Regular appends further sections."""
    return _sha256({"index": part["index"], "section": part["section"], "items": part["items"]})


def packet_digest(packet: dict[str, Any]) -> str:
    material = dict(packet)
    material.pop("packet_sha256", None)
    return _sha256(material)


def rendered_bytes(packet: dict[str, Any]) -> int:
    return sum(encoded_bytes(part) for part in packet["parts"])


def mode_contract() -> dict[str, Any]:
    contract = read_json(ROOT / "core" / "startup.json")
    sources = contract.get("mode_sources")
    quick_budget = contract.get("quick_budget_bytes")
    if (not isinstance(sources, dict) or type(quick_budget) is not int or quick_budget <= 0
            or any(not isinstance(sources.get(mode), list) or not sources[mode]
                   or any(name not in SECTIONS for name in sources[mode]) for mode in ("quick", "regular"))):
        raise StateError("startup contract does not define mode_sources and quick_budget_bytes")
    if sources["regular"][:len(sources["quick"])] != sources["quick"]:
        raise StateError("startup contract regular sources must begin with the quick sources")
    return {"mode_sources": sources, "quick_budget_bytes": quick_budget}


def source_mode(mode: str) -> str:
    """Only Quick has a reduced source set; every other mode reads the Regular set."""
    return "quick" if mode == "quick" else "regular"


def projection_files(brain: dict[str, Any]) -> set[str]:
    state = brain.get("state") if isinstance(brain.get("state"), dict) else {}
    return {state[key] for key in ("memory", "tasks", "lessons") if isinstance(state.get(key), str)}


def standing_file_names(index: dict[str, Any], brain: dict[str, Any]) -> list[str]:
    skipped = EXCLUDED_STANDING | projection_files(brain)
    return [name for name in index["files"] if name not in skipped]


def _lesson_id(operation_id: str, revision: int, position: int, content: str) -> str:
    raw = f"lesson\0{operation_id}\0{revision}\0{position}\0{content}".encode()
    return "lesson_" + hashlib.sha256(raw).hexdigest()[:32]


def _bundle(record: dict[str, Any]) -> dict[str, Any] | None:
    details = record.get("details")
    receipt = details.get("receipt") if isinstance(details, dict) else None
    bundle = receipt.get("bundle") if isinstance(receipt, dict) else None
    return bundle if isinstance(bundle, dict) else None


def _text_chunks(text: str, room_for: Callable[[int], int]) -> list[str]:
    """Split text into pieces whose JSON encoding fits the room each chunk has."""
    chunks: list[str] = []
    current: list[str] = []
    used = 0
    room = room_for(0)
    for char in text:
        cost = len(json.dumps(char, ensure_ascii=False).encode("utf-8")) - 2
        if current and used + cost > room:
            chunks.append("".join(current))
            current, used = [], 0
            room = room_for(len(chunks))
        current.append(char)
        used += cost
    if current or not chunks:
        chunks.append("".join(current))
    return chunks


def _cut_text(text: str, room: int) -> str:
    used = 0
    for position, char in enumerate(text):
        used += len(json.dumps(char, ensure_ascii=False).encode("utf-8")) - 2
        if used > room:
            return text[:position]
    return text


class _Packer:
    """Pack section items into parts that never exceed the part ceiling."""

    def __init__(self, max_part_bytes: int) -> None:
        self.max_part_bytes = max_part_bytes
        self.parts: list[dict[str, Any]] = []
        self.cut_items = 0

    def _skeleton(self, section: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        # Size with the widest index, count and digest the final part can carry.
        return {"index": 9999, "of": 9999, "section": section, "items": items, "part_sha256": "0" * 64}

    def room(self, section: str) -> int:
        return self.max_part_bytes - encoded_bytes(self._skeleton(section, []))

    def add_section(self, section: str, items: list[dict[str, Any]]) -> None:
        current: list[dict[str, Any]] = []
        for item in items:
            item = self._fit(section, item)
            if current and encoded_bytes(self._skeleton(section, [*current, item])) > self.max_part_bytes:
                self._close(section, current)
                current = []
            current.append(item)
        self._close(section, current)

    def _fit(self, section: str, item: dict[str, Any]) -> dict[str, Any]:
        if encoded_bytes(self._skeleton(section, [item])) <= self.max_part_bytes:
            return item
        cut = dict(item)
        cut["text"] = ""
        cut["truncated_item"] = True
        room = self.max_part_bytes - encoded_bytes(self._skeleton(section, [cut]))
        if room < 0:
            raise StateError(f"startup packet part size {self.max_part_bytes} cannot hold one {section} item")
        cut["text"] = _cut_text(item["text"], room)
        self.cut_items += 1
        return cut

    def _close(self, section: str, items: list[dict[str, Any]]) -> None:
        self.parts.append({"index": len(self.parts) + 1, "of": 0, "section": section, "items": items})

    def finish(self) -> list[dict[str, Any]]:
        for part in self.parts:
            part["of"] = len(self.parts)
            part["part_sha256"] = part_digest(part)
        return self.parts


def _standing_items(workspace: Path, names: list[str], packer: _Packer) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for name in names:
        path = require_managed_path(workspace, name, label="indexed startup source")
        if not path.is_file():
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StateError(f"standing file is not UTF-8 text: {name}") from exc

        def room_for(position: int, name: str = name) -> int:
            shell = {"file": name, "chunk": 9999, "of": 9999, "text": ""}
            return max(1, packer.room("standing_files") - encoded_bytes(shell) - 1)

        chunks = _text_chunks(text, room_for)
        for position, chunk in enumerate(chunks, start=1):
            items.append({"file": name, "chunk": position, "of": len(chunks), "text": chunk})
    return items


def collect(workspace: Path) -> dict[str, Any]:
    """Read one consistent ledger snapshot and derive every dynamic section from it."""
    records = list_operation_records(workspace)
    state = replay_records(records)
    facts = sorted((item for item in state["facts"] if item.get("status") == "active"),
                   key=lambda item: (item.get("provenance", {}).get("revision", 0), item["fact_id"]))
    tasks = sorted((item for item in state["tasks"] if item.get("status") == "open"),
                   key=lambda item: (item.get("provenance", {}).get("revision", 0), item["task_id"]))
    lessons: list[dict[str, Any]] = []
    last_session: list[dict[str, Any]] = []
    for _, record in records:
        if record.get("kind") != "wrap_up":
            continue
        bundle = _bundle(record)
        if bundle is None:
            continue
        operation_id, revision = record["operation_id"], record["revision"]
        for position, lesson in enumerate(bundle.get("reusable_lessons", [])):
            if isinstance(lesson, str):
                lessons.append({"id": _lesson_id(operation_id, revision, position, lesson),
                                "revision": revision, "text": lesson})
        checkpoint = bundle.get("checkpoint") if isinstance(bundle.get("checkpoint"), dict) else {}
        last_session = [{"id": operation_id, "revision": revision, "kind": "summary",
                         "text": str(checkpoint.get("summary", ""))}]
        last_session += [{"id": operation_id, "revision": revision, "kind": "history", "text": entry}
                         for entry in bundle.get("history", []) if isinstance(entry, str)]
    checkpoint_items: list[dict[str, Any]] = []
    latest = newest_valid_checkpoint(workspace)
    if latest is not None:
        _, checkpoint = latest
        identity = checkpoint.get("id")
        checkpoint_items.append({"id": identity, "kind": "summary", "created_at": checkpoint.get("created_at"),
                                 "project": checkpoint.get("project"), "text": str(checkpoint.get("summary", ""))})
        for kind, field in (("completed", "completed"), ("next_step", "next_steps")):
            checkpoint_items += [{"id": identity, "kind": kind, "text": entry}
                                 for entry in checkpoint.get(field, []) if isinstance(entry, str)]
    return {
        "revision": state["revision"],
        "active_facts": [{"id": item["fact_id"], "revision": item.get("provenance", {}).get("revision", 0),
                          "text": item["statement"]} for item in facts],
        "open_tasks": [{"id": item["task_id"], "revision": item.get("provenance", {}).get("revision", 0),
                        "text": item["description"]} for item in tasks],
        "lessons": lessons,
        "latest_checkpoint": checkpoint_items,
        "last_session": last_session,
    }


def _reduced(task: dict[str, Any]) -> dict[str, Any]:
    if len(task["text"]) <= TASK_REDUCED_CHARS:
        return task
    return {**task, "text": task["text"][:TASK_REDUCED_CHARS], "reduced": True}


def _largest_keep(total: int, fits: Callable[[int], bool]) -> int | None:
    """Largest number of newest items that still fits, or None when even zero does not."""
    if fits(total):
        return total
    if not fits(0):
        return None
    low, high = 0, total
    while high - low > 1:
        middle = (low + high) // 2
        if fits(middle):
            low = middle
        else:
            high = middle
    return low


def build_startup_packet(workspace: Path, mode: str, *, max_part_bytes: int = DEFAULT_PART_BYTES,
                         runtime: str = "unknown") -> dict[str, Any]:
    """Return the startup packet for a mode, cut to the workspace byte budget.

    The ceiling for the packet is the mode budget minus the fixed startup sources
    (framework contracts, runtime profile, generated bridge text and the workspace
    identity and inventory files). Standing files are always delivered whole.
    """
    from drift_checks import fixed_startup_sources, load_index

    if type(max_part_bytes) is not int or max_part_bytes < MIN_PART_BYTES:
        raise StateError(f"startup packet part size must be at least {MIN_PART_BYTES} bytes")
    workspace = Path(workspace)
    # Byte accounting also runs on the framework's own workspace template, which is
    # not a usable workspace; callers that serve a packet verify the workspace first.
    brain = read_json(require_managed_path(workspace, "BRAIN.json", label="workspace identity"))
    contract = mode_contract()
    selected_mode = source_mode(mode)
    index = load_index(workspace)
    fixed = sum(fixed_startup_sources(workspace, index, runtime).values())
    regular_budget = index["startup_budget_bytes"]
    quick_budget = min(contract["quick_budget_bytes"], regular_budget)
    data = collect(workspace)
    names = standing_file_names(index, brain)
    standing = _standing_items(workspace, names, _Packer(max_part_bytes))
    quick_sections = contract["mode_sources"]["quick"]
    sections = contract["mode_sources"][selected_mode]

    # "older_facts" are the active facts that did not fit the Quick portion. Regular
    # delivers them in further active_facts parts placed after the Quick parts.
    data["older_facts"] = []
    keep = {name: len(data[name]) for name in DROPPABLE}
    keep["older_facts"] = 0
    reduce_tasks = False

    def newest(name: str) -> list[dict[str, Any]]:
        return data[name][len(data[name]) - keep[name]:] if keep[name] else []

    def assemble(names_in_order: list[str]) -> tuple[list[dict[str, Any]], int]:
        packer = _Packer(max_part_bytes)
        for name in names_in_order:
            if name == "standing_files":
                items = standing
            elif name == "latest_checkpoint":
                items = data[name]
            else:
                items = newest(name)
                if name == "open_tasks" and reduce_tasks:
                    items = [_reduced(item) for item in items]
            packer.add_section(name, items)
            if name == "active_facts" and keep["older_facts"]:
                packer.add_section(name, newest("older_facts"))
        return packer.finish(), packer.cut_items

    def size(names_in_order: list[str]) -> int:
        return fixed + sum(encoded_bytes(part) for part in assemble(names_in_order)[0])

    def shrink(name: str, names_in_order: list[str], budget: int) -> bool:
        def fits(count: int) -> bool:
            keep[name] = count
            return size(names_in_order) <= budget
        kept = _largest_keep(len(data[name]), fits)
        keep[name] = kept or 0
        return kept is not None

    def over_budget(budget: int) -> StateError:
        listing = ", ".join(f"{name} ({(workspace / name).stat().st_size} bytes)" for name in names
                            if (workspace / name).is_file()) or "none"
        return StateError(
            f"startup context exceeds byte budget: {size(['standing_files'])} > {budget} "
            f"with every ledger item omitted; standing files are delivered whole: {listing}. "
            "Shorten a standing file, move reference material out of the indexed top level, or raise startup_budget_bytes.")

    # The Quick portion is fitted first, under the Quick ceiling, and is the same in
    # both modes. An upgrade to Regular therefore keeps every part already read.
    if not shrink("active_facts", quick_sections, quick_budget):
        raise over_budget(quick_budget)
    all_facts = data["active_facts"]
    if selected_mode == "regular":
        split = len(all_facts) - keep["active_facts"]
        data["older_facts"], data["active_facts"] = all_facts[:split], all_facts[split:]
        keep["older_facts"] = split
    if selected_mode == "regular" and size(sections) > regular_budget:
        # Drop order: the last session, then oldest lessons, then oldest facts. Every
        # open task is shortened before any task is dropped.
        keep["last_session"] = 0
        if not (size(sections) <= regular_budget or shrink("lessons", sections, regular_budget)
                or shrink("older_facts", sections, regular_budget)
                or shrink("active_facts", sections, regular_budget)):
            reduce_tasks = True
            if not (size(sections) <= regular_budget or shrink("open_tasks", sections, regular_budget)):
                raise over_budget(regular_budget)

    parts, cut_items = assemble(sections)
    omitted = {name: len(data[name]) - keep[name] for name in DROPPABLE if name in sections}
    omitted["active_facts"] = len(all_facts) - keep["active_facts"] - keep["older_facts"]
    packet: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "mode": selected_mode,
        "source_revision": data["revision"],
        "parts": parts,
        "omitted": omitted,
        "truncated": bool(cut_items or reduce_tasks or any(omitted.values())),
        "token_equivalence_claimed": False,
    }
    packet["packet_sha256"] = packet_digest(packet)
    return packet


def manifest(packet: dict[str, Any]) -> dict[str, Any]:
    """Describe a packet without its content: what to read and how large it is."""
    listing = {key: value for key, value in packet.items() if key != "parts"}
    listing["parts"] = [{"index": part["index"], "of": part["of"], "section": part["section"],
                         "item_count": len(part["items"]), "bytes": encoded_bytes(part)}
                        for part in packet["parts"]]
    listing["total_bytes"] = rendered_bytes(packet)
    return listing


def session_defaults(workspace: Path) -> tuple[str | None, str | None]:
    """Mode and runtime of the active session, so a read matches what startup issued."""
    path = require_managed_path(workspace, "state/session_authority.json", label="session authority record")
    if not path.is_file():
        return None, None
    session = read_json(path)
    mode, runtime = session.get("mode"), session.get("requested_runtime")
    return (mode if isinstance(mode, str) else None, runtime if isinstance(runtime, str) else None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the bounded startup packet, or one part of it.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--mode", choices=("quick", "regular"), help="Defaults to the active session's mode")
    parser.add_argument("--runtime", help="Defaults to the active session's runtime")
    parser.add_argument("--part", type=int, help="Print only this part, counted from 1")
    parser.add_argument("--max-part-bytes", type=int, default=DEFAULT_PART_BYTES)
    args = parser.parse_args(argv)
    try:
        workspace = resolve_workspace(args.workspace)
        require_workspace(workspace)
        session_mode, session_runtime = session_defaults(workspace)
        mode = args.mode or source_mode(session_mode or "regular")
        import runtime_trust
        runtime = runtime_trust.runtime_name(args.runtime or session_runtime or "unknown")
        packet = build_startup_packet(workspace, mode, max_part_bytes=args.max_part_bytes, runtime=runtime)
        if args.part is None:
            print(canonical_json(manifest(packet)))
            return 0
        if not 1 <= args.part <= len(packet["parts"]):
            raise StateError(f"startup packet has parts 1 to {len(packet['parts'])}; part {args.part} does not exist")
        print(canonical_json(packet["parts"][args.part - 1]))
        return 0
    except StateError as exc:
        print(f"STARTUP PACKET FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
