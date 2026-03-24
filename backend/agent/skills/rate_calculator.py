"""Interest rate calculator skill."""
from langchain_core.tools import tool


@tool
def calculate_loan_payment(principal: float, annual_rate: float, months: int, method: str = "원리금균등") -> str:
    """대출 원리금 상환액을 계산합니다.

    Args:
        principal: 대출 원금 (만원 단위, 예: 5000 = 5천만원)
        annual_rate: 연 이자율 (%, 예: 4.5)
        months: 상환 기간 (개월)
        method: 상환 방식 ("원리금균등", "원금균등", "만기일시")
    """
    principal_won = principal * 10000  # 만원 -> 원
    monthly_rate = annual_rate / 100 / 12

    if method == "원리금균등":
        if monthly_rate == 0:
            payment = principal_won / months
        else:
            payment = principal_won * monthly_rate * (1 + monthly_rate)**months / ((1 + monthly_rate)**months - 1)
        total = payment * months
        total_interest = total - principal_won
        return f"""## 원리금균등 상환 계산 결과

- 대출원금: {principal_won:,.0f}원 ({principal:,.0f}만원)
- 연이자율: {annual_rate}%
- 상환기간: {months}개월 ({months // 12}년 {months % 12}개월)
- **월 상환액: {payment:,.0f}원**
- 총 상환액: {total:,.0f}원
- 총 이자: {total_interest:,.0f}원
"""

    elif method == "원금균등":
        monthly_principal = principal_won / months
        total_interest = 0
        for i in range(months):
            remaining = principal_won - monthly_principal * i
            interest = remaining * monthly_rate
            total_interest += interest
        first_payment = monthly_principal + principal_won * monthly_rate
        last_payment = monthly_principal + (principal_won - monthly_principal * (months - 1)) * monthly_rate
        return f"""## 원금균등 상환 계산 결과

- 대출원금: {principal_won:,.0f}원
- 연이자율: {annual_rate}%
- 상환기간: {months}개월
- **첫 달 상환액: {first_payment:,.0f}원**
- **마지막 달 상환액: {last_payment:,.0f}원**
- 총 이자: {total_interest:,.0f}원
"""

    elif method == "만기일시":
        monthly_interest = principal_won * monthly_rate
        total_interest = monthly_interest * months
        return f"""## 만기일시 상환 계산 결과

- 대출원금: {principal_won:,.0f}원
- 연이자율: {annual_rate}%
- 상환기간: {months}개월
- **월 이자: {monthly_interest:,.0f}원**
- 만기 시 상환원금: {principal_won:,.0f}원
- 총 이자: {total_interest:,.0f}원
"""
    return "지원하지 않는 상환 방식입니다."


@tool
def calculate_deposit_maturity(principal: float, annual_rate: float, months: int, tax_type: str = "일반과세") -> str:
    """정기예금/적금 만기 수령액을 계산합니다.

    Args:
        principal: 예치금액 (만원 단위)
        annual_rate: 연 이자율 (%)
        months: 예치 기간 (개월)
        tax_type: 과세 유형 ("일반과세", "비과세", "세금우대")
    """
    principal_won = principal * 10000
    interest = principal_won * (annual_rate / 100) * (months / 12)

    tax_rates = {"일반과세": 0.154, "비과세": 0.0, "세금우대": 0.095}
    tax_rate = tax_rates.get(tax_type, 0.154)
    tax = interest * tax_rate
    net_interest = interest - tax
    maturity = principal_won + net_interest

    return f"""## 예금 만기 수령액 계산 결과

- 예치금액: {principal_won:,.0f}원 ({principal:,.0f}만원)
- 연이자율: {annual_rate}%
- 예치기간: {months}개월
- 과세유형: {tax_type}
- 세전이자: {interest:,.0f}원
- 세금: {tax:,.0f}원 ({tax_rate * 100:.1f}%)
- **세후이자: {net_interest:,.0f}원**
- **만기수령액: {maturity:,.0f}원**
"""
