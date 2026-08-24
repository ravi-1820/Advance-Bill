from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('index/', views.index, name='index_alt'),
    path('distributor-login/', views.distributor_login, name='distributor_login'),
    path('admin-login/', views.admin_login, name='admin_login'),
    path('logout/', views.logout_view, name='logout'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('distributor-dashboard/', views.distributor_dashboard, name='distributor_dashboard'),
    path('distributor-profile/', views.distributor_profile, name='distributor_profile'),
    path('distributor-register/', views.distributor_register, name='distributor_register'),
    path('register/', views.distributor_register, name='register'),
    path('forgot-password/generate-otp/', views.generate_forgot_otp, name='generate_forgot_otp'),
    path('forgot-password/verify-reset/', views.verify_reset_password, name='verify_reset_password'),
]
