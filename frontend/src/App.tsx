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
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(ALL_CATEGORIES);
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
        <div style={{ fontSize: 24, marginBottom: 8 }}>KB 금융상품 지식그래프</div>
        <div style={{ color: "#888" }}>데이터를 불러오는 중...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={centerStyle}>
        <div style={{ fontSize: 24, marginBottom: 8, color: "#e74c3c" }}>연결 오류</div>
        <div style={{ color: "#888" }}>{error}</div>
        <div style={{ color: "#666", fontSize: 13, marginTop: 12 }}>
          Backend가 실행 중인지 확인하세요: <code>uvicorn backend.main:app</code>
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div style={{ height: "100vh", width: "100vw", background: "#16162a", fontFamily: "'Noto Sans KR', sans-serif" }}>
      <ResizablePanels
        left={<ChatPanel onHighlightNodes={handleChatHighlight} />}
        right={
          <div style={{ display: "flex", height: "100%", width: "100%" }}>
            {/* Sidebar */}
            <div style={sidebarStyle}>
              <h1 style={{ color: "#fff", fontSize: 16, marginTop: 0, marginBottom: 16 }}>
                KB 금융상품
                <br />
                <span style={{ color: "#4A90D9", fontSize: 13, fontWeight: "normal" }}>지식그래프</span>
              </h1>

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

              <div style={{ marginTop: 24, padding: "12px", background: "#252540", borderRadius: 8 }}>
                <div style={{ color: "#888", fontSize: 11, marginBottom: 4 }}>통계</div>
                <div style={{ color: "#ddd", fontSize: 13 }}>
                  노드: {data.metadata.stats.total_nodes} · 엣지: {data.metadata.stats.total_edges}
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

const centerStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  height: "100vh",
  background: "#16162a",
  color: "#fff",
  fontFamily: "'Noto Sans KR', sans-serif",
};

const sidebarStyle: React.CSSProperties = {
  width: 250,
  height: "100%",
  background: "#1e1e32",
  borderRight: "1px solid #333",
  overflowY: "auto",
  padding: "16px",
  boxSizing: "border-box",
  flexShrink: 0,
};
