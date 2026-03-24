"""Export knowledge graph JSON directly from markdown files (no Neo4j required).

Reuses the existing parser, ontology, and model infrastructure to produce
the same ``data/graph/graph.json`` that ``exporter.py`` creates via Neo4j.

Usage::

    python -m knowledge_graph.export_from_md
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from knowledge_graph.models import GraphLink, GraphNode
from knowledge_graph.ontology import COLOR_MAP, GROUP_INDEX, NODE_LABELS
from knowledge_graph.parser import ParsedProduct, parse_all_products

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PRODUCTS_DIR = _PROJECT_ROOT / "data" / "products"
_OUTPUT_DIR = _PROJECT_ROOT / "data" / "graph"
_OUTPUT_FILE = _OUTPUT_DIR / "graph.json"

# ---------------------------------------------------------------------------
# Label -> frontend type mapping (mirrors exporter.py)
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

_LOWERCASE_COLORS: dict[str, str] = {
    v: COLOR_MAP[k] for k, v in _LABEL_TO_TYPE.items() if k in COLOR_MAP
}

# ---------------------------------------------------------------------------
# Category hierarchy (mirrors builder.py)
# ---------------------------------------------------------------------------
_HIERARCHY: dict[str, dict[str, Any]] = {
    "예금": {
        "name_en": "Deposits",
        "subcategories": ["입출금통장", "정기예금", "적금", "청약"],
    },
    "대출": {
        "name_en": "Loans",
        "subcategories": ["신용대출", "담보대출", "전월세대출", "자동차대출"],
    },
}


# ---------------------------------------------------------------------------
# Internal accumulators
# ---------------------------------------------------------------------------

class _GraphAccumulator:
    """Collect unique nodes and links, then emit D3 JSON."""

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}  # keyed by node id
        self.links: list[GraphLink] = []
        self.degree: dict[str, int] = defaultdict(int)

    # -- helpers --

    def _add_node(self, node_id: str, label: str, neo4j_label: str, props: dict[str, Any]) -> None:
        if node_id in self.nodes:
            return
        node_type = _LABEL_TO_TYPE.get(neo4j_label, neo4j_label.lower())
        group = GROUP_INDEX.get(neo4j_label, 0)
        data = {k: v for k, v in props.items() if k != "id"}
        self.nodes[node_id] = GraphNode(
            id=node_id,
            label=label,
            type=node_type,
            group=group,
            data=data,
        )

    def _add_link(self, source: str, target: str, rel_type: str) -> None:
        self.links.append(GraphLink(source=source, target=target, type=rel_type, value=1.0))
        self.degree[source] += 1
        self.degree[target] += 1

    # -- ingest a single ParsedProduct --

    def ingest(self, pp: ParsedProduct) -> None:  # noqa: C901 (complexity acceptable here)
        prod = pp.product
        if prod is None:
            return

        # Product node
        self._add_node(prod.id, prod.name, "Product", {
            "name": prod.name,
            "product_type": prod.product_type,
            "category": pp.category.name if pp.category else "",
            "description": prod.description,
            "amount_max_raw": prod.amount_max_raw,
            "amount_max_won": prod.amount_max_won,
            "eligibility_summary": prod.eligibility_summary,
            "page_url": prod.page_url,
            "scraped_at": prod.scraped_at.isoformat() if prod.scraped_at else None,
        })

        # Category
        if pp.category:
            cat = pp.category
            self._add_node(cat.id, cat.name, "Category", {
                "name": cat.name,
                "name_en": cat.name_en,
            })
            self._add_link(prod.id, cat.id, "BELONGS_TO")

        # Features
        for feat in pp.features:
            self._add_node(feat.id, feat.name, "Feature", {
                "name": feat.name,
                "description": feat.description,
            })
            self._add_link(prod.id, feat.id, "HAS_FEATURE")

        # Interest rates
        for rate in pp.rates:
            label = f"{prod.name} 금리"
            self._add_node(rate.id, label, "InterestRate", {
                "name": label,
                "rate_type": rate.rate_type,
                "min_rate": rate.min_rate,
                "max_rate": rate.max_rate,
                "base_rate_name": rate.base_rate_name,
                "spread": rate.spread,
            })
            self._add_link(prod.id, rate.id, "HAS_RATE")

        # Terms
        for term in pp.terms:
            label = term.raw_text or f"{term.min_months or '?'}~{term.max_months or '?'}개월"
            self._add_node(term.id, label, "Term", {
                "name": label,
                "min_months": term.min_months,
                "max_months": term.max_months,
                "raw_text": term.raw_text,
            })
            self._add_link(prod.id, term.id, "HAS_TERM")

        # Eligibility
        if pp.eligibility:
            ec = pp.eligibility
            label = (ec.target_audience or "가입자격") + (f" 만{ec.min_age}세이상" if ec.min_age else "")
            self._add_node(ec.id, label, "EligibilityCondition", {
                "name": label,
                "description": ec.description,
                "min_age": ec.min_age,
                "target_audience": ec.target_audience,
            })
            self._add_link(prod.id, ec.id, "REQUIRES")

        # Channels
        for ch in pp.channels:
            self._add_node(ch.id, ch.name, "Channel", {
                "name": ch.name,
                "name_en": ch.name_en,
            })
            self._add_link(prod.id, ch.id, "AVAILABLE_VIA")

        # Repayment methods
        for rm in pp.repayment_methods:
            self._add_node(rm.id, rm.name, "RepaymentMethod", {
                "name": rm.name,
                "description": rm.description,
            })
            self._add_link(prod.id, rm.id, "REPAID_VIA")

        # Tax benefit
        if pp.tax_benefit:
            tb = pp.tax_benefit
            label = tb.type + (" 가능" if tb.eligible else " 불가")
            self._add_node(tb.id, label, "TaxBenefit", {
                "name": label,
                "type": tb.type,
                "eligible": tb.eligible,
                "description": tb.description,
            })
            self._add_link(prod.id, tb.id, "HAS_TAX_BENEFIT")

        # Deposit protection
        if pp.deposit_protection:
            dp = pp.deposit_protection
            label = "예금자보호 " + ("1억원" if dp.max_amount_won else "해당")
            self._add_node(dp.id, label, "DepositProtection", {
                "name": label,
                "protected": dp.protected,
                "max_amount_won": dp.max_amount_won,
                "description": dp.description,
            })
            self._add_link(prod.id, dp.id, "PROTECTED_BY")

        # Preferential rates
        for pr in pp.preferential_rates:
            self._add_node(pr.id, pr.name, "PreferentialRate", {
                "name": pr.name,
                "condition_description": pr.condition_description,
                "rate_value_pp": pr.rate_value_pp,
            })
            self._add_link(prod.id, pr.id, "HAS_PREFERENTIAL_RATE")

        # Fees
        for fee in pp.fees:
            self._add_node(fee.id, fee.fee_type, "Fee", {
                "name": fee.fee_type,
                "fee_type": fee.fee_type,
                "description": fee.description,
            })
            self._add_link(prod.id, fee.id, "HAS_FEE")

        # Product type
        if pp.product_type:
            pt = pp.product_type
            self._add_node(pt.id, pt.name, "ProductType", {
                "name": pt.name,
            })
            self._add_link(prod.id, pt.id, "HAS_TYPE")

    # -- category hierarchy (mirrors builder._create_category_hierarchy) --

    def build_category_hierarchy(self) -> None:
        existing_cats = {
            n.data.get("name"): nid
            for nid, n in self.nodes.items()
            if n.type == "category"
        }
        for parent_name, info in _HIERARCHY.items():
            parent_id = f"parent__{parent_name}"
            self._add_node(parent_id, parent_name, "ParentCategory", {
                "name": parent_name,
                "name_en": info["name_en"],
            })
            for sub_name in info["subcategories"]:
                if sub_name in existing_cats:
                    self._add_link(parent_id, existing_cats[sub_name], "HAS_SUBCATEGORY")

    # -- COMPETES_WITH inference (mirrors builder._infer_competes_with) --

    def infer_competes_with(self, all_parsed: list[ParsedProduct]) -> None:
        # Build lookup structures
        cat_products: dict[str, list[ParsedProduct]] = defaultdict(list)
        prod_repay: dict[str, set[str]] = defaultdict(set)

        for pp in all_parsed:
            if pp.product is None or pp.category is None:
                continue
            cat_products[pp.category.id].append(pp)
            for rm in pp.repayment_methods:
                prod_repay[pp.product.id].add(rm.id)

        for cat_id, members in cat_products.items():
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    pa, pb = a.product, b.product
                    if pa is None or pb is None:
                        continue
                    if pa.id >= pb.id:
                        src, tgt = pb.id, pa.id
                    else:
                        src, tgt = pa.id, pb.id

                    if pa.product_type != pb.product_type:
                        continue

                    # Shared repayment method?
                    shared_repay = bool(prod_repay[pa.id] & prod_repay[pb.id])

                    # Similar amount range?
                    similar_amount = False
                    if pa.amount_max_won is not None and pb.amount_max_won is not None:
                        avg = (pa.amount_max_won + pb.amount_max_won) / 2
                        if avg > 0 and abs(pa.amount_max_won - pb.amount_max_won) < 0.5 * avg:
                            similar_amount = True

                    if shared_repay or similar_amount:
                        self._add_link(src, tgt, "COMPETES_WITH")

    # -- final export --

    def export(self, output_path: Path) -> dict[str, Any]:
        nodes = list(self.nodes.values())

        # Compute sizes based on degree (same as exporter.py)
        max_degree = max((self.degree.get(n.id, 1) for n in nodes), default=1)
        min_size, max_size = 5, 30
        for node in nodes:
            deg = self.degree.get(node.id, 1)
            node.data["size"] = min_size + (max_size - min_size) * (deg / max(max_degree, 1))

        node_types = sorted({n.type for n in nodes})
        edge_types = sorted({lnk.type for lnk in self.links})

        payload: dict[str, Any] = {
            "nodes": [n.model_dump() for n in nodes],
            "links": [lnk.model_dump() for lnk in self.links],
            "metadata": {
                "node_types": node_types,
                "edge_types": edge_types,
                "colors": {nt: _LOWERCASE_COLORS.get(nt, "#999999") for nt in node_types},
                "stats": {
                    "total_nodes": len(nodes),
                    "total_edges": len(self.links),
                    "nodes_by_type": {nt: sum(1 for n in nodes if n.type == nt) for nt in node_types},
                    "links_by_type": {et: sum(1 for lnk in self.links if lnk.type == et) for et in edge_types},
                },
            },
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[export_from_md] wrote {output_path}  ({len(nodes)} nodes, {len(self.links)} links)")
        return payload


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(products_dir: Path | None = None, output_path: Path | None = None) -> dict[str, Any]:
    """Parse markdown files and export graph.json without Neo4j."""
    products_dir = products_dir or _PRODUCTS_DIR
    output_path = output_path or _OUTPUT_FILE

    print(f"[export_from_md] parsing products from {products_dir} ...")
    all_parsed = parse_all_products(products_dir)
    print(f"[export_from_md] found {len(all_parsed)} product file(s)")

    acc = _GraphAccumulator()

    for idx, pp in enumerate(all_parsed, 1):
        name = pp.product.name if pp.product else "(unknown)"
        print(f"[export_from_md] ({idx}/{len(all_parsed)}) ingesting: {name}")
        acc.ingest(pp)

    print("[export_from_md] building category hierarchy ...")
    acc.build_category_hierarchy()

    print("[export_from_md] inferring COMPETES_WITH relationships ...")
    acc.infer_competes_with(all_parsed)

    print("[export_from_md] exporting ...")
    return acc.export(output_path)


if __name__ == "__main__":
    main()
