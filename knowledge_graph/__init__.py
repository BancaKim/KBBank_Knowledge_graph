"""Knowledge graph module for banking product data."""

from knowledge_graph.db import Neo4jConnection

__all__ = [
    "Neo4jConnection",
    "build_graph",
    "export_graph",
    "main",
    "parse_all_products",
    "parse_product_file",
]


def __getattr__(name: str):
    """Lazy imports for build/parse tools that need extra dependencies."""
    if name in ("build_graph", "main"):
        from knowledge_graph.deposit_builder import build_graph, main
        return build_graph if name == "build_graph" else main
    if name == "export_graph":
        from knowledge_graph.exporter import export_graph
        return export_graph
    if name in ("parse_all_products", "parse_product_file"):
        from knowledge_graph.deposit_parser import parse_all_products, parse_product_file
        return parse_all_products if name == "parse_all_products" else parse_product_file
    raise AttributeError(f"module 'knowledge_graph' has no attribute {name!r}")
