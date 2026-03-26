import type { GraphNode } from "../types/graph";
import { NODE_COLORS } from "../types/graph";

interface Props {
  node: GraphNode | null;
  onClose: () => void;
}

export default function DetailPanel({ node, onClose }: Props) {
  if (!node) return null;

  const d = node.data;

  return (
    <div
      style={{
        width: 350,
        height: "100%",
        background: "#FAFAF8",
        borderLeft: "1px solid #E2E0D8",
        overflowY: "auto",
        padding: "20px",
        boxSizing: "border-box",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <span
          style={{
            display: "inline-block",
            padding: "3px 10px",
            borderRadius: 12,
            background: NODE_COLORS[node.type] || "#999",
            color: "#fff",
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.3px",
          }}
        >
          {node.type.toUpperCase()}
        </span>
        <button
          onClick={onClose}
          aria-label="닫기"
          style={{
            background: "none",
            border: "none",
            color: "#9C9A95",
            fontSize: 18,
            cursor: "pointer",
            lineHeight: 1,
            padding: "2px 4px",
            borderRadius: 4,
            transition: "color 0.15s",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "#1A1917")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "#9C9A95")}
        >
          ✕
        </button>
      </div>

      <h2 style={{ color: "#1A1917", fontSize: 17, marginBottom: 16, lineHeight: 1.4, letterSpacing: "-0.3px", fontWeight: 700 }}>
        {node.label}
      </h2>

      {node.type === "product" && (
        <>
          {d.product_type && (
            <InfoRow label="유형" value={String(d.product_type)} />
          )}
          {d.description && (
            <Section title="상품설명">
              <p style={{ color: "#4A4845", fontSize: 13, lineHeight: 1.6, margin: 0 }}>
                {String(d.description).slice(0, 300)}
                {String(d.description).length > 300 ? "..." : ""}
              </p>
            </Section>
          )}
          {d.amount_max_raw && (
            <InfoRow label="최대한도" value={String(d.amount_max_raw)} />
          )}
          {d.eligibility_summary && (
            <InfoRow label="가입대상" value={String(d.eligibility_summary).slice(0, 150)} />
          )}
          {d.page_url && (
            <a
              href={String(d.page_url)}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: "block",
                marginTop: 20,
                padding: "10px",
                background: "#FDB913",
                color: "#1A1917",
                borderRadius: 8,
                textAlign: "center",
                textDecoration: "none",
                fontSize: 13,
                fontWeight: 700,
                letterSpacing: "-0.2px",
              }}
            >
              은행에서 보기
            </a>
          )}
        </>
      )}

      {node.type === "category" && (
        <>
          {d.name_en && <InfoRow label="English" value={String(d.name_en)} />}
        </>
      )}

      {node.type === "interestrate" && (
        <>
          {d.min_rate != null && d.max_rate != null && (
            <RateBar min={Number(d.min_rate)} max={Number(d.max_rate)} />
          )}
          {d.min_rate != null && (
            <InfoRow
              label="금리 범위"
              value={`${d.min_rate}% ~ ${d.max_rate}%`}
            />
          )}
          {d.rate_type && (
            <InfoRow label="금리 유형" value={String(d.rate_type)} />
          )}
        </>
      )}

      {node.type === "eligibilitycondition" && (
        <>
          {d.description && <InfoRow label="조건" value={String(d.description).slice(0, 200)} />}
          {d.target_audience && <InfoRow label="대상" value={String(d.target_audience)} />}
          {d.min_age != null && <InfoRow label="최소연령" value={`만 ${d.min_age}세`} />}
        </>
      )}

      {node.type === "taxbenefit" && (
        <>
          {d.type && <InfoRow label="유형" value={String(d.type)} />}
          {d.description && <InfoRow label="설명" value={String(d.description).slice(0, 200)} />}
        </>
      )}

      {node.type === "depositprotection" && (
        <>
          {d.description && <InfoRow label="설명" value={String(d.description).slice(0, 200)} />}
          {d.max_amount_won != null && <InfoRow label="보호한도" value={`${Number(d.max_amount_won).toLocaleString()}원`} />}
        </>
      )}

      {node.type === "preferentialrate" && (
        <>
          {d.condition_description && <InfoRow label="조건" value={String(d.condition_description)} />}
          {d.rate_value_pp != null && <InfoRow label="우대금리" value={`연 ${d.rate_value_pp}%p`} />}
        </>
      )}

      {node.type === "fee" && (
        <>
          {d.fee_type && <InfoRow label="유형" value={String(d.fee_type)} />}
          {d.description && <InfoRow label="설명" value={String(d.description).slice(0, 200)} />}
        </>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <h4 style={{ color: "#9C9A95", fontSize: 11, marginBottom: 6, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.4px" }}>
        {title}
      </h4>
      {children}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginBottom: 10, display: "flex", gap: 8, padding: "8px 10px", background: "#F4F3EF", borderRadius: 6 }}>
      <span style={{ color: "#9C9A95", fontSize: 11, minWidth: 64, flexShrink: 0, paddingTop: 1, fontWeight: 500 }}>
        {label}
      </span>
      <span style={{ color: "#1A1917", fontSize: 13, lineHeight: 1.45 }}>{value}</span>
    </div>
  );
}

function RateBar({ min, max }: { min: number; max: number }) {
  const maxRate = 10;
  return (
    <div style={{ marginBottom: 12 }}>
      <div
        style={{
          height: 7,
          background: "#E8E5DD",
          borderRadius: 4,
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: `${(min / maxRate) * 100}%`,
            width: `${((max - min) / maxRate) * 100}%`,
            height: "100%",
            background: "linear-gradient(90deg, #FDB913, #F5A623)",
            borderRadius: 4,
          }}
        />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
        <span style={{ color: "#6B6860", fontSize: 13, fontWeight: 600 }}>
          {min}%
        </span>
        <span style={{ color: "#1A1917", fontSize: 13, fontWeight: 700 }}>
          {max}%
        </span>
      </div>
    </div>
  );
}
