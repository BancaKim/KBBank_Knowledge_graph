import { useState, useRef, useEffect, useCallback } from "react";
import { API_BASE } from "../config";

const genId = (): string =>
  typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;

const API_KEY_STORAGE_KEY = "openai_api_key";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  referencedNodes?: Array<{ id: string; type: string; name: string }>;
}

interface Props {
  onHighlightNodes: (nodeIds: string[]) => void;
}

export default function ChatPanel({ onHighlightNodes }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: genId(),
      role: "assistant",
      content:
        "안녕하세요! KB국민은행 금융상품 상담 챗봇입니다. 예금, 적금, 대출 등 금융상품에 대해 궁금한 점을 물어보세요.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  // API key state
  const [apiKey, setApiKey] = useState<string>(() => {
    try {
      return localStorage.getItem(API_KEY_STORAGE_KEY) || "";
    } catch {
      return "";
    }
  });
  const [apiKeyInput, setApiKeyInput] = useState(apiKey);
  const [showApiKeySection, setShowApiKeySection] = useState(false);
  const [showKeyValue, setShowKeyValue] = useState(false);

  // Persist API key to localStorage
  const saveApiKey = useCallback(() => {
    const trimmed = apiKeyInput.trim();
    setApiKey(trimmed);
    try {
      if (trimmed) {
        localStorage.setItem(API_KEY_STORAGE_KEY, trimmed);
      } else {
        localStorage.removeItem(API_KEY_STORAGE_KEY);
      }
    } catch {
      // localStorage may be unavailable
    }
  }, [apiKeyInput]);

  const clearApiKey = useCallback(() => {
    setApiKey("");
    setApiKeyInput("");
    try {
      localStorage.removeItem(API_KEY_STORAGE_KEY);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    if (!apiKey) {
      setMessages((prev) => [
        ...prev,
        { id: genId(), role: "user" as const, content: text },
        { id: genId(), role: "assistant" as const, content: "챗봇을 사용하려면 OpenAI API 키를 입력해주세요." },
      ]);
      setInput("");
      return;
    }

    const userMsg: ChatMessage = { id: genId(), role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const history = messagesRef.current
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({ role: m.role, content: m.content }));

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (apiKey) {
        headers["X-OpenAI-Key"] = apiKey;
      }

      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({ message: text, history }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => null);
        const detail = errorData?.detail || `API error: ${res.status}`;
        throw new Error(detail);
      }

      const data = await res.json();
      const assistantMsg: ChatMessage = {
        id: genId(),
        role: "assistant",
        content: data.answer,
        referencedNodes: data.referenced_nodes || [],
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // Highlight referenced nodes on the graph
      if (data.referenced_nodes?.length > 0) {
        onHighlightNodes(
          data.referenced_nodes.map((n: { id: string }) => n.id)
        );
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: genId(),
          role: "assistant" as const,
          content: `오류가 발생했습니다: ${err instanceof Error ? err.message : "알 수 없는 오류"}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, apiKey, onHighlightNodes]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleNodeClick = (nodeIds: string[]) => {
    onHighlightNodes(nodeIds);
  };

  const hasKey = apiKey.length > 0;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "#1a1a2e",
        fontFamily: "'Noto Sans KR', sans-serif",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "16px 20px",
          borderBottom: "1px solid #333",
          background: "#1e1e32",
        }}
      >
        <h2 style={{ color: "#fff", fontSize: 16, margin: 0 }}>
          KB 금융상품 상담
        </h2>
        <p style={{ color: "#888", fontSize: 12, margin: "4px 0 0" }}>
          GraphRAG 기반 지식그래프 챗봇
        </p>
      </div>

      {/* API Key Section */}
      <div
        style={{
          borderBottom: "1px solid #333",
          background: "#16162a",
        }}
      >
        <button
          onClick={() => setShowApiKeySection((v) => !v)}
          style={{
            width: "100%",
            padding: "8px 20px",
            background: "none",
            border: "none",
            color: "#ccc",
            fontSize: 12,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontFamily: "'Noto Sans KR', sans-serif",
          }}
        >
          <span>API 키 설정</span>
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span
              style={{
                display: "inline-block",
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: hasKey ? "#4ade80" : "#f87171",
              }}
            />
            <span style={{ color: hasKey ? "#4ade80" : "#f87171", fontSize: 11 }}>
              {hasKey ? "API 키 설정됨" : "API 키 미설정"}
            </span>
            <span style={{ fontSize: 10, color: "#666" }}>
              {showApiKeySection ? "▲" : "▼"}
            </span>
          </span>
        </button>

        {showApiKeySection && (
          <div style={{ padding: "0 20px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <div style={{ position: "relative", flex: 1 }}>
                <input
                  type={showKeyValue ? "text" : "password"}
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      saveApiKey();
                    }
                  }}
                  placeholder="sk-..."
                  style={{
                    width: "100%",
                    padding: "7px 36px 7px 10px",
                    borderRadius: 8,
                    border: "1px solid #444",
                    background: "#2a2a3e",
                    color: "#eee",
                    fontSize: 12,
                    outline: "none",
                    fontFamily: "monospace",
                    boxSizing: "border-box",
                  }}
                />
                <button
                  onClick={() => setShowKeyValue((v) => !v)}
                  title={showKeyValue ? "숨기기" : "보기"}
                  style={{
                    position: "absolute",
                    right: 4,
                    top: "50%",
                    transform: "translateY(-50%)",
                    background: "none",
                    border: "none",
                    color: "#888",
                    cursor: "pointer",
                    fontSize: 13,
                    padding: "2px 4px",
                    lineHeight: 1,
                  }}
                >
                  {showKeyValue ? "◉" : "○"}
                </button>
              </div>
              <button
                onClick={saveApiKey}
                style={{
                  padding: "7px 12px",
                  borderRadius: 8,
                  border: "none",
                  background: "#4A90D9",
                  color: "#fff",
                  fontSize: 12,
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                  fontFamily: "'Noto Sans KR', sans-serif",
                }}
              >
                저장
              </button>
              {hasKey && (
                <button
                  onClick={clearApiKey}
                  style={{
                    padding: "7px 12px",
                    borderRadius: 8,
                    border: "1px solid #555",
                    background: "transparent",
                    color: "#f87171",
                    fontSize: 12,
                    cursor: "pointer",
                    whiteSpace: "nowrap",
                    fontFamily: "'Noto Sans KR', sans-serif",
                  }}
                >
                  키 삭제
                </button>
              )}
            </div>
            <p style={{ color: "#666", fontSize: 11, margin: 0 }}>
              OpenAI API 키는 브라우저에만 저장되며 서버에 기록되지 않습니다.
            </p>
          </div>
        )}
      </div>

      {/* Messages */}
      <div
        role="log"
        aria-live="polite"
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "16px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {messages.map((msg) => (
          <div key={msg.id}>
            <div
              style={{
                display: "flex",
                justifyContent:
                  msg.role === "user" ? "flex-end" : "flex-start",
              }}
            >
              <div
                style={{
                  maxWidth: "85%",
                  padding: "12px 16px",
                  borderRadius:
                    msg.role === "user"
                      ? "16px 16px 4px 16px"
                      : "16px 16px 16px 4px",
                  background: msg.role === "user" ? "#4A90D9" : "#2a2a3e",
                  color: "#fff",
                  fontSize: 14,
                  lineHeight: 1.6,
                  whiteSpace: "pre-wrap",
                }}
              >
                {msg.content}
              </div>
            </div>

            {/* Referenced nodes chips */}
            {msg.referencedNodes && msg.referencedNodes.length > 0 && (
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 6,
                  marginTop: 8,
                  paddingLeft: 8,
                }}
              >
                <span
                  style={{
                    color: "#666",
                    fontSize: 11,
                    alignSelf: "center",
                  }}
                >
                  참조:
                </span>
                {msg.referencedNodes.slice(0, 8).map((node, j) => (
                  <button
                    key={j}
                    onClick={() => handleNodeClick([node.id])}
                    style={{
                      padding: "3px 10px",
                      borderRadius: 12,
                      border: "1px solid #444",
                      background: "#252540",
                      color: "#8ecae6",
                      fontSize: 11,
                      cursor: "pointer",
                    }}
                  >
                    {node.name || node.id}
                  </button>
                ))}
                {msg.referencedNodes.length > 8 && (
                  <span
                    style={{
                      color: "#666",
                      fontSize: 11,
                      alignSelf: "center",
                    }}
                  >
                    +{msg.referencedNodes.length - 8}
                  </span>
                )}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div style={{ display: "flex", justifyContent: "flex-start" }}>
            <div
              style={{
                padding: "12px 16px",
                borderRadius: "16px 16px 16px 4px",
                background: "#2a2a3e",
                color: "#888",
                fontSize: 14,
              }}
            >
              답변 생성 중...
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div
        style={{
          padding: "12px 16px",
          borderTop: "1px solid #333",
          background: "#1e1e32",
          display: "flex",
          gap: 8,
        }}
      >
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="금융상품에 대해 질문하세요..."
          rows={1}
          style={{
            flex: 1,
            padding: "10px 14px",
            borderRadius: 12,
            border: "1px solid #444",
            background: "#2a2a3e",
            color: "#eee",
            fontSize: 14,
            outline: "none",
            resize: "none",
            fontFamily: "'Noto Sans KR', sans-serif",
          }}
        />
        <button
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          style={{
            padding: "10px 20px",
            borderRadius: 12,
            border: "none",
            background: loading || !input.trim() ? "#333" : "#4A90D9",
            color: "#fff",
            fontSize: 14,
            cursor: loading || !input.trim() ? "default" : "pointer",
            fontFamily: "'Noto Sans KR', sans-serif",
          }}
        >
          전송
        </button>
      </div>
    </div>
  );
}
