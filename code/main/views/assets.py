from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from ._helpers import _current_moni_user, _current_bank_accounts


@login_required
def asset_detail(request):
    moni_user = _current_moni_user(request)

    current_accounts = _current_bank_accounts(moni_user)
    total_assets = sum((acc.current_balance or 0) for acc in current_accounts)

    current_goal = moni_user.goals.order_by("-goal_id").first()
    goal_target_amount = getattr(current_goal, "target_amount", None) if current_goal else None
    goal_progress_percent = None
    goal_progress_bar_percent = 0
    goal_remaining_amount = None
    if goal_target_amount and goal_target_amount > 0:
        goal_progress_percent = (total_assets / goal_target_amount) * 100
        goal_progress_bar_percent = max(0, min(100, goal_progress_percent))
        goal_remaining_amount = goal_target_amount - total_assets

    category_sum = {}
    for acc in current_accounts:
        category_sum[acc.display_category] = category_sum.get(acc.display_category, 0) + (acc.current_balance or 0)

    category_totals = [{"category": k, "total_balance": v} for k, v in category_sum.items()]
    total_abs = sum(abs(row["total_balance"] or 0) for row in category_totals) or 0

    def _dot_class(category: str) -> str:
        if not category:
            return "dot-deposit"
        if "입출금" in category:
            return "dot-deposit"
        if "예" in category or "적금" in category:
            return "dot-saving"
        if "증권" in category:
            return "dot-stock"
        if "대출" in category:
            return "dot-loan"
        return "dot-deposit"

    dot_to_color = {
        "dot-deposit": "#D9F99D",
        "dot-saving": "#A7F3D0",
        "dot-stock": "#BFDBFE",
        "dot-loan": "#FCA5A5",
    }

   
    preferred_order = ["입출금", "예금", "적금", "예적금", "예·적금", "증권", "대출"]
    def _order_key(cat: str) -> int:
        for idx, key in enumerate(preferred_order):
            if key in (cat or ""):
                return idx
        return 999

    category_totals_sorted = sorted(category_totals, key=lambda r: _order_key(r["category"]))

    asset_categories = []
    for row in category_totals_sorted:
        category = row["category"]
        amount = row["total_balance"] or 0
        dot = _dot_class(category)
        percent = (abs(amount) / total_abs * 100) if total_abs else 0
        percent_signed = (amount / total_abs * 100) if total_abs else 0
        asset_categories.append(
            {
                "category": category,
                "amount": amount,
                "percent": percent,
                "percent_signed": percent_signed,
                "dot_class": dot,
            }
        )

    
    start = 0.0
    slices = []
    for item in asset_categories:
        color = dot_to_color.get(item["dot_class"], "#D9F99D")
        size = item["percent"]
        end = min(100.0, start + size)
        if size > 0:
            slices.append(f"{color} {start:.2f}% {end:.2f}%")
            start = end

    if not slices:
        donut_conic = "#e5e7eb 0 100%"
    else:
        donut_conic = ", ".join(slices)

    accounts_by_category = {}
    for acc in sorted(current_accounts, key=lambda a: (a.display_category or "", a.bank or "", a.id)):
        accounts_by_category.setdefault(acc.display_category, []).append(acc)

    asset_groups = []
    seen = set()
    for item in asset_categories:
        cat = item["category"]
        rows = accounts_by_category.get(cat, [])
        total = sum((acc.current_balance or 0) for acc in rows)
        asset_groups.append({"category": cat, "total": total, "rows": rows})
        seen.add(cat)

    for cat, rows in accounts_by_category.items():
        if cat in seen:
            continue
        total = sum((acc.current_balance or 0) for acc in rows)
        asset_groups.append({"category": cat, "total": total, "rows": rows})

    return render(
        request,
        "asset_detail.html",
        {
            "page": "asset_detail",
            "active_menu": "asset_detail",
            "user": moni_user,
            "total_assets": total_assets,
            "current_goal": current_goal,
            "goal_target_amount": goal_target_amount,
            "goal_progress_percent": goal_progress_percent,
            "goal_progress_bar_percent": goal_progress_bar_percent,
            "goal_remaining_amount": goal_remaining_amount,
            "asset_categories": asset_categories,
            "donut_conic": donut_conic,
            "asset_groups": asset_groups,
        },
    )
