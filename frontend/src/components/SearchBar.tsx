import { useState, useCallback } from "react";
import { useSearch } from "../hooks/useSearch";
import type { GraphNode } from "../types/graph";

interface Props {
  onSelectResult: (nodeId: string) => void;
  nodes: GraphNode[];
}

export default function SearchBar({ onSelectResult, nodes }: Props) {
  const [query, setQuery] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const { results, searching, search, clear } = useSearch();

  const handleInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setQuery(value);
      if (value.trim()) {
        search(value);
        setShowDropdown(true);
      } else {
        clear();
        setShowDropdown(false);
      }
    },
    [search, clear]
  );

  const handleSelect = useCallback(
    (productId: string) => {
      // Find matching node
      const node = nodes.find(
        (n) => n.id === productId || n.id === `product_${productId}`
      );
      if (node) {
        onSelectResult(node.id);
      }
      setShowDropdown(false);
      setQuery("");
      clear();
    },
    [nodes, onSelectResult, clear]
  );

  return (
    <div style={{ position: "relative" }}>
      <input
        type="text"
        value={query}
        onChange={handleInput}
        onFocus={(e) => { e.currentTarget.style.borderColor = "#FDB913"; if (results.length > 0) setShowDropdown(true); }}
        onBlur={(e) => { e.currentTarget.style.borderColor = "#DDD9CE"; setShowDropdown(false); }}
        placeholder="상품 검색..."
        style={{
          width: "100%",
          padding: "10px 14px",
          borderRadius: "8px",
          border: "1.5px solid #DDD9CE",
          background: "#FFFFFF",
          color: "#1A1917",
          fontSize: "14px",
          outline: "none",
          boxSizing: "border-box",
          fontFamily: "inherit",
          transition: "border-color 0.15s",
        }}
      />
      {searching && (
        <span
          style={{
            position: "absolute",
            right: 12,
            top: "50%",
            transform: "translateY(-50%)",
            color: "#9C9A95",
            fontSize: "12px",
          }}
        >
          검색중...
        </span>
      )}
      {showDropdown && results.length > 0 && (
        <div
          role="listbox"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            background: "#FFFFFF",
            border: "1.5px solid #DDD9CE",
            borderTop: "none",
            borderRadius: "0 0 8px 8px",
            maxHeight: 300,
            overflowY: "auto",
            zIndex: 100,
            boxShadow: "0 8px 20px rgba(0,0,0,0.08)",
          }}
        >
          {results.map((p) => (
            <div
              key={p.id}
              role="option"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => handleSelect(p.id)}
              style={{
                padding: "10px 14px",
                cursor: "pointer",
                borderBottom: "1px solid #F0EEE8",
                color: "#1A1917",
              }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.background = "#FDF9EE")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.background = "transparent")
              }
            >
              <div style={{ fontWeight: "bold", fontSize: 13 }}>{p.name}</div>
              <div style={{ fontSize: 11, color: "#9C9A95", marginTop: 2 }}>
                {p.category}
                {p.rate_min != null && ` · ${p.rate_min}% ~ ${p.rate_max}%`}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
