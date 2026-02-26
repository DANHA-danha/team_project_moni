from django.urls import path
from .views.home import home
from .views.analysis import spending_analysis, api_spending_pattern
from .views.spending_detail import spending_history_view, spending_type, spending_memo_update
from .views.assets import asset_detail
from .views.pages import mypage, profile_edit
from .views.goals import set_goal
from .views.mydata import mydata_start
from .views.auth import login_view, signup_view, logout_view, notifications_push, notifications_unread_count, mark_all_read

urlpatterns = [
    path("", home, name="home"),
    path("spending-analysis/", spending_analysis, name="spending_analysis"),
    path("api/spending-pattern/", api_spending_pattern, name="api_spending_pattern"),
    path("spending-history/", spending_history_view, name="spending_history"),
    path("api/spending/memo/", spending_memo_update, name="spending_memo_update"),
    path("spending-type/", spending_type, name="spending_type"),
    path("assets/", asset_detail, name="asset_detail"),
    path("mypage/", mypage, name="mypage"),
    path("profile/edit/", profile_edit, name="profile_edit"),
    path("goal/set/", set_goal, name="set_goal"),
    path("mydata/start/", mydata_start, name="mydata_start"),
    path("login/", login_view, name="login"),
    path("signup/", signup_view, name="signup"),
    path("logout/", logout_view, name="logout"),
    path("notifications/push/", notifications_push, name="notifications_push"),
    path("notification/notification_unread_count/", notifications_unread_count, name="notifications_unread_count"),
    path("notification/mark_all_read/", mark_all_read, name="mark_all_read"),
]
