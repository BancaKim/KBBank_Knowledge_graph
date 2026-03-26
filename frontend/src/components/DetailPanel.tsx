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
        background: "#1e1e32",
        borderLeft: "1px solid #333",
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
            background: NODE_COLORS[node.type] || "#555",
            color: "#fff",
            fontSize: 11,
            fontWeight: "bold",
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
            color: "#888",
            fontSize: 20,
            cursor: "pointer",
          }}
        >
          ✕
        </button>
      </div>

      <h2 style={{ color: "#fff", fontSize: 18, marginBottom: 16, lineHeight: 1.3 }}>
        {node.label}
      </h2>

      {node.type === "product" && (
        <>
          {d.product_type && (
            <InfoRow label="유형" value={String(d.product_type)} />
          )}
          {d.description && (
            <Section title="상품설명">
              <p style={{ color: "#bbb", fontSize: 13, lineHeight: 1.6 }}>
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
                background: "#4A90D9",
                color: "#fff",
                borderRadius: 8,
                textAlign: "center",
                textDecoration: "none",
                fontSize: 13,
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
      <h4 style={{ color: "#999", fontSize: 12, marginBottom: 6 }}>
        {title}
      </h4>
      {children}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginBottom: 10, display: "flex", gap: 8 }}>
      <span style={{ color: "#888", fontSize: 12, minWidth: 70, flexShrink: 0 }}>
        {label}
      </span>
      <span style={{ color: "#ddd", fontSize: 13 }}>{value}</span>
    </div>
  );
}

function RateBar({ min, max }: { min: number; max: number }) {
  const maxRate = 10;
  return (
    <div style={{ marginBottom: 6 }}>
      <div
        style={{
          height: 8,
          background: "#333",
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
            background: "linear-gradient(90deg, #4A90D9, #7ED321)",
            borderRadius: 4,
          }}
        />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
        <span style={{ color: "#4A90D9", fontSize: 14, fontWeight: "bold" }}>
          {min}%
        </span>
        <span style={{ color: "#7ED321", fontSize: 14, fontWeight: "bold" }}>
          {max}%
        </span>
      </div>
    </div>
  );
}
