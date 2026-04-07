"""Export Neo4j Aura graph to a reproducible Cypher dump file.

Generates MERGE statements for all nodes and relationships so the dump
can be replayed against an empty database to restore the full graph.

Usage:
    python -m knowledge_graph.cypher_dump
    python -m knowledge_graph.cypher_dump --output /tmp/backup.cypher
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Any

from knowledge_graph.db import Neo4jConnection

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BACKUP_DIR = _PROJECT_ROOT / "data" / "backup"
_SCHEMA_DIR = Path(__file__).resolve().parent


def _cypher_literal(value: Any) -> str:
    """Convert a Python value to a Cypher literal string."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        items = ", ".join(_cypher_literal(v) for v in value)
        return f"[{items}]"
    # String — escape backslashes, single quotes, and newlines
    s = str(value)
    s = s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
    return f"'{s}'"


def _props_map(props: dict[str, Any]) -> str:
    """Build a Cypher map literal from a dict, e.g. {name: 'foo', age: 30}."""
    if not props:
        return "{}"
    pairs = ", ".join(f"`{k}`: {_cypher_literal(v)}" for k, v in sorted(props.items()))
    return f"{{{pairs}}}"


def _fetch_all_nodes(conn: Neo4jConnection) -> list[dict[str, Any]]:
    return conn.run_query(
        "MATCH (n) RETURN labels(n) AS labels, properties(n) AS props"
    )


def _fetch_all_relationships(conn: Neo4jConnection) -> list[dict[str, Any]]:
    return conn.run_query(
        """
        MATCH (a)-[r]->(b)
        RETURN a.id AS src_id, labels(a) AS src_labels,
               b.id AS tgt_id, labels(b) AS tgt_labels,
               type(r) AS rel_type, properties(r) AS rel_props
        """
    )


def _node_merge_statement(labels: list[str], props: dict[str, Any]) -> str:
    """Generate a MERGE statement for a single node."""
    node_id = props.get("id")
    if node_id is None:
        return ""
    label_str = ":".join(f"`{l}`" for l in labels)
    other_props = {k: v for k, v in props.items() if k != "id"}
    stmt = f"MERGE (n:{label_str} {{id: {_cypher_literal(node_id)}}})"
    if other_props:
        stmt += f" SET n += {_props_map(other_props)}"
    return stmt + ";"


def _rel_merge_statement(
    src_id: str,
    src_labels: list[str],
    tgt_id: str,
    tgt_labels: list[str],
    rel_type: str,
    rel_props: dict[str, Any],
) -> str:
    """Generate a MATCH + MERGE statement for a single relationship."""
    src_label = f"`{src_labels[0]}`" if src_labels else ""
    tgt_label = f"`{tgt_labels[0]}`" if tgt_labels else ""
    stmt = (
        f"MATCH (a:{src_label} {{id: {_cypher_literal(src_id)}}}), "
        f"(b:{tgt_label} {{id: {_cypher_literal(tgt_id)}}}) "
        f"MERGE (a)-[r:`{rel_type}`]->(b)"
    )
    if rel_props:
        stmt += f" SET r += {_props_map(rel_props)}"
    return stmt + ";"


def dump(conn: Neo4jConnection, output_path: Path | None = None) -> Path:
    """Export the full graph to a Cypher dump file."""
    if output_path is None:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = _BACKUP_DIR / f"dump_{ts}.cypher"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []

    # -- Schema ----------------------------------------------------------------
    lines.append("// ==========================================================")
    lines.append("// Neo4j Cypher Dump")
    lines.append(f"// Generated: {dt.datetime.now().isoformat()}")
    lines.append("// ==========================================================\n")

    for schema_file in ("schema.cypher", "loan_schema.cypher"):
        path = _SCHEMA_DIR / schema_file
        if path.exists():
            lines.append(f"// --- {schema_file} ---")
            lines.append(path.read_text(encoding="utf-8").strip())
            lines.append("")

    # -- Nodes -----------------------------------------------------------------
    raw_nodes = _fetch_all_nodes(conn)
    lines.append(f"\n// --- Nodes ({len(raw_nodes)}) ---")
    for rec in raw_nodes:
        stmt = _node_merge_statement(rec["labels"], rec["props"])
        if stmt:
            lines.append(stmt)

    # -- Relationships ---------------------------------------------------------
    raw_rels = _fetch_all_relationships(conn)
    lines.append(f"\n// --- Relationships ({len(raw_rels)}) ---")
    for rec in raw_rels:
        if rec["src_id"] is None or rec["tgt_id"] is None:
            continue
        lines.append(
            _rel_merge_statement(
                rec["src_id"],
                rec["src_labels"],
                rec["tgt_id"],
                rec["tgt_labels"],
                rec["rel_type"],
                rec["rel_props"],
            )
        )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[cypher_dump] wrote {output_path}")
    print(f"  nodes: {len(raw_nodes)}, relationships: {len(raw_rels)}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Neo4j graph as Cypher dump")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output .cypher file path (default: data/backup/dump_<timestamp>.cypher)",
    )
    args = parser.parse_args()

    with Neo4jConnection() as conn:
        dump(conn, args.output)


if __name__ == "__main__":
    main()
