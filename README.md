# KB국민은행 금융상품 GraphRAG 챗봇

**KB국민은행 금융상품 지식그래프 & GraphRAG 기반 대화형 챗봇**

이 프로젝트는 KB국민은행의 금융상품 데이터를 수집하여 Neo4j 지식그래프로 구축하고, LangGraph 기반 에이전트와 GraphRAG 기술을 활용한 지능형 금융상품 상담 챗봇입니다. 1,233개 노드와 3,757개 관계로 이루어진 구조화된 지식그래프와 D3.js 기반 인터랙티브 시각화를 제공합니다.

---![Uploading 스크린샷 2026-03-24 오후 1.05.56.png…]()


## 주요 기능

- **지식그래프 기반 검색**: 14개 엔티티 타입과 15개 관계 타입으로 구성된 Neo4j 그래프에서 정확한 금융상품 정보 검색
- **GraphRAG 챗봇**: LangGraph를 활용한 7가지 도구/스킬로 금융상품 상담 제공
  - 상품 검색 (GraphRAG)
  - 상품 상세 조회
  - 카테고리별 상품 목록
  - 상품 비교
  - 대출 상환액 계산 (원리금균등/원금균등/만기일시)
  - 예금 만기액 계산
  - 가입 자격 확인
- **D3.js 인터랙티브 시각화**: 1,233개 노드와 3,757개 엣지의 지식그래프를 실시간으로 조작 및 탐색
- **웹 스크래핑**: Playwright를 활용한 KB국민은행 금융상품 자동 수집

---

## 기술 스택

| 계층 | 기술 | 버전 |
|------|------|------|
| **프론트엔드** | React 19, TypeScript, D3.js 7, Vite | React 19.2.4 |
| **백엔드** | FastAPI, LangChain, LangGraph, Neo4j Driver | Python 3.11+ |
| **데이터베이스** | Neo4j Community | 5.x |
| **LLM** | OpenAI GPT-4o-mini | - |
| **스크래퍼** | Playwright (헤드리스 브라우저) | 1.40+ |

---

## 아키텍처

```
┌─────────────────────────────────────────────────┐
│                  Frontend (React)                 │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │  ChatPanel    │  │  Knowledge Graph (D3.js) │ │
│  │  (GraphRAG)   │  │  1233 nodes, 3757 edges    │ │
│  │  7가지 스킬   │  │  인터랙티브 시각화        │ │
│  └──────────────┘  └──────────────────────────┘ │
└──────────────┬──────────────────────────────────┘
               │ REST API (JSON)
┌──────────────▼──────────────────────────────────┐
│              Backend (FastAPI)                    │
│  /api/chat    - LangGraph 에이전트 + 7 도구     │
│  /api/graph   - 그래프 데이터 (캐시됨)         │
│  /api/products - 상품 CRUD 작업                 │
│  /api/search  - 풀텍스트 검색 (CJK 지원)       │
│  /health      - 상태 확인                        │
└──────────────┬──────────────────────────────────┘
               │ Bolt Protocol
┌──────────────▼──────────────────────────────────┐
│           Neo4j Knowledge Graph                  │
│  14 엔티티 타입 | 15 관계 타입                   │
│  1233 노드 | 3757 관계                             │
│  CJK 풀텍스트 인덱스 지원                        │
└─────────────────────────────────────────────────┘
```

### 데이터 흐름

```
웹 스크래핑 (Playwright)
    ↓
마크다운 파일 생성 (163개)
    ↓
엔티티 추출 및 파싱
    ↓
Neo4j 그래프 구축
    ↓
D3.js JSON 내보내기
    ↓
REST API 제공
    ↓
프론트엔드 시각화 & 챗봇
```

---

## 지식그래프 스키마

### 엔티티 타입 (14개)

