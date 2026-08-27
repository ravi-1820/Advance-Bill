from django.contrib import admin
from billing.models import *

admin.site.register(User)
admin.site.register(OTP)
admin.site.register(Customer) 
admin.site.register(Product)
