"""통합 주택담보대출 한도 계산 스킬.

최종 대출한도 = min(LTV 한도, DSR 한도, 주택가격대별 상한)

LTV 한도: 시세 × LTV비율 - 선순위대출 - 임차보증금
DSR 한도: 연소득 × DSR한도 / 연간원리금상환액 비율로 역산
"""

from __future__ import annotations

from langchain_core.tools import tool

from backend.agent.skills.ltv_calculator import (
    _calculate_ltv_limit,
    _resolve_borrower_type,
    _resolve_regulation_zone,
    _get_small_deposit,
)
from backend.agent.skills.dsr_calculator import (
    _max_loan_by_dsr,
    _parse_existing_loans,
    _get_stress_rate,
    calculate_annual_repayment,
    STRESS_RATIO_BY_RATE_TYPE,
    DSR_LIMIT_BANK,
    DSR_LIMIT_NON_BANK,
    BULLET_MATURITY_CAP,
)


# 수도권/규제지역 만기 상한 (6.27 대책: 수도권/규제지역 주담대 만기 30년 제한)
MAX_MONTHS_REGULATED = 360  # 30년


@tool
def calculate_mortgage_limit(
    property_value: float,
    annual_income: float,
    loan_rate: float,
    loan_months: int = 360,
    loan_method: str = "원리금균등",
    loan_rate_type: str = "변동",
    region: str = "수도권",
    sector: str = "은행",
    is_first_time: bool = False,
    num_homes: int = 0,
    disposal_condition: bool = False,
    prior_loans: float = 0.0,
    lease_deposit: float = 0.0,
    is_apartment: bool = True,
    num_rooms: int = 1,
    existing_loans: str = "",
) -> str:
    """주택담보대출 최종 한도를 계산합니다. LTV와 DSR을 모두 계산하여 낮은 금액을 안내합니다.

    아파트 시세, 연소득, 기존대출 등을 종합적으로 고려하여
    LTV 한도와 DSR 한도를 각각 산출한 뒤, 최종 대출 가능액을 결정합니다.

    Args:
        property_value: 주택 시세 (만원, 예: 50000 = 5억)
        annual_income: 연소득 (만원, 예: 5000 = 5천만원)
        loan_rate: 예상 대출 약정 연이자율 (%, 예: 4.5)
        loan_months: 상환기간 (개월, 예: 360 = 30년)
        loan_method: 상환방식 ("원리금균등", "원금균등", "만기일시")
        loan_rate_type: 금리유형 ("변동", "혼합5년", "혼합10년", "고정" 등)
        region: 지역 ("서울", "수도권", "규제지역", "지방" 등)
        sector: 금융권 ("은행", "2금융")
        is_first_time: 생애최초 주택구입 여부
        num_homes: 보유 주택 수 (0=무주택)
        disposal_condition: 1주택자 처분조건 수용 여부
        prior_loans: 동일 담보물건 선순위 대출 잔액 (만원)
        lease_deposit: 동일 물건 임차보증금 합계 (만원)
        is_apartment: 아파트 여부
        num_rooms: 방 수 (소액임차보증금 계산용)
        existing_loans: 기존 대출 정보 ("잔액:금리:잔여개월:상환방식:유형:금리유형", | 구분)
    """
    zone = _resolve_regulation_zone(region)
    borrower_type = _resolve_borrower_type(is_first_time, num_homes, disposal_condition)
    small_deposit = _get_small_deposit(region, num_rooms, is_apartment)

    # 수도권/규제지역 만기 30년 제한 (6.27 대책)
    effective_months = loan_months
    months_capped = False
    if zone == "규제지역" and loan_months > MAX_MONTHS_REGULATED:
        effective_months = MAX_MONTHS_REGULATED
        months_capped = True

    # ── Step 1: LTV 한도 ──
    ltv_result = _calculate_ltv_limit(
        property_value, zone, borrower_type,
        prior_loans, lease_deposit, small_deposit,
    )
    ltv_limit = ltv_result["final_limit"]  # 만원

    # ── Step 2: DSR 한도 ──
    income_won = annual_income * 10000
    dsr_limit = DSR_LIMIT_BANK if sector == "은행" else DSR_LIMIT_NON_BANK
    stress_rate = _get_stress_rate(region, "주담대", loan_rate_type)
    rate_stressed = loan_rate + stress_rate
    stress_ratio = STRESS_RATIO_BY_RATE_TYPE.get(loan_rate_type, 1.0)
    stress_base = _get_stress_rate(region, "주담대", "변동")

    existing_annual_total, existing_details = _parse_existing_loans(existing_loans, region)

    dsr_max_won = _max_loan_by_dsr(
        income_won, dsr_limit, existing_annual_total,
        rate_stressed, effective_months, loan_method, "주담대",
    )
    dsr_limit_man = dsr_max_won / 10000  # 원 → 만원

    # ── Step 3: 최종 한도 = min(LTV, DSR) ──
    final_limit = min(ltv_limit, dsr_limit_man)
    if final_limit < 0:
        final_limit = 0

    # 제약 요인 판별
    if ltv_limit == 0 and ltv_result["ltv_ratio"] == 0:
        binding = "LTV 대출불가"
    elif ltv_limit <= dsr_limit_man:
        binding = "LTV"
    else:
        binding = "DSR"

    # DSR 역산 (최종 한도 기준)
    final_won = final_limit * 10000
    final_annual = calculate_annual_repayment(
        final_won, rate_stressed, effective_months, loan_method, "주담대",
    )
    total_annual = existing_annual_total + final_annual
    actual_dsr = (total_annual / income_won * 100) if income_won > 0 else 0.0

    # ── 결과 포맷 ──
    lines = [
        "## 주택담보대출 최종 한도 계산\n",
        "### 입력 조건",
        f"- 주택 시세: **{property_value:,.0f}만원** ({property_value / 10000:.1f}억원)",
        f"- 연소득: **{annual_income:,.0f}만원** ({annual_income / 10000:.1f}억원)",
        f"- 지역: {region} → **{zone}**",
        f"- 차주유형: **{borrower_type}**",
        f"- 금융권: {sector} (DSR 한도 {dsr_limit}%)",
        f"- 약정금리: {loan_rate}%, 금리유형: {loan_rate_type}",
        f"- 상환기간: {loan_months}개월 ({loan_months // 12}년)"
        + (f" → **{effective_months}개월({effective_months // 12}년)로 제한** (수도권 30년 상한)" if months_capped else ""),
        f"- 상환방식: {loan_method}",
    ]
    if prior_loans > 0:
        lines.append(f"- 선순위 대출: {prior_loans:,.0f}만원")
    if lease_deposit > 0:
        lines.append(f"- 임차보증금: {lease_deposit:,.0f}만원")
    if existing_details:
        lines.append(f"- 기존 대출: {len(existing_details)}건")
    lines.append("")

    # ── LTV 결과 ──
    lines.append("### ① LTV 기준 한도")
    if ltv_result["ltv_ratio"] == 0:
        lines.append(f"- **{zone}에서 {borrower_type}는 주택담보대출 불가**")
    else:
        lines.append(f"- 적용 LTV: **{ltv_result['ltv_ratio']}%**")
        lines.append(f"- LTV 대출액: {property_value:,.0f} × {ltv_result['ltv_ratio']}% = {ltv_result['gross_limit']:,.0f}만원")
        total_deduct = prior_loans + lease_deposit + small_deposit
        if total_deduct > 0:
            lines.append(f"- 차감 (선순위+보증금): -{total_deduct:,.0f}만원")
        if ltv_result["price_cap"] is not None:
            lines.append(f"- 주택가격대별 상한: {ltv_result['price_cap']:,.0f}만원")
        if ltv_result["first_time_cap"] is not None:
            lines.append(f"- 생애최초 상한: {ltv_result['first_time_cap']:,.0f}만원")
        lines.append(f"- **LTV 한도: {ltv_limit:,.0f}만원 ({ltv_limit / 10000:.1f}억원)**")
    lines.append("")

    # ── DSR 결과 ──
    lines.append("### ② DSR 기준 한도")
    lines.append(f"- 스트레스 가산금리: {stress_base}%p × {stress_ratio * 100:.0f}% = +{stress_rate}%p")
    lines.append(f"- DSR 산정금리: {loan_rate}% + {stress_rate}%p = **{rate_stressed}%**")
    if existing_annual_total > 0:
        lines.append(f"- 기존 대출 연상환액: {existing_annual_total:,.0f}원")
        for i, d in enumerate(existing_details, 1):
            lines.append(f"  - 대출{i}({d['type']}): {d['amount']:,.0f}원, {d['rate']}%, 연{d['annual']:,.0f}원")
    lines.append(f"- **DSR 한도: {dsr_limit_man:,.0f}만원 ({dsr_limit_man / 10000:.1f}억원)**")
    lines.append("")

    # ── 최종 결과 ──
    lines.append("### ③ 최종 대출 가능액")
    lines.append(f"| 구분 | 한도 |")
    lines.append(f"|------|------|")
    lines.append(f"| LTV 기준 | {ltv_limit:,.0f}만원 ({ltv_limit / 10000:.1f}억원) |")
    lines.append(f"| DSR 기준 | {dsr_limit_man:,.0f}만원 ({dsr_limit_man / 10000:.1f}억원) |")
    lines.append(f"| **최종 한도** | **{final_limit:,.0f}만원 ({final_limit / 10000:.1f}억원)** |")
    lines.append(f"| 제약 요인 | {binding} |")
    lines.append("")

    if final_limit > 0:
        lines.append("### 예상 상환 정보")
        lines.append(f"- 대출금: {final_limit:,.0f}만원")
        lines.append(f"- 월 상환액: **{final_annual / 12:,.0f}원**")
        lines.append(f"- 예상 DSR: **{actual_dsr:.2f}%** (한도 {dsr_limit}%)")
        lines.append("")

    # 상환방식별 비교
    lines.append("### 상환방식별 한도 비교")
    lines.append("| 상환방식 | DSR 한도 | LTV 한도 | 최종 한도 | 월 상환액 |")
    lines.append("|---------|:-------:|:-------:|:--------:|:--------:|")
    for m in ["원리금균등", "원금균등", "만기일시"]:
        dsr_m_won = _max_loan_by_dsr(
            income_won, dsr_limit, existing_annual_total,
            rate_stressed, effective_months, m, "주담대",
        )
        dsr_m_man = dsr_m_won / 10000
        final_m = min(ltv_limit, dsr_m_man)
        if final_m > 0:
            final_m_won = final_m * 10000
            annual_m = calculate_annual_repayment(final_m_won, rate_stressed, effective_months, m, "주담대")
            monthly_m = annual_m / 12
            marker = " **←**" if m == loan_method else ""
            lines.append(f"| {m} | {dsr_m_man:,.0f}만원 | {ltv_limit:,.0f}만원 | **{final_m:,.0f}만원** | {monthly_m:,.0f}원 |{marker}")
        else:
            lines.append(f"| {m} | {dsr_m_man:,.0f}만원 | {ltv_limit:,.0f}만원 | 0원 | - |")

    # 기간별 비교
    lines.append(f"\n### 상환기간별 한도 비교 ({loan_method})")
    lines.append("| 기간 | DSR 한도 | 최종 한도 | 월 상환액 |")
    lines.append("|------|:-------:|:--------:|:--------:|")
    for years in [10, 15, 20, 25, 30]:
        months = years * 12
        if zone == "규제지역" and months > MAX_MONTHS_REGULATED:
            continue
        dsr_y_won = _max_loan_by_dsr(
            income_won, dsr_limit, existing_annual_total,
            rate_stressed, months, loan_method, "주담대",
        )
        dsr_y_man = dsr_y_won / 10000
        final_y = min(ltv_limit, dsr_y_man)
        if final_y > 0:
            annual_y = calculate_annual_repayment(final_y * 10000, rate_stressed, months, loan_method, "주담대")
            marker = " **←**" if months == effective_months else ""
            lines.append(f"| {years}년 | {dsr_y_man:,.0f}만원 | **{final_y:,.0f}만원** | {annual_y / 12:,.0f}원 |{marker}")
        else:
            lines.append(f"| {years}년 | {dsr_y_man:,.0f}만원 | 0원 | - |")

    if zone != "규제지역":
        for years in [35, 40]:
            months = years * 12
            dsr_y_won = _max_loan_by_dsr(
                income_won, dsr_limit, existing_annual_total,
                rate_stressed, months, loan_method, "주담대",
            )
            dsr_y_man = dsr_y_won / 10000
            final_y = min(ltv_limit, dsr_y_man)
            if final_y > 0:
                annual_y = calculate_annual_repayment(final_y * 10000, rate_stressed, months, loan_method, "주담대")
                marker = " **←**" if months == effective_months else ""
                lines.append(f"| {years}년 | {dsr_y_man:,.0f}만원 | **{final_y:,.0f}만원** | {annual_y / 12:,.0f}원 |{marker}")

    lines.append("\n---")
    lines.append("※ LTV: 2025.6.27 대책 + 10.15 대책 기준")
    lines.append("※ DSR: 금감원 스트레스 DSR 3단계 (2025.7.1~) 적용")
    lines.append("※ 수도권/규제지역 주담대 만기 30년 상한 적용 (6.27 대책)")
    lines.append("※ 실제 한도는 은행 심사(신용등급, 소득증빙 등)에 따라 달라질 수 있습니다.")
    lines.append("※ KB국민은행 고객센터(1588-9999) 또는 영업점 방문 상담을 권장합니다.")

    return "\n".join(lines)
