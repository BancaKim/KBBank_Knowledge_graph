import { useState, useRef, useEffect, useCallback } from "react";
import Markdown from "react-markdown";
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
  elapsedSeconds?: number;
}

interface Props {
  onHighlightNodes: (nodeIds: string[]) => void;
}

const styles = `
  @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

  .chat-root {
    --gold: #FDB913;
    --gold-deep: #e6a510;
    --gold-light: rgba(253, 185, 19, 0.12);
    --gold-glow: rgba(253, 185, 19, 0.25);
    --surface: #FAFAF8;
    --surface-2: #F4F3EF;
    --surface-3: #ECEAE3;
    --border: rgba(0, 0, 0, 0.08);
    --border-strong: rgba(0, 0, 0, 0.14);
    --text-primary: #1A1917;
    --text-secondary: #6B6860;
    --text-muted: #9C9A95;
    --user-bubble: #1A1917;
    --assistant-bubble: #FFFFFF;
    --error: #DC2626;
    --success: #16A34A;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04);
    --radius: 16px;
    --radius-sm: 10px;
    --radius-xs: 8px;
    font-family: 'Pretendard', 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
    background: var(--surface);
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .chat-header {
    padding: 18px 20px 14px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .chat-header-title-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 3px;
  }

  .chat-header-logo {
    width: 28px;
    height: 28px;
    background: var(--gold);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    font-weight: 800;
    color: #1A1917;
    letter-spacing: -0.5px;
    flex-shrink: 0;
  }

  .chat-header-title {
    font-size: 15px;
    font-weight: 700;
    color: var(--text-primary);
    margin: 0;
    letter-spacing: -0.3px;
  }

  .chat-header-disclaimer {
    color: #ff7070;
    font-size: 11px;
    font-weight: 400;
    margin-left: 38px;
  }

  .chat-header-subtitle {
    color: var(--text-muted);
    font-size: 12px;
    margin: 0;
    margin-left: 38px;
    letter-spacing: 0.1px;
  }

  /* API key section */
  .api-key-section {
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    flex-shrink: 0;
  }

  .api-key-toggle {
    width: 100%;
    padding: 9px 20px;
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 12px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-family: inherit;
    transition: background 0.15s;
  }

  .api-key-toggle:hover {
    background: var(--surface-2);
  }

  .api-key-status {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .api-key-dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .api-key-body {
    padding: 0 20px 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .api-key-row {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .api-key-input-wrap {
    position: relative;
    flex: 1;
  }

  .api-key-input {
    width: 100%;
    padding: 8px 36px 8px 12px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--border-strong);
    background: var(--surface-2);
    color: var(--text-primary);
    font-size: 12px;
    outline: none;
    font-family: 'SF Mono', 'Fira Code', ui-monospace, monospace;
    box-sizing: border-box;
    transition: border-color 0.15s, box-shadow 0.15s;
  }

  .api-key-input::placeholder {
    color: var(--text-muted);
  }

  .api-key-input:focus {
    border-color: var(--gold);
    box-shadow: 0 0 0 3px var(--gold-glow);
    background: #fff;
  }

  .api-key-eye {
    position: absolute;
    right: 6px;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 13px;
    padding: 2px 4px;
    line-height: 1;
    transition: color 0.15s;
  }

  .api-key-eye:hover {
    color: var(--text-secondary);
  }

  .api-btn-save {
    padding: 8px 14px;
    border-radius: var(--radius-xs);
    border: none;
    background: var(--gold);
    color: #1A1917;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    font-family: inherit;
    transition: background 0.15s, transform 0.1s;
  }

  .api-btn-save:hover {
    background: var(--gold-deep);
    transform: translateY(-1px);
  }

  .api-btn-save:active {
    transform: translateY(0);
  }

  .api-btn-clear {
    padding: 8px 14px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--border-strong);
    background: transparent;
    color: var(--error);
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    white-space: nowrap;
    font-family: inherit;
    transition: background 0.15s, border-color 0.15s;
  }

  .api-btn-clear:hover {
    background: #FEF2F2;
    border-color: var(--error);
  }

  .api-key-hint {
    color: var(--text-muted);
    font-size: 11px;
    margin: 0;
    line-height: 1.5;
  }

  /* Messages area */
  .messages-area {
    flex: 1;
    overflow-y: auto;
    padding: 20px 16px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    scroll-behavior: smooth;
  }

  .messages-area::-webkit-scrollbar {
    width: 4px;
  }

  .messages-area::-webkit-scrollbar-track {
    background: transparent;
  }

  .messages-area::-webkit-scrollbar-thumb {
    background: var(--border-strong);
    border-radius: 2px;
  }

  .message-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
    animation: msgFadeIn 0.2s ease-out;
  }

  @keyframes msgFadeIn {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .message-row {
    display: flex;
  }

  .message-row--user {
    justify-content: flex-end;
  }

  .message-row--assistant {
    justify-content: flex-start;
    align-items: flex-end;
    gap: 8px;
  }

  .assistant-avatar {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--gold);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 800;
    color: #1A1917;
    flex-shrink: 0;
    margin-bottom: 2px;
  }

  .bubble {
    max-width: 82%;
    padding: 11px 15px;
    font-size: 14px;
    line-height: 1.65;
    word-break: break-word;
  }
  .bubble--assistant p { margin: 0.4em 0; }
  .bubble--assistant ul, .bubble--assistant ol { margin: 0.4em 0; padding-left: 1.4em; }
  .bubble--assistant li { margin: 0.2em 0; }
  .bubble--assistant strong { font-weight: 700; }
  .bubble--assistant h3 { font-size: 15px; font-weight: 700; margin: 0.8em 0 0.3em; }
  .bubble--assistant h4 { font-size: 14px; font-weight: 700; margin: 0.6em 0 0.2em; }
  .bubble--assistant table { border-collapse: collapse; width: 100%; margin: 0.5em 0; font-size: 13px; }
  .bubble--assistant th, .bubble--assistant td { border: 1px solid var(--border); padding: 6px 10px; text-align: left; }
  .bubble--assistant th { background: var(--bg-secondary); font-weight: 600; }
  .bubble--assistant code { background: var(--bg-secondary); padding: 1px 5px; border-radius: 4px; font-size: 13px; }
  .bubble--assistant hr { border: none; border-top: 1px solid var(--border); margin: 0.6em 0; }

  .bubble--user {
    background: var(--user-bubble);
    color: #FFFFFF;
    border-radius: 18px 18px 5px 18px;
    box-shadow: var(--shadow-sm);
  }

  .bubble--assistant {
    background: var(--assistant-bubble);
    color: var(--text-primary);
    border-radius: 5px 18px 18px 18px;
    box-shadow: var(--shadow-sm);
    border: 1px solid var(--border);
  }

  .message-meta {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 4px;
    padding: 0 4px;
  }

  .message-meta--user {
    text-align: right;
  }

  .message-meta--assistant {
    text-align: left;
    margin-left: 36px;
  }

  /* Referenced nodes */
  .ref-nodes {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-top: 8px;
    margin-left: 36px;
    align-items: center;
  }

  .ref-label {
    color: var(--text-muted);
    font-size: 11px;
    align-self: center;
  }

  .ref-chip {
    padding: 3px 10px;
    border-radius: 20px;
    border: 1px solid var(--border-strong);
    background: var(--surface-2);
    color: #2563EB;
    font-size: 11px;
    cursor: pointer;
    font-family: inherit;
    transition: background 0.15s, border-color 0.15s, transform 0.1s;
  }

  .ref-chip:hover {
    background: #EFF6FF;
    border-color: #93C5FD;
    transform: translateY(-1px);
  }

  .ref-more {
    color: var(--text-muted);
    font-size: 11px;
    align-self: center;
  }

  /* Typing indicator */
  .typing-row {
    display: flex;
    justify-content: flex-start;
    align-items: flex-end;
    gap: 8px;
  }

  .typing-bubble {
    padding: 13px 17px;
    background: var(--assistant-bubble);
    border-radius: 5px 18px 18px 18px;
    box-shadow: var(--shadow-sm);
    border: 1px solid var(--border);
    display: flex;
    gap: 5px;
    align-items: center;
  }

  .typing-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-muted);
    animation: typingBounce 1.2s ease-in-out infinite;
  }

  .typing-dot:nth-child(2) { animation-delay: 0.2s; }
  .typing-dot:nth-child(3) { animation-delay: 0.4s; }

  @keyframes typingBounce {
    0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
    30%            { transform: translateY(-5px); opacity: 1; }
  }

  /* Input area */
  .input-area {
    padding: 12px 16px 14px;
    background: var(--surface);
    border-top: 1px solid var(--border);
    flex-shrink: 0;
  }

  .input-wrap {
    display: flex;
    align-items: flex-end;
    gap: 8px;
    padding: 8px 8px 8px 14px;
    background: #fff;
    border: 1.5px solid var(--border-strong);
    border-radius: 14px;
    transition: border-color 0.15s, box-shadow 0.15s;
  }

  .input-wrap:focus-within {
    border-color: var(--gold);
    box-shadow: 0 0 0 3px var(--gold-glow);
  }

  .chat-textarea {
    flex: 1;
    padding: 2px 0;
    border: none;
    background: transparent;
    color: var(--text-primary);
    font-size: 14px;
    outline: none;
    resize: none;
    font-family: inherit;
    line-height: 1.5;
    min-height: 22px;
    max-height: 120px;
  }

  .chat-textarea::placeholder {
    color: var(--text-muted);
  }

  .send-btn {
    width: 34px;
    height: 34px;
    border-radius: 10px;
    border: none;
    background: var(--gold);
    color: #1A1917;
    font-size: 15px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: background 0.15s, transform 0.1s, opacity 0.15s;
    line-height: 1;
  }

  .send-btn:disabled {
    background: var(--surface-3);
    color: var(--text-muted);
    cursor: default;
  }

  .send-btn:not(:disabled):hover {
    background: var(--gold-deep);
    transform: scale(1.05);
  }

  .send-btn:not(:disabled):active {
    transform: scale(0.97);
  }

  .api-key-toggle-arrow {
    font-size: 9px;
    color: var(--text-muted);
    margin-left: 4px;
  }
`;