| 엔티티 | 개수 | 설명 |
|--------|------|------|
| **Product** | 161 | 금융상품 (대출/예금/적금) |
| **PreferentialRate** | 83 | 우대금리 조건 |
| **Feature** | 69 | 상품 특징 및 장점 |
| **EligibilityCondition** | 161 | 가입 자격 조건 |
| **Term** | 47 | 가입/대출 기간 |
| **Fee** | 40 | 수수료 |
| **TaxBenefit** | 26 | 세제혜택 |
| **DepositProtection** | 25 | 예금자보호 |
| **InterestRate** | 16 | 기본금리 |
| **ProductType** | 11 | 상품유형 |
| **Category** | 8 | 하위 카테고리 |
| **RepaymentMethod** | 8 | 상환방법 |
| **Channel** | 3 | 가입채널 (온라인/영업점/자동차) |
| **ParentCategory** | 2 | 상위 카테고리 (예금/대출) |

### 관계 타입 (15개)

```
BELONGS_TO          - 상품이 속한 카테고리
HAS_SUBCATEGORY     - 부모 카테고리의 자식 카테고리
AVAILABLE_VIA       - 가입 채널
REPAID_VIA          - 상환 방식
HAS_RATE            - 기본금리
HAS_PREFERENTIAL_RATE - 우대금리
HAS_TERM            - 가입 기간
REQUIRES            - 필수 조건
HAS_TAX_BENEFIT     - 세제혜택
PROTECTED_BY        - 예금자보호 적용
HAS_FEATURE         - 상품의 특징
HAS_FEE             - 수수료
HAS_TYPE            - 상품 유형
COMPETES_WITH       - 경쟁 상품
```

### 카테고리 계층

```
예금 (Deposits)
├── 정기예금 (4개)
├── 적금 (10개)
├── 입출금통장 (10개)
└── 청약 (2개)

대출 (Loans)
├── 신용대출 (10개)
├──── 담보대출 (10개)
├── 전월세대출 (10개)
└── 자동차대출 (10개)
```

---

## LangGraph 에이전트 & 7가지 스킬

### 워크플로우

```
사용자 쿼리
    ↓
[지식그래프 컨텍스트 검색]
    ↓
[LLM 호출 + 도구 선택]
    ↓
[도구 실행 (7가지 스킬 중 선택)]
    ↓
[응답 생성]
    ↓
사용자에게 반환
```

### 7가지 도구/스킬

#### 1. `search_products` - GraphRAG 상품 검색
- 사용자 쿼리로 지식그래프에서 관련 상품 검색
- 풀텍스트 검색 활용
- 예: "신용대출 추천해줘" → 신용대출 상품 목록

#### 2. `get_product_detail` - 상품 상세 조회
- 특정 상품의 모든 상세 정보 조회
- 금리, 한도, 조건, 수수료, 특징 등
- 예: "토스뱅크 신용대출의 조건이 뭐야?" → 상세 정보 반환

#### 3. `list_products_by_category` - 카테고리별 상품 목록
- 카테고리에 속한 모든 상품 나열
- 예: "예금 상품 다 보여줘" → 예금 전체 상품

#### 4. `compare_products` - 상품 비교
- 두 상품의 주요 정보 비교
- 금리, 한도, 수수료 등 한눈에 비교
- 예: "A상품과 B상품 비교해줄래?" → 비교표

#### 5. `calculate_loan_payment` - 대출 상환액 계산
- 대출금액, 금리, 기간에 따른 월 상환액 계산
- 3가지 상환방식 지원:
  - 원리금균등분할: 매달 같은 금액
  - 원금균등분할: 원금은 일정, 이자는 감소
  - 만기일시상환: 만기에 전액 상환
- 예: "3000만원을 5년에 걸쳐 빌리면 월 상환액이?"

#### 6. `calculate_deposit_maturity` - 예금 만기액 계산
- 예금액, 금리, 기간에 따른 만기 수령액 계산
- 단리/복리 지원
- 예: "100만원을 2년간 예금하면 얼마?"

#### 7. `check_eligibility` - 가입 자격 확인
- 상품 가입 자격 조건 확인
- 예: "직장인인데 이 대출 가입 가능해?" → 자격 확인

---

## 프로젝트 구조

