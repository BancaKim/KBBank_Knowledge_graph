"""LTV (담보인정비율) 기반 대출 한도 계산 스킬.

2025.10.15 대책 반영:
1. 규제지역 LTV: 무주택 40%, 생애최초 70%, 1주택처분조건 50%
2. 비규제지역 LTV: 무주택 70%, 생애최초 80%
3. 주택가격대별 한도 상한: 15억↓6억, 25억↓4억, 25억↑2억 (규제지역)
4. 소액임차보증금 차감
5. 선순위 대출·임차보증금 차감
"""

from __future__ import annotations

import math

from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# 규제 상수 (2025.10.15 대책 기준)
# ---------------------------------------------------------------------------

# LTV 비율 (%) — {규제여부: {차주유형: LTV비율}}
LTV_RATIO: dict[str, dict[str, float]] = {
    "규제지역": {
        "무주택": 40.0,
        "생애최초": 70.0,
        "1주택_처분조건": 50.0,
        "1주택": 0.0,       # 처분조건 미충족 시 불가
        "다주택": 0.0,       # 대출 불가
    },
    "비규제지역": {
        "무주택": 70.0,
        "생애최초": 80.0,
        "1주택_처분조건": 70.0,
        "1주택": 70.0,
        "다주택": 60.0,
    },
}

# 주택가격대별 한도 상한 (규제지역, 만원 단위)
PRICE_TIER_CAP_REGULATED: list[tuple[float, float]] = [
    (150000, 60000),  # 15억 이하 → 최대 6억
    (250000, 40000),  # 15억 초과 ~ 25억 이하 → 최대 4억
    (float("inf"), 20000),  # 25억 초과 → 최대 2억
]

# 생애최초 한도 상한 (규제지역, 만원)
FIRST_TIME_CAP = 60000  # 6억

# 소액임차보증금 (지역별, 만원 단위, 2025년 기준)
SMALL_DEPOSIT_BY_REGION: dict[str, float] = {
    "서울": 5500,
    "수도권_과밀억제": 4800,
    "광역시": 2800,
    "기타": 2000,
}

# 지역 → 규제지역/비규제지역 매핑
REGULATED_REGIONS = {"서울", "강남", "서초", "송파", "용산", "수도권", "규제지역"}


# ---------------------------------------------------------------------------
# 내부 계산 함수
# ---------------------------------------------------------------------------

def _resolve_regulation_zone(region: str) -> str:
    """지역명을 규제지역/비규제지역으로 매핑."""
    if region in REGULATED_REGIONS or "규제" in region:
        return "규제지역"
    return "비규제지역"


def _resolve_borrower_type(
    is_first_time: bool,
    num_homes: int,
    disposal_condition: bool = False,
) -> str:
    """차주 유형 결정."""
    if num_homes == 0:
        return "생애최초" if is_first_time else "무주택"
    elif num_homes == 1:
        return "1주택_처분조건" if disposal_condition else "1주택"
    else:
        return "다주택"


def _get_ltv_ratio(zone: str, borrower_type: str) -> float:
    """LTV 비율 조회."""
    zone_ratios = LTV_RATIO.get(zone, LTV_RATIO["비규제지역"])
    return zone_ratios.get(borrower_type, 0.0)


def _get_price_tier_cap(property_value: float, zone: str) -> float:
    """주택가격대별 한도 상한 (만원). 규제지역에만 적용."""
    if zone != "규제지역":
        return float("inf")
    for threshold, cap in PRICE_TIER_CAP_REGULATED:
        if property_value <= threshold:
            return cap
    return PRICE_TIER_CAP_REGULATED[-1][1]


def _get_small_deposit(region: str, num_rooms: int, is_apartment: bool) -> float:
    """소액임차보증금 차감액 (만원).

    아파트: 1실로 고정 (차감 없음 또는 최소)
    일반주택: (방 수 - 1) × 소액임차보증금
    """
    if is_apartment:
        # 아파트는 호수당 1실로 간주 → (1-1)=0 → 차감 없음
        return 0.0
    if num_rooms <= 1:
        return 0.0

    # 지역별 소액임차보증금 결정
    if "서울" in region:
        deposit = SMALL_DEPOSIT_BY_REGION["서울"]
    elif region in ("경기", "인천", "수도권", "수도권_과밀억제"):
        deposit = SMALL_DEPOSIT_BY_REGION["수도권_과밀억제"]
    elif region in ("부산", "대구", "광주", "대전", "울산", "세종"):
        deposit = SMALL_DEPOSIT_BY_REGION["광역시"]
    else:
        deposit = SMALL_DEPOSIT_BY_REGION["기타"]

    return (num_rooms - 1) * deposit


