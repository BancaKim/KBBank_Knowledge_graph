"""DSR (총부채원리금상환비율) 계산 스킬.

금감원 DSR 산정기준을 정확히 반영:
1. 만기일시상환 → 원리금균등 전환 가정 + 대출유형별 산정만기 상한
2. 금리유형별 스트레스 가산금리 차등 적용 (변동 100%, 혼합 60~80%, 고정 0%)
3. 기존대출은 약정금리 기준 (실행 당시 스트레스 반영 여부는 사용자 선택)
4. DSR 한도 내 최대 대출 가능액 역산
"""

from __future__ import annotations

import math

from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# 규제 상수 (2025.10.15 대책 / 스트레스 DSR 3단계 기준)
# ---------------------------------------------------------------------------

DSR_LIMIT_BANK = 40.0   # 은행권 DSR 한도 (%)
DSR_LIMIT_NON_BANK = 50.0  # 2금융권 DSR 한도 (%)

# 스트레스 기본 가산금리 (%p) — 변동금리 100% 기준
STRESS_BASE_RATE: dict[str, float] = {
    "수도권": 3.0,
    "규제지역": 3.0,
    "지방": 0.75,
    "신용대출": 1.5,
    "기타가계": 1.5,
}

# 금리유형별 스트레스 적용 비율 (3단계, 2025.7.1~)
STRESS_RATIO_BY_RATE_TYPE: dict[str, float] = {
    "변동": 1.0,       # 100% — 금리변동주기 5년 미만
    "혼합5년": 0.8,    # 80% — 고정 5~9년 후 변동
    "혼합10년": 0.6,   # 60% — 고정 9~15년 후 변동
    "혼합15년": 0.4,   # 40% — 고정 15~21년 후 변동
    "주기형5년": 0.4,  # 40% — 5~9년 주기
    "주기형10년": 0.3, # 30% — 9~15년 주기
    "주기형15년": 0.2, # 20% — 15~21년 주기
    "고정": 0.0,       # 0% — 만기까지 고정
}

# 대출유형별 만기일시상환 DSR 산정만기 상한 (개월)
BULLET_MATURITY_CAP: dict[str, int] = {
    "주담대": 120,       # 10년
    "신용대출": 60,      # 5년
    "마이너스통장": 120,  # 10년
    "한도대출": 120,     # 10년
    "오피스텔담보": 96,  # 8년
    "전세보증금담보": 48,  # 4년
    "카드론": 36,        # 3년
    "기타": 120,         # 10년 (기본값)
}


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
    """원금균등상환 연간 원리금 상환액 (첫해 기준 — DSR 산정 시 최대값)."""
    if total_months <= 0:
        return 0.0
    monthly_principal = principal / total_months
    monthly_rate = annual_rate / 100 / 12
    total = 0.0
    for i in range(min(12, total_months)):
        remaining = principal - monthly_principal * i
        total += monthly_principal + remaining * monthly_rate
    return total


def _annual_repayment_bullet(
    principal: float,
    annual_rate: float,
    total_months: int,
    loan_type: str = "주담대",
) -> float:
    """만기일시상환 연간 원리금 상환액 (금감원 기준).

    금감원 DSR 산정기준:
    - 만기일시상환은 원리금균등상환으로 **전환(의제)** 하여 계산
    - 산정만기 = min(실제만기, 대출유형별 상한)
    - 주담대 상한 10년, 신용대출 5년, 마통 10년 등
    """
    if total_months <= 0:
        return 0.0
    # 산정만기 상한 적용
    cap_months = BULLET_MATURITY_CAP.get(loan_type, BULLET_MATURITY_CAP["기타"])
    deemed_months = min(total_months, cap_months)
    # 원리금균등으로 전환하여 계산
    return _annual_repayment_equal_installment(principal, annual_rate, deemed_months)