```
banking_bot/
├── backend/                          # FastAPI 백엔드
│   ├── main.py                       # FastAPI 애플리케이션 진입점
│   ├── dependencies.py               # 의존성 주입
│   ├── chatbot.py                    # 챗봇 래퍼 (에이전트로 연결)
│   │
│   ├── agent/                        # LangGraph 에이전트
│   │   ├── graph.py                  # LangGraph StateGraph 워크플로우
│   │   ├── state.py                  # 에이전트 상태 정의
│   │   │
│   │   └── skills/                   # 7가지 도구/스킬
│   │       ├── graph_rag.py          # search_products - GraphRAG 검색
│   │       ├── product_search.py     # get_product_detail, list_products_by_category
│   │       ├── product_compare.py    # compare_products - 상품 비교
│   │       ├── rate_calculator.py    # calculate_loan_payment, calculate_deposit_maturity
│   │       └── eligibility_check.py  # check_eligibility - 자격 확인
│   │
│   └── routers/                      # REST API 엔드포인트
│       ├── graph.py                  # GET /api/graph, /api/graph/stats
│       ├── products.py               # GET /api/products, /api/products/{id}, /api/products/{id}/compare/{other_id}
│       ├── search.py                 # GET /api/search, /api/categories
│       └── chat.py                   # POST /api/chat
│
├── knowledge_graph/                  # 지식그래프 구축 및 관리
│   ├── models.py                     # 14개 Pydantic 엔티티 모델
│   ├── parser.py                     # 마크다운 파일에서 엔티티 추출
│   ├── builder.py                    # Neo4j 그래프 구축 및 인덱싱
│   ├── exporter.py                   # D3.js JSON 내보내기
│   ├── ontology.py                   # 스키마 정의 (엔티티/관계)
│   ├── query.py                      # Neo4j Cypher 쿼리 모음
│   ├── db.py                         # Neo4j 연결 관리
│   ├── schema.cypher                 # Neo4j 제약사항 및 인덱스
│   └── standalone_builder.py         # 독립실행형 그래프 빌더
│
├── scraper/                          # 웹 스크래퍼
│   ├── run_scraper.py                # 메인 스크래퍼 (전체 상품 수집)
│   ├── discovery.py                  # 상품 발견 및 분류
│   ├── extractor.py                  # 상세 정보 추출
│   ├── enrich_from_listing.py        # 리스팅 페이지에서 정보 보강
│   ├── scrape_loan_details.py        # 대출 상세 페이지 스크래핑
│   ├── enrich_products.py            # 상품 정보 보강
│   ├── markdown_writer.py            # 마크다운 파일 작성
│   ├── config.py                     # 스크래퍼 설정
│   └── browser.py                    # Playwright 브라우저 관리
│
├── frontend/                         # React 프론트엔드
│   ├── src/
│   │   ├── App.tsx                   # 메인 앱 컴포넌트
│   │   ├── config.ts                 # API 설정
│   │   ├── main.tsx                  # 진입점
│   │   ├── index.css                 # 전역 스타일
│   │   ├── App.css                   # 앱 스타일
│   │   │
│   │   ├── components/               # React 컴포넌트
│   │   │   ├── GraphCanvas.tsx       # D3.js 그래프 시각화
│   │   │   ├── ChatPanel.tsx         # 대화형 챗봇 인터페이스
│   │   │   ├── ResizablePanels.tsx   # 분할 레이아웃
│   │   │   ├── DetailPanel.tsx       # 선택된 노드 상세 정보
│   │   │   ├── CategoryFilter.tsx    # 계층적 카테고리 필터
│   │   │   ├── SearchBar.tsx         # 상품 검색 바
│   │   │   ├── Legend.tsx            # 범례
│   │   │   └── Toolbar.tsx           # 도구 모음
│   │   │
│   │   ├── hooks/                    # React Hooks
│   │   └── types/                    # TypeScript 타입 정의
│   │
│   ├── package.json                  # npm 의존성
│   ├── vite.config.ts                # Vite 설정
│   └── tsconfig.json                 # TypeScript 설정
│
├── data/                             # 데이터 파일
│   ├── products/                     # 163개 마크다운 상품 파일
│   │   ├── 대출/                    # 대출 상품 (40개)
│   │   ├── 예금/                    # 예금 상품 (14개)
│   │   ├── 적금/                    # 적금 상품 (12개)
│   │   └── ...
│   │
│   ├── graph/                        # 그래프 데이터
│   │   └── graph.json                # D3.js 내보내기 (노드 + 엣지)
│   │
│   └── raw/                          # 원본 HTML/JSON 데이터
│
├── docker-compose.yml                # Docker Compose 설정 (Neo4j)
├── pyproject.toml                    # Python 프로젝트 설정
├── .env                              # 환경변수 (gitignored)
├── .env.example                      # 환경변수 예시
└── .gitignore                        # Git 무시 목록
```

