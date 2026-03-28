"""Knowledge graph ontology: node labels, relationship types, and visualization config."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Node labels
# ---------------------------------------------------------------------------
NODE_LABELS: list[str] = [
    # Deposit
    "Product",
    "Category",
    "ParentCategory",
    "Feature",
    "InterestRate",
    "Term",
    "Channel",
    "EligibilityCondition",
    "Benefit",
    "TaxBenefit",
    "DepositProtection",
    "PreferentialRate",
    "ProductType",
    # Loan
    "LoanProduct",
    "LoanCategory",
    "LoanRate",
    "LoanTerm",
    "LoanEligibility",
    "RepaymentMethod",
    "LoanFee",
    "LoanPreferentialRate",
    "Collateral",
    "PenaltyRate",
    "TermExtension",
    "Overdraft",
]

# ---------------------------------------------------------------------------
# Relationship type definitions with source/target label constraints
# ---------------------------------------------------------------------------
RELATIONSHIP_TYPES: dict[str, dict[str, str]] = {
    "BELONGS_TO": {"source": "Product", "target": "Category"},
    "AVAILABLE_VIA": {"source": "Product", "target": "Channel"},
    "HAS_RATE": {"source": "Product", "target": "InterestRate"},
    "HAS_PREFERENTIAL_RATE": {"source": "Product", "target": "PreferentialRate"},
    "HAS_TERM": {"source": "Product", "target": "Term"},
    "REQUIRES": {"source": "Product", "target": "EligibilityCondition"},
    "HAS_TAX_BENEFIT": {"source": "Product", "target": "TaxBenefit"},
    "PROTECTED_BY": {"source": "Product", "target": "DepositProtection"},
    "HAS_FEATURE": {"source": "Product", "target": "Feature"},
    "HAS_BENEFIT": {"source": "Product", "target": "Benefit"},
    "HAS_TYPE": {"source": "Product", "target": "ProductType"},
    "COMPETES_WITH": {"source": "Product", "target": "Product"},
    "HAS_SUBCATEGORY": {"source": "ParentCategory", "target": "Category"},
}

# ---------------------------------------------------------------------------
# Visualization: color mapping (hex) for each node label
# ---------------------------------------------------------------------------
COLOR_MAP: dict[str, str] = {
    # Deposit
    "Product": "#4A90D9",            # blue
    "Category": "#F5A623",           # orange
    "ParentCategory": "#E65100",     # deep orange
    "Feature": "#7ED321",            # green
    "InterestRate": "#D0021B",       # red
    "Term": "#9B59B6",               # purple
    "Channel": "#1ABC9C",            # teal
    "EligibilityCondition": "#95A5A6",  # gray
    "Benefit": "#2ECC71",            # green
    "TaxBenefit": "#27AE60",         # emerald
    "DepositProtection": "#2980B9",  # dark blue
    "PreferentialRate": "#E74C3C",   # coral
    "ProductType": "#16A085",        # dark teal
    # Loan (mapped to same colors as deposit equivalents)
    "LoanProduct": "#4A90D9",
    "LoanCategory": "#F5A623",
    "LoanRate": "#D0021B",
    "LoanTerm": "#9B59B6",
    "LoanEligibility": "#95A5A6",
    "RepaymentMethod": "#E67E22",
    "LoanFee": "#8E44AD",
    "LoanPreferentialRate": "#E74C3C",
    "Collateral": "#7F8C8D",
    "PenaltyRate": "#C0392B",
    "TermExtension": "#2C3E50",
    "Overdraft": "#D35400",
}

# ---------------------------------------------------------------------------
# D3.js group index mapping (deterministic integer per label)
# ---------------------------------------------------------------------------
GROUP_INDEX: dict[str, int] = {label: idx for idx, label in enumerate(NODE_LABELS)}
