import { useState, useCallback, useRef, useEffect } from "react";

interface Props {
  left: React.ReactNode;
  right: React.ReactNode;
  defaultLeftWidth?: number; // percentage, default 40
  minLeftWidth?: number; // percentage, default 20
  maxLeftWidth?: number; // percentage, default 80
}

const MOBILE_BREAKPOINT = 768;

export default function ResizablePanels({
  left,
  right,
  defaultLeftWidth = 40,
  minLeftWidth = 20,
  maxLeftWidth = 80,
}: Props) {
  const [leftWidth, setLeftWidth] = useState(defaultLeftWidth);
  const [isMobile, setIsMobile] = useState(
    typeof window !== "undefined" ? window.innerWidth < MOBILE_BREAKPOINT : false
  );
  const [mobileView, setMobileView] = useState<"chat" | "graph">("chat");
  const dragging = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const handleMouseDown = useCallback(() => {
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setLeftWidth(Math.min(maxLeftWidth, Math.max(minLeftWidth, pct)));
    };

    const onUp = () => {
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [minLeftWidth, maxLeftWidth]);

  // Mobile: show only chat or graph with a toggle button
  if (isMobile) {
    return (
      <div style={{ width: "100%", height: "100%", position: "relative" }}>
        <div style={{ width: "100%", height: "100%" }}>
          {mobileView === "chat" ? left : right}
        </div>
        <button
          onClick={() => setMobileView(mobileView === "chat" ? "graph" : "chat")}
          style={{
            position: "fixed",
            top: 16,
            right: 16,
            zIndex: 1000,
            width: 48,
            height: 48,
            borderRadius: "50%",
            background: "#4A90D9",
            color: "#fff",
            border: "none",
            fontSize: 20,
            cursor: "pointer",
            boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
          title={mobileView === "chat" ? "그래프 보기" : "챗봇으로 돌아가기"}
        >
          {mobileView === "chat" ? "📊" : "💬"}
        </button>
      </div>
    );
  }

  // Desktop: resizable split panels
  return (
    <div
      ref={containerRef}
      style={{ display: "flex", width: "100%", height: "100%" }}
    >
      <div style={{ width: `${leftWidth}%`, height: "100%", overflow: "hidden" }}>
        {left}
      </div>
      <div
        onMouseDown={handleMouseDown}
        style={{
          width: 6,
          cursor: "col-resize",
          background: "#333",
          flexShrink: 0,
          transition: "background 0.2s",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "#4A90D9")}
        onMouseLeave={(e) => {
          if (!dragging.current) e.currentTarget.style.background = "#333";
        }}
      />
      <div style={{ flex: 1, height: "100%", overflow: "hidden" }}>
        {right}
      </div>
    </div>
  );
}