---

## REST API 엔드포인트

### 기본 API

| HTTP 메서드 | 엔드포인트 | 설명 |
|-----------|----------|------|
| GET | `/health` | 헬스 체크 (DB 연결 확인) |

### 그래프 API

| HTTP 메서드 | 엔드포인트 | 설명 |
|-----------|----------|------|
| GET | `/api/graph` | 전체 그래프 데이터 (노드 + 엣지) |
| GET | `/api/graph/stats` | 그래프 통계 (노드/엣지 개수, 엔티티 타입별 분포) |

### 상품 API

| HTTP 메서드 | 엔드포인트 | 설명 |
|-----------|----------|------|
| GET | `/api/products` | 전체 상품 목록 (카테고리별 필터 가능) |
| GET | `/api/products/{id}` | 특정 상품 상세 정보 |
| GET | `/api/products/{id}/compare/{other_id}` | 두 상품 비교 |
| GET | `/api/categories` | 카테고리 계층 구조 |

### 검색 API

| HTTP 메서드 | 엔드포인트 | 설명 |
|-----------|----------|------|
| GET | `/api/search?q=keyword` | 풀텍스트 검색 (상품명, 특징 등) |

### 챗봇 API

| HTTP 메서드 | 엔드포인트 | 설명 |
|-----------|----------|------|
| POST | `/api/chat` | GraphRAG 챗봇 대화 (JSON 요청) |

---

## 설치 및 실행

### 필수 사항

- **Python 3.11 이상**
- **Node.js 18 이상**
- **Docker** (Neo4j 데이터베이스)
- **OpenAI API 키**

### 빠른 시작

#### 1단계: 저장소 클론 및 디렉토리 이동

```bash
git clone <repository-url>
cd banking_bot
```

#### 2단계: 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 다음 값들을 설정합니다:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_secure_password
OPENAI_API_KEY=your_openai_api_key
```

#### 3단계: Neo4j 데이터베이스 시작 (Docker)

```bash
docker-compose up -d
```

데이터베이스가 시작될 때까지 10초 정도 기다립니다.

#### 4단계: Python 백엔드 설치

```bash
pip install -e .
```

#### 5단계: 지식그래프 구축 (선택사항)

이미 빌드된 그래프가 있다면 생략 가능합니다.

```bash
python -m knowledge_graph.builder
```

#### 6단계: 백엔드 서버 시작

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

또는:

```bash
python -m backend.main
```

#### 7단계: 프론트엔드 설치 및 실행

새로운 터미널을 열고:

```bash
cd frontend
npm install
npm run dev
```

### 서비스 URL

| 서비스 | URL | 설명 |
|--------|-----|------|
| 프론트엔드 | http://localhost:5173 | React 앱 (그래프 + 챗봇) |
| 백엔드 API | http://localhost:8000 | FastAPI 백엔드 |
| API 문서 | http://localhost:8000/docs | Swagger UI (인터랙티브 API) |
| Neo4j Browser | http://localhost:7474 | Neo4j 웹 인터페이스 |
| 헬스 체크 | http://localhost:8000/health | API 상태 확인 |

---

## 환경변수 설정

### `.env` 파일 예시

```env
# Neo4j 데이터베이스
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_secure_password

# OpenAI LLM
OPENAI_API_KEY=sk-your-actual-key-here

