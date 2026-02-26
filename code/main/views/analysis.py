from datetime import date, datetime, time
from calendar import monthrange

from django.contrib.auth.decorators import login_required
from django.db.models import Max, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from main.models import Spending
from ._helpers import _current_moni_user


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


def _expense_qs(moni_user, start, end):

    if isinstance(start, date) and not isinstance(start, datetime):
        start = timezone.make_aware(datetime.combine(start, time.min))
    if isinstance(end, date) and not isinstance(end, datetime):
        end = timezone.make_aware(datetime.combine(end, time.min))

    base = (
        Spending.objects
        .filter(
            user_id=moni_user.user_id,
            spend_date__gte=start,
            spend_date__lt=end,
        )
    )


    preferred = base.filter(transaction_type="출금")
    if preferred.exists():
        return preferred


    return base.exclude(transaction_type__in=["입금", "수입"])


def _reference_date(moni_user) -> date:

    last_expense = (
        Spending.objects
        .filter(user_id=moni_user.user_id)
        .exclude(transaction_type__in=["입금", "수입"])
        .aggregate(Max("spend_date"))
        .get("spend_date__max")
    )
    last_any = None
    if not last_expense:
        last_any = (
            Spending.objects
            .filter(user_id=moni_user.user_id)
            .aggregate(Max("spend_date"))
            .get("spend_date__max")
        )

    last = last_expense or last_any
    if not last:
        return timezone.localdate()

    if timezone.is_naive(last):
        last = timezone.make_aware(last)

    return timezone.localtime(last).date()


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return date(y, m, day)


def _month_start_end(year: int, month: int):
    start = date(year, month, 1)
    end = _add_months(start, 1)
    return start, end


def _yearly_month_bars(moni_user, ref_date: date):
    start_month = _add_months(ref_date.replace(day=1), -11)  
    end_month = _add_months(ref_date.replace(day=1), 1)      

    month_map = {}
    rows = _expense_qs(moni_user, start_month, end_month).values_list("spend_date", "price")
    for spend_dt, price in rows:
        if not spend_dt:
            continue
        if timezone.is_naive(spend_dt):
            spend_dt = timezone.make_aware(spend_dt)
        m = timezone.localtime(spend_dt).date().replace(day=1)
        month_map[m] = month_map.get(m, 0) + float(price or 0)

    labels, values = [], []
    cur = start_month
    for _ in range(12):
        labels.append(f"{cur.month}월")
        values.append(int(month_map.get(cur, 0) or 0))
        cur = _add_months(cur, 1)

    return {"labels": labels, "values": values}


def _monthly_category_donut(moni_user, year: int, month: int):
    start, end = _month_start_end(year, month)

    rows = (
        _expense_qs(moni_user, start, end)
        .values("category")
        .annotate(total=Sum("price"))
        .order_by("-total")
    )

    items = []
    total_sum = 0
    for r in rows:
        raw_cat = (r["category"] or "").strip()
        if raw_cat.startswith("subscription_"):
            cat = "구독"
        else:
            key = raw_cat.lower()
            cat = CATEGORY_LABELS_KO.get(key, raw_cat) or "기타"
        amt = int(r["total"] or 0)
        total_sum += amt
        items.append({"label": cat, "amount": amt})

    for it in items:
        it["percent"] = (it["amount"] / total_sum * 100) if total_sum else 0

    return {
        "year": year,
        "month": month,
        "month_title": f"{month}월",
        "total": total_sum,
        "items": items,
    }


@login_required
def spending_analysis(request):
    moni_user = _current_moni_user(request)
    has_spending = Spending.objects.filter(user=moni_user).exists()

    ref_date = _reference_date(moni_user)
    year, month = ref_date.year, ref_date.month

    bars = _yearly_month_bars(moni_user, ref_date)
    donut = _monthly_category_donut(moni_user, year, month)

    return render(
        request,
        "spending_analysis.html",
        {
            "page": "spending_analysis",
            "active_menu": "spending_analysis",
            "show_mydata_popup": (not has_spending),

            "year_bar_labels": bars["labels"],
            "year_bar_values": bars["values"],

            "donut_year": donut["year"],
            "donut_month": donut["month"],
            "donut_month_title": donut["month_title"],
            "donut_total": donut["total"],
            "donut_items": donut["items"],
        },
    )


@require_GET
def api_spending_pattern(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "authentication required"}, status=401)

    moni_user = _current_moni_user(request)

    month_str = request.GET.get("month")  # "YYYY-MM"
    if not month_str:
        ref_date = _reference_date(moni_user)
        year, month = ref_date.year, ref_date.month
    else:
        try:
            year, month = map(int, month_str.split("-"))
        except ValueError:
            return JsonResponse({"error": "invalid month format. use YYYY-MM"}, status=400)

    donut = _monthly_category_donut(moni_user, year, month)
    return JsonResponse(donut)
