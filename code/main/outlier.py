import pandas as pd
from main.models import Spending, Notification
from django.utils import timezone 
from datetime import datetime, timedelta
from django.db import connection


def check_notification(moni_user, today_date, detail):
    with connection.cursor() as cursor: 
            cursor.execute(
                """
                SELECT * 
                FROM moni.notification 
                WHERE user_id = %s 
                AND DATE(notification_time) = %s
                AND notification_detail = %s
                LIMIT 1 """, 
                [moni_user.user_id, today_date, detail])
            row = cursor.fetchone()
            return row

def check_outlier(moni_user):
    today_date = timezone.now().date()
            
    qs = Spending.objects.filter(user=moni_user).values()
    df = pd.DataFrame(list(qs))
    df = df[df["transaction_type"] == "출금"].copy()

    df["spend_date"] = (
        pd.to_datetime(df["spend_date"], utc=True)
          .dt.tz_convert("Asia/Seoul")
          .dt.tz_localize(None)
    )

    latest_day = df["spend_date"].max().normalize()
    cutoff = latest_day - pd.Timedelta(days=1)
    df_past = df[df["spend_date"] < cutoff].copy()
    df_past["day"] = df_past["spend_date"].dt.date

    past_daily = (
        df_past
        .groupby(["category", "day"])["price"]
        .sum()
        .reset_index()
    )

    box_stats = (
        past_daily
        .groupby("category")["price"]
        .agg(
            Q1=lambda x: x.quantile(0.25),
            Q3=lambda x: x.quantile(0.75),
        )
    )
    box_stats["IQR"] = box_stats["Q3"] - box_stats["Q1"]
    box_stats["upper_fence"] = box_stats["Q3"] + 0.5 * box_stats["IQR"]

    target_date = (timezone.now() - timedelta(days=1)).date()

    today_spending = (
        df[df["spend_date"].dt.date == target_date]
        .groupby("category")["price"]
        .sum()
        .reset_index(name="today_sum")
    )

    today_spending = today_spending.merge(
        box_stats[["upper_fence"]],
        on="category",
        how="left"
    )
    
    today_spending["is_anomaly"] = (
        today_spending["today_sum"] > today_spending["upper_fence"]
    )

    if today_spending["is_anomaly"].any():
        anomaly_list = (
            today_spending[today_spending["is_anomaly"]]
            .assign(excess=lambda x: x["today_sum"] - x["upper_fence"])
            [["category", "excess"]]
            .to_dict("records")
        )
    else:
        anomaly_list = []

    if not anomaly_list:
        detail = "어제는 충동적인 소비가 없었어요 >.<!"
        
    for item in anomaly_list:
        category = item["category"]
        excess = int(item["excess"])

        if excess >= 50000:
            detail = f"어제 {category}에서 {excess:,}원만큼 과소비가 발생했어요 T.T"
        else:
            detail = f"어제 {category}에서 평소보다 소비가 높았어요"

    if check_notification(moni_user, today_date, detail):
        return

    Notification.objects.create(
        user=moni_user,
        notification_detail=detail
        )

    return