def _calculate_ltv_limit(
    property_value: float,
    zone: str,
    borrower_type: str,
    prior_loans: float = 0.0,
    lease_deposit: float = 0.0,
    small_deposit: float = 0.0,
) -> dict:
    """LTV 기반 대출 한도 계산 (만원 단위).

    Returns:
        dict with ltv_ratio, gross_limit, deductions, net_limit, price_cap, final_limit
    """
    ltv_ratio = _get_ltv_ratio(zone, borrower_type)

    if ltv_ratio == 0:
        return {
            "ltv_ratio": 0.0,
            "gross_limit": 0.0,
            "prior_loans": prior_loans,
            "lease_deposit": lease_deposit,
            "small_deposit": small_deposit,
            "net_limit": 0.0,
            "price_cap": 0.0,
            "first_time_cap": 0.0,
            "final_limit": 0.0,
            "binding_constraint": "대출불가",
        }

    gross_limit = property_value * ltv_ratio / 100
    deductions = prior_loans + lease_deposit + small_deposit
    net_limit = max(0, gross_limit - deductions)

    price_cap = _get_price_tier_cap(property_value, zone)

    # 생애최초 상한
    first_time_cap = FIRST_TIME_CAP if borrower_type == "생애최초" and zone == "규제지역" else float("inf")

    final_limit = min(net_limit, price_cap, first_time_cap)
    final_limit = math.floor(final_limit / 100) * 100  # 100만원 단위 절사

    # 제약 요인 판별
    if net_limit <= 0:
        binding = "차감액 초과 (선순위+보증금)"
    elif final_limit == price_cap and price_cap < net_limit:
        binding = f"주택가격대별 상한 ({price_cap:,.0f}만원)"
    elif final_limit == first_time_cap and first_time_cap < net_limit:
        binding = f"생애최초 상한 ({first_time_cap:,.0f}만원)"
    else:
        binding = "LTV 비율"

    return {
        "ltv_ratio": ltv_ratio,
        "gross_limit": gross_limit,
        "prior_loans": prior_loans,
        "lease_deposit": lease_deposit,
        "small_deposit": small_deposit,
        "net_limit": net_limit,
        "price_cap": price_cap if price_cap != float("inf") else None,
        "first_time_cap": first_time_cap if first_time_cap != float("inf") else None,
        "final_limit": final_limit,
        "binding_constraint": binding,
    }


# ---------------------------------------------------------------------------
# LangChain Tools
# ---------------------------------------------------------------------------

