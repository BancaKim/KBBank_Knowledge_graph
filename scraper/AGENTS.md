# scraper/

금융기관(obank.kbstar.com) 금융상품 웹 스크래퍼. Playwright 기반.
Source: public banking website

## 파일

| 파일 | 역할 |
|------|------|
| `run_scraper.py` | CLI 진입점 - 전체 스크래핑 파이프라인 (Discovery → Extraction → Markdown) |
| `discovery.py` | 상품 목록 페이지에서 상품 발견 - 탭 네비게이션, 페이지네이션 처리 |
| `extractor.py` | 상품 상세 페이지 데이터 추출 - 헤더, 상품안내, 금리 탭 파싱 |
| `markdown_writer.py` | 추출 데이터 → YAML frontmatter + Markdown 파일 생성 |
| `enrich_from_listing.py` | 목록 페이지 기반 MD 파일 보강 - 설명, 채널, 금액 추출 |
| `enrich_products.py` | 상세 페이지 기반 MD 파일 보강 (예금/적금용) |
| `scrape_loan_details.py` | 대출 상세 스크래핑 - dtlLoan() JS 함수 호출로 상세 페이지 접근 |
| `browser.py` | Playwright 브라우저 관리 - 헤드리스, User-Agent 로테이션 |
| `config.py` | 스크래퍼 설정 - URL, 카테고리 매핑, 딜레이, 출력 경로 |
| `__init__.py` | 패키지 초기화 |