def calculate_annual_repayment(
    principal: float,
    annual_rate: float,
    total_months: int,
    method: str = "원리금균등",
    loan_type: str = "주담대",
) -> float:
    """상환방식에 따른 연간 원리금 상환액 계산 (DSR 산정 기준)."""
    if method == "원리금균등":
        return _annual_repayment_equal_installment(principal, annual_rate, total_months)
    elif method == "원금균등":
        return _annual_repayment_equal_principal(principal, annual_rate, total_months)
    elif method == "만기일시":
        return _annual_repayment_bullet(principal, annual_rate, total_months, loan_type)
    else:
        return _annual_repayment_equal_installment(principal, annual_rate, total_months)


def _get_stress_rate(region: str, loan_type: str, rate_type: str = "변동") -> float:
    """스트레스 가산금리 결정.

    스트레스 가산금리 = 기본 가산금리 × 금리유형별 적용비율

    Args:
        region: 지역 ("수도권", "지방", "규제지역")
        loan_type: 대출유형 ("주담대", "신용대출" 등)
        rate_type: 금리유형 ("변동", "혼합5년", "혼합10년", "고정" 등)
    """
    # 기본 가산금리 결정
    if loan_type == "신용대출":
        base = STRESS_BASE_RATE["신용대출"]
    elif region in ("수도권", "규제지역", "서울"):
        base = STRESS_BASE_RATE["수도권"]
    else:
        base = STRESS_BASE_RATE["지방"]

    # 금리유형별 적용비율
    ratio = STRESS_RATIO_BY_RATE_TYPE.get(rate_type, 1.0)
    return round(base * ratio, 2)


def _parse_existing_loans(existing_loans: str, region: str) -> tuple[float, list[dict]]:
    """기존 대출 문자열을 파싱하여 연간 상환액 합계와 상세 리스트 반환.

    형식: "잔액(만원):금리(%):잔여개월:상환방식:유형:금리유형" (금리유형 생략 시 "변동")
    여러 건은 | 구분.

    기존대출은 약정금리(실행 당시 금리) 기준으로 연상환액을 산정합니다.
    (금감원 규정: 기존대출에는 실행 당시 스트레스 금리가 적용되며,
     신규 강화된 스트레스 금리가 소급 적용되지 않음)
    """
    total = 0.0
    details = []

    if not existing_loans or not existing_loans.strip():
        return total, details

    for entry in existing_loans.split("|"):
        parts = [p.strip() for p in entry.split(":")]
        if len(parts) < 3:
            continue
        ex_amount = float(parts[0]) * 10000
        ex_rate = float(parts[1])
        ex_months = int(parts[2])
        ex_method = parts[3] if len(parts) > 3 else "원리금균등"
        ex_type = parts[4] if len(parts) > 4 else "기타"
        ex_rate_type = parts[5] if len(parts) > 5 else "변동"

        # 기존대출: 약정금리 기준 연상환액 (스트레스 미가산)
        ex_annual = calculate_annual_repayment(
            ex_amount, ex_rate, ex_months, ex_method, ex_type,
        )
        total += ex_annual
        details.append({
            "amount": ex_amount,
            "rate": ex_rate,
            "months": ex_months,
            "method": ex_method,
            "type": ex_type,
            "rate_type": ex_rate_type,
            "annual": ex_annual,
        })

    return total, details