@tool
def calculate_ltv_limit(
    property_value: float,
    region: str = "수도권",
    is_first_time: bool = False,
    num_homes: int = 0,
    disposal_condition: bool = False,
    prior_loans: float = 0.0,
    lease_deposit: float = 0.0,
    num_rooms: int = 1,
    is_apartment: bool = True,
) -> str:
    """LTV(담보인정비율) 기반 주택담보대출 최대 한도를 계산합니다.

    아파트/주택 시세를 기반으로 규제지역/비규제지역, 차주 유형에 따른
    LTV 한도를 계산합니다. 선순위대출, 임차보증금, 소액임차보증금을 차감하고
    주택가격대별 상한도 적용합니다.

    Args:
        property_value: 주택 시세 (만원 단위, 예: 50000 = 5억원)
        region: 지역 ("서울", "수도권", "규제지역", "경기", "지방" 등)
        is_first_time: 생애최초 주택구입 여부
        num_homes: 현재 보유 주택 수 (0=무주택, 1=1주택, 2+=다주택)
        disposal_condition: 1주택자의 경우 기존주택 6개월 내 처분 조건 수용 여부
        prior_loans: 동일 담보물건 선순위 대출 잔액 (만원 단위)
        lease_deposit: 동일 물건 임차보증금 합계 (만원 단위)
        num_rooms: 방 수 (소액임차보증금 계산용, 아파트는 무관)
        is_apartment: 아파트 여부 (True=아파트, False=다세대/연립 등)
    """
    zone = _resolve_regulation_zone(region)
    borrower_type = _resolve_borrower_type(is_first_time, num_homes, disposal_condition)
    small_deposit = _get_small_deposit(region, num_rooms, is_apartment)

    result = _calculate_ltv_limit(
        property_value, zone, borrower_type,
        prior_loans, lease_deposit, small_deposit,
    )

    # --- 결과 포맷 ---
    lines = [
        "## LTV 기준 대출 한도 계산\n",
        "### 입력 조건",
        f"- 주택 시세: **{property_value:,.0f}만원** ({property_value / 10000:.1f}억원)",
        f"- 지역: {region} → **{zone}**",
        f"- 주택유형: {'아파트' if is_apartment else '다세대/연립/단독'}",
        f"- 차주유형: **{borrower_type}** "
        f"({'생애최초' if is_first_time else ''}"
        f"{'무주택' if num_homes == 0 and not is_first_time else ''}"
        f"{f'{num_homes}주택' if num_homes > 0 else ''})",
    ]

    if prior_loans > 0:
        lines.append(f"- 선순위 대출: {prior_loans:,.0f}만원")
    if lease_deposit > 0:
        lines.append(f"- 임차보증금: {lease_deposit:,.0f}만원")
    if small_deposit > 0:
        lines.append(f"- 소액임차보증금: {small_deposit:,.0f}만원 (방 {num_rooms}개)")
    lines.append("")

    if result["ltv_ratio"] == 0:
        lines.append("### 결과")
        lines.append(f"- **{zone}에서 {borrower_type}는 주택담보대출이 불가합니다.**")
        if num_homes >= 2:
            lines.append("- 다주택자는 규제지역에서 주택담보대출이 제한됩니다.")
        elif num_homes == 1 and not disposal_condition:
            lines.append("- 1주택자는 기존주택 6개월 내 처분 조건 수용 시 LTV 50% 적용 가능합니다.")
        lines.append("\n---")
        lines.append("※ 2025.10.15 대책 기준")
        return "\n".join(lines)

    lines.append("### LTV 산출")
    lines.append(f"- 적용 LTV: **{result['ltv_ratio']}%**")
    lines.append(f"- LTV 기준 대출액: {property_value:,.0f} × {result['ltv_ratio']}% = **{result['gross_limit']:,.0f}만원**")

    total_deduction = prior_loans + lease_deposit + small_deposit
    if total_deduction > 0:
        lines.append(f"\n### 차감 항목")
        if prior_loans > 0:
            lines.append(f"- 선순위 대출: -{prior_loans:,.0f}만원")
        if lease_deposit > 0:
            lines.append(f"- 임차보증금: -{lease_deposit:,.0f}만원")
        if small_deposit > 0:
            lines.append(f"- 소액임차보증금: -{small_deposit:,.0f}만원")
        lines.append(f"- 차감 후: {result['gross_limit']:,.0f} - {total_deduction:,.0f} = **{result['net_limit']:,.0f}만원**")

    lines.append(f"\n### 한도 상한 적용")
    if result["price_cap"] is not None:
        lines.append(f"- 주택가격대별 상한: **{result['price_cap']:,.0f}만원**")
    else:
        lines.append("- 주택가격대별 상한: 해당 없음 (비규제지역)")
    if result["first_time_cap"] is not None:
        lines.append(f"- 생애최초 상한: **{result['first_time_cap']:,.0f}만원**")

    lines.append(f"\n### 최종 결과")
    lines.append(f"- **LTV 기준 최대 대출 한도: {result['final_limit']:,.0f}만원 ({result['final_limit'] / 10000:.1f}억원)**")
    lines.append(f"- 제약 요인: {result['binding_constraint']}")

    # 차주유형별 비교표
    lines.append(f"\n### 차주유형별 LTV 비교 ({zone})")
    lines.append("| 차주유형 | LTV | 최대 대출액 | 비고 |")
    lines.append("|---------|:---:|:----------:|------|")
    for bt in ["무주택", "생애최초", "1주택_처분조건"]:
        ratio = _get_ltv_ratio(zone, bt)
        if ratio > 0:
            gross = property_value * ratio / 100
            cap = _get_price_tier_cap(property_value, zone)
            ft_cap = FIRST_TIME_CAP if bt == "생애최초" and zone == "규제지역" else float("inf")
            limit = min(max(0, gross - prior_loans - lease_deposit - small_deposit), cap, ft_cap)
            limit = math.floor(limit / 100) * 100
            marker = " **← 현재**" if bt == borrower_type else ""
            lines.append(f"| {bt} | {ratio}% | {limit:,.0f}만원 | {marker} |")
        else:
            lines.append(f"| {bt} | 0% | 불가 | |")

    lines.append("\n---")
    lines.append("※ 2025.6.27 대책 + 10.15 대책 기준")
    lines.append("※ 실제 LTV는 KB시세·감정가·공시지가 중 낮은 금액 기준으로 산정됩니다.")
    lines.append("※ 이 결과는 참고용이며, 최종 한도는 은행 심사를 통해 결정됩니다.")
    lines.append("※ DSR 한도와 비교하여 낮은 금액이 실제 대출 가능액입니다.")

    return "\n".join(lines)
