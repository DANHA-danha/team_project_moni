from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User as AuthUser
from main.models import MoniUser, Notification, Spending
from django.db import IntegrityError
from datetime import datetime

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User as AuthUser
from main.models import MoniUser, Notification, Spending
from django.db import IntegrityError
from datetime import datetime
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from main.outlier import check_outlier
from django.views.decorators.http import require_POST

def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            
            moni_user = MoniUser.objects.get(ID=username)
            if Spending.objects.filter(user_id=moni_user.user_id).exists():
                check_outlier(moni_user)
            return redirect("home")
        else:
            error = "ID 또는 비밀번호가 올바르지 않습니다."
            return render(request, "login.html", {"error": error})

    # GET 요청 → 로그인 폼 보여주기
    return render(request, "login.html")


def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username") or request.POST.get("login_id")
        password = request.POST.get("password")
        name = request.POST.get("name")
        email = request.POST.get("email", "").strip() or None

        if not username or not password or not name or not email:
            return render(
                request, "signup.html", {"error": "필수 항목을 모두 입력하세요."}
            )

        try:
            AuthUser.objects.create_user(
                username=username, password=password, first_name=name, email=email
            )
            moni = MoniUser.objects.create(ID=username, password=password, name=name, email=email)
            now = datetime.now()
            Notification.objects.create(user=moni, notification_time=now, notification_detail=f"{name} 님, 회원가입을 환영합니다 !")
            
        except IntegrityError:
            return render(
                request, "signup.html", {"error": "이미 존재하는 아이디입니다."}
            )

        
        return redirect("login")

    return render(request, "signup.html")

def notifications(request):
    if request.user.is_authenticated:
        try:
            moni = MoniUser.objects.get(ID=request.user.username)
            notis = Notification.objects.filter(user=moni).order_by('-notification_time', '-id')
        except MoniUser.DoesNotExist:
            moni = None
            notis = []
    else:
        moni = None
        notis = []

    last_seen_id = int(request.session.get("notifications_last_seen_id", 0) or 0)
    unread_count = 0
    if moni is not None:
        try:
            unread_count = Notification.objects.filter(user=moni, id__gt=last_seen_id).count()
        except Exception:
            unread_count = 0

    latest_id = 0
    if moni is not None:
        try:
            latest_id = (
                Notification.objects
                .filter(user=moni)
                .order_by("-id")
                .values_list("id", flat=True)
                .first()
            ) or 0
        except Exception:
            latest_id = 0

    return {
        'notifications': notis,
        "notifications_unread_count": unread_count,
        "notifications_last_seen_id": last_seen_id,
        "notifications_latest_id": int(latest_id),
    }

def notifications_push(request):
    last_id = request.GET.get("last_id", "0")
    try:
        last_id = int(last_id)
    except ValueError:
        last_id = 0

    try:
        moni = MoniUser.objects.get(ID=request.user.username)
    except MoniUser.DoesNotExist:
        return JsonResponse({"ok": True, "items": [], "latest_id": last_id})

    qs = (Notification.objects
          .filter(user=moni, id__gt=last_id)
          .order_by("id"))

    items = list(qs.values("id", "notification_time", "notification_detail")[:10])

    for it in items:
        t = it.get("notification_time")
        if t:
            it["notification_time"] = timezone.localtime(t).strftime("%Y-%m-%d %H:%M:%S")

    latest_id = items[-1]["id"] if items else last_id

    return JsonResponse({"ok": True, "items": items, "latest_id": latest_id})

def _current_moni_user_for_notifications(request):
    if not request.user.is_authenticated:
        return None
    username = getattr(request.user, "username", None)
    if not username:
        return None
    try:
        return MoniUser.objects.get(ID=username)
    except MoniUser.DoesNotExist:
        return None


@login_required
def notifications_unread_count(request):
    moni = _current_moni_user_for_notifications(request)
    if moni is None:
        return JsonResponse({"unread_count": 0})

    last_seen_id = int(request.session.get("notifications_last_seen_id", 0) or 0)
    cnt = Notification.objects.filter(user=moni, id__gt=last_seen_id).count()
    return JsonResponse({"unread_count": cnt})
    
@login_required
@require_POST
def mark_all_read(request):
    moni = _current_moni_user_for_notifications(request)
    if moni is None:
        return JsonResponse({"ok": True})

    latest_id = (
        Notification.objects
        .filter(user=moni)
        .order_by("-id")
        .values_list("id", flat=True)
        .first()
    ) or 0
    request.session["notifications_last_seen_id"] = int(latest_id)

    try:
        Notification.objects.filter(user=moni).update(is_read=True)
    except Exception:
        pass

    return JsonResponse({"ok": True, "latest_id": int(latest_id)})


def logout_view(request):
    logout(request)
    return redirect("login")