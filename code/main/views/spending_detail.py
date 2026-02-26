from email.mime import base
from urllib import request
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone

from main.models import Type, SpendingTypeJob
from ._helpers import _current_moni_user
import calendar
from datetime import date
import datetime
import json

import pandas as pd
import numpy as np
import lightgbm as lgb
from datetime import timedelta
import google.generativeai as genai
import time
from tqdm import tqdm

from django.utils import timezone
from main.models import Spending, Notification
from main.data import use_gemini_api, spending_to_dataframe


CATEGORY_LABELS_KO = {
    "shopping": "쇼핑",
    "entertainment": "여가",
    "transport": "교통",
    "food": "식비",
    "beauty": "뷰티",
    "investment": "투자",
    "living": "생활",
    "savemoney": "저축",
    "coffee": "카페",
    "income": "수입",
    "health": "건강",
    "etc": "기타",
}


@login_required
def spending_type(request):
    moni_user = _current_moni_user(request)

    preview = request.GET.get("preview")  # 예: "1", "2", ...
    preview_type = None
    if preview:
        try:
            preview_type = Type.objects.get(type_id=int(preview))
        except (ValueError, Type.DoesNotExist):
            preview_type = None

    analysis_job = (
        SpendingTypeJob.objects.filter(user=moni_user)
        .order_by("-created_at", "-id")
        .first()
    )

    is_spending_type_loading = False

    if analysis_job and analysis_job.status == "DONE":
        user_type = analysis_job.result_type or moni_user.type
    else:
        user_type = moni_user.type

    display_type = preview_type or user_type
    explanation_sentences = []
    if display_type and display_type.explanation2:
        explanation_sentences = [
            s.strip()
            for s in display_type.explanation2.split(".")
            if s.strip()
        ]
    return render(
        request,
        "spending_type.html",
        {
            "page": "spending_type",
            "active_menu": "spending_type",
            "user": moni_user,
            "user_type": user_type,
            "display_type": display_type,
            "preview_type": preview_type,
            "is_spending_type_loading": is_spending_type_loading,
            "explanation_sentences": explanation_sentences,
        },
    )


# Utils
def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def money_to_int(value):
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def is_income(transaction_type: str) -> bool:
    """transaction_type: '입금' | '출금'"""
    return transaction_type == "입금"


# Builders
def build_month_days(moni_user, year: int, month: int):
    """
    템플릿용 days 생성
    - 일요일 시작 달력
    - placeholder 포함
    - 각 day: {day, income, expense}
    """
    start = timezone.make_aware(datetime.datetime(year, month, 1, 0, 0, 0))
    if month == 12:
        end = timezone.make_aware(datetime.datetime(year + 1, 1, 1, 0, 0, 0))
    else:
        end = timezone.make_aware(datetime.datetime(year, month + 1, 1, 0, 0, 0))

    qs = (
        Spending.objects.filter(
            user=moni_user,
            spend_date__gte=start,
            spend_date__lt=end,
        )
        .values_list("spend_date", "price", "transaction_type")
        .iterator()
    )

    # 일자별 합계
    totals_by_day = {}
    for spend_dt, price, tx_type in qs:
        day = timezone.localtime(spend_dt).day
        bucket = totals_by_day.setdefault(day, {"income": 0, "expense": 0})

        amount = money_to_int(price)
        if is_income(tx_type):
            bucket["income"] += amount
        else:
            bucket["expense"] += amount

    # 달력 placeholder 계산 (일요일 시작)
    first_weekday_mon0, last_day = calendar.monthrange(year, month)
    first_weekday_sun0 = (first_weekday_mon0 + 1) % 7

    days = []

    # placeholder
    for _ in range(first_weekday_sun0):
        days.append({"day": None, "income": None, "expense": None})

    # 실제 날짜
    for d in range(1, last_day + 1):
        totals = totals_by_day.get(d)
        days.append(
            {
                "day": d,
                "income": totals["income"] if totals and totals["income"] else None,
                "expense": totals["expense"] if totals and totals["expense"] else None,
            }
        )

    return days, bool(totals_by_day)


