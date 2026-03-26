import { NODE_COLORS } from "../types/graph";

const LEGEND_ITEMS = [
  { type: "product", label: "상품" },
  { type: "category", label: "카테고리" },
  { type: "parentcategory", label: "상위카테고리" },
  { type: "feature", label: "특징" },
  { type: "interestrate", label: "금리" },
  { type: "term", label: "기간" },
  { type: "channel", label: "채널" },
  { type: "eligibilitycondition", label: "가입조건" },
  { type: "repaymentmethod", label: "상환방법" },
  { type: "taxbenefit", label: "세제혜택" },
  { type: "depositprotection", label: "예금자보호" },
  { type: "preferentialrate", label: "우대금리" },
  { type: "fee", label: "수수료" },
  { type: "producttype", label: "상품유형" },
];

export default function Legend() {
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
      {LEGEND_ITEMS.map(({ type, label }) => (
        <div
          key={type}
          style={{ display: "flex", alignItems: "center", gap: 5 }}
        >
          <span
            style={{
              width: 9,
              height: 9,
              borderRadius: "50%",
              background: NODE_COLORS[type],
              display: "inline-block",
              flexShrink: 0,
            }}
          />
          <span style={{ color: "#4A4845", fontSize: 11, fontWeight: 500 }}>{label}</span>
        </div>
      ))}
    </div>
  );
}
