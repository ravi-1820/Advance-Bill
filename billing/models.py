from django.db import models
import random
from django.contrib.auth.models import BaseUserManager
from django.contrib.auth.hashers import make_password, check_password


class UserManager(models.Manager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = BaseUserManager.normalize_email(email).strip().lower()
        
        usertype = extra_fields.get('usertype', 'distributor')
        distributor_id = extra_fields.get('distributor_id')
        if usertype == 'distributor' and not distributor_id:
            while True:
                candidate_id = f"DIST-{random.randint(10000, 99999)}"
                if not self.filter(distributor_id=candidate_id).exists():
                    extra_fields['distributor_id'] = candidate_id
                    break

        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.password = ''
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('usertype', 'admin')
        return self.create_user(email, password, **extra_fields)


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

    objects = UserManager()

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        if not self.password:
            return False
        return check_password(raw_password, self.password) or self.password == raw_password

    def __str__(self):
        return f"{self.company_name or self.name or self.email} ({self.usertype})"


class OTP(models.Model):
    identity = models.CharField(max_length=150)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.identity} - {self.otp}"


class Customer(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Invoice(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('paid', 'Paid'),
        ('unpaid', 'Unpaid'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='invoices')
    invoice_number = models.CharField(max_length=50, blank=True, null=True, unique=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='paid')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice #{self.invoice_number or self.id} - {self.customer.name}"


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='invoice_items')
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.product.name} ({self.quantity}) - Invoice #{self.invoice.id}"



