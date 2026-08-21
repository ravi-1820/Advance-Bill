from django.shortcuts import render

def index(request):
    return render(request, 'billing/index.html')

def login_view(request):
    return render(request, 'billing/login.html')

def admin_login(request):
    return render(request, 'billing/admin-login.html')

def distributor_login(request):
    return render(request, 'billing/distributor-login.html')

def admin_dashboard(request):
    return render(request, 'billing/admin-dashboard.html')

def distributor_dashboard(request):
    return render(request, 'billing/distributor-dashboard.html')

