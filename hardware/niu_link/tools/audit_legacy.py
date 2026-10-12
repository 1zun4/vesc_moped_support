#!/usr/bin/env python3
"""Read-only KiCad source inventory; does not replace ERC/DRC or a netlist export."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]


def parse(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text)
    root, stack = [], []
    current = root
    for token in tokens:
        if token == "(":
            node = []
            current.append(node)
            stack.append(current)
            current = node
        elif token == ")":
            if not stack:
                raise ValueError("Unbalanced closing parenthesis")
            current = stack.pop()
        else:
            current.append(json.loads(token) if token.startswith('"') else token)
    if stack or len(root) != 1:
        raise ValueError("Unbalanced or multiple root expressions")
    return root[0]


def children(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def properties(node):
    return {x[1]: x[2] for x in children(node, "property")}


def inventory(node, kind):
    return {properties(x)["Reference"]: properties(x).get("Value", "")
            for x in children(node, kind)
            if "Reference" in properties(x)
            and not properties(x)["Reference"].startswith("#")}


def audit():
    legacy = ROOT / "bridge_n1s"
    schematic = parse((legacy / "N1S_bridge.kicad_sch").read_text())
    pcb = parse((legacy / "N1S_bridge.kicad_pcb").read_text())
    sch_parts, pcb_parts = inventory(schematic, "symbol"), inventory(pcb, "footprint")
    pads = {}
    for footprint in children(pcb, "footprint"):
        ref = properties(footprint).get("Reference")
        if ref not in ("J1", "U2"):
            continue
        pads[ref] = {}
        for pad in children(footprint, "pad"):
            nets = children(pad, "net")
            pads[ref][pad[1]] = nets[0][-1] if nets else None
    return {
        "schematic_only": {k: sch_parts[k] for k in sorted(sch_parts.keys() - pcb_parts.keys())},
        "pcb_only": {k: pcb_parts[k] for k in sorted(pcb_parts.keys() - sch_parts.keys())},
        "different_values": {k: [sch_parts[k], pcb_parts[k]]
                             for k in sorted(sch_parts.keys() & pcb_parts.keys())
                             if sch_parts[k] != pcb_parts[k]},
        "pad_net_assignments": pads,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
