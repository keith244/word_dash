from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import RegisterForm, LoginForm
from django.contrib.auth.decorators import login_required

def register_view(request):
    # if request.user.is_authenticated:
    #     return redirect('lobby')
    
    form = RegisterForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            messages.success(request, 'Account created! Please log in.')
            return redirect('login')
        else:
            messages.error(request, 'Please fix the errors below.')
    
    return render(request, 'users/register.html', {'form': form})


def login_view(request):
    # if request.user.is_authenticated:
    #     return redirect('lobby')

    form = LoginForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username_or_email'],
                password=form.cleaned_data['password']
            )
            if user:
                login(request, user)
                return redirect('lobby')
            else:
                messages.error(request, 'Invalid credentials.')

    return render(request, 'users/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')

