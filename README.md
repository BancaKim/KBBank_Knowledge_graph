# KB국민은행 금융상품 지식그래프

![메인 화면](docs/mainPage.png)

KB국민은행의 금융상품 데이터를 수집하여 **Neo4j 지식그래프**로 구축한 프로젝트입니다. 162개 금융상품을 14개 엔티티 타입과 14개 관계 타입으로 구조화하고, D3.js 기반 인터랙티브 시각화와 GraphRAG 챗봇을 제공합니다.

> **1,310개 노드 · 3,861개 관계 · 162개 금융상품**

---

## 데이터 수집

KB국민은행 웹사이트에서 두 가지 방법으로 금융상품 데이터를 수집합니다.

```mermaid
flowchart LR
    A[KB국민은행 웹사이트] --> B{수집 방법}
    B --> C[Playwright 웹 스크래핑]
    B --> D[PDF 다운로드 + OCR]

    C --> E[HTML 파싱]
    D --> F[PyMuPDF 텍스트 추출]
    F --> G[GPT-4o-mini 구조화]
    E --> H[YAML frontmatter + Markdown]
    G --> H

    H --> I["162개 상품 마크다운 파일"]
```

### 수집 경로별 상품 수

| 수집 방법 | 카테고리 | 상품 수 |
|----------|---------|--------|
| PDF 파싱 | 신용대출 | 47개 |
| PDF 파싱 | 담보대출 | 41개 |
| PDF 파싱 | 전월세대출 | 37개 |
| PDF 파싱 | 자동차대출 | 10개 |
| PDF 파싱 | 정기예금 | 5개 |
| PDF 파싱 | 적금 | 10개 |
| PDF 파싱 | 입출금자유 | 10개 |
| PDF 파싱 | 주택청약 | 2개 |
| **합계** | | **162개** |

### 마크다운 파일 구조

각 상품은 YAML frontmatter + 본문으로 구성됩니다.

```yaml
---
name: KB Star 정기예금
category: 정기예금
rates: 연 2.4% ~ 2.9%
terms: 1개월 이상 36개월 이하
channels: [인터넷, 스타뱅킹, 고객센터]
eligibility_summary: 개인 및 개인사업자
source: 'PDF: KB-Star-정기예금.pdf'
---
# KB Star 정기예금
## 상품설명
## 금리
## 가입대상
## 가입기간
## 우대금리
## 유의사항
```

### 한국어 데이터 처리

| 처리 항목 | 예시 | 변환 결과 |
|----------|------|----------|
| 금액 파싱 | "3백만원", "1억5천만원" | 3,000,000 / 150,000,000 |
| 기간 파싱 | "6~36개월", "최장 10년" | min=6, max=36 / max=120 |
| 금리 필터링 | "연 3.5%" (15% 초과 제거) | 3.5 |
| CJK 풀텍스트 | Neo4j fulltext index | 한글 검색 지원 |

---

## 온톨로지 설계

### 엔티티-관계 모델

```mermaid
erDiagram
    Product ||--o{ Feature : HAS_FEATURE
    Product ||--o{ InterestRate : HAS_RATE
    Product ||--o{ PreferentialRate : HAS_PREFERENTIAL_RATE
    Product ||--o{ Term : HAS_TERM
    Product ||--o{ Fee : HAS_FEE
    Product ||--|| EligibilityCondition : REQUIRES
    Product ||--o{ Channel : AVAILABLE_VIA
    Product ||--o{ RepaymentMethod : REPAID_VIA
    Product ||--o| TaxBenefit : HAS_TAX_BENEFIT
    Product ||--o| DepositProtection : PROTECTED_BY
    Product ||--o| ProductType : HAS_TYPE
    Product }o--|| Category : BELONGS_TO
    Category }o--|| ParentCategory : HAS_SUBCATEGORY
    Product }o--o{ Product : COMPETES_WITH
```

### 14개 엔티티 타입

| 엔티티 | 노드 수 | 설명 | 주요 속성 |
|--------|--------|------|----------|
| **Product** | 162 | 금융상품 | name, product_type, description, amount_max |
| **PreferentialRate** | 308 | 우대금리 조건 | name, rate_value_pp, condition_description |
| **Feature** | 306 | 상품 특징 | name, description |
| **EligibilityCondition** | 161 | 가입 자격 | description, min_age, target_audience |
| **Term** | 141 | 가입/대출 기간 | min_months, max_months, raw_text |
| **Fee** | 40 | 수수료 | fee_type, description |
| **TaxBenefit** | 28 | 세제혜택 | type (비과세/일반과세), eligible |
| **DepositProtection** | 28 | 예금자보호 | protected, max_amount_won |
| **InterestRate** | 16 | 기본금리 | rate_type, min_rate, max_rate |
| **RepaymentMethod** | 12 | 상환방법 | name (원리금균등/원금균등/일시상환) |
| **ProductType** | 11 | 상품유형 | name |
| **Channel** | 10 | 가입채널 | name (스타뱅킹/인터넷/영업점) |
| **Category** | 9 | 하위 카테고리 | name, name_en |
| **ParentCategory** | 2 | 상위 카테고리 | name (예금/대출) |