export default function ChatPanel({ onHighlightNodes }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: genId(),
      role: "assistant",
      content:
        "안녕하세요! 큽 금융상품 상담 챗봇입니다. 예금, 적금, 대출 등 금융상품에 대해 궁금한 점을 물어보세요.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

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
        elapsedSeconds: data.elapsed_seconds,
      };
      setMessages((prev) => [...prev, assistantMsg]);

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
    <>
      <style>{styles}</style>
      <div className="chat-root">
        {/* Header */}
        <div className="chat-header">
          <div className="chat-header-title-row">
            <div className="chat-header-logo">큽</div>
            <h2 className="chat-header-title">큽 금융상품 상담</h2>
          </div>
          <p className="chat-header-subtitle">GraphRAG 기반 지식그래프 챗봇</p>
          <p className="chat-header-disclaimer">개인 프로젝트 · 실제 은행과 무관</p>
        </div>

        {/* API Key Section */}
        <div className="api-key-section">
          <button
            onClick={() => setShowApiKeySection((v) => !v)}
            className="api-key-toggle"
          >
            <span style={{ fontWeight: 500 }}>API 키 설정</span>
            <span className="api-key-status">
              <span
                className="api-key-dot"
                style={{ background: hasKey ? "#16A34A" : "#DC2626" }}
              />
              <span style={{ color: hasKey ? "#16A34A" : "#DC2626", fontSize: 11, fontWeight: 500 }}>
                {hasKey ? "설정됨" : "미설정"}
              </span>
              <span className="api-key-toggle-arrow">
                {showApiKeySection ? "▲" : "▼"}
              </span>
            </span>
          </button>

          {showApiKeySection && (
            <div className="api-key-body">
              <div className="api-key-row">
                <div className="api-key-input-wrap">
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
                    className="api-key-input"
                  />
                  <button
                    onClick={() => setShowKeyValue((v) => !v)}
                    title={showKeyValue ? "숨기기" : "보기"}
                    className="api-key-eye"
                  >
                    {showKeyValue ? "◉" : "○"}
                  </button>
                </div>
                <button onClick={saveApiKey} className="api-btn-save">
                  저장
                </button>
                {hasKey && (
                  <button onClick={clearApiKey} className="api-btn-clear">
                    삭제
                  </button>
                )}
              </div>
              <p className="api-key-hint">
                API 키는 브라우저에만 저장되며 서버에 기록되지 않습니다.
              </p>
            </div>
          )}
        </div>

        {/* Messages */}
        <div
          role="log"
          aria-live="polite"
          className="messages-area"
        >
          {messages.map((msg) => (
            <div key={msg.id} className="message-group">
              <div className={`message-row message-row--${msg.role}`}>
                {msg.role === "assistant" && (
                  <div className="assistant-avatar">큽</div>
                )}
                <div className={`bubble bubble--${msg.role}`}>
                  <Markdown>{msg.content}</Markdown>
                </div>
              </div>

              {msg.role === "assistant" && msg.elapsedSeconds != null && (
                <div className="message-meta message-meta--assistant">
                  {msg.elapsedSeconds}초
                </div>
              )}

              {msg.referencedNodes && msg.referencedNodes.length > 0 && (
                <div className="ref-nodes">
                  <span className="ref-label">참조</span>
                  {msg.referencedNodes.slice(0, 8).map((node, j) => (
                    <button
                      key={j}
                      onClick={() => handleNodeClick([node.id])}
                      className="ref-chip"
                    >
                      {node.name || node.id}
                    </button>
                  ))}
                  {msg.referencedNodes.length > 8 && (
                    <span className="ref-more">
                      +{msg.referencedNodes.length - 8}
                    </span>
                  )}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="typing-row">
              <div className="assistant-avatar">큽</div>
              <div className="typing-bubble">
                <div className="typing-dot" />
                <div className="typing-dot" />
                <div className="typing-dot" />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="input-area">
          <div className="input-wrap">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="금융상품에 대해 질문하세요..."
              rows={1}
              className="chat-textarea"
            />
            <button
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              className="send-btn"
              aria-label="전송"
            >
              ↑
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
