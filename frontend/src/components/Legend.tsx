import { useState, useEffect } from "react";
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

const MOBILE_BREAKPOINT = 768;

export default function Legend() {
  const [isMobile, setIsMobile] = useState(
    typeof window !== "undefined" ? window.innerWidth < MOBILE_BREAKPOINT : false
  );
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  if (isMobile) {
    return (
      <div
        style={{
          position: "absolute",
          bottom: 16,
          left: 16,
          zIndex: 10,
        }}
      >
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
            {LEGEND_ITEMS.map(({ type, label }) => (
              <div key={type} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span
                  style={{
                    width: 8,
                    height: 8,
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
