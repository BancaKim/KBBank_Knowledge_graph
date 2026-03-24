"""Standalone knowledge graph builder using NetworkX (no Neo4j required).

Parses all product MD files and exports a D3.js-compatible JSON graph.
Use this when Neo4j/Docker is not available.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import frontmatter
import networkx as nx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_DIR = PROJECT_ROOT / "data" / "products"
GRAPH_OUTPUT = PROJECT_ROOT / "data" / "graph" / "graph.json"

# Color scheme matching frontend types
COLORS = {
    "product": "#4A90D9",
    "category": "#F5A623",
    "parentcategory": "#E65100",
    "feature": "#7ED321",
    "interestrate": "#D0021B",
    "term": "#9B59B6",
    "channel": "#1ABC9C",
    "eligibilitycondition": "#95A5A6",
    "repaymentmethod": "#E67E22",
    "taxbenefit": "#27AE60",
    "depositprotection": "#2980B9",
    "preferentialrate": "#E74C3C",
    "fee": "#8E44AD",
    "producttype": "#16A085",
}

GROUPS = {
    "product": 0,
    "category": 1,
    "parentcategory": 2,
    "feature": 3,
    "interestrate": 4,
    "term": 5,
    "channel": 6,
    "eligibilitycondition": 7,
    "repaymentmethod": 8,
    "taxbenefit": 9,
    "depositprotection": 10,
    "preferentialrate": 11,
    "fee": 12,
    "producttype": 13,
}

CATEGORY_LABELS = {
    "예금": "Deposits",
    "적금": "Savings",
    "대출": "Loans",
    "펀드": "Funds",
    "신탁": "Trusts",
    "ISA": "ISA",
    "외화예금": "Foreign Currency",
}


def slugify_id(text: str) -> str:
    """Create a simple ID from text."""
    return re.sub(r"[^\w가-힣]", "_", text.lower()).strip("_")


def parse_product(path: Path) -> dict | None:
    """Parse a single product MD file."""
    try:
        post = frontmatter.load(str(path))
        meta = post.metadata
        content = post.content

        name = meta.get("name", path.stem)
        category = meta.get("category", path.parent.name)

        # Parse rates
        rates = meta.get("rates", {})
        rate_min = None
        rate_max = None
        if rates:
            rate_min_str = str(rates.get("min", ""))
            rate_max_str = str(rates.get("max", ""))
            rate_min_match = re.search(r"(\d+\.?\d*)", rate_min_str)
            rate_max_match = re.search(r"(\d+\.?\d*)", rate_max_str)
            if rate_min_match:
                rate_min = float(rate_min_match.group(1))
            if rate_max_match:
                rate_max = float(rate_max_match.group(1))

        # Parse terms
        terms = meta.get("terms", {})
        term_min = str(terms.get("min", "")) if terms else ""
        term_max = str(terms.get("max", "")) if terms else ""

        # Parse channels
        channels = meta.get("channels", [])
        if isinstance(channels, str):
            channels = [c.strip() for c in channels.split(",")]

        # Extract description from content
        description = ""
        desc_match = re.search(r"## 상품설명\s*\n\s*(.+?)(?=\n##|\Z)", content, re.DOTALL)
        if desc_match:
            description = desc_match.group(1).strip()

        # Extract eligibility
        eligibility = ""
        elig_match = re.search(r"## 가입대상\s*\n\s*(.+?)(?=\n##|\Z)", content, re.DOTALL)
        if elig_match:
            eligibility = elig_match.group(1).strip()

        # Extract features
        features = []
        feat_match = re.search(r"## 특징\s*\n(.+?)(?=\n##|\Z)", content, re.DOTALL)
        if feat_match:
            for line in feat_match.group(1).strip().split("\n"):
                line = line.strip().lstrip("- ")
                if line and len(line) > 3:
                    features.append(line[:80])

        return {
            "name": name,
            "category": category,
            "description": description,
            "rate_min": rate_min,
            "rate_max": rate_max,
            "rate_type": meta.get("rate_type", ""),
            "term_min": term_min,
            "term_max": term_max,
            "eligibility": eligibility,
            "features": features,
            "channels": channels,
            "page_url": meta.get("page_url", ""),
            "page_id": meta.get("page_id", ""),
            "scraped_at": meta.get("scraped_at", ""),
        }
    except Exception as exc:
        print(f"  Warning: failed to parse {path}: {exc}")
        return None


def build_graph() -> dict:
    """Build the knowledge graph from MD files and export as D3 JSON."""
    G = nx.DiGraph()
    products = []

    # Parse all product files
    for md_file in sorted(PRODUCTS_DIR.rglob("*.md")):
        product = parse_product(md_file)
        if product:
            products.append(product)
            print(f"  Parsed: {product['name']} ({product['category']})")

    print(f"\nTotal products parsed: {len(products)}")

    # Add category nodes
    categories_seen = set()
    for p in products:
        cat = p["category"]
        if cat not in categories_seen:
            cat_id = f"cat_{slugify_id(cat)}"
            G.add_node(cat_id, label=cat, type="category",
                       data={"label_en": CATEGORY_LABELS.get(cat, cat),
                             "product_count": sum(1 for pp in products if pp["category"] == cat)})
            categories_seen.add(cat)

    # Add product nodes and relationships
    for p in products:
        pid = f"prod_{slugify_id(p['name'])}"
        G.add_node(pid, label=p["name"], type="product", data={
            "category": p["category"],
            "description": p["description"][:200] if p["description"] else "",
            "rate_min": p["rate_min"],
            "rate_max": p["rate_max"],
            "rate_type": p["rate_type"],
            "term_min": p["term_min"],
            "term_max": p["term_max"],
            "eligibility": p["eligibility"][:150] if p["eligibility"] else "",
            "features": p["features"][:5],
            "page_url": p["page_url"],
        })

        # BELONGS_TO category
        cat_id = f"cat_{slugify_id(p['category'])}"
        G.add_edge(pid, cat_id, type="BELONGS_TO", value=1)

        # Add channel nodes
        for ch in p["channels"]:
            if not ch:
                continue
            ch_id = f"ch_{slugify_id(ch)}"
            if not G.has_node(ch_id):
                G.add_node(ch_id, label=ch, type="channel", data={"name": ch})
            G.add_edge(pid, ch_id, type="AVAILABLE_VIA", value=0.5)

        # Add rate node if rates exist
        if p["rate_min"] is not None:
            rate_label = f"{p['rate_min']}%~{p['rate_max']}%"
            rate_id = f"rate_{slugify_id(rate_label)}"
            if not G.has_node(rate_id):
                G.add_node(rate_id, label=rate_label, type="rate", data={
                    "min_value": p["rate_min"],
                    "max_value": p["rate_max"],
                    "rate_type": p["rate_type"],
                })
            G.add_edge(pid, rate_id, type="HAS_RATE", value=0.7)

        # Add term node if terms exist
        if p["term_min"]:
            term_label = f"{p['term_min']}"
            if p["term_max"]:
                term_label += f"~{p['term_max']}"
            term_id = f"term_{slugify_id(term_label)}"
            if not G.has_node(term_id):
                G.add_node(term_id, label=term_label, type="term", data={
                    "min": p["term_min"],
                    "max": p["term_max"],
                })
            G.add_edge(pid, term_id, type="HAS_TERM", value=0.5)

    # Infer COMPETES_WITH (same category, products with rates)
    for i, a in enumerate(products):
        for b in products[i + 1:]:
            if a["category"] == b["category"] and a["rate_min"] is not None and b["rate_min"] is not None:
                rate_diff = abs((a["rate_min"] or 0) - (b["rate_min"] or 0))
                if rate_diff <= 1.0:
                    aid = f"prod_{slugify_id(a['name'])}"
                    bid = f"prod_{slugify_id(b['name'])}"
                    G.add_edge(aid, bid, type="COMPETES_WITH", value=0.3)

    # Infer SIMILAR_RATE (cross-category, within 0.5%)
    for i, a in enumerate(products):
        for b in products[i + 1:]:
            if a["category"] != b["category"] and a["rate_min"] is not None and b["rate_min"] is not None:
                rate_diff = abs((a["rate_min"] or 0) - (b["rate_min"] or 0))
                if rate_diff <= 0.5:
                    aid = f"prod_{slugify_id(a['name'])}"
                    bid = f"prod_{slugify_id(b['name'])}"
                    G.add_edge(aid, bid, type="SIMILAR_RATE", value=0.2)

    # Export to D3 JSON
    nodes = []
    for node_id, attrs in G.nodes(data=True):
        node_type = attrs.get("type", "product")
        degree = G.degree(node_id)
        nodes.append({
            "id": node_id,
            "label": attrs.get("label", node_id),
            "type": node_type,
            "group": GROUPS.get(node_type, 0),
            "data": attrs.get("data", {}),
            "size": min(8 + degree * 2, 30),
        })

    links = []
    for src, tgt, attrs in G.edges(data=True):
        links.append({
            "source": src,
            "target": tgt,
            "type": attrs.get("type", "RELATED"),
            "value": attrs.get("value", 1),
        })

    node_types = sorted(set(n["type"] for n in nodes))
    edge_types = sorted(set(l["type"] for l in links))

    graph_data = {
        "nodes": nodes,
        "links": links,
        "metadata": {
            "node_types": node_types,
            "edge_types": edge_types,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(links),
            },
        },
    }

    # Write output
    GRAPH_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_OUTPUT.write_text(json.dumps(graph_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGraph exported to {GRAPH_OUTPUT}")
    print(f"  Nodes: {len(nodes)}")
    print(f"  Edges: {len(links)}")
    print(f"  Node types: {node_types}")
    print(f"  Edge types: {edge_types}")

    return graph_data


if __name__ == "__main__":
    build_graph()
