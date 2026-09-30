from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ParentProfileForm, ParentRegistrationForm


def register(request):
    """家長註冊，成功後直接登入並導向新增第一個孩子。"""
    if request.user.is_authenticated:
        return redirect("questionnaires:parent-home")

    if request.method == "POST":
        form = ParentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("questionnaires:child-add")
    else:
        form = ParentRegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile(request):
    if request.method == "POST":
        form = ParentProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            return redirect("accounts:profile")
    else:
        form = ParentProfileForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})
