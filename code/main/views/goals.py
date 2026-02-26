from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from main.models import Goal
from ._helpers import _current_moni_user


@require_POST
@login_required
def set_goal(request):
    moni_user = _current_moni_user(request)

    title = request.POST.get("title")
    target_amount = request.POST.get("target_amount")
    if not title or not target_amount:
        return redirect("home")

    try:
        amount_int = int(target_amount)
    except ValueError:
        return redirect("home")
 
    Goal.objects.update_or_create(
        user=moni_user,
        defaults={"title": title, "target_amount": amount_int},
    )

    return redirect("home")
