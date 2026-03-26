interface Props {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
  isMobile?: boolean;
}

export default function Toolbar({ onZoomIn, onZoomOut, onReset, isMobile = false }: Props) {
  return (
    <div
      style={{
        position: "absolute",
        // On mobile: move to bottom-right to avoid colliding with the toggle button at top-right
        ...(isMobile
          ? { bottom: 16, right: 16 }
          : { top: 16, right: 16 }),
        display: "flex",
        flexDirection: "column",
        gap: 4,
        zIndex: 10,
      }}
    >
      {[
        { label: "+", action: onZoomIn, ariaLabel: "확대" },
        { label: "−", action: onZoomOut, ariaLabel: "축소" },
        { label: "⟲", action: onReset, ariaLabel: "초기화" },
      ].map(({ label, action, ariaLabel }) => (
        <button
          key={label}
          onClick={action}
          aria-label={ariaLabel}
          style={{
            width: 36,
            height: 36,
            border: "1px solid #E2E0D8",
            borderRadius: 8,
            background: "rgba(255,255,252,0.92)",
            color: "#3D3B37",
            fontSize: 18,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            backdropFilter: "blur(6px)",
            boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
            transition: "border-color 0.15s, background 0.15s",
            fontFamily: "inherit",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "#FDB913";
            e.currentTarget.style.background = "#FDF9EE";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "#E2E0D8";
            e.currentTarget.style.background = "rgba(255,255,252,0.92)";
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