### 14개 관계 타입

```mermaid
graph TD
    subgraph 카테고리 계층
        PC[ParentCategory] -->|HAS_SUBCATEGORY| C[Category]
        P[Product] -->|BELONGS_TO| C
    end

    subgraph 상품 속성
        P -->|HAS_RATE| IR[InterestRate]
        P -->|HAS_PREFERENTIAL_RATE| PR[PreferentialRate]
        P -->|HAS_TERM| T[Term]
        P -->|HAS_FEATURE| F[Feature]
        P -->|HAS_FEE| FE[Fee]
        P -->|HAS_TYPE| PT[ProductType]
    end

    subgraph 조건/보호
        P -->|REQUIRES| EC[EligibilityCondition]
        P -->|HAS_TAX_BENEFIT| TB[TaxBenefit]
        P -->|PROTECTED_BY| DP[DepositProtection]
    end

    subgraph 이용 방법
        P -->|AVAILABLE_VIA| CH[Channel]
        P -->|REPAID_VIA| RM[RepaymentMethod]
    end

    subgraph 추론 관계
        P -.->|COMPETES_WITH| P2[Product]
    end

    style PC fill:#E65100,color:#fff
    style C fill:#F5A623,color:#000
    style P fill:#4A90D9,color:#fff
    style IR fill:#D0021B,color:#fff
    style PR fill:#E74C3C,color:#fff
    style T fill:#9B59B6,color:#fff
    style F fill:#7ED321,color:#000
    style FE fill:#8E44AD,color:#fff
    style EC fill:#95A5A6,color:#000
    style TB fill:#27AE60,color:#fff
    style DP fill:#2980B9,color:#fff
    style CH fill:#1ABC9C,color:#fff
    style RM fill:#E67E22,color:#fff
    style PT fill:#16A085,color:#fff
```

### 카테고리 계층 구조

```mermaid
graph TD
    예금[예금 Deposits] --> 정기예금["정기예금 (5)"]
    예금 --> 적금["적금 (10)"]
    예금 --> 입출금자유["입출금자유 (10)"]
    예금 --> 주택청약["주택청약 (2)"]

    대출[대출 Loans] --> 신용대출["신용대출 (47)"]
    대출 --> 담보대출["담보대출 (41)"]
    대출 --> 전월세대출["전월세대출 (37)"]
    대출 --> 자동차대출["자동차대출 (10)"]

    style 예금 fill:#E65100,color:#fff,font-weight:bold
    style 대출 fill:#E65100,color:#fff,font-weight:bold
    style 정기예금 fill:#F5A623
    style 적금 fill:#F5A623
    style 입출금자유 fill:#F5A623
    style 주택청약 fill:#F5A623
    style 신용대출 fill:#F5A623
    style 담보대출 fill:#F5A623
    style 전월세대출 fill:#F5A623
    style 자동차대출 fill:#F5A623
```

---

## 데이터 파이프라인

```mermaid
flowchart TD
    A["KB국민은행 웹사이트"] --> B["Playwright 스크래핑 / PDF 다운로드"]
    B --> C["data/raw/ (150개 PDF)"]
    C --> D["PyMuPDF 텍스트 추출"]
    D --> E["GPT-4o-mini 구조화 추출"]
    E --> F["data/products/ (162개 Markdown)"]
    F --> G["knowledge_graph/parser.py\n엔티티 추출 (Pydantic 모델)"]
    G --> H["knowledge_graph/builder.py\nNeo4j MERGE 쿼리"]
    H --> I["Neo4j Knowledge Graph\n1,310 노드 · 3,861 관계"]
    I --> J["knowledge_graph/exporter.py\nD3.js JSON 내보내기"]
    J --> K["data/graph/graph.json"]
    K --> L["Frontend (React + D3.js)\n인터랙티브 시각화"]
    I --> M["Backend (FastAPI)\nREST API + GraphRAG 챗봇"]

    style A fill:#FFB300,color:#000
    style I fill:#4A90D9,color:#fff
    style L fill:#7ED321,color:#000
    style M fill:#9B59B6,color:#fff
```

### 파서 동작 과정

```mermaid
sequenceDiagram
    participant MD as Markdown 파일
    participant P as parser.py
    participant M as Pydantic Models
    participant B as builder.py
    participant N as Neo4j

    MD->>P: frontmatter + body 로드
    P->>P: YAML frontmatter 파싱
    P->>P: 본문 섹션 분할 (## 헤딩 기준)
    P->>M: Product, Category, Feature... 생성
    P->>P: 금리/기간/금액 한국어 파싱
    P->>P: 우대금리 조건 추출
    P->>P: 수수료/세제혜택/예금자보호 추출
    M->>B: ParsedProduct 전달
    B->>N: MERGE 쿼리 (상품별 13개 노드/관계)
    B->>N: 카테고리 계층 생성
    B->>N: COMPETES_WITH 추론
```

