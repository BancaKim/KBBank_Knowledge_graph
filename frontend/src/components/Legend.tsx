import { useState, useEffect, useMemo } from "react";
import { NODE_COLORS } from "../types/graph";
import type { GraphData } from "../types/graph";

/** Human-readable Korean labels for each node type */
const NODE_TYPE_LABELS: Record<string, string> = {
  product: "상품",
  category: "카테고리",
  parentcategory: "상위카테고리",
  feature: "특징",
  interestrate: "금리",
  term: "기간",
  channel: "채널",
  eligibilitycondition: "가입조건",
  repaymentmethod: "상환방법",
  taxbenefit: "세제혜택",
  depositprotection: "예금자보호",
  preferentialrate: "우대금리",
  fee: "수수료",
  producttype: "상품유형",
  penaltyrate: "연체금리",
  termextension: "기한연장",
  overdraft: "통장자동대출",
  collateral: "담보",
};

/** Display ordering for legend items (lower = first) */
const TYPE_ORDER: Record<string, number> = {
  product: 0,
  category: 1,
  parentcategory: 2,
  feature: 3,
  interestrate: 4,
  term: 5,
  channel: 6,
  eligibilitycondition: 7,
  preferentialrate: 8,
  repaymentmethod: 9,
  taxbenefit: 10,
  depositprotection: 11,
  fee: 12,
  producttype: 13,
  collateral: 14,
  penaltyrate: 15,
  termextension: 16,
  overdraft: 17,
};

interface Props {
  data: GraphData | null;
  selectedCategories: Set<string>;
  selectedNodeTypes: Set<string>;
}

const DEPOSIT_CATS = new Set(["정기예금", "적금", "입출금자유", "주택청약"]);
const LOAN_CATS = new Set([
  "신용대출", "담보대출", "전월세대출", "자동차대출",
  "집단중도금_이주비대출", "주택도시기금대출",
]);

const MOBILE_BREAKPOINT = 768;

export default function Legend({ data, selectedCategories, selectedNodeTypes }: Props) {
  const [isMobile, setIsMobile] = useState(
    typeof window !== "undefined" ? window.innerWidth < MOBILE_BREAKPOINT : false
  );
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const visibleTypes = useMemo(() => {
    if (!data) return [];

    // Determine which parent categories are active
    const hasDeposit = selectedCategories.size === 0 || [...selectedCategories].some((c) => DEPOSIT_CATS.has(c));
    const hasLoan = selectedCategories.size === 0 || [...selectedCategories].some((c) => LOAN_CATS.has(c));

    // Collect node types actually present in the data that match the active view
    const typesInData = new Set<string>();
    data.nodes.forEach((n) => {
      if (selectedNodeTypes.has(n.type)) typesInData.add(n.type);
    });

    // Filter to only types in the data, then sort by display order
    return [...typesInData]
      .filter((t) => {
        // Always show shared types if they exist in data
        const label = NODE_TYPE_LABELS[t];
        if (!label) return false;

        // Deposit-only types: hide if no deposit category selected
        if (["feature", "taxbenefit", "depositprotection", "producttype"].includes(t)) return hasDeposit;
        // Loan-only types: hide if no loan category selected
        if (["repaymentmethod", "fee", "collateral", "penaltyrate", "termextension", "overdraft"].includes(t)) return hasLoan;

        return true;
      })
      .sort((a, b) => (TYPE_ORDER[a] ?? 99) - (TYPE_ORDER[b] ?? 99));
  }, [data, selectedCategories, selectedNodeTypes]);

  if (visibleTypes.length === 0) return null;

  const items = visibleTypes.map((type) => (
    <div key={type} style={{ display: "flex", alignItems: "center", gap: 5 }}>
      <span
        style={{
          width: isMobile ? 8 : 9,
          height: isMobile ? 8 : 9,
          borderRadius: "50%",
          background: NODE_COLORS[type],
          display: "inline-block",
          flexShrink: 0,
        }}
      />
      <span style={{ color: "#4A4845", fontSize: 11, fontWeight: 500 }}>
        {NODE_TYPE_LABELS[type]}
      </span>
    </div>
  ));

  if (isMobile) {
    return (
      <div style={{ position: "absolute", bottom: 16, left: 16, zIndex: 10 }}>
        {expanded && (
          <div
            style={{
              background: "rgba(255,255,252,0.96)",
              border: "1px solid #E2E0D8",
              borderRadius: 10,
              padding: "10px 14px",
              display: "flex",
              gap: 10,
              flexWrap: "wrap",
              maxWidth: "calc(100vw - 80px)",
              backdropFilter: "blur(6px)",
              boxShadow: "0 2px 12px rgba(0,0,0,0.10)",
              marginBottom: 8,
              animation: "fadeInUp 0.18s ease-out",
            }}
          >
            <style>{`@keyframes fadeInUp { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }`}</style>
            {items}
          </div>
        )}
        <button
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? "범례 닫기" : "범례 보기"}
          style={{
            width: 36,
            height: 36,
            borderRadius: 8,
            background: "rgba(255,255,252,0.95)",
            border: "1px solid #E2E0D8",
            color: "#3D3B37",
            fontSize: 13,
            fontWeight: 700,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backdropFilter: "blur(6px)",
            boxShadow: "0 1px 6px rgba(0,0,0,0.10)",
          }}
        >
          {expanded ? "✕" : "●●"}
        </button>
      </div>
    );
  }

  return (
    <div
      style={{
        position: "absolute",
        bottom: 16,
        left: 16,
        background: "rgba(255,255,252,0.92)",
        border: "1px solid #E2E0D8",
        borderRadius: 10,
        padding: "10px 14px",
        display: "flex",
        gap: 12,
        flexWrap: "wrap",
        maxWidth: 520,
        backdropFilter: "blur(6px)",
        boxShadow: "0 2px 12px rgba(0,0,0,0.07)",
      }}
    >
      {items}
    </div>
  );
}
