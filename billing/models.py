from django.db import models

class User(models.Model):
    name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, null=True)
    distributor_id = models.CharField(max_length=50, blank=True, null=True, unique=True)
    company_name = models.CharField(max_length=150, blank=True)
    usertype = models.CharField(max_length=20, default='distributor')  # 'distributor' or 'admin'
    today_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    available_inventory = models.IntegerField(default=1000)

    def __str__(self):
        return f"{self.company_name or self.name or self.email} ({self.usertype})"
