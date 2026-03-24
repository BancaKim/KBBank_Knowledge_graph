# frontend/src/components/

React UI 컴포넌트.

## 파일

| 파일 | 역할 |
|------|------|
| `GraphCanvas.tsx` | D3.js 포스 그래프 - 노드/엣지 렌더링, 줌/드래그, 호버 하이라이트, 화살표 엣지, ResizeObserver |
| `ChatPanel.tsx` | 챗봇 UI - 메시지 기록, 참조 노드 칩, 입력, GraphRAG API 호출 |
| `ResizablePanels.tsx` | 리사이저블 분할 레이아웃 - 좌(채팅)/우(그래프), document 레벨 드래그 |
| `DetailPanel.tsx` | 노드 상세 사이드바 - 상품/금리/자격/세제혜택/수수료 등 타입별 렌더링, RateBar |
| `CategoryFilter.tsx` | 카테고리 필터 - 예금/대출 계층 그룹, 체크박스, indeterminate 상태 |
| `SearchBar.tsx` | 검색 입력 - 디바운스 API 검색, 드롭다운 결과, 노드 선택 |
| `Legend.tsx` | 범례 - 14개 노드 타입 색상 표시 |
| `Toolbar.tsx` | 줌 컨트롤 - 확대/축소/초기화 (ARIA 라벨) |
