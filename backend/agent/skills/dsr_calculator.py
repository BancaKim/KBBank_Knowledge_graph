"""DSR (총부채원리금상환비율) 계산 스킬.

한국 주택담보대출 시 DSR 규제를 정확히 반영하여:
1. 현재 DSR 비율 계산
2. DSR 한도 내 최대 대출 가능액 산출
3. 스트레스 DSR 가산금리 자동 적용
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# 규제 상수 (2025.10.15 대책 / 스트레스 DSR 3단계 기준)
# ---------------------------------------------------------------------------

DSR_LIMIT_BANK = 40.0  # 은행권 DSR 한도 (%)
DSR_LIMIT_NON_BANK = 50.0  # 2금융권 DSR 한도 (%)

# 스트레스 가산금리 (%p)
STRESS_RATE: dict[str, float] = {
    "수도권": 3.0,
    "규제지역": 3.0,
    "지방": 0.75,
    "신용대출": 1.5,
}

# 상환방식별 만기일시 신용대출 가정 만기(년)
CREDIT_LOAN_ASSUMED_MATURITY_YEARS = 5


# ---------------------------------------------------------------------------
# 내부 계산 함수
# ---------------------------------------------------------------------------

def _annual_repayment_equal_installment(
    principal: float,
    annual_rate: float,
    total_months: int,
) -> float:
    """원리금균등상환 연간 원리금 상환액."""
    if total_months <= 0:
        return 0.0
    monthly_rate = annual_rate / 100 / 12
    if monthly_rate == 0:
        return (principal / total_months) * 12
    monthly = principal * monthly_rate * (1 + monthly_rate) ** total_months / (
        (1 + monthly_rate) ** total_months - 1
    )
    return monthly * 12


def _annual_repayment_equal_principal(
    principal: float,
    annual_rate: float,
    total_months: int,
) -> float:
    """원금균등상환 연간 원리금 상환액 (첫해 기준 — DSR 산정 시 최대값 사용)."""
    if total_months <= 0:
        return 0.0
    monthly_principal = principal / total_months
    monthly_rate = annual_rate / 100 / 12
    # 첫해 12개월 합산 (가장 큰 값)
    total = 0.0
    for i in range(min(12, total_months)):
        remaining = principal - monthly_principal * i
        total += monthly_principal + remaining * monthly_rate
    return total


def _annual_repayment_bullet(
    principal: float,
    annual_rate: float,
    total_months: int,
) -> float:
    """만기일시상환 연간 원리금 상환액.

    DSR 산정 시: 연이자 + (원금 / 대출기간(년))
    금감원 DSR 산정기준에 따라 만기일시는 원금균등분할 가정하여 산정.
    """
    if total_months <= 0:
        return 0.0
    annual_interest = principal * annual_rate / 100
    years = total_months / 12
    annual_principal = principal / years if years > 0 else principal
    return annual_interest + annual_principal


def calculate_annual_repayment(
    principal: float,
    annual_rate: float,
    total_months: int,
    method: str = "원리금균등",
) -> float:
    """상환방식에 따른 연간 원리금 상환액 계산."""
    if method == "원리금균등":
        return _annual_repayment_equal_installment(principal, annual_rate, total_months)
    elif method == "원금균등":
        return _annual_repayment_equal_principal(principal, annual_rate, total_months)
    elif method == "만기일시":
        return _annual_repayment_bullet(principal, annual_rate, total_months)
    else:
        # 기본: 원리금균등
        return _annual_repayment_equal_installment(principal, annual_rate, total_months)


def _get_stress_rate(region: str, loan_type: str) -> float:
    """스트레스 가산금리 결정."""
    if loan_type == "신용대출":
        return STRESS_RATE["신용대출"]
    if region in ("수도권", "규제지역", "서울"):
        return STRESS_RATE["수도권"]
    return STRESS_RATE["지방"]


def _max_loan_by_dsr(
    annual_income: float,
    dsr_limit: float,
    existing_annual_repayment: float,
    annual_rate_with_stress: float,
    total_months: int,
    method: str,
) -> float:
    """DSR 한도 내 최대 신규 대출 가능 원금 역산.

    DSR = (기존부채 연상환액 + 신규대출 연상환액) / 연소득 × 100 ≤ dsr_limit
    → 신규대출 연상환액 ≤ 연소득 × dsr_limit/100 - 기존부채 연상환액
    """
    max_new_annual = annual_income * dsr_limit / 100 - existing_annual_repayment
    if max_new_annual <= 0:
        return 0.0

    # 이진탐색으로 원금 역산
    lo, hi = 0.0, annual_income * 50  # 넉넉한 상한
    for _ in range(100):
        mid = (lo + hi) / 2
        repay = calculate_annual_repayment(mid, annual_rate_with_stress, total_months, method)
        if repay <= max_new_annual:
            lo = mid
        else:
            hi = mid
    return math.floor(lo / 10000) * 10000  # 만원 단위 절삭


# ---------------------------------------------------------------------------
# LangChain Tools
# ---------------------------------------------------------------------------

@tool
def calculate_dsr(
    annual_income: float,
    new_loan_amount: float,
    new_loan_rate: float,
    new_loan_months: int,
    new_loan_method: str = "원리금균등",
    region: str = "수도권",
    sector: str = "은행",
    existing_loans: str = "",
) -> str:
    """DSR(총부채원리금상환비율)을 계산하고 규제 충족 여부를 판단합니다.

    신규 주택담보대출의 DSR을 스트레스 금리 포함하여 정확히 산출합니다.

    Args:
        annual_income: 연소득 (만원 단위, 예: 5000 = 5천만원)
        new_loan_amount: 신규 대출 원금 (만원 단위, 예: 30000 = 3억원)
        new_loan_rate: 신규 대출 연이자율 (%, 예: 4.5)
        new_loan_months: 신규 대출 상환기간 (개월, 예: 360 = 30년)
        new_loan_method: 상환방식 ("원리금균등", "원금균등", "만기일시")
        region: 지역 ("수도권", "지방", "규제지역")
        sector: 금융권 ("은행", "2금융")
        existing_loans: 기존 대출 정보 (형식: "잔액(만원):금리(%):잔여개월:상환방식:유형" 여러 건은 | 구분)
            예: "5000:5.0:48:원리금균등:신용대출|10000:3.5:240:원리금균등:주담대"
    """
    income_won = annual_income * 10000
    new_principal_won = new_loan_amount * 10000
    dsr_limit = DSR_LIMIT_BANK if sector == "은행" else DSR_LIMIT_NON_BANK

    # --- 기존 대출 연간 상환액 ---
    existing_annual_total = 0.0
    existing_details = []

    if existing_loans and existing_loans.strip():
        for entry in existing_loans.split("|"):
            parts = [p.strip() for p in entry.split(":")]
            if len(parts) < 4:
                continue
            ex_amount = float(parts[0]) * 10000
            ex_rate = float(parts[1])
            ex_months = int(parts[2])
            ex_method = parts[3] if len(parts) > 3 else "원리금균등"
            ex_type = parts[4] if len(parts) > 4 else "기타"

            # 기존대출 스트레스 가산금리 적용
            ex_stress = _get_stress_rate(region, ex_type)
            ex_rate_stressed = ex_rate + ex_stress

            ex_annual = calculate_annual_repayment(ex_amount, ex_rate_stressed, ex_months, ex_method)
            existing_annual_total += ex_annual
            existing_details.append({
                "amount": ex_amount,
                "rate": ex_rate,
                "stress": ex_stress,
                "rate_stressed": ex_rate_stressed,
                "months": ex_months,
                "method": ex_method,
                "type": ex_type,
                "annual": ex_annual,
            })

    # --- 신규 대출 스트레스 금리 반영 ---
    stress_rate = _get_stress_rate(region, "주담대")
    new_rate_stressed = new_loan_rate + stress_rate
    new_annual = calculate_annual_repayment(new_principal_won, new_rate_stressed, new_loan_months, new_loan_method)

    # --- DSR 계산 ---
    total_annual = existing_annual_total + new_annual
    dsr = (total_annual / income_won) * 100 if income_won > 0 else 999.0
    is_ok = dsr <= dsr_limit

    # --- 결과 포맷 ---
    lines = [
        "## DSR 계산 결과\n",
        "### 기본 정보",
        f"- 연소득: **{income_won:,.0f}원** ({annual_income:,.0f}만원)",
        f"- 금융권: {sector} (DSR 한도 **{dsr_limit}%**)",
        f"- 지역: {region} (스트레스 가산금리 **+{stress_rate}%p**)\n",
    ]

    # 신규 대출
    lines.append("### 신규 주택담보대출")
    lines.append(f"- 대출원금: **{new_principal_won:,.0f}원** ({new_loan_amount:,.0f}만원)")
    lines.append(f"- 약정금리: {new_loan_rate}%")
    lines.append(f"- 스트레스 금리: {new_loan_rate}% + {stress_rate}%p = **{new_rate_stressed}%**")
    lines.append(f"- 상환기간: {new_loan_months}개월 ({new_loan_months // 12}년)")
    lines.append(f"- 상환방식: {new_loan_method}")
    lines.append(f"- 연간 원리금 상환액: **{new_annual:,.0f}원**\n")

    # 기존 대출
    if existing_details:
        lines.append("### 기존 대출")
        for i, d in enumerate(existing_details, 1):
            lines.append(
                f"- 대출{i} ({d['type']}): {d['amount']:,.0f}원, "
                f"금리 {d['rate']}%+{d['stress']}%p={d['rate_stressed']}%, "
                f"{d['months']}개월, {d['method']}, "
                f"연상환액 {d['annual']:,.0f}원"
            )
        lines.append(f"- **기존 대출 연상환액 합계: {existing_annual_total:,.0f}원**\n")
    else:
        lines.append("### 기존 대출: 없음\n")

    # DSR 결과
    lines.append("### DSR 산출")
    lines.append(f"- 총 연간 원리금 상환액: **{total_annual:,.0f}원**")
    lines.append(f"- 연소득: {income_won:,.0f}원")
    lines.append(f"- **DSR = {total_annual:,.0f} / {income_won:,.0f} × 100 = {dsr:.2f}%**")
    lines.append(f"- DSR 한도: {dsr_limit}%")
    result_emoji = "충족" if is_ok else "초과"
    lines.append(f"- 결과: **{result_emoji}** {'✅ 대출 가능' if is_ok else '❌ DSR 초과로 대출 불가'}\n")

    if not is_ok:
        # 초과 시 가능한 최대 금액 안내
        max_principal = _max_loan_by_dsr(
            income_won, dsr_limit, existing_annual_total,
            new_rate_stressed, new_loan_months, new_loan_method,
        )
        lines.append(f"### DSR 한도 내 최대 대출 가능액")
        lines.append(f"- 동일 조건(금리 {new_rate_stressed}%, {new_loan_months}개월, {new_loan_method}) 기준")
        lines.append(f"- **최대 대출 가능액: 약 {max_principal:,.0f}원 ({max_principal / 10000:,.0f}만원)**\n")

    lines.append("---")
    lines.append("※ 본 계산은 스트레스 DSR 3단계(2025.7.1~) 기준입니다.")
    lines.append("※ 실제 DSR은 금융기관별 세부 산정방식에 따라 다를 수 있습니다.")
    lines.append("※ 보증부 전세대출, 학자금대출(ICL), 500만원 이하 소액대출은 DSR에서 제외됩니다.")

    return "\n".join(lines)


@tool
def calculate_max_mortgage_by_dsr(
    annual_income: float,
    loan_rate: float,
    loan_months: int,
    loan_method: str = "원리금균등",
    region: str = "수도권",
    sector: str = "은행",
    existing_loans: str = "",
) -> str:
    """DSR 한도 내에서 받을 수 있는 최대 주택담보대출 금액을 계산합니다.

    소득과 기존 부채를 고려하여 DSR 규제 한도 내 최대 신규 대출 가능액을 산출합니다.

    Args:
        annual_income: 연소득 (만원 단위, 예: 5000 = 5천만원)
        loan_rate: 예상 대출 연이자율 (%, 예: 4.5)
        loan_months: 희망 상환기간 (개월, 예: 360 = 30년)
        loan_method: 상환방식 ("원리금균등", "원금균등", "만기일시")
        region: 지역 ("수도권", "지방", "규제지역")
        sector: 금융권 ("은행", "2금융")
        existing_loans: 기존 대출 정보 (형식: "잔액(만원):금리(%):잔여개월:상환방식:유형" 여러 건은 | 구분)
    """
    income_won = annual_income * 10000
    dsr_limit = DSR_LIMIT_BANK if sector == "은행" else DSR_LIMIT_NON_BANK
    stress_rate = _get_stress_rate(region, "주담대")
    rate_stressed = loan_rate + stress_rate

    # 기존 대출 처리
    existing_annual_total = 0.0
    existing_details = []

    if existing_loans and existing_loans.strip():
        for entry in existing_loans.split("|"):
            parts = [p.strip() for p in entry.split(":")]
            if len(parts) < 4:
                continue
            ex_amount = float(parts[0]) * 10000
            ex_rate = float(parts[1])
            ex_months = int(parts[2])
            ex_method = parts[3] if len(parts) > 3 else "원리금균등"
            ex_type = parts[4] if len(parts) > 4 else "기타"

            ex_stress = _get_stress_rate(region, ex_type)
            ex_rate_stressed = ex_rate + ex_stress
            ex_annual = calculate_annual_repayment(ex_amount, ex_rate_stressed, ex_months, ex_method)
            existing_annual_total += ex_annual
            existing_details.append({
                "amount": ex_amount,
                "rate": ex_rate,
                "stress": ex_stress,
                "months": ex_months,
                "method": ex_method,
                "type": ex_type,
                "annual": ex_annual,
            })

    # 최대 대출 가능액 산출
    max_principal = _max_loan_by_dsr(
        income_won, dsr_limit, existing_annual_total,
        rate_stressed, loan_months, loan_method,
    )

    max_annual = calculate_annual_repayment(max_principal, rate_stressed, loan_months, loan_method)
    total_annual = existing_annual_total + max_annual
    actual_dsr = (total_annual / income_won) * 100 if income_won > 0 else 0.0

    # --- 결과 ---
    lines = [
        "## DSR 기준 최대 대출 가능액 계산\n",
        "### 입력 조건",
        f"- 연소득: **{income_won:,.0f}원** ({annual_income:,.0f}만원)",
        f"- 금융권: {sector} (DSR 한도 **{dsr_limit}%**)",
        f"- 지역: {region}",
        f"- 약정금리: {loan_rate}%",
        f"- 스트레스 가산금리: +{stress_rate}%p → 적용금리 **{rate_stressed}%**",
        f"- 상환기간: {loan_months}개월 ({loan_months // 12}년)",
        f"- 상환방식: {loan_method}\n",
    ]

    if existing_details:
        lines.append("### 기존 대출 현황")
        for i, d in enumerate(existing_details, 1):
            lines.append(
                f"- 대출{i} ({d['type']}): {d['amount']:,.0f}원, "
                f"연상환액 {d['annual']:,.0f}원"
            )
        lines.append(f"- 기존 대출 연상환액 합계: **{existing_annual_total:,.0f}원**\n")

    lines.append("### 산출 결과")
    dsr_available = income_won * dsr_limit / 100
    new_available = dsr_available - existing_annual_total
    lines.append(f"- DSR 한도 내 총 연상환 가능액: {income_won:,.0f} × {dsr_limit}% = {dsr_available:,.0f}원")
    if existing_annual_total > 0:
        lines.append(f"- 기존 대출 차감 후: {dsr_available:,.0f} - {existing_annual_total:,.0f} = **{new_available:,.0f}원**")
    lines.append(f"- **최대 신규 대출 가능액: {max_principal:,.0f}원 ({max_principal / 10000:,.0f}만원)**")
    lines.append(f"- 예상 DSR: **{actual_dsr:.2f}%** (한도 {dsr_limit}%)\n")

    # 상환방식별 비교
    lines.append("### 상환방식별 최대 대출 가능액 비교")
    lines.append("| 상환방식 | 최대 대출 가능액 | 월 상환액 (약) | 비고 |")
    lines.append("|---------|:-------------:|:-----------:|------|")
    for m in ["원리금균등", "원금균등", "만기일시"]:
        mp = _max_loan_by_dsr(
            income_won, dsr_limit, existing_annual_total,
            rate_stressed, loan_months, m,
        )
        if mp > 0:
            ma = calculate_annual_repayment(mp, rate_stressed, loan_months, m)
            monthly = ma / 12
            note = "← 선택" if m == loan_method else ""
            lines.append(f"| {m} | {mp / 10000:,.0f}만원 | {monthly:,.0f}원 | {note} |")
        else:
            lines.append(f"| {m} | 0원 | - | DSR 초과 |")

    lines.append("")

    # 상환기간별 비교 (선택한 상환방식 기준)
    lines.append(f"### 상환기간별 최대 대출 가능액 ({loan_method} 기준)")
    lines.append("| 상환기간 | 최대 대출 가능액 | 월 상환액 (약) |")
    lines.append("|---------|:-------------:|:-----------:|")
    for years in [10, 15, 20, 25, 30, 35, 40]:
        months = years * 12
        mp = _max_loan_by_dsr(
            income_won, dsr_limit, existing_annual_total,
            rate_stressed, months, loan_method,
        )
        if mp > 0:
            ma = calculate_annual_repayment(mp, rate_stressed, months, loan_method)
            monthly = ma / 12
            marker = " ←" if months == loan_months else ""
            lines.append(f"| {years}년 | {mp / 10000:,.0f}만원 | {monthly:,.0f}원 |{marker}")
        else:
            lines.append(f"| {years}년 | 0원 | - |")

    lines.append("\n---")
    lines.append("※ 스트레스 DSR 3단계(2025.7.1~) 기준, 실제 한도는 LTV 규제와 비교하여 낮은 금액 적용")
    lines.append("※ 규제지역 주택가격대별 한도(15억↓6억, 25억↓4억, 25억↑2억)도 별도 적용됩니다.")
    lines.append("※ KB국민은행 고객센터(1588-9999) 또는 영업점 방문 상담을 권장합니다.")

    return "\n".join(lines)
