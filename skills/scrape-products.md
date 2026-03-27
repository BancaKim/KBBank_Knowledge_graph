---
name: scrape-products
description: Scrape financial institution product descriptions from public banking website
---

# 금융기관 상품 스크래핑

Source: public banking website (obank.kbstar.com)

## 트리거
- 사용자가 "상품 데이터 수집", "스크래핑", "상품 업데이트" 요청 시

## 동작

1. **의존성 확인**
   ```bash
   cd /Users/a1654530/Desktop/banking_bot
   pip install -e . 2>/dev/null
   playwright install chromium 2>/dev/null
   ```

2. **스크래핑 실행**
   ```bash
   python -m scraper.run_scraper --categories 예금,적금,대출,펀드,신탁,ISA --output data/products/ --headless
   ```

3. **결과 확인**
   - `data/products/` 하위 카테고리 폴더에 MD 파일 생성 확인
   - 각 MD 파일의 YAML frontmatter에 상품명, 금리, 기간 등 포함 여부 검증

4. **지식그래프 갱신**
   ```bash
   python -m knowledge_graph.builder
   ```

## 옵션
- `--categories`: 특정 카테고리만 스크래핑 (쉼표 구분)
- `--discover-only`: 상품 목록만 탐색하고 상세 페이지 방문하지 않음
- `--headless`: 브라우저 UI 없이 실행 (기본값)

## 참고
- 금융기관 URL 패턴: `https://obank.kbstar.com/quics?page=C######`
- 요청 간 2-5초 랜덤 딜레이 적용 (봇 차단 방지)
- 실패한 상품은 건너뛰고 계속 진행
