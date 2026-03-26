import { useState, useCallback, useMemo, useRef } from "react";
import { useGraphData } from "./hooks/useGraphData";
import GraphCanvas from "./components/GraphCanvas";
import type { GraphCanvasRef } from "./components/GraphCanvas";
import SearchBar from "./components/SearchBar";
import CategoryFilter from "./components/CategoryFilter";
import DetailPanel from "./components/DetailPanel";
import Legend from "./components/Legend";
import Toolbar from "./components/Toolbar";
import ResizablePanels from "./components/ResizablePanels";
import ChatPanel from "./components/ChatPanel";
import type { GraphNode } from "./types/graph";

const ALL_NODE_TYPES = new Set([
  "product", "category", "parentcategory", "feature", "interestrate", "term",
  "channel", "eligibilitycondition", "repaymentmethod", "taxbenefit",
  "depositprotection", "preferentialrate", "fee", "producttype",
]);
const ALL_CATEGORIES = new Set([
  "정기예금", "적금", "입출금통장", "청약",
  "신용대출", "담보대출", "전월세대출", "자동차대출",
]);

export default function App() {
  const { data, loading, error } = useGraphData();
  const graphRef = useRef<GraphCanvasRef>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlightNodeId, setHighlightNodeId] = useState<string | null>(null);
  const [highlightNodeIds, setHighlightNodeIds] = useState<string[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(
    new Set(["정기예금", "적금", "입출금통장", "청약"])
  );
  const [selectedNodeTypes, setSelectedNodeTypes] = useState<Set<string>>(ALL_NODE_TYPES);

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode(node);
    setHighlightNodeId(node.id);
    setHighlightNodeIds([node.id]);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setSelectedNode(null);
    setHighlightNodeId(null);
    setHighlightNodeIds([]);
  }, []);

  const handleSearchSelect = useCallback(
    (nodeId: string) => {
      if (!data) return;
      const node = data.nodes.find((n) => n.id === nodeId);
      if (node) {
        setSelectedNode(node);
        setHighlightNodeId(node.id);
        setHighlightNodeIds([node.id]);
      }
    },
    [data]
  );

  const handleChatHighlight = useCallback((nodeIds: string[]) => {
    setHighlightNodeIds(nodeIds);
    setHighlightNodeId(nodeIds.length > 0 ? nodeIds[0] : null);
  }, []);

  const categoryCounts = useMemo(() => {
    if (!data) return {};
    const counts: Record<string, number> = {};
    data.nodes
      .filter((n) => n.type === "product")
      .forEach((n) => {
        const cat = String(n.data.category || "");
        counts[cat] = (counts[cat] || 0) + 1;
      });
    return counts;
  }, [data]);

  const handleZoomIn = () => graphRef.current?.zoomIn();
  const handleZoomOut = () => graphRef.current?.zoomOut();
  const handleReset = () => {
    graphRef.current?.resetZoom();
    setSelectedNode(null);
    setHighlightNodeId(null);
    setHighlightNodeIds([]);
    setSelectedCategories(ALL_CATEGORIES);
    setSelectedNodeTypes(ALL_NODE_TYPES);
  };

  if (loading) {
    return (
      <div style={centerStyle}>
        <div style={loadingLogoStyle}>큽</div>
        <div style={{ fontSize: 18, fontWeight: 700, color: "#1A1917", marginBottom: 8, letterSpacing: "-0.3px" }}>큽 금융상품 지식그래프</div>
        <div style={{ color: "#9C9A95", fontSize: 14 }}>데이터를 불러오는 중...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={centerStyle}>
        <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 8, color: "#DC2626", letterSpacing: "-0.3px" }}>연결 오류</div>
        <div style={{ color: "#6B6860", fontSize: 14 }}>{error}</div>
        <div style={{ color: "#9C9A95", fontSize: 13, marginTop: 12, background: "#F4F3EF", padding: "8px 14px", borderRadius: 8 }}>
          Backend가 실행 중인지 확인하세요: <code style={{ fontFamily: "ui-monospace, monospace", fontSize: 12 }}>uvicorn backend.main:app</code>
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div style={{ height: "100vh", width: "100vw", background: "#ECEAE3", fontFamily: "'Pretendard', 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif" }}>
      <ResizablePanels
        left={<ChatPanel onHighlightNodes={handleChatHighlight} />}
        right={
          <div style={{ display: "flex", height: "100%", width: "100%" }}>
            {/* Sidebar — warm light theme matching chatbot */}
            <div style={sidebarStyle}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                <div style={{
                  width: 28, height: 28, background: "#FDB913", borderRadius: 8,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 13, fontWeight: 800, color: "#1A1917", flexShrink: 0,
                  boxShadow: "0 2px 6px rgba(253,185,19,0.28)",
                }}>큽</div>
                <h1 style={{ color: "#1A1917", fontSize: 15, margin: 0, fontWeight: 700, letterSpacing: "-0.3px" }}>
                  금융상품 지식그래프
                </h1>
              </div>
              <div style={{ color: "#C0392B", fontSize: 11, marginBottom: 18, marginLeft: 38, opacity: 0.75 }}>
                개인 토이프로젝트 · 실제 은행과 무관
              </div>

              <SearchBar onSelectResult={handleSearchSelect} nodes={data.nodes} />

              <div style={{ marginTop: 20 }}>
                <CategoryFilter
                  selectedCategories={selectedCategories}
                  onCategoryChange={setSelectedCategories}
                  selectedNodeTypes={selectedNodeTypes}
                  onNodeTypeChange={setSelectedNodeTypes}
                  categoryCounts={categoryCounts}
                />
              </div>

              <div style={{ marginTop: 24, padding: "12px", background: "#ECEAE3", borderRadius: 8, border: "1px solid #DDD9CE" }}>
                <div style={{ color: "#9C9A95", fontSize: 11, marginBottom: 4, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px" }}>통계</div>
                <div style={{ color: "#3D3B37", fontSize: 13, fontWeight: 500 }}>
                  노드 {data.metadata.stats.total_nodes} · 엣지 {data.metadata.stats.total_edges}
                </div>
              </div>

              <div style={{
                marginTop: "auto",
                paddingTop: 20,
                borderTop: "1px solid #E2E0D8",
                marginBottom: 8,
              }}>
                <div style={{
                  padding: "10px 12px",
                  background: "rgba(192, 57, 43, 0.05)",
                  borderRadius: 8,
                  border: "1px solid rgba(192, 57, 43, 0.18)",
                }}>
                  <div style={{ color: "#C0392B", fontSize: 11, fontWeight: 700, marginBottom: 4, letterSpacing: "0.3px" }}>
                    DISCLAIMER
                  </div>
                  <div style={{ color: "#6B6860", fontSize: 11, lineHeight: 1.55 }}>
                    본 서비스는 실제 은행과 무관한 <strong style={{ color: "#3D3B37" }}>개인 토이프로젝트</strong>입니다.
                    제공되는 정보는 참고용이며, 실제 금융 상담은 반드시 해당 금융기관에 문의하시기 바랍니다.
                  </div>
                </div>
              </div>
            </div>

            {/* Graph Area */}
            <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
              <GraphCanvas
                ref={graphRef}
                data={data}
                onNodeClick={handleNodeClick}
                highlightNodeId={highlightNodeId}
                highlightNodeIds={highlightNodeIds}
                selectedCategories={selectedCategories}
                selectedNodeTypes={selectedNodeTypes}
              />
              <Legend />
              <Toolbar onZoomIn={handleZoomIn} onZoomOut={handleZoomOut} onReset={handleReset} />
            </div>

            {/* Detail Panel */}
            {selectedNode && <DetailPanel node={selectedNode} onClose={handleCloseDetail} />}
          </div>
        }
        defaultLeftWidth={40}
        minLeftWidth={20}
        maxLeftWidth={80}
      />
    </div>
  );
}

const loadingLogoStyle: React.CSSProperties = {
  width: 48,
  height: 48,
  background: "#FDB913",
  borderRadius: 14,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  fontSize: 18,
  fontWeight: 800,
  color: "#1A1917",
  marginBottom: 20,
  boxShadow: "0 4px 16px rgba(253, 185, 19, 0.35)",
};

const centerStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  height: "100vh",
  background: "#FAFAF8",
  color: "#1A1917",
  fontFamily: "'Pretendard', 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif",
};

const sidebarStyle: React.CSSProperties = {
  width: 250,
  height: "100%",
  background: "#F4F3EF",
  borderRight: "1px solid #E2E0D8",
  overflowY: "auto",
  padding: "16px",
  boxSizing: "border-box",
  flexShrink: 0,
  display: "flex",
  flexDirection: "column",
};