def _max_loan_by_dsr(
    annual_income: float,
    dsr_limit: float,
    existing_annual_repayment: float,
    annual_rate_with_stress: float,
    total_months: int,
    method: str,
    loan_type: str = "주담대",
) -> float:
    """DSR 한도 내 최대 신규 대출 가능 원금 역산.

    DSR = (기존부채 연상환액 + 신규대출 연상환액) / 연소득 × 100 ≤ dsr_limit

    원리금균등의 경우 closed-form 역산 가능:
      허용 월상환액 M = (연소득 × DSR한도/100 - 기존연상환액) / 12
      최대원금 P = M × [(1+r)^n - 1] / [r × (1+r)^n]
    원금균등/만기일시는 이진탐색 사용.
    """
    max_new_annual = annual_income * dsr_limit / 100 - existing_annual_repayment
    if max_new_annual <= 0:
        return 0.0

    monthly_rate = annual_rate_with_stress / 100 / 12

    # 원리금균등: closed-form 역산
    if method == "원리금균등" and monthly_rate > 0:
        max_monthly = max_new_annual / 12
        n = total_months
        principal = max_monthly * ((1 + monthly_rate) ** n - 1) / (
            monthly_rate * (1 + monthly_rate) ** n
        )
        return math.floor(principal / 10000) * 10000

    # 원금균등/만기일시: 이진탐색
    lo, hi = 0.0, annual_income * 50
    for _ in range(100):
        mid = (lo + hi) / 2
        repay = calculate_annual_repayment(
            mid, annual_rate_with_stress, total_months, method, loan_type,
        )
        if repay <= max_new_annual:
            lo = mid
        else:
            hi = mid
    return math.floor(lo / 10000) * 10000


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
    new_loan_rate_type: str = "변동",
    region: str = "수도권",
    sector: str = "은행",
    existing_loans: str = "",
) -> str:
    """DSR(총부채원리금상환비율)을 계산하고 규제 충족 여부를 판단합니다.

    신규 주택담보대출의 DSR을 스트레스 금리 포함하여 금감원 기준으로 산출합니다.

    Args:
        annual_income: 연소득 (만원 단위, 예: 5000 = 5천만원)
        new_loan_amount: 신규 대출 원금 (만원 단위, 예: 30000 = 3억원)
        new_loan_rate: 신규 대출 약정 연이자율 (%, 예: 4.5)
        new_loan_months: 신규 대출 상환기간 (개월, 예: 360 = 30년)
        new_loan_method: 상환방식 ("원리금균등", "원금균등", "만기일시")
        new_loan_rate_type: 금리유형 ("변동", "혼합5년", "혼합10년", "고정" 등)
        region: 지역 ("수도권", "지방", "규제지역")
        sector: 금융권 ("은행", "2금융")
        existing_loans: 기존 대출 정보 (형식: "잔액(만원):금리(%):잔여개월:상환방식:유형:금리유형"
            여러 건은 | 구분, 예: "5000:5.0:48:원리금균등:신용대출:변동|10000:3.5:240:원리금균등:주담대:혼합5년")
    """
    income_won = annual_income * 10000
    new_principal_won = new_loan_amount * 10000
    dsr_limit = DSR_LIMIT_BANK if sector == "은행" else DSR_LIMIT_NON_BANK

    # --- 기존 대출 연간 상환액 (약정금리 기준) ---
    existing_annual_total, existing_details = _parse_existing_loans(existing_loans, region)

    # --- 신규 대출 스트레스 금리 반영 ---
    stress_rate = _get_stress_rate(region, "주담대", new_loan_rate_type)
    new_rate_stressed = new_loan_rate + stress_rate
    new_annual = calculate_annual_repayment(
        new_principal_won, new_rate_stressed, new_loan_months, new_loan_method, "주담대",
    )

    # --- DSR 계산 ---
    total_annual = existing_annual_total + new_annual
    dsr = (total_annual / income_won) * 100 if income_won > 0 else 999.0
    is_ok = dsr <= dsr_limit

    # --- 결과 포맷 ---
    stress_ratio = STRESS_RATIO_BY_RATE_TYPE.get(new_loan_rate_type, 1.0)
    stress_base = _get_stress_rate(region, "주담대", "변동")  # 100% 기준

    lines = [
        "## DSR 계산 결과\n",
        "### 기본 정보",
        f"- 연소득: **{income_won:,.0f}원** ({annual_income:,.0f}만원)",
        f"- 금융권: {sector} (DSR 한도 **{dsr_limit}%**)",
        f"- 지역: {region}\n",
    ]

    # 신규 대출
    lines.append("### 신규 주택담보대출")
    lines.append(f"- 대출원금: **{new_principal_won:,.0f}원** ({new_loan_amount:,.0f}만원)")
    lines.append(f"- 약정금리: {new_loan_rate}%")
    lines.append(f"- 금리유형: {new_loan_rate_type} (스트레스 적용비율 {stress_ratio * 100:.0f}%)")
    lines.append(f"- 스트레스 가산금리: {stress_base}%p × {stress_ratio * 100:.0f}% = **+{stress_rate}%p**")
    lines.append(f"- DSR 산정금리: {new_loan_rate}% + {stress_rate}%p = **{new_rate_stressed}%**")
    lines.append(f"- 상환기간: {new_loan_months}개월 ({new_loan_months // 12}년)")
    lines.append(f"- 상환방식: {new_loan_method}")
    if new_loan_method == "만기일시":
        cap = BULLET_MATURITY_CAP["주담대"]
        deemed = min(new_loan_months, cap)
        lines.append(f"- DSR 산정: 원리금균등 전환 가정, 산정만기 {deemed}개월({deemed // 12}년) 적용")
    lines.append(f"- 연간 원리금 상환액: **{new_annual:,.0f}원** (월 {new_annual / 12:,.0f}원)\n")

    # 기존 대출
    if existing_details:
        lines.append("### 기존 대출 (약정금리 기준)")
        for i, d in enumerate(existing_details, 1):
            method_note = ""
            if d["method"] == "만기일시":
                cap = BULLET_MATURITY_CAP.get(d["type"], BULLET_MATURITY_CAP["기타"])
                deemed = min(d["months"], cap)
                method_note = f" → 원리금균등전환({deemed // 12}년)"
            lines.append(
                f"- 대출{i} ({d['type']}): {d['amount']:,.0f}원, "
                f"금리 {d['rate']}%, "
                f"{d['months']}개월, {d['method']}{method_note}, "
                f"연상환액 {d['annual']:,.0f}원"
            )
        lines.append(f"- **기존 대출 연상환액 합계: {existing_annual_total:,.0f}원**\n")
    else:
        lines.append("### 기존 대출: 없음\n")

    # DSR 결과
    lines.append("### DSR 산출")
    lines.append(f"- 총 연간 원리금 상환액: **{total_annual:,.0f}원**")
    lines.append(f"  - 신규대출: {new_annual:,.0f}원 (스트레스 금리 반영)")
    if existing_annual_total > 0:
        lines.append(f"  - 기존대출: {existing_annual_total:,.0f}원 (약정금리 기준)")
    lines.append(f"- 연소득: {income_won:,.0f}원")
    lines.append(f"- **DSR = {total_annual:,.0f} / {income_won:,.0f} × 100 = {dsr:.2f}%**")
    lines.append(f"- DSR 한도: {dsr_limit}%")
    result_text = "충족" if is_ok else "초과"
    lines.append(f"- 결과: **{result_text}** {'- 대출 가능' if is_ok else '- DSR 초과로 대출 불가'}\n")

    if not is_ok:
        max_principal = _max_loan_by_dsr(
            income_won, dsr_limit, existing_annual_total,
            new_rate_stressed, new_loan_months, new_loan_method, "주담대",
        )
        lines.append("### DSR 한도 내 최대 대출 가능액")
        lines.append(f"- 동일 조건(금리 {new_rate_stressed}%, {new_loan_months}개월, {new_loan_method}) 기준")
        lines.append(f"- **최대 대출 가능액: 약 {max_principal:,.0f}원 ({max_principal / 10000:,.0f}만원)**\n")

    lines.append("---")
    lines.append("※ 금감원 DSR 산정기준 적용 (스트레스 DSR 3단계, 2025.7.1~)")
    lines.append("※ 만기일시상환은 원리금균등 전환 가정, 대출유형별 산정만기 상한 적용")
    lines.append("※ 기존대출은 약정금리 기준 연상환액 산정 (실행 당시 스트레스 반영)")
    lines.append("※ 보증부 전세대출, 학자금대출(ICL), 500만원 이하 소액대출은 DSR 제외")
    lines.append("※ 실제 DSR은 금융기관별 세부 산정방식에 따라 다를 수 있습니다.")

    return "\n".join(lines)


