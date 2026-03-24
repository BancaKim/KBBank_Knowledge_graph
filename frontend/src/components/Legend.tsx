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
        background: "rgba(26,26,46,0.9)",
        border: "1px solid #333",
        borderRadius: 8,
        padding: "10px 14px",
        display: "flex",
        gap: 14,
        flexWrap: "wrap",
      }}
    >
      {LEGEND_ITEMS.map(({ type, label }) => (
        <div
          key={type}
          style={{ display: "flex", alignItems: "center", gap: 5 }}
        >
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: NODE_COLORS[type],
              display: "inline-block",
            }}
          />
          <span style={{ color: "#bbb", fontSize: 11 }}>{label}</span>
        </div>
      ))}
    </div>
  );
}
