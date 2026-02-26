from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from main.models import Spending
from ._helpers import _current_moni_user, _current_bank_accounts, get_monthly_asset_report, generate_svg_coords


@login_required
def home(request):
    moni_user = _current_moni_user(request)
    has_spending = Spending.objects.filter(user=moni_user).exists()

    is_spending_type_loading = has_spending and (moni_user.type_id is None)
    user_type = None if is_spending_type_loading else moni_user.type


 
    current_goal = moni_user.goals.order_by("-goal_id").first()

# ----자산 분석 및 그래프 데이터 생성------

    svg_data = None
    report_list = []
    current_accounts = _current_bank_accounts(moni_user)
    total_assets = sum((acc.current_balance or 0) for acc in current_accounts)
    if has_spending:
        # 1. 월별 자산 리포트 계산 (Pandas DataFrame 반환)
        report_df = get_monthly_asset_report(moni_user)
        
        if not isinstance(report_df, str) and not report_df.empty:
            # 2. SVG 그래프용 좌표 생성
            svg_data = generate_svg_coords(report_df)
            
            # 3. 템플릿 사용을 위해 리스트 형식으로 변환
            report_list = report_df.to_dict('records')
            
            # 4. 전체 자산 업데이트
            
            total_assets = sum((acc.current_balance or 0) for acc in current_accounts)
        else:
            pass
    else:
        pass

    goal_target_amount = getattr(current_goal, "target_amount", None) if current_goal else None
    goal_progress_percent = None
    goal_progress_bar_percent = 0
    goal_remaining_amount = None
    if goal_target_amount and goal_target_amount > 0:
        goal_progress_percent = (total_assets / goal_target_amount) * 100
        goal_progress_bar_percent = max(0, min(100, goal_progress_percent))
        goal_remaining_amount = goal_target_amount - total_assets

    bank_summary_map = {}
    for acc in current_accounts:
        bank_summary_map[acc.bank] = bank_summary_map.get(acc.bank, 0) + (acc.current_balance or 0)
    bank_summary = [{"bank": k, "total_balance": v} for k, v in sorted(bank_summary_map.items(), key=lambda x: x[0] or "")]

    show_mydata_popup =(not has_spending)
    

    context = {
        "page": "home",
        "active_menu": "home",
        "user": moni_user,
        "user_type": user_type,
        "is_spending_type_loading": is_spending_type_loading,
        "current_goal": current_goal,
        "total_assets": total_assets,
        "goal_target_amount": goal_target_amount,
        "goal_progress_percent": goal_progress_percent,
        "goal_progress_bar_percent": goal_progress_bar_percent,
        "goal_remaining_amount": goal_remaining_amount,
        "bank_summary": bank_summary,
        "show_mydata_popup": show_mydata_popup,

        "svg_data": svg_data,
        "monthly_report": report_list,
    }
    return render(request, "home.html", context)