@tool
def calculate_max_mortgage_by_dsr(
    annual_income: float,
    loan_rate: float,
    loan_months: int,
    loan_method: str = "원리금균등",
    loan_rate_type: str = "변동",
    region: str = "수도권",
    sector: str = "은행",
    existing_loans: str = "",
) -> str:
    """DSR 한도 내에서 받을 수 있는 최대 주택담보대출 금액을 계산합니다.

    소득과 기존 부채를 고려하여 DSR 규제 한도 내 최대 신규 대출 가능액을 산출합니다.
    상환방식별·기간별 비교표도 함께 제공합니다.

    Args:
        annual_income: 연소득 (만원 단위, 예: 5000 = 5천만원)
        loan_rate: 예상 대출 약정 연이자율 (%, 예: 4.5)
        loan_months: 희망 상환기간 (개월, 예: 360 = 30년)
        loan_method: 상환방식 ("원리금균등", "원금균등", "만기일시")
        loan_rate_type: 금리유형 ("변동", "혼합5년", "혼합10년", "고정" 등)
        region: 지역 ("수도권", "지방", "규제지역")
        sector: 금융권 ("은행", "2금융")
        existing_loans: 기존 대출 정보 (형식: "잔액(만원):금리(%):잔여개월:상환방식:유형:금리유형"
            여러 건은 | 구분)
    """
    income_won = annual_income * 10000
    dsr_limit = DSR_LIMIT_BANK if sector == "은행" else DSR_LIMIT_NON_BANK
    stress_rate = _get_stress_rate(region, "주담대", loan_rate_type)
    rate_stressed = loan_rate + stress_rate
    stress_ratio = STRESS_RATIO_BY_RATE_TYPE.get(loan_rate_type, 1.0)
    stress_base = _get_stress_rate(region, "주담대", "변동")

    # 기존 대출 처리 (약정금리 기준)
    existing_annual_total, existing_details = _parse_existing_loans(existing_loans, region)

    # 최대 대출 가능액 산출
    max_principal = _max_loan_by_dsr(
        income_won, dsr_limit, existing_annual_total,
        rate_stressed, loan_months, loan_method, "주담대",
    )

    max_annual = calculate_annual_repayment(
        max_principal, rate_stressed, loan_months, loan_method, "주담대",
    )
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
        f"- 금리유형: {loan_rate_type} (스트레스 적용비율 {stress_ratio * 100:.0f}%)",
        f"- 스트레스 가산금리: {stress_base}%p × {stress_ratio * 100:.0f}% = **+{stress_rate}%p**",
        f"- DSR 산정금리: {loan_rate}% + {stress_rate}%p = **{rate_stressed}%**",
        f"- 상환기간: {loan_months}개월 ({loan_months // 12}년)",
        f"- 상환방식: {loan_method}",
    ]
    if loan_method == "만기일시":
        cap = BULLET_MATURITY_CAP["주담대"]
        deemed = min(loan_months, cap)
        lines.append(f"- DSR 산정: 원리금균등 전환, 산정만기 {deemed}개월({deemed // 12}년)")
    lines.append("")

    if existing_details:
        lines.append("### 기존 대출 현황 (약정금리 기준)")
        for i, d in enumerate(existing_details, 1):
            method_note = ""
            if d["method"] == "만기일시":
                cap = BULLET_MATURITY_CAP.get(d["type"], BULLET_MATURITY_CAP["기타"])
                deemed = min(d["months"], cap)
                method_note = f" → 전환({deemed // 12}년)"
            lines.append(
                f"- 대출{i} ({d['type']}): {d['amount']:,.0f}원, "
                f"금리 {d['rate']}%, {d['method']}{method_note}, "
                f"연상환액 {d['annual']:,.0f}원"
            )
        lines.append(f"- 기존 대출 연상환액 합계: **{existing_annual_total:,.0f}원**\n")

    lines.append("### 산출 결과")
    dsr_available = income_won * dsr_limit / 100
    new_available = dsr_available - existing_annual_total
    lines.append(f"- DSR 한도 내 총 연상환 가능액: {income_won:,.0f} × {dsr_limit}% = **{dsr_available:,.0f}원**")
    if existing_annual_total > 0:
        lines.append(f"- 기존 대출 차감 후 잔여: {dsr_available:,.0f} - {existing_annual_total:,.0f} = **{new_available:,.0f}원**")
    lines.append(f"- **최대 신규 대출 가능액: {max_principal:,.0f}원 ({max_principal / 10000:,.0f}만원)**")
    lines.append(f"- 이때 월 상환액: **{max_annual / 12:,.0f}원**")
    lines.append(f"- 예상 DSR: **{actual_dsr:.2f}%** (한도 {dsr_limit}%)\n")

    # 상환방식별 비교
    lines.append("### 상환방식별 최대 대출 가능액 비교")
    lines.append("| 상환방식 | 최대 대출 가능액 | 월 상환액 (약) | 비고 |")
    lines.append("|---------|:-------------:|:-----------:|------|")
    for m in ["원리금균등", "원금균등", "만기일시"]:
        mp = _max_loan_by_dsr(
            income_won, dsr_limit, existing_annual_total,
            rate_stressed, loan_months, m, "주담대",
        )
        if mp > 0:
            ma = calculate_annual_repayment(mp, rate_stressed, loan_months, m, "주담대")
            monthly = ma / 12
            note = " **선택**" if m == loan_method else ""
            lines.append(f"| {m} | {mp / 10000:,.0f}만원 | {monthly:,.0f}원 | {note} |")
        else:
            lines.append(f"| {m} | 0원 | - | DSR 초과 |")

    lines.append("")

    # 상환기간별 비교
    lines.append(f"### 상환기간별 최대 대출 가능액 ({loan_method} 기준)")
    lines.append("| 상환기간 | 최대 대출 가능액 | 월 상환액 (약) |")
    lines.append("|---------|:-------------:|:-----------:|")
    for years in [10, 15, 20, 25, 30, 35, 40]:
        months = years * 12
        mp = _max_loan_by_dsr(
            income_won, dsr_limit, existing_annual_total,
            rate_stressed, months, loan_method, "주담대",
        )
        if mp > 0:
            ma = calculate_annual_repayment(mp, rate_stressed, months, loan_method, "주담대")
            monthly = ma / 12
            marker = " **<-**" if months == loan_months else ""
            lines.append(f"| {years}년 | {mp / 10000:,.0f}만원 | {monthly:,.0f}원 |{marker}")
        else:
            lines.append(f"| {years}년 | 0원 | - |")

    # 금리유형별 비교 (고정 vs 변동 차이 보여주기)
    lines.append("")
    lines.append(f"### 금리유형별 최대 대출 가능액 ({loan_method}, {loan_months // 12}년)")
    lines.append("| 금리유형 | 스트레스 가산 | DSR 산정금리 | 최대 대출 가능액 |")
    lines.append("|---------|:----------:|:----------:|:-------------:|")
    for rt_name, rt_ratio in [("변동", "변동"), ("혼합5년", "혼합5년"), ("혼합10년", "혼합10년"), ("고정", "고정")]:
        sr = _get_stress_rate(region, "주담대", rt_ratio)
        rr = loan_rate + sr
        mp = _max_loan_by_dsr(
            income_won, dsr_limit, existing_annual_total,
            rr, loan_months, loan_method, "주담대",
        )
        marker = " **<-**" if rt_ratio == loan_rate_type else ""
        lines.append(f"| {rt_name} | +{sr}%p | {rr}% | {mp / 10000:,.0f}만원 |{marker}")

    lines.append("\n---")
    lines.append("※ 금감원 DSR 산정기준 적용 (스트레스 DSR 3단계, 2025.7.1~)")
    lines.append("※ 실제 한도는 LTV 규제와 비교하여 낮은 금액 적용")
    lines.append("※ 규제지역 주택가격대별 한도(15억↓6억, 25억↓4억, 25억↑2억)도 별도 적용")
    lines.append("※ KB국민은행 고객센터(1588-9999) 또는 영업점 방문 상담을 권장합니다.")

    return "\n".join(lines)