def build_day_transactions(moni_user, target_date: datetime):
    start = timezone.make_aware(
        datetime.datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
    )
    end = start + datetime.timedelta(days=1)

    qs = (
        Spending.objects.filter(
            user=moni_user,
            spend_date__gte=start,
            spend_date__lt=end,
        )
        .order_by("-spend_date", "-spending_id")
        .only(
            "spending_id",
            "details",
            "category",
            "price",
            "transaction_type",
            "memo",
            "spend_date",
        )
    )

    transactions = []
    for s in qs:
        amount = money_to_int(s.price)
        signed_amount = amount if is_income(s.transaction_type) else -amount

        raw_category = (s.category or "").strip()
        category_ko = CATEGORY_LABELS_KO.get(raw_category, raw_category)

        transactions.append(
            {
                "id": s.spending_id,
                "name": s.details or s.category or "거래",
                "amount": signed_amount,
                "amount_abs": amount,
                "icon": "🧾",
                "memo": s.memo or "",
                "category": category_ko,
                "spend_date": (
                    timezone.localtime(s.spend_date).strftime("%Y.%m.%d %H:%M")
                    if s.spend_date
                    else ""
                ),
            }
        )

    return transactions

def get_coaching_report(ml_result_df):
    model = use_gemini_api()
    """
    모든 카테고리별 예측치를 종합하여, 
    사용자에게 보낼 단 하나의 통합 코칭 문구를 생성합니다.
    """
    # 예측 데이터 추출 (카테고리명과 예측 금액)
    data_to_send = ml_result_df[['category', 'predicted_spend']].to_dict(orient='records')

    prompt = f"""
    당신은 사용자의 소비를 미리 관리해주는 '소비 코치'입니다. 
    아래의 [이번 주 소비 예측 데이터]를 분석하여, 사용자가 지갑을 열기 전에 들려줄 
    '단 하나의 통합 코칭 문구'를 작성하세요.

    [다음 주 소비 예측 데이터]:
    {data_to_send}

    [작성 가이드라인]:
    1. 여러 문장을 나열하지 말고, 흐름이 자연스러운 '한 개의 메시지'로 작성하세요.
    2. 예측 금액이 가장 높은 카테고리나, 주의가 필요한 항목을 언급하며 경고와 격려를 섞어주세요.
    3. 무조건 "다음주 ~지출이 클 것으로 예상되니," 라는 문구로 시작하세요.
    4. "~할 것으로 예상되니 ~하는 것이 좋겠어요"와 같은 예방적 어조를 사용하세요.
    5. 전체 길이는 30자 내외로 핵심만 전달하세요.
    6. 엔터테인먼트 카테고리는 여가 라고 표현하세요. 

    [출력 형식]: 반드시 아래 JSON 형식을 지키세요.
    {{
        "coaching_message": "다음주엔 외식비 지출이 클 것으로 보여요. 도시락을 준비해보는 건 어떨까요?"
    }}
    """

    retry_count = 0
    while retry_count < 5:
        try:
            response = model.generate_content(prompt, request_options={'timeout': 30})
            res_json = json.loads(response.text)
            return res_json.get("coaching_message", "데이터 분석 중입니다.")
        except Exception as e:
            retry_count += 1
            print(f"⚡ 통신 재시도 중... ({retry_count}/5)")
            time.sleep(2)
    
    return "소비 패턴을 분석할 수 없습니다."

