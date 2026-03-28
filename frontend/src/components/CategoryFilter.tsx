import { NODE_COLORS } from "../types/graph";

const CATEGORY_GROUPS = [
  {
    parent: "예금",
    children: ["정기예금", "적금", "입출금자유", "주택청약"],
  },
  {
    parent: "대출",
    children: ["신용대출", "담보대출", "전월세대출", "자동차대출", "집단중도금/이주비대출", "주택도시기금대출"],
  },
];

const ALL_SUBCATEGORIES = CATEGORY_GROUPS.flatMap((g) => g.children);

const NODE_TYPES = [
  { key: "product", label: "상품" },
  { key: "category", label: "카테고리" },
  { key: "parentcategory", label: "상위카테고리" },
  { key: "feature", label: "특징" },
  { key: "interestrate", label: "금리" },
  { key: "term", label: "기간" },
  { key: "channel", label: "채널" },
  { key: "eligibilitycondition", label: "가입조건" },
  { key: "repaymentmethod", label: "상환방법" },
  { key: "taxbenefit", label: "세제혜택" },
  { key: "depositprotection", label: "예금자보호" },
  { key: "preferentialrate", label: "우대금리" },
  { key: "fee", label: "수수료" },
  { key: "producttype", label: "상품유형" },
  { key: "penaltyrate", label: "연체금리" },
  { key: "termextension", label: "기한연장" },
  { key: "overdraft", label: "통장자동대출" },
  { key: "collateral", label: "담보" },
];

interface Props {
  selectedCategories: Set<string>;
  onCategoryChange: (categories: Set<string>) => void;
  selectedNodeTypes: Set<string>;
  onNodeTypeChange: (types: Set<string>) => void;
  categoryCounts?: Record<string, number>;
}

export default function CategoryFilter({
  selectedCategories,
  onCategoryChange,
  selectedNodeTypes,
  onNodeTypeChange,
  categoryCounts = {},
}: Props) {
  const toggleCategory = (cat: string) => {
    const next = new Set(selectedCategories);
    if (next.has(cat)) next.delete(cat);
    else next.add(cat);
    onCategoryChange(next);
  };

  const toggleGroup = (children: string[]) => {
    const next = new Set(selectedCategories);
    const allSelected = children.every((c) => next.has(c));
    if (allSelected) {
      children.forEach((c) => next.delete(c));
    } else {
      children.forEach((c) => next.add(c));
    }
    onCategoryChange(next);
  };

  const isGroupChecked = (children: string[]) =>
    children.every((c) => selectedCategories.has(c));

  const isGroupIndeterminate = (children: string[]) =>
    children.some((c) => selectedCategories.has(c)) && !isGroupChecked(children);

  const groupCount = (children: string[]) =>
    children.reduce((sum, c) => sum + (categoryCounts[c] || 0), 0);

  const toggleNodeType = (type: string) => {
    const next = new Set(selectedNodeTypes);
    if (next.has(type)) next.delete(type);
    else next.add(type);
    onNodeTypeChange(next);
  };

  const selectAll = () => onCategoryChange(new Set(ALL_SUBCATEGORIES));
  const clearAll = () => onCategoryChange(new Set());

  return (
    <div style={{ padding: "0 4px" }}>
      <h3 style={{ color: "#3D3B37", fontSize: 13, marginBottom: 8, marginTop: 0, fontWeight: 600, letterSpacing: "-0.2px" }}>
        카테고리
      </h3>
      <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
        <button onClick={selectAll} style={btnStyle}>
          전체 선택
        </button>
        <button onClick={clearAll} style={btnStyle}>
          초기화
        </button>
      </div>

      {CATEGORY_GROUPS.map(({ parent, children }) => (
        <div key={parent} style={{ marginBottom: 8 }}>
          {/* Parent group header */}
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 0",
              cursor: "pointer",
              color: "#1A1917",
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            <input
              type="checkbox"
              checked={isGroupChecked(children)}
              ref={(el) => {
                if (el) el.indeterminate = isGroupIndeterminate(children);
              }}
              onChange={() => toggleGroup(children)}
              style={{ accentColor: "#FDB913" }}
            />
            <span
              style={{
                width: 12,
                height: 12,
                borderRadius: "50%",
                background: NODE_COLORS.category,
                display: "inline-block",
                flexShrink: 0,
              }}
            />
            <span>{parent}</span>
            <span
              style={{
                marginLeft: "auto",
                background: "#E8E5DD",
                borderRadius: 10,
                padding: "1px 8px",
                fontSize: 11,
                color: "#6B6860",
                fontWeight: "normal",
              }}
            >
              {groupCount(children)}
            </span>
          </label>

          {/* Child subcategories */}
          <div style={{ paddingLeft: 24 }}>
            {children.map((cat) => (
              <label
                key={cat}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "4px 0",
                  cursor: "pointer",
                  color: "#4A4845",
                  fontSize: 12,
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedCategories.has(cat)}
                  onChange={() => toggleCategory(cat)}
                  style={{ accentColor: "#FDB913" }}
                />
                <span>{cat}</span>
                {categoryCounts[cat] != null && (
                  <span
                    style={{
                      marginLeft: "auto",
                      background: "#ECEAE3",
                      borderRadius: 10,
                      padding: "1px 8px",
                      fontSize: 11,
                      color: "#9C9A95",
                    }}
                  >
                    {categoryCounts[cat]}
                  </span>
                )}
              </label>
            ))}
          </div>
        </div>
      ))}

      <h3 style={{ color: "#3D3B37", fontSize: 13, marginBottom: 8, marginTop: 20, fontWeight: 600, letterSpacing: "-0.2px" }}>
        노드 타입
      </h3>
      {NODE_TYPES.map(({ key, label }) => (
        <label
          key={key}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "4px 0",
            cursor: "pointer",
            color: "#4A4845",
            fontSize: 12,
          }}
        >
          <input
            type="checkbox"
            checked={selectedNodeTypes.has(key)}
            onChange={() => toggleNodeType(key)}
            style={{ accentColor: NODE_COLORS[key] || "#FDB913" }}
          />
          <span
            style={{
              width: 9,
              height: 9,
              borderRadius: "50%",
              background: NODE_COLORS[key] || "#999",
              display: "inline-block",
              flexShrink: 0,
            }}
          />
          <span>{label}</span>
        </label>
      ))}
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  padding: "4px 10px",
  fontSize: 11,
  border: "1px solid #DDD9CE",
  borderRadius: 6,
  background: "#FFFFFF",
  color: "#4A4845",
  cursor: "pointer",
  fontFamily: "inherit",
  transition: "border-color 0.15s, background 0.15s",
};