# 선택사항: 스크래퍼 설정
HEADLESS=true
DEBUG=false
```

---

## 스크래핑 명령어

### 전체 상품 스크래핑

모든 금융상품을 KB국민은행 웹사이트에서 수집합니다.

```bash
python -m scraper.run_scraper
```

**소요 시간**: 약 30분 (대역폭 및 서버 응답에 따라 다름)

**출력**: `data/products/` 디렉토리에 163개의 마크다운 파일

### 리스팅 페이지에서 정보 보강

상품 리스팅 페이지에서 추가 정보 수집:

```bash
python -m scraper.enrich_from_listing
```

### 대출 상세 페이지 스크래핑

대출 상품의 상세 정보 수집 (특수 JavaScript 함수 호출):

```bash
python -m scraper.scrape_loan_details
```

### 지식그래프 다시 구축

마크다운 파일로부터 Neo4j 그래프 재구축:

```bash
python -m knowledge_graph.builder
```

### 그래프 내보내기 (D3.js 용)

Neo4j 그래프를 D3.js 형식으로 내보내기:

```bash
python -m knowledge_graph.exporter
```

---

## 사용 예제

### 1. 프론트엔드에서 챗봇 사용

1. 브라우저에서 http://localhost:5173 접속
2. "신용대출 추천해줘" 등 질문 입력
3. 챗봇이 7가지 스킬을 활용하여 답변 생성
4. 왼쪽 그래프에서 관련 상품 노드 시각화

### 2. REST API로 상품 검색

```bash
# 신용대출 상품 검색
curl "http://localhost:8000/api/search?q=신용대출"

# 응답 예시:
# [
#   {
#     "id": "credit_loan_001",
#     "name": "토스뱅크 신용대출",
#     "category": "신용대출",
#     "description": "...",
#     "rate": 4.5
#   }
# ]
```

### 3. 상품 상세 조회

```bash
curl "http://localhost:8000/api/products/credit_loan_001"
```

### 4. 두 상품 비교

```bash
curl "http://localhost:8000/api/products/product_001/compare/product_002"
```

### 5. 카테고리별 상품 목록

```bash
curl "http://localhost:8000/api/products?category=신용대출"
```

### 6. 전체 그래프 데이터 조회

```bash
curl "http://localhost:8000/api/graph"

# 응답 예시:
# {
#   "nodes": [
#     {"id": "product_001", "name": "...", "type": "Product"},
#     ...
#   ],
#   "links": [
#     {"source": "product_001", "target": "rate_001", "type": "HAS_RATE"},
#     ...
#   ]
# }
```

### 7. 챗봇 API 직접 호출

```bash
curl -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "3000만원 신용대출을 5년에 걸쳐 빌리면 월 상환액이 얼마?"}'