def build_future_spend_prediction(df):
    pd.options.mode.chained_assignment = None

    # 1. 전처리 및 시간 데이터 설정
    df = df[df["trans_type"] == "출금"].copy()
    df["trans_dtime"] = (
        pd.to_datetime(df["trans_dtime"], utc=True)
        .dt.tz_convert("Asia/Seoul")
        .dt.tz_localize(None)
    )

    # 2. 기초 특징 추출
    iso = df["trans_dtime"].dt.isocalendar()
    df["year"] = iso.year.astype(int)
    df["week"] = iso.week.astype(int)
    df["yearweek"] = df["year"] * 100 + df["week"]
    df["month"] = df["trans_dtime"].dt.month.astype(int)
    df["weekday"] = df["trans_dtime"].dt.weekday
    df["is_weekend"] = (df["weekday"] >= 5).astype(int)

    # 3. 주차별/카테고리별 집계
    weekly_cat = (
        df.groupby(["yearweek", "year", "week", "month", "category"], as_index=False)
        .agg(
            total_spend=("amount", "sum"),
            spend_count=("amount", "count"),
            weekend_ratio=("is_weekend", "mean"),
        )
    )

    # 4. 미래 주차(Next Week) 생성 로직
    last_date = df["trans_dtime"].max()
    next_date = last_date + timedelta(days=7)
    next_iso = next_date.isocalendar()
    
    next_year = int(next_iso[0])
    next_week = int(next_iso[1])
    next_yearweek = next_year * 100 + next_week
    next_month = next_date.month

    # 모든 카테고리에 대해 미래 행 생성
    cats = weekly_cat["category"].unique()
    future_rows = pd.DataFrame({
        "yearweek": [next_yearweek] * len(cats),
        "year": [next_year] * len(cats),
        "week": [next_week] * len(cats),
        "month": [next_month] * len(cats),
        "category": cats,
        "total_spend": [0] * len(cats), # 미래이므로 실제 지출은 0(또는 NaN)으로 세팅
        "spend_count": [0] * len(cats),
        "weekend_ratio": [0] * len(cats)
    })

    # 기존 데이터와 미래 행 결합
    weekly_cat = pd.concat([weekly_cat, future_rows], ignore_index=True)

    # 5. 시계열 특징 생성 (Lag, Rolling)
    weekly_cat = weekly_cat.sort_values(["category", "yearweek"]).reset_index(drop=True)
    
    # 과거 데이터를 한 칸씩 밀어서 미래 행이 과거의 정보를 갖게 함
    weekly_cat["lag_1"] = weekly_cat.groupby("category")["total_spend"].shift(1)
    weekly_cat["lag_2"] = weekly_cat.groupby("category")["total_spend"].shift(2)
    weekly_cat["roll_mean_2"] = weekly_cat.groupby("category")["total_spend"].shift(1).rolling(2).mean().reset_index(level=0, drop=True)
    weekly_cat["roll_mean_4"] = weekly_cat.groupby("category")["total_spend"].shift(1).rolling(4).mean().reset_index(level=0, drop=True)
    weekly_cat["roll_std_4"] = weekly_cat.groupby("category")["total_spend"].shift(1).rolling(4).std().reset_index(level=0, drop=True)

    # 6. 학습 및 예측 데이터 분리
    # 미래 행(next_yearweek)은 예측용(forecast), 나머지는 학습용
    train_data = weekly_cat[weekly_cat["yearweek"] < next_yearweek].dropna()
    forecast_data = weekly_cat[weekly_cat["yearweek"] == next_yearweek]

    features = [
        "yearweek", "week", "month", "category",
        "spend_count", "weekend_ratio",
        "lag_1", "lag_2", "roll_mean_2", "roll_mean_4", "roll_std_4"
    ]
    target = "total_spend"

    # 카테고리 타입 변환
    train_data["category"] = train_data["category"].astype("category")
    forecast_data["category"] = forecast_data["category"].astype("category")

    # 7. 모델 학습
    model = lgb.LGBMRegressor(objective="regression", n_estimators=1000, learning_rate=0.05, verbosity=-1)
    model.fit(train_data[features], np.log1p(train_data[target]))

    # 8. 미래 예측 및 결과 필터링
    forecast_data["predicted_spend"] = np.expm1(model.predict(forecast_data[features]))
    
    # 제외할 카테고리 리스트
    exclude_categories = ["savemoney", "health", "etc"]
    result = forecast_data[~forecast_data["category"].isin(exclude_categories)].copy()
    
    # 결과 정리
    result = result[["yearweek", "category", "predicted_spend"]].sort_values("predicted_spend", ascending=False)
    return result

def run_spending_analysis(raw_df):
    # (1) ML 모델을 통한 예측 및 실제 데이터 산출
    # 사용자님이 작성하신 build_weekly_spend_prediction 함수 호출
    ml_result = build_future_spend_prediction(raw_df) 
    # print(ml_result)
    
    # (2) Gemini에게 결과 전달 및 코칭 메시지 수신
    if not ml_result.empty:
        coaching_data = get_coaching_report(ml_result)
        # print(coaching_data)
        return coaching_data
    else:
        print("분석할 소비 데이터가 부족합니다.")
        return None


