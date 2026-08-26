from django.contrib import admin
from billing.models import User, OTP, Customer

admin.site.register(User)
admin.site.register(OTP)
admin.site.register(Customer) 
  