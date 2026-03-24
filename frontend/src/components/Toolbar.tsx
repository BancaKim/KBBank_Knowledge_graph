interface Props {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
}

export default function Toolbar({ onZoomIn, onZoomOut, onReset }: Props) {
  return (
    <div
      style={{
        position: "absolute",
        top: 16,
        right: 16,
        display: "flex",
        flexDirection: "column",
        gap: 4,
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
            border: "1px solid #444",
            borderRadius: 6,
            background: "#2a2a3e",
            color: "#ccc",
            fontSize: 18,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
