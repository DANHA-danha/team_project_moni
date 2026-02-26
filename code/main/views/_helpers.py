from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from ..models import MoniUser, BankAccount
from ..data import spending_to_dataframe
import pandas as pd


def _current_moni_user(request) -> MoniUser:
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        raise PermissionDenied("authentication required")

    username = getattr(request.user, "username", None)
    if username:
        try:
            return MoniUser.objects.get(ID=username)
        except ObjectDoesNotExist:
            pass

    return MoniUser.objects.get(user_id=request.user.id)


def _current_bank_accounts(moni_user: MoniUser):

    def display_category(category: str) -> str:
        cat = (category or "").strip()
        if cat == "일출금":
            return "입출금"
        return cat or "기타"

    rows_desc = list(
        BankAccount.objects
        .filter(user=moni_user)
        .order_by("-id")
    )

    seen_keys = set()
    batch_desc = []
    for acc in rows_desc:
        key = (acc.category, acc.bank)
        if key in seen_keys and batch_desc:
            break
        seen_keys.add(key)
        batch_desc.append(acc)

    current = list(reversed(batch_desc))

    for acc in current:
        acc.display_category = display_category(acc.category)
        if "대출" in acc.display_category:
            acc.current_balance = -abs(acc.balance or 0)
        else:
            acc.current_balance = acc.balance or 0

    return current

def get_monthly_asset_report(moni_user):
    """
    저축과 투자를 분리하여 계산하고, 월별 자산 현황을 상세히 출력합니다.
    """
    # 1. DB 데이터를 데이터프레임으로 변환 및 정렬
    df = spending_to_dataframe(moni_user)
    if df.empty:
        return "데이터가 없습니다."

    # 2. [타임존 계산] UTC -> Asia/Seoul 변환
    df["trans_dtime"] = pd.to_datetime(df["trans_dtime"])
    
    # 데이터가 타임존 정보가 없는(naive) 경우 localize, 있는(aware) 경우 convert
    if df["trans_dtime"].dt.tz is None:
        df["trans_dtime"] = df["trans_dtime"].dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul')
    else:
        df["trans_dtime"] = df["trans_dtime"].dt.tz_convert('Asia/Seoul')

    # 한국 시간 기준으로 년-월 추출 (이제 1일 아침 거래도 당월로 정확히 계산됨)
    df["year_month"] = df["trans_dtime"].dt.strftime("%Y-%m")
    df = df.sort_values("trans_dtime")

    # 2. 카테고리 정의
    SAVING_CAT = 'savemoney'
    INVEST_CAT = 'investment'

    # 3. 항목별 금액 분류 컬럼 생성
    # - 수입
    df['income_amt'] = df.apply(lambda x: x['amount'] if x['trans_type'] == '입금' else 0, axis=1)
    
    # - 저축액 (예적금 등)
    df['savings_amt'] = df.apply(
        lambda x: x['amount'] if (x['trans_type'] == '출금' and x['category'] == SAVING_CAT) else 0, axis=1
    )
    
    # - 투자액 (주식, 증권 등)
    df['invest_amt'] = df.apply(
        lambda x: x['amount'] if (x['trans_type'] == '출금' and x['category'] == INVEST_CAT) else 0, axis=1
    )
    
    # - 순수 소비액 (저축/투자 제외한 일반 지출)
    df['pure_expense_amt'] = df.apply(
        lambda x: x['amount'] if (x['trans_type'] == '출금' and x['category'] not in [SAVING_CAT, INVEST_CAT]) else 0, axis=1
    )

    # 4. 누적 잔액 및 순자산 계산용 컬럼
    # 통장 잔고: 수입 - (소비 + 저축 + 투자) 모두 차감
    df['cash_diff'] = df['income_amt'] - (df['pure_expense_amt'] + df['savings_amt'] + df['invest_amt'])
    # 순자산: 수입 - 순수소비 (저축/투자는 내 자산으로 남음)
    df['wealth_diff'] = df['income_amt'] - df['pure_expense_amt']

    df['cash_balance'] = df['cash_diff'].cumsum()
    df['net_wealth'] = df['wealth_diff'].cumsum()

    # 5. 월별 집계
    monthly_summary = df.groupby("year_month").agg({
        'income_amt': 'sum',
        'pure_expense_amt': 'sum',
        'savings_amt': 'sum',
        'invest_amt': 'sum',
        'cash_balance': 'last',
        'net_wealth': 'last'
    }).reset_index()

    # 6. 총 자산 축적액 계산 (저축 + 투자)
    monthly_summary['total_asset_acc'] = monthly_summary['savings_amt'] + monthly_summary['invest_amt']

    # 컬럼명 가독성 정리
    monthly_summary.columns = [
        '년-월', '총수입', '순수소비', '저축(현금성)', '투자(자산성)', 
        '통장잔고', '순자산총액', '총자산축적(저축+투자)'
    ]

    print(monthly_summary)
    return monthly_summary

def generate_svg_coords(monthly_report):
    """
    월별 리포트 데이터를 SVG 좌표 문자열로 변환합니다.
    기준 컬럼: '순자산총액'
    """
    # 1. 데이터 추출
    values = monthly_report['순자산총액'].tolist()
    
    # 데이터가 12개가 아닐 경우를 대비해 12개로 맞춤 (부족하면 0으로 채움)
    if len(values) < 12:
        values = [0] * (12 - len(values)) + values
    
    # 2. 정규화 (Y축 계산)
    # SVG 높이가 40이지만, 바닥선을 32, 천장을 8 정도로 잡음 (여백 확보)
    min_val = min(values)
    max_val = max(values)
    val_range = max_val - min_val if max_val != min_val else 1
    
    y_top = 8   # 가장 높은 값의 Y 좌표
    y_bottom = 28  # 가장 낮은 값의 Y 좌표
    
    points = []
    for i, val in enumerate(values):
        # X축: 0, 9, 18, 27... 순으로 계산
        x = i * 9.09 
        # Y축: (최댓값일 때 y_top, 최솟값일 때 y_bottom)
        y = y_bottom - ((val - min_val) / val_range * (y_bottom - y_top))
        points.append((round(x, 1), round(y, 1)))

    # 3. SVG용 문자열 생성
    # Polyline & Dots용: "x1,y1 x2,y2 ..."
    polyline_points = " ".join([f"{x},{y}" for x, y in points])
    
    # Path Area용: "M0,32 L0,y1 L9,y2 ... L100,32 Z"
    path_d = f"M0,32 " + " ".join([f"L{x},{y}" for x, y in points]) + " L100,32 Z"
    
    return {
        'polyline_points': polyline_points,
        'path_d': path_d,
        'points': points  # Circle 생성용 리스트
    }