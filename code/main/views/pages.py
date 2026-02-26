from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from main.models import MoniUser


@login_required
def mypage(request):
    return render(
        request,
        "mypage.html",
        {
            "page": "mypage",
            "active_menu": "mypage",
        },
    )


@login_required
def profile_edit(request):
    auth_user = request.user
    moni_user = MoniUser.objects.filter(ID=auth_user.username).first()

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        new_password = (request.POST.get("password") or "").strip()

        if not name or not email:
            return render(
                request,
                "profile_edit.html",
                {
                    "page": "mypage",
                    "active_menu": "mypage",
                    "error": "이름과 이메일은 필수입니다.",
                    "username": auth_user.username,
                    "name": name or auth_user.first_name,
                    "email": email or auth_user.email,
                },
            )

        with transaction.atomic():
            # 1) Django auth_user 업데이트
            auth_user.first_name = name
            auth_user.email = email
            if new_password:
                auth_user.set_password(new_password)
            auth_user.save()

            # 비번 바꾸면 세션 유지
            if new_password:
                update_session_auth_hash(request, auth_user)

            # 2) MoniUser(user 테이블)도 같이 업데이트
            if moni_user is not None:
                update_data = {"name": name, "email": email}
                if new_password:
                    update_data["password"] = new_password
                MoniUser.objects.filter(user_id=moni_user.user_id).update(**update_data)

        return redirect("home")

    # GET: 기존 값 보여주기
    return render(
        request,
        "profile_edit.html",
        {
            "page": "mypage",
            "active_menu": "mypage",
            "username": auth_user.username,
            "name": moni_user.name if moni_user else auth_user.first_name,
            "email": (
                moni_user.email if (moni_user and moni_user.email) else auth_user.email
            ),
        },
    )