---

## 시각화

D3.js 기반 인터랙티브 그래프 시각화를 제공합니다.

- **카테고리별 클러스터링**: 같은 카테고리 상품이 가까이 모여 표시
- **노드 크기 계층**: ParentCategory > Category > Product > 기타
- **클릭 선택**: 노드 클릭 시 연결된 노드/엣지 하이라이트, 비관련 노드 페이드
- **관계 타입별 엣지 색상**: 13가지 색상으로 관계 구분
- **카테고리 필터**: 특정 카테고리/노드 타입만 표시
- **줌/팬/드래그**: 자유로운 그래프 탐색

---

## GraphRAG 챗봇 (부가 기능)

지식그래프를 활용한 LangGraph 기반 대화형 상담 챗봇입니다.

```mermaid
flowchart LR
    Q[사용자 질문] --> R[지식그래프 컨텍스트 검색]
    R --> L[LLM + 도구 선택]
    L --> T{7가지 도구}
    T --> T1[상품 검색]
    T --> T2[상세 조회]
    T --> T3[카테고리별 목록]
    T --> T4[상품 비교]
    T --> T5[대출 상환액 계산]
    T --> T6[예금 만기액 계산]
    T --> T7[가입 자격 확인]
    T1 & T2 & T3 & T4 & T5 & T6 & T7 --> A[응답 생성]
```

- 사용자 본인의 OpenAI API 키를 프론트엔드에서 입력하여 사용
- Neo4j 없이도 정적 graph.json 기반으로 그래프/검색/상품 조회 가능

---

## 기술 스택

| 계층 | 기술 |
|------|------|
| **지식그래프** | Neo4j 5.x, Cypher, CJK Fulltext Index |
| **데이터 수집** | Playwright, PyMuPDF, GPT-4o-mini |
| **온톨로지** | Pydantic v2, 14 엔티티 타입, 14 관계 타입 |
| **백엔드** | FastAPI, LangChain, LangGraph |
| **프론트엔드** | React 19, TypeScript, D3.js 7, Vite |
| **인프라** | Docker (Neo4j), Python 3.11+ |

---

## 빠른 시작

```bash
# 1. 클론
git clone https://github.com/BancaKim/KBBank_Knowledge_graph.git
cd KBBank_Knowledge_graph

# 2. 환경변수
cp .env.example .env
# .env 파일에 NEO4J_PASSWORD, OPENAI_API_KEY 설정

# 3. Neo4j 시작
docker-compose up -d

# 4. Python 설치
pip install -e .

# 5. 지식그래프 구축
python -m knowledge_graph.builder

# 6. 백엔드 시작
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 7. 프론트엔드 시작 (새 터미널)
cd frontend && npm install && npm run dev
```

| 서비스 | URL |
|--------|-----|
| 프론트엔드 | http://localhost:5173 |
| 백엔드 API | http://localhost:8000 |
| API 문서 | http://localhost:8000/docs |
| Neo4j Browser | http://localhost:7474 |

> Neo4j 없이도 동작합니다 (정적 graph.json 폴백 모드).

---

## 프로젝트 구조

```
KBBank_Knowledge_Graph/
├── knowledge_graph/          # 온톨로지 및 그래프 구축
│   ├── models.py             # 14개 Pydantic 엔티티 모델
│   ├── ontology.py           # 노드/관계 스키마 정의
│   ├── parser.py             # 마크다운 → 엔티티 추출
│   ├── builder.py            # Neo4j 그래프 구축
│   ├── exporter.py           # D3.js JSON 내보내기
│   ├── export_from_md.py     # Neo4j 없이 직접 내보내기
│   ├── query.py              # Cypher 쿼리 모음
│   ├── db.py                 # Neo4j 연결 관리
│   └── schema.cypher         # 제약사항 및 인덱스
│
├── scraper/                  # 데이터 수집
│   ├── run_scraper.py        # 메인 웹 스크래퍼
│   ├── download_pdfs.py      # 대출 PDF 다운로드
│   ├── download_deposit_pdfs.py  # 예금 PDF 다운로드
│   ├── parse_pdfs.py         # PDF → 마크다운 파싱
│   └── parse_missing_pdfs.py # 누락 PDF 증분 파싱
│
├── data/
│   ├── raw/                  # 원본 PDF (150개)
│   ├── products/             # 파싱된 마크다운 (162개)
│   └── graph/graph.json      # D3.js 그래프 데이터
│
├── backend/                  # FastAPI 백엔드
│   ├── main.py               # 앱 진입점 (Neo4j 선택적)
│   ├── routers/              # REST API 엔드포인트
│   └── agent/                # LangGraph 챗봇 에이전트
│
├── frontend/                 # React + D3.js 프론트엔드
│   └── src/components/
│       └── GraphCanvas.tsx   # 인터랙티브 그래프 시각화
│
└── docker-compose.yml        # Neo4j 컨테이너
```

---

## 라이선스

MIT License

---

**마지막 업데이트**: 2026년 3월 24일
