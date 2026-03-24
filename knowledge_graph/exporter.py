"""Export Neo4j graph to D3.js compatible JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowledge_graph.db import Neo4jConnection
from knowledge_graph.models import GraphLink, GraphNode
from knowledge_graph.ontology import COLOR_MAP, GROUP_INDEX, NODE_LABELS

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_OUTPUT_DIR = _PROJECT_ROOT / "data" / "graph"
_OUTPUT_FILE = _OUTPUT_DIR / "graph.json"


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _fetch_nodes(conn: Neo4jConnection) -> list[dict[str, Any]]:
    """Fetch all nodes with their labels and properties."""
    return conn.run_query(
        """
        MATCH (n)
        WHERE any(lbl IN labels(n) WHERE lbl IN $labels)
        RETURN n.id AS id,
               labels(n) AS labels,
               properties(n) AS props,
               size([(n)--() | 1]) AS degree
        """,
        {"labels": NODE_LABELS},
    )


def _fetch_relationships(conn: Neo4jConnection) -> list[dict[str, Any]]:
    """Fetch all relationships between known node types."""
    return conn.run_query(
        """
        MATCH (a)-[r]->(b)
        WHERE any(lbl IN labels(a) WHERE lbl IN $labels)
          AND any(lbl IN labels(b) WHERE lbl IN $labels)
        RETURN a.id AS source,
               b.id AS target,
               type(r) AS rel_type
        """,
        {"labels": NODE_LABELS},
    )


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

_LABEL_TO_TYPE: dict[str, str] = {
    "Product": "product",
    "Category": "category",
    "ParentCategory": "parentcategory",
    "Feature": "feature",
    "InterestRate": "interestrate",
    "Term": "term",
    "Channel": "channel",
    "EligibilityCondition": "eligibilitycondition",
    "RepaymentMethod": "repaymentmethod",
    "TaxBenefit": "taxbenefit",
    "DepositProtection": "depositprotection",
    "PreferentialRate": "preferentialrate",
    "Fee": "fee",
    "ProductType": "producttype",
}


_LOWERCASE_COLORS: dict[str, str] = {v: COLOR_MAP[k] for k, v in _LABEL_TO_TYPE.items() if k in COLOR_MAP}


def _primary_label(labels: list[str]) -> str:
    """Pick the first label that appears in NODE_LABELS and return frontend-compatible type."""
    for lbl in labels:
        if lbl in GROUP_INDEX:
            return _LABEL_TO_TYPE.get(lbl, lbl.lower())
    raw = labels[0] if labels else "Unknown"
    return _LABEL_TO_TYPE.get(raw, raw.lower())


def _raw_label(labels: list[str]) -> str:
    """Pick the first label that appears in NODE_LABELS (capitalized)."""
    for lbl in labels:
        if lbl in GROUP_INDEX:
            return lbl
    return labels[0] if labels else "Unknown"


def _build_graph_node(record: dict[str, Any]) -> GraphNode:
    node_id: str = record["id"]
    labels: list[str] = record["labels"]
    props: dict[str, Any] = record["props"]
    degree: int = record.get("degree", 1)

    raw = _raw_label(labels)
    node_type = _LABEL_TO_TYPE.get(raw, raw.lower())

    # Remove id from data to avoid duplication
    data = {k: v for k, v in props.items() if k != "id"}
    data["_degree"] = degree

    return GraphNode(
        id=node_id,
        label=props.get("name", node_id),
        type=node_type,
        group=GROUP_INDEX.get(raw, 0),
        data=data,
    )


def _build_graph_link(record: dict[str, Any]) -> GraphLink:
    return GraphLink(
        source=record["source"],
        target=record["target"],
        type=record["rel_type"],
        value=1.0,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_graph(conn: Neo4jConnection, output_path: Path | None = None) -> Path:
    """Query Neo4j and write D3-compatible JSON to *output_path*."""
    output_path = output_path or _OUTPUT_FILE

    raw_nodes = _fetch_nodes(conn)
    raw_links = _fetch_relationships(conn)

    nodes = [_build_graph_node(r) for r in raw_nodes]
    links = [_build_graph_link(r) for r in raw_links]

    # Compute node sizes based on degree (connections)
    max_degree = max((n.data.get("_degree", 1) for n in nodes), default=1)
    min_size, max_size = 5, 30
    for node in nodes:
        deg = node.data.pop("_degree", 1)
        node.data["size"] = min_size + (max_size - min_size) * (deg / max(max_degree, 1))

    # Collect metadata
    node_types = sorted({n.type for n in nodes})
    edge_types = sorted({lnk.type for lnk in links})

    payload: dict[str, Any] = {
        "nodes": [n.model_dump() for n in nodes],
        "links": [lnk.model_dump() for lnk in links],
        "metadata": {
            "node_types": node_types,
            "edge_types": edge_types,
            "colors": {nt: _LOWERCASE_COLORS.get(nt, "#999999") for nt in node_types},
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(links),
                "nodes_by_type": {nt: sum(1 for n in nodes if n.type == nt) for nt in node_types},
                "links_by_type": {et: sum(1 for lnk in links if lnk.type == et) for et in edge_types},
            },
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[exporter] wrote {output_path}  ({len(nodes)} nodes, {len(links)} links)")
    return output_path