# View
@login_required
def spending_history_view(request):
    moni_user = _current_moni_user(request)

    # 마이데이터 유도 팝업
    has_spending = Spending.objects.filter(user=moni_user).exists()
    show_mydata_popup = not has_spending

    # 기준 날짜 (현재 월)
    today = timezone.localdate()

    if has_spending and (
        request.GET.get("year") is None and request.GET.get("month") is None
    ):
        latest_dt = (
            Spending.objects.filter(user=moni_user)
            .order_by("-spend_date")
            .values_list("spend_date", flat=True)
            .first()
        )
        base = timezone.localtime(latest_dt).date() if latest_dt else today
    else:
        base = today

    year = to_int(request.GET.get("year"), base.year)
    month = to_int(request.GET.get("month"), base.month)

    # 이전/다음 월 계산
    prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
    next_year, next_month = (year, month + 1) if month < 12 else (year + 1, 1)

    _, last_day = calendar.monthrange(year, month)
    selected_day = to_int(request.GET.get("day"), min(base.day, last_day))
    selected_day = max(1, min(selected_day, last_day))

    # 데이터 생성
    days, has_month_data = build_month_days(moni_user, year, month)
    transactions = build_day_transactions(moni_user, date(year, month, selected_day))

    now = timezone.now()
    weekday = now.weekday()  # 4:금, 5:토
    # hour = now.hour

    # 1. 이번 주차를 식별하는 ID 생성 (예: '2026-01' -> 2026년 1번째 주)
    current_week_id = now.strftime("%Y-%U")
    
    # 세션에서 '마지막으로 실행했던 주차 ID'를 가져옴
    last_run_week = request.session.get('last_run_week')
    
    is_active = 0
    prediction_result = None

    # 2. 원하는 시간대인지 확인
    is_in_time_window = True
    if weekday == 6 or weekday < 3: # 일, 월, 화, 수, 목
        is_in_time_window = False


    # 3. 핵심 로직: 시간대 안이고 + 이번 주에 아직 실행 안 했다면 실행
    if is_in_time_window:
        if last_run_week != current_week_id:
            # --- [최초 1회 실행되는 구간] ---
            # 여기서 이전의 LightGBM 예측 함수를 호출하세요.
            df = spending_to_dataframe(moni_user)
            prediction_result = run_spending_analysis(df)
            Notification.objects.create(user=moni_user, notification_time=now, notification_detail=prediction_result)
            
            # 실행했음을 세션에 기록 (주차 ID 저장)
            request.session['last_run_week'] = current_week_id
            
            
            is_active = 1
            # print("이번 주 최초 실행 완료!")
            # ------------------------------
        else:
            # 이번 주에 이미 실행했다면, 무거운 계산은 안 하고 상태만 1로 유지
            is_active = 1
            # print("이미 실행된 주차입니다. 상태만 유지합니다.")
    else:
        # 토요일이 지나면 0으로 초기화
        is_active = 0
        # print("비활성화 시간대입니다.")

    return render(
        request,
        "spending_history.html",
        {
            "page": "spending_history",
            "active_menu": "spending_history",
            "year": year,
            "month": month,
            "days": days,
            "prev_year": prev_year,
            "prev_month": prev_month,
            "next_year": next_year,
            "next_month": next_month,
            "selected_day": selected_day,
            "transactions": transactions,
            "has_month_data": has_month_data,
            "show_mydata_popup": show_mydata_popup,
            "empty_message": "내역이 없습니다",
        },
    )


@require_POST
@login_required
def spending_memo_update(request):
    moni_user = _current_moni_user(request)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    spending_id = payload.get("spending_id")
    memo = (payload.get("memo") or "").strip()

    try:
        spending_id = int(spending_id)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "invalid_spending_id"}, status=400)

    # 모델 memo max_length=45 방어
    if len(memo) > 45:
        return JsonResponse(
            {"ok": False, "error": "memo_too_long", "max": 45}, status=400
        )

    updated = Spending.objects.filter(user=moni_user, spending_id=spending_id).update(
        memo=memo
    )
    if updated == 0:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    return JsonResponse({"ok": True, "spending_id": spending_id, "memo": memo})
