from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.db.models import Q
from main.models import Spending
from main.models import Type
from main import data, outlier
from datetime import datetime
from main.models import Notification
from ._helpers import _current_moni_user, get_monthly_asset_report


def mydata_start(request):
    moni_user = _current_moni_user(request)
    userid = moni_user.user_id
    name = moni_user.name

    has_spending = Spending.objects.filter(user=moni_user).exists()
    if not has_spending:
        df = data.generate_merged_user_data(userid)
        data.save_spending_df_to_db(df, moni_user)
    
        data.auto_categorize_spending_with_gemini(moni_user)
        data.sync_bank_accounts_from_report(moni_user)
        
        has_uncategorized = Spending.objects.filter(user=moni_user).filter(
            Q(category__isnull=True) | Q(category='')).exists()
        
        if not has_uncategorized:
            feature = data.extract_feature_vector(moni_user)
            pred = data.use_classify_model(feature)
            type_obj = Type.objects.get(type_name=pred)

            moni_user.type = type_obj
            moni_user.save(update_fields=["type"])
            now = datetime.now()
            Notification.objects.create(user=moni_user, notification_time=now, notification_detail=f"{name} 님, 소비 패턴이 달라졌어요")
     
    outlier.check_outlier(moni_user)    
    return redirect("home")