# 응답 예시:
# {
#   "response": "3000만원을 5년(60개월) 동안 빌릴 경우 연리 5%일 때...",
#   "tools_used": ["calculate_loan_payment"]
# }
```

---

## 데이터 파이프라인

### 스크래핑 프로세스

```
KB국민은행 웹사이트 (https://obank.kbstar.com/)
    ↓
Playwright 헤드리스 브라우저
    ↓
상품 발견 (카테고리별)
    ↓
상세 정보 추출
    ↓
마크다운 파일 저장 (163개)
    ↓
엔티티 추출 및 파싱
    ↓
Neo4j 그래프 구축
    ↓
인덱싱 및 최적화
    ↓
D3.js JSON 내보내기
    ↓
REST API 제공
```

### 한국어 특화 처리

- **금액 파싱**: "3백만원", "5천만원" → 숫자로 변환
- **기간 파싱**: "6~36개월", "1~10년" → min/max 범위로 파싱
- **금리 필터링**: 15% 이상의 비합리적인 금리 제거
- **CJK 풀텍스트 검색**: Neo4j 내 한글 검색 지원

---

## 주요 기술 특징

### GraphRAG (Graph Retrieval-Augmented Generation)

1. **컨텍스트 검색**: 사용자 쿼리로 지식그래프에서 관련 노드 검색
2. **관계 활용**: 검색된 노드의 관련 엔티티(금리, 조건, 수수료 등) 함께 추출
3. **LLM 입력**: 검색된 구조화된 정보를 LLM 프롬프트에 포함
4. **응답 생성**: LLM이 정확한 금융 정보 기반 답변 생성

### LangGraph 워크플로우

```
User Input
    ↓
retrieve_context() - 지식그래프 검색
    ↓
process_agent() - LLM + Tool Calling
    ↓
Tool Call? → 도구 실행
    ↓
응답 완성
```

### D3.js 인터랙티브 시각화

- **1,233개 노드**: 상품, 금리, 조건, 수수료 등
- **3,757개 엣지**: 15가지 관계 타입으로 노드 연결
- **드래그 & 드롭**: 노드 이동으로 그래프 조작
- **줌 & 팬**: 세부 사항 확인
- **카테고리 필터**: 특정 상품 유형만 표시
- **노드 선택**: 상세 정보 패널에 표시

---

## 문제 해결

### Neo4j 연결 실패

```
Error: Could not establish connection to bolt://localhost:7687
```

**해결책**:
1. Docker 실행 확인: `docker ps | grep neo4j`
2. 포트 확인: `lsof -i :7687`
3. Docker 로그 확인: `docker logs banking_bot_neo4j`
4. Docker 재시작: `docker-compose down && docker-compose up -d`

### OpenAI API 키 오류

```
Error: OpenAI API key not found
```

**해결책**:
1. `.env` 파일에 `OPENAI_API_KEY` 설정 확인
2. 키 형식 확인: `sk-`로 시작해야 함
3. 홀따옴표/쌍따옴표 제거: `OPENAI_API_KEY=sk-xxx` (따옴표 없음)

### 프론트엔드 백엔드 연결 오류

```
Failed to fetch from http://localhost:8000/api/graph
```

**해결책**:
1. 백엔드 서버 실행 확인: `curl http://localhost:8000/health`
2. CORS 설정 확인: `backend/main.py` 에서 `allow_origins`
3. 포트 번호 확인: 백엔드는 8000, 프론트엔드는 5173

### 스크래핑 실패

```
Playwright browser not found
```

**해결책**:
```bash
playwright install
```

---

## 개발 가이드

### 새로운 도구/스킬 추가

1. `backend/agent/skills/` 디렉토리에 새 파일 생성
2. `@tool` 데코레이터로 도구 정의
3. `backend/agent/graph.py`의 `_get_tools()` 함수에 추가
4. 시스템 프롬프트에 도구 설명 추가

### 새로운 엔티티 타입 추가

1. `knowledge_graph/models.py`에 Pydantic 모델 정의
2. `knowledge_graph/ontology.py`에 스키마 추가
3. `knowledge_graph/parser.py`에 파싱 로직 추가
4. `knowledge_graph/builder.py`에 생성 로직 추가

### 프론트엔드 컴포넌트 추가

1. `frontend/src/components/` 에 새 `.tsx` 파일 생성
2. React 함수형 컴포넌트로 구현
3. `App.tsx`에 import 및 렌더링

---

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

---

## 문의 및 지원

문제가 발생하거나 질문이 있으시면, GitHub Issues를 통해 보고해주세요.

---

## 변경 로그

### v0.1.0 (초기 릴리스)

- KB국민은행 금융상품 163개 수집 (웹 스크래핑 + PDF 파싱)
- Neo4j 지식그래프 구축 (1,233 노드, 3,757 엣지)
- LangGraph 기반 7가지 도구 챗봇
- React + D3.js 인터랙티브 시각화
- FastAPI REST API

---

## 감사의 말

- KB국민은행 금융상품 정보 제공
- LangChain, LangGraph 오픈소스 커뮤니티
- Neo4j 커뮤니티 에디션
- D3.js 시각화 라이브러리

---

**마지막 업데이트**: 2026년 3월 23일

**언어**: 한국어 / **프로젝트**: KB국민은행 금융상품 GraphRAG 챗봇
