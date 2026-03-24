import { useState, useCallback, useRef } from "react";

interface Props {
  left: React.ReactNode;
  right: React.ReactNode;
  defaultLeftWidth?: number; // percentage, default 40
  minLeftWidth?: number; // percentage, default 20
  maxLeftWidth?: number; // percentage, default 80
}

export default function ResizablePanels({
  left,
  right,
  defaultLeftWidth = 40,
  minLeftWidth = 20,
  maxLeftWidth = 80,
}: Props) {
  const [leftWidth, setLeftWidth] = useState(defaultLeftWidth);
  const dragging = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

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
