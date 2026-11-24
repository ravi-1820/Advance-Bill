import io
import base64
import random
import time
from datetime import timedelta, datetime
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.views.decorators.cache import never_cache
from django.http import JsonResponse, HttpResponse, Http404
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from django.db import transaction
from django.db.models import Q, Sum, Count, Avg
from django.core.paginator import Paginator
import qrcode
from xhtml2pdf import pisa
from billing.models import User, OTP, Customer, Product, Invoice, InvoiceItem
from billing.forms import InvoiceCreationForm


def index(request):
    return render(request, 'billing/distributor-login.html')


@csrf_exempt
def distributor_login(request):
    # Check if user is already authenticated in session
    if request.method == 'GET':
        user_id = request.session.get('user_id')
        if user_id:
            try:
                user = User.objects.get(id=user_id, usertype='distributor', is_active=True)
                return redirect('distributor_dashboard')
            except User.DoesNotExist:
                pass
        elif getattr(request, 'user', None) and request.user.is_authenticated and getattr(request.user, 'usertype', '') == 'distributor':
            return redirect('distributor_dashboard')

    if request.method == 'POST':
        # Support both standard form data and JSON payloads
        if request.content_type == 'application/json':
            try:
                import json
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                data = {}
            is_json = True
        else:
            data = request.POST
            is_json = False

        identity = (
            data.get('identity') or 
            data.get('distributor_id') or 
            data.get('email') or 
            data.get('username') or ''
        ).strip()
        mobile = (data.get('mobile') or data.get('phone') or '').strip()
        password = data.get('password', '').strip()

        # Missing fields validation
        if not password or (not identity and not mobile):
            err_msg = "Please enter all required fields..!"
            if is_json:
                return JsonResponse({'success': False, 'message': err_msg}, status=400)
            messages.error(request, err_msg)
            return render(request, 'billing/distributor-login.html', {'identity': identity, 'mobile': mobile})

        try:
            user = None

            # 1. Search by mobile number if provided
            if mobile:
                clean_mobile = ''.join(c for c in mobile if c.isdigit())
                user = User.objects.filter(Q(phone=mobile) | Q(phone=clean_mobile)).first()

            # 2. Search by distributor ID, email, phone, or name
            if not user and identity:
                user = User.objects.filter(
                    Q(distributor_id__iexact=identity) | 
                    Q(email__iexact=identity) | 
                    Q(phone=identity) |
                    Q(name__iexact=identity)
                ).first()

            # 3. Check if account exists
            if not user:
                err_msg = "Distributor account doesn't exist..!"
                if is_json:
                    return JsonResponse({'success': False, 'message': err_msg}, status=404)
                messages.error(request, err_msg)
                return render(request, 'billing/distributor-login.html', {'identity': identity, 'mobile': mobile})

            # 4. Role restriction: Prevent Admin accounts from logging in through distributor portal
            if user.usertype != 'distributor':
                err_msg = "Access restricted: This portal is for Distributors only..!"
                if is_json:
                    return JsonResponse({'success': False, 'message': err_msg}, status=403)
                messages.error(request, err_msg)
                return render(request, 'billing/distributor-login.html', {'identity': identity, 'mobile': mobile})

            # 5. Check if user is active
            if not getattr(user, 'is_active', True):
                err_msg = "Your account is inactive. Please contact administrator..!"
                if is_json:
                    return JsonResponse({'success': False, 'message': err_msg}, status=403)
                messages.error(request, err_msg)
                return render(request, 'billing/distributor-login.html', {'identity': identity, 'mobile': mobile})

            # 6. Validate password using Django's check_password
            if user.check_password(password):
                auth_login(request, user, backend='billing.auth_backends.BillingModelBackend')
                request.session['user_id'] = user.id
                request.session['email'] = user.email
                request.session['name'] = user.company_name or user.name or user.email
                request.session['usertype'] = 'distributor'
                messages.success(request, f"Welcome back, {user.company_name or user.name}!")
                if is_json:
                    return JsonResponse({
                        'success': True,
                        'message': 'Login successful.',
                        'redirect_url': '/distributor-dashboard/'
                    })
                return redirect('distributor_dashboard')
            else:
                err_msg = "Password doesn't match..!"
                if is_json:
                    return JsonResponse({'success': False, 'message': err_msg}, status=401)
                messages.error(request, err_msg)
                return render(request, 'billing/distributor-login.html', {'identity': identity, 'mobile': mobile})

        except Exception:
            err_msg = "Something went wrong. Please try again."
            if is_json:
                return JsonResponse({'success': False, 'message': err_msg}, status=500)
            messages.error(request, err_msg)
            return render(request, 'billing/distributor-login.html', {'identity': identity, 'mobile': mobile})

    return render(request, 'billing/distributor-login.html')


@csrf_exempt
def admin_login(request):
    # Check if user is already authenticated in session
    if request.method == 'GET':
        user_id = request.session.get('user_id')
        if user_id:
            try:
                user = User.objects.get(id=user_id, usertype='admin', is_active=True)
                return redirect('admin_dashboard')
            except User.DoesNotExist:
                pass
        elif getattr(request, 'user', None) and request.user.is_authenticated and getattr(request.user, 'usertype', '') == 'admin':
            return redirect('admin_dashboard')

    if request.method == 'POST':
        # Support both standard form data and JSON payloads
        if request.content_type == 'application/json':
            try:
                import json
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                data = {}
            is_json = True
        else:
            data = request.POST
            is_json = False

        admin_identity = (
            data.get('admin_email') or 
            data.get('identity') or 
            data.get('email') or 
            data.get('username') or ''
        ).strip()
        password = (
            data.get('admin_password') or 
            data.get('password') or ''
        ).strip()

        # Missing fields validation
        if not admin_identity or not password:
            err_msg = "Please enter both admin email and password..!"
            if is_json:
                return JsonResponse({'success': False, 'message': err_msg}, status=400)
            messages.error(request, err_msg)
            return render(request, 'billing/admin-login.html', {'admin_email': admin_identity})

        try:
            # 1. Search admin by email or name/username (case-insensitive)
            user = User.objects.filter(
                Q(email__iexact=admin_identity) | Q(name__iexact=admin_identity)
            ).first()

            # 2. Check if account exists
            if not user:
                err_msg = "Admin account doesn't exist..!"
                if is_json:
                    return JsonResponse({'success': False, 'message': err_msg}, status=404)
                messages.error(request, err_msg)
                return render(request, 'billing/admin-login.html', {'admin_email': admin_identity})

            # 3. Role restriction: Prevent non-admin accounts from logging in through admin portal
            if user.usertype != 'admin':
                err_msg = "Access restricted: This portal is for Administrators only..!"
                if is_json:
                    return JsonResponse({'success': False, 'message': err_msg}, status=403)
                messages.error(request, err_msg)
                return render(request, 'billing/admin-login.html', {'admin_email': admin_identity})

            # 4. Check if user is active
            if not getattr(user, 'is_active', True):
                err_msg = "Your account is inactive. Please contact administrator..!"
                if is_json:
                    return JsonResponse({'success': False, 'message': err_msg}, status=403)
                messages.error(request, err_msg)
                return render(request, 'billing/admin-login.html', {'admin_email': admin_identity})

            # 5. Validate password using Django's check_password
            if user.check_password(password):
                auth_login(request, user, backend='billing.auth_backends.BillingModelBackend')
                request.session['user_id'] = user.id
                request.session['email'] = user.email
                request.session['name'] = user.name or user.email
                request.session['usertype'] = 'admin'
                messages.success(request, f"Welcome back, {user.name or 'Admin'}!")
                if is_json:
                    return JsonResponse({
                        'success': True,
                        'message': 'Login successful.',
                        'redirect_url': '/admin-dashboard/'
                    })
                return redirect('admin_dashboard')
            else:
                err_msg = "Password doesn't match..!"
                if is_json:
                    return JsonResponse({'success': False, 'message': err_msg}, status=401)
                messages.error(request, err_msg)
                return render(request, 'billing/admin-login.html', {'admin_email': admin_identity})

        except Exception:
            err_msg = "Something went wrong. Please try again."
            if is_json:
                return JsonResponse({'success': False, 'message': err_msg}, status=500)
            messages.error(request, err_msg)
            return render(request, 'billing/admin-login.html', {'admin_email': admin_identity})

    return render(request, 'billing/admin-login.html')


def logout_view(request):
    was_admin = (
        request.session.get('usertype') == 'admin' or
        (getattr(request, 'user', None) and getattr(request.user, 'usertype', '') == 'admin')
    )
    next_url = request.GET.get('next') or request.POST.get('next')
    try:
        auth_logout(request)
        messages.info(request, "Logged out successfully..!")
    except Exception:
        try:
            request.session.flush()
        except Exception:
            pass
    if next_url:
        return redirect(next_url)
    if was_admin:
        return redirect('admin_login')
    return redirect('index')


@never_cache
def distributor_dashboard(request):
    try:
        user_id = request.session.get('user_id')
        user = None
        if user_id:
            try:
                user = User.objects.get(id=user_id, usertype='distributor')
            except User.DoesNotExist:
                user = None

        if not user and request.user.is_authenticated and getattr(request.user, 'usertype', '') == 'distributor':
            user = request.user

        if not user:
            messages.error(request, "Access restricted to Distributors only..!")
            return redirect('distributor_login')

        if not getattr(user, 'is_active', True):
            request.session.flush()
            messages.error(request, "Your account is inactive. Please contact administrator..!")
            return redirect('distributor_login')

        return render(request, 'billing/distributor-dashboard.html', {'user': user, 'profile': user})
    except Exception:
        return redirect('distributor_login')


@csrf_exempt
def distributor_profile(request):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('distributor_login')

        user = User.objects.get(id=user_id, usertype='distributor')

        if request.method == 'POST':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            company_name = request.POST.get('company_name', '').strip()

            if not name:
                messages.error(request, "Please enter your full name.")
                return render(request, 'billing/distributor-profile.html', {'user': user, 'profile': user, 'is_edit_mode': True})

            if not email:
                messages.error(request, "Please enter your email address.")
                return render(request, 'billing/distributor-profile.html', {'user': user, 'profile': user, 'is_edit_mode': True})

            if '@' not in email or '.' not in email:
                messages.error(request, "Please enter a valid email address.")
                return render(request, 'billing/distributor-profile.html', {'user': user, 'profile': user, 'is_edit_mode': True})

            if User.objects.filter(email=email).exclude(id=user.id).exists():
                messages.error(request, "An account with this email address already exists.")
                return render(request, 'billing/distributor-profile.html', {'user': user, 'profile': user, 'is_edit_mode': True})

            if not phone:
                messages.error(request, "Please enter your phone number.")
                return render(request, 'billing/distributor-profile.html', {'user': user, 'profile': user, 'is_edit_mode': True})

            clean_phone = ''.join(c for c in phone if c.isdigit())
            if len(clean_phone) < 10:
                messages.error(request, "Please enter a valid phone number (at least 10 digits).")
                return render(request, 'billing/distributor-profile.html', {'user': user, 'profile': user, 'is_edit_mode': True})

            if User.objects.filter(phone=phone).exclude(id=user.id).exists():
                messages.error(request, "An account with this phone number already exists.")
                return render(request, 'billing/distributor-profile.html', {'user': user, 'profile': user, 'is_edit_mode': True})

            if not company_name:
                messages.error(request, "Please enter your company / outlet name.")
                return render(request, 'billing/distributor-profile.html', {'user': user, 'profile': user, 'is_edit_mode': True})

            user.name = name
            user.email = email
            user.phone = phone
            user.company_name = company_name
            user.save()

            request.session['email'] = user.email
            request.session['name'] = user.company_name or user.name

            messages.success(request, "Profile updated successfully!")
            return redirect('distributor_profile')

        return render(request, 'billing/distributor-profile.html', {'user': user, 'profile': user})
    except User.DoesNotExist:
        messages.error(request, "Access restricted to Distributors only..!")
        return redirect('distributor_login')
    except Exception:
        return redirect('distributor_login')


@csrf_exempt
def add_customer(request):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('distributor_login')

        user = User.objects.get(id=user_id, usertype='distributor')

        if request.method == 'POST':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            address = request.POST.get('address', '').strip()

            if not name:
                messages.error(request, "Please enter customer name.")
                return render(request, 'billing/add-customer.html', {'user': user, 'profile': user})

            if not email:
                messages.error(request, "Please enter customer email address.")
                return render(request, 'billing/add-customer.html', {'user': user, 'profile': user})

            if '@' not in email or '.' not in email:
                messages.error(request, "Please enter a valid email address.")
                return render(request, 'billing/add-customer.html', {'user': user, 'profile': user})

            if not phone:
                messages.error(request, "Please enter phone number.")
                return render(request, 'billing/add-customer.html', {'user': user, 'profile': user})

            clean_phone = ''.join(c for c in phone if c.isdigit())
            if len(clean_phone) < 10:
                messages.error(request, "Please enter a valid phone number (at least 10 digits).")
                return render(request, 'billing/add-customer.html', {'user': user, 'profile': user})

            if not address:
                messages.error(request, "Please enter address.")
                return render(request, 'billing/add-customer.html', {'user': user, 'profile': user})

            Customer.objects.create(
                name=name,
                email=email,
                phone=phone,
                address=address
            )

            messages.success(request, "Customer added successfully.")
            return redirect('customer_list')

        return render(request, 'billing/add-customer.html', {'user': user, 'profile': user})
    except User.DoesNotExist:
        messages.error(request, "Access restricted to Distributors only..!")
        return redirect('distributor_login')
    except Exception:
        return redirect('distributor_login')


@csrf_exempt
def add_product(request):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('distributor_login')

        user = User.objects.get(id=user_id)
        if user.usertype not in ['admin', 'distributor']:
            messages.error(request, "Access restricted to authorized users..!")
            return redirect('distributor_login')

        if request.method == 'POST':
            name = request.POST.get('name', '').strip()
            category = request.POST.get('category', '').strip()
            price_str = request.POST.get('price', '').strip()
            stock_str = request.POST.get('stock', '').strip()
            gst_rate_str = request.POST.get('gst_rate', '').strip()

            context = {
                'user': user,
                'profile': user,
                'name': name,
                'category': category,
                'price': price_str,
                'stock': stock_str,
                'gst_rate': gst_rate_str
            }

            if not name:
                messages.error(request, "Please enter product name.")
                return render(request, 'billing/add-product.html', context)

            if not category:
                messages.error(request, "Please enter category.")
                return render(request, 'billing/add-product.html', context)

            if not price_str:
                messages.error(request, "Price must be greater than 0.")
                return render(request, 'billing/add-product.html', context)

            try:
                price = float(price_str)
                if price <= 0:
                    messages.error(request, "Price must be greater than 0.")
                    return render(request, 'billing/add-product.html', context)
            except ValueError:
                messages.error(request, "Price must be greater than 0.")
                return render(request, 'billing/add-product.html', context)

            if not stock_str:
                messages.error(request, "Stock cannot be negative.")
                return render(request, 'billing/add-product.html', context)

            try:
                stock = int(stock_str)
                if stock < 0:
                    messages.error(request, "Stock cannot be negative.")
                    return render(request, 'billing/add-product.html', context)
            except ValueError:
                messages.error(request, "Stock cannot be negative.")
                return render(request, 'billing/add-product.html', context)

            gst_rate = 0.0
            if gst_rate_str:
                try:
                    gst_rate = float(gst_rate_str)
                    if gst_rate < 0:
                        messages.error(request, "GST rate cannot be negative.")
                        return render(request, 'billing/add-product.html', context)
                except ValueError:
                    messages.error(request, "Please enter a valid GST rate.")
                    return render(request, 'billing/add-product.html', context)

            Product.objects.create(
                name=name,
                category=category,
                price=price,
                stock=stock,
                gst_rate=gst_rate
            )

            messages.success(request, "Product added successfully.")
            return redirect('product_list')

        return render(request, 'billing/add-product.html', {'user': user, 'profile': user})

    except User.DoesNotExist:
        messages.error(request, "Access restricted to Distributors only..!")
        return redirect('distributor_login')
    except Exception:
        return redirect('distributor_login')


def product_list(request):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('distributor_login')

        user = User.objects.get(id=user_id)
        if user.usertype not in ['admin', 'distributor']:
            messages.error(request, "Access restricted to authorized users..!")
            return redirect('distributor_login')

        search = request.GET.get('search', '').strip()
        if search:
            products_qs = Product.objects.filter(
                Q(name__icontains=search) | Q(category__icontains=search)
            ).order_by('-id')
        else:
            products_qs = Product.objects.all().order_by('-id')

        total_products = Product.objects.count()

        paginator = Paginator(products_qs, 10)
        page_number = request.GET.get('page', 1)
        products = paginator.get_page(page_number)

        return render(request, 'billing/product-list.html', {
            'user': user,
            'profile': user,
            'products': products,
            'search': search,
            'total_products': total_products
        })
    except User.DoesNotExist:
        messages.error(request, "Access restricted to Distributors only..!")
        return redirect('distributor_login')
    except Exception:
        return redirect('distributor_login')


def customer_list(request):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('distributor_login')

        user = User.objects.get(id=user_id, usertype='distributor')

        search = request.GET.get('search', '').strip()
        if search:
            customers = Customer.objects.filter(
                Q(name__icontains=search) | Q(email__icontains=search) | Q(phone__icontains=search)
            )
        else:
            customers = Customer.objects.all()

        return render(request, 'billing/customer-list.html', {
            'user': user,
            'profile': user,
            'customers': customers,
            'search': search
        })
    except User.DoesNotExist:
        messages.error(request, "Access restricted to Distributors only..!")
        return redirect('distributor_login')
    except Exception:
        return redirect('distributor_login')


@csrf_exempt
def edit_customer(request, id):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('distributor_login')

        user = User.objects.get(id=user_id, usertype='distributor')
        customer = Customer.objects.get(id=id)

        if request.method == 'POST':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            address = request.POST.get('address', '').strip()

            if not name:
                messages.error(request, "Please enter customer name.")
                return render(request, 'billing/edit-customer.html', {'user': user, 'profile': user, 'customer': customer})

            if not email:
                messages.error(request, "Please enter customer email address.")
                return render(request, 'billing/edit-customer.html', {'user': user, 'profile': user, 'customer': customer})

            if '@' not in email or '.' not in email:
                messages.error(request, "Please enter a valid email address.")
                return render(request, 'billing/edit-customer.html', {'user': user, 'profile': user, 'customer': customer})

            if not phone:
                messages.error(request, "Please enter phone number.")
                return render(request, 'billing/edit-customer.html', {'user': user, 'profile': user, 'customer': customer})

            clean_phone = ''.join(c for c in phone if c.isdigit())
            if len(clean_phone) < 10:
                messages.error(request, "Please enter a valid phone number (at least 10 digits).")
                return render(request, 'billing/edit-customer.html', {'user': user, 'profile': user, 'customer': customer})

            if not address:
                messages.error(request, "Please enter address.")
                return render(request, 'billing/edit-customer.html', {'user': user, 'profile': user, 'customer': customer})

            customer.name = name
            customer.email = email
            customer.phone = phone
            customer.address = address
            customer.save()

            messages.success(request, "Customer updated successfully.")
            return redirect('customer_list')

        return render(request, 'billing/edit-customer.html', {'user': user, 'profile': user, 'customer': customer})
    except (User.DoesNotExist, Customer.DoesNotExist):
        messages.error(request, "Customer not found.")
        return redirect('customer_list')
    except Exception:
        return redirect('customer_list')


@csrf_exempt
def edit_product(request, id):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('distributor_login')

        user = User.objects.get(id=user_id)
        if user.usertype not in ['admin', 'distributor']:
            messages.error(request, "Access restricted to authorized users..!")
            return redirect('distributor_login')
        product = Product.objects.get(id=id)

        if request.method == 'POST':
            name = request.POST.get('name', '').strip()
            category = request.POST.get('category', '').strip()
            price_str = request.POST.get('price', '').strip()
            stock_str = request.POST.get('stock', '').strip()
            gst_rate_str = request.POST.get('gst_rate', '').strip()

            context = {
                'user': user,
                'profile': user,
                'product': product,
                'name': name,
                'category': category,
                'price': price_str,
                'stock': stock_str,
                'gst_rate': gst_rate_str,
            }

            if not name:
                messages.error(request, "Please enter product name.")
                return render(request, 'billing/edit-product.html', context)

            if not category:
                messages.error(request, "Please enter category.")
                return render(request, 'billing/edit-product.html', context)

            if not price_str:
                messages.error(request, "Price must be greater than 0.")
                return render(request, 'billing/edit-product.html', context)

            try:
                price = float(price_str)
                if price <= 0:
                    messages.error(request, "Price must be greater than 0.")
                    return render(request, 'billing/edit-product.html', context)
            except ValueError:
                messages.error(request, "Price must be greater than 0.")
                return render(request, 'billing/edit-product.html', context)

            if not stock_str:
                messages.error(request, "Stock cannot be negative.")
                return render(request, 'billing/edit-product.html', context)

            try:
                stock = int(stock_str)
                if stock < 0:
                    messages.error(request, "Stock cannot be negative.")
                    return render(request, 'billing/edit-product.html', context)
            except ValueError:
                messages.error(request, "Stock cannot be negative.")
                return render(request, 'billing/edit-product.html', context)

            gst_rate = 0.0
            if gst_rate_str:
                try:
                    gst_rate = float(gst_rate_str)
                    if gst_rate < 0:
                        messages.error(request, "GST rate cannot be negative.")
                        return render(request, 'billing/edit-product.html', context)
                except ValueError:
                    messages.error(request, "Please enter a valid GST rate.")
                    return render(request, 'billing/edit-product.html', context)

            product.name = name
            product.category = category
            product.price = price
            product.stock = stock
            product.gst_rate = gst_rate
            product.save()

            messages.success(request, "Product updated successfully.")
            return redirect('product_list')

        return render(request, 'billing/edit-product.html', {
            'user': user,
            'profile': user,
            'product': product,
            'name': product.name,
            'category': product.category,
            'price': product.price,
            'stock': product.stock,
            'gst_rate': product.gst_rate,
        })
    except (User.DoesNotExist, Product.DoesNotExist):
        messages.error(request, "Product not found.")
        return redirect('product_list')
    except Exception:
        return redirect('product_list')



def delete_customer(request, id):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('distributor_login')

        user = User.objects.get(id=user_id, usertype='distributor')
        customer = Customer.objects.get(id=id)
        customer.delete()

        messages.success(request, "Customer deleted successfully.")
        return redirect('customer_list')
    except (User.DoesNotExist, Customer.DoesNotExist):
        messages.error(request, "Customer not found.")
        return redirect('customer_list')
    except Exception:
        return redirect('customer_list')


@csrf_exempt
def delete_product(request, id):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('distributor_login')

        user = User.objects.get(id=user_id)
        if user.usertype not in ['admin', 'distributor']:
            messages.error(request, "Access restricted to authorized users..!")
            return redirect('distributor_login')

        product = Product.objects.get(id=id)

        # Protect historical invoices: verify product is not associated with InvoiceItem records
        if product.invoice_items.exists():
            messages.error(request, "Cannot delete product associated with historical invoice records.")
            return redirect('product_list')

        if request.method == 'POST' or request.method == 'GET':
            product.delete()
            messages.success(request, "Product deleted successfully.")
            return redirect('product_list')

        return redirect('product_list')
    except (User.DoesNotExist, Product.DoesNotExist):
        messages.error(request, "Product not found.")
        return redirect('product_list')
    except Exception:
        return redirect('product_list')



@never_cache
def admin_dashboard(request):
    try:
        user_id = request.session.get('user_id')
        user = None
        if user_id:
            try:
                user = User.objects.get(id=user_id, usertype='admin')
            except User.DoesNotExist:
                user = None

        if not user and request.user.is_authenticated and getattr(request.user, 'usertype', '') == 'admin':
            user = request.user

        if not user:
            messages.error(request, "Access restricted to Administrators only..!")
            return redirect('admin_login')

        if not getattr(user, 'is_active', True):
            request.session.flush()
            messages.error(request, "Your account is inactive. Please contact administrator..!")
            return redirect('admin_login')

        return render(request, 'billing/admin-dashboard.html', {'user': user})
    except Exception:
        return redirect('admin_login')


def admin_products(request):
    """
    Dedicated Product Management interface inside Admin Dashboard.
    Supports search, category filtering, pagination, and modal CRUD operations.
    Restricted strictly to Administrator users.
    """
    try:
        user_id = request.session.get('user_id')
        user = None
        if user_id:
            try:
                user = User.objects.get(id=user_id, usertype='admin')
            except User.DoesNotExist:
                user = None

        if not user and request.user.is_authenticated and getattr(request.user, 'usertype', '') == 'admin':
            user = request.user

        if not user:
            messages.error(request, "Access restricted to Administrators only..!")
            return redirect('admin_login')

        search = request.GET.get('search', '').strip()
        category = request.GET.get('category', '').strip()

        qs = Product.objects.all().order_by('-id')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(category__icontains=search))
        if category:
            qs = qs.filter(category__iexact=category)

        total_products = Product.objects.count()
        total_stock = sum(p.stock for p in Product.objects.all())
        low_stock_count = Product.objects.filter(stock__lte=5).count()
        categories = list(Product.objects.values_list('category', flat=True).distinct().order_by('category'))

        paginator = Paginator(qs, 10)
        page_number = request.GET.get('page', 1)
        products = paginator.get_page(page_number)

        return render(request, 'billing/admin-products.html', {
            'user': user,
            'products': products,
            'search': search,
            'selected_category': category,
            'categories': categories,
            'total_products': total_products,
            'total_stock': total_stock,
            'low_stock_count': low_stock_count,
        })
    except Exception as e:
        messages.error(request, f"Error loading products: {str(e)}")
        return redirect('admin_dashboard')


def get_filtered_report_data(request):
    """
    Helper function to filter invoices and compute report metrics based on preset or custom date range.
    Supported presets: 'all', 'today', 'week', 'month', 'custom'.
    Validates that the end date cannot be earlier than the start date.
    Includes both the start date (00:00:00) and end date (23:59:59.999999) inclusively.
    """
    preset = request.GET.get('preset', '').strip().lower()
    start_date_str = request.GET.get('start_date', '').strip()
    end_date_str = request.GET.get('end_date', '').strip()
    search = request.GET.get('search', '').strip()

    now = timezone.now()
    start_dt = None
    end_dt = None
    date_error = None
    active_filter_label = "All Invoices"

    # 1. Custom Date Range Validation & Processing
    is_custom_date_request = (
        preset == 'custom' or
        ('start_date' in request.GET and not preset) or
        ('end_date' in request.GET and not preset) or
        bool(start_date_str) or
        bool(end_date_str)
    )

    if is_custom_date_request:
        preset = 'custom'
        d_start = None
        d_end = None

        # Scenario 1 & 8: Both dates empty / missing
        if not start_date_str and not end_date_str:
            date_error = "Please select a Start Date."
        # Scenario 2: Start Date empty
        elif not start_date_str:
            try:
                datetime.strptime(end_date_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                date_error = "Please enter a valid date."
            if not date_error:
                date_error = "Please select a Start Date."
        # Scenario 3: End Date empty
        elif not end_date_str:
            try:
                datetime.strptime(start_date_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                date_error = "Please enter a valid date."
            if not date_error:
                date_error = "Please select an End Date."
        else:
            # Both dates provided - validate format (Scenario 7)
            try:
                d_start = datetime.strptime(start_date_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                date_error = "Please enter a valid date."

            try:
                d_end = datetime.strptime(end_date_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                if not date_error:
                    date_error = "Please enter a valid date."

            if not date_error:
                # Scenario 4: End Date earlier than Start Date
                if d_start > d_end:
                    date_error = "End Date cannot be earlier than Start Date."
                else:
                    # Scenario 5 & 6: Start Date equal to End Date or valid range
                    start_dt = timezone.make_aware(d_start.replace(hour=0, minute=0, second=0, microsecond=0))
                    end_dt = timezone.make_aware(d_end.replace(hour=23, minute=59, second=59, microsecond=999999))
                    active_filter_label = f"{start_date_str} to {end_date_str}"

        if date_error:
            messages.error(request, date_error)
            active_filter_label = "Invalid Date Range"
            start_dt = None
            end_dt = None

    # 2. Preset Range Processing
    elif preset == 'today':
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        active_filter_label = "Today"
    elif preset == 'week':
        start_dt = now - timedelta(days=7)
        end_dt = now
        active_filter_label = "This Week"
    elif preset == 'month':
        start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_dt = now
        active_filter_label = "This Month"
    else:
        preset = 'all'
        active_filter_label = "All Invoices"

    # 3. Database Querying via Django ORM
    if date_error:
        qs = Invoice.objects.none()
    else:
        qs = Invoice.objects.all().select_related('customer').prefetch_related('items__product').order_by('-id')
        if start_dt:
            qs = qs.filter(created_at__gte=start_dt)
        if end_dt:
            qs = qs.filter(created_at__lte=end_dt)

    if search and not date_error:
        qs = qs.filter(
            Q(invoice_number__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__phone__icontains=search)
        )

    # Calculate aggregate metrics directly from database
    # A. Total Number of Invoices within selected date range
    total_invoices = qs.count()

    # B. Total Amount Collected: include only successfully collected/paid amounts
    # Exclude pending, failed, and unpaid invoices from collected amounts
    paid_qs = qs.filter(payment_status__iexact='paid')
    collected_agg = paid_qs.aggregate(total_collected=Sum('total_amount'))
    total_amount_collected = collected_agg['total_collected'] or Decimal('0.00')

    # Total sales (gross transaction value across paid invoices)
    total_sales = total_amount_collected

    # Total units sold across all invoice items in filtered invoices
    units_agg = InvoiceItem.objects.filter(invoice__in=qs).aggregate(total_units=Sum('quantity'))
    total_units_sold = units_agg['total_units'] or 0

    total_products = Product.objects.count()
    avg_invoice_val = (total_amount_collected / total_invoices) if total_invoices > 0 else Decimal('0.00')

    # Product-wise sales performance
    product_sales = list(InvoiceItem.objects.filter(invoice__in=qs).values(
        'product__id',
        'product__name',
        'product__category'
    ).annotate(
        units_sold=Sum('quantity'),
        total_revenue=Sum('total_price')
    ).order_by('-total_revenue')[:10])

    return {
        'qs': qs,
        'total_invoices': total_invoices,
        'total_amount_collected': total_amount_collected,
        'total_sales': total_sales,
        'total_units_sold': total_units_sold,
        'total_products': total_products,
        'avg_invoice_val': avg_invoice_val,
        'product_sales': product_sales,
        'preset': preset,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'search': search,
        'active_filter_label': active_filter_label,
        'date_error': date_error,
    }


def admin_reports(request):
    """
    Dedicated Reports and Analytics dashboard inside Admin Dashboard.
    Supports real-time metrics, date filtering (Today, Week, Month, Custom),
    product-wise sales performance, and paginated invoice logs.
    Restricted strictly to Administrator users.
    """
    try:
        user_id = request.session.get('user_id')
        user = None
        if user_id:
            try:
                user = User.objects.get(id=user_id, usertype='admin')
            except User.DoesNotExist:
                user = None

        if not user and request.user.is_authenticated and getattr(request.user, 'usertype', '') == 'admin':
            user = request.user

        if not user:
            messages.error(request, "Access restricted to Administrators only..!")
            return redirect('admin_login')

        data = get_filtered_report_data(request)

        # Pagination for invoice report table
        paginator = Paginator(data['qs'], 10)
        page_number = request.GET.get('page', 1)
        invoices = paginator.get_page(page_number)

        context = {
            'user': user,
            'invoices': invoices,
            'total_invoices': data['total_invoices'],
            'total_amount_collected': data['total_amount_collected'],
            'total_sales': data['total_sales'],
            'total_units_sold': data['total_units_sold'],
            'total_products': data['total_products'],
            'avg_invoice_value': data['avg_invoice_val'],
            'product_sales': data['product_sales'],
            'preset': data['preset'],
            'start_date': data['start_date'],
            'end_date': data['end_date'],
            'search': data['search'],
            'active_filter_label': data['active_filter_label'],
            'date_error': data.get('date_error'),
            'generated_at': timezone.now(),
        }
        return render(request, 'billing/admin-reports.html', context)
    except Exception as e:
        messages.error(request, f"Error generating reports: {str(e)}")
        return redirect('admin_dashboard')


def admin_reports_pdf(request):
    """
    Generate and download professional PDF export of the filtered Invoice Report.
    Uses xhtml2pdf (pisa) for PDF generation based on selected Start Date and End Date.
    Restricted strictly to Administrator users.
    """
    try:
        user_id = request.session.get('user_id')
        user = None
        if user_id:
            try:
                user = User.objects.get(id=user_id, usertype='admin')
            except User.DoesNotExist:
                user = None

        if not user and request.user.is_authenticated and getattr(request.user, 'usertype', '') == 'admin':
            user = request.user

        if not user:
            messages.error(request, "Access restricted to Administrators only..!")
            return redirect('admin_login')

        data = get_filtered_report_data(request)

        if data.get('date_error'):
            messages.error(request, data['date_error'])
            return redirect('admin_reports')

        context = {
            'admin': user,
            'business_name': getattr(user, 'company_name', None) or "Advance Billing System with QR",
            'invoices': data['qs'],
            'total_invoices': data['total_invoices'],
            'total_amount_collected': data['total_amount_collected'],
            'total_sales': data['total_sales'],
            'total_units_sold': data['total_units_sold'],
            'total_products': data['total_products'],
            'avg_invoice_value': data['avg_invoice_val'],
            'product_sales': data['product_sales'],
            'start_date': data['start_date'],
            'end_date': data['end_date'],
            'active_filter_label': data['active_filter_label'],
            'generated_at': timezone.now(),
        }

        html_content = render_to_string('billing/reports_pdf.html', context)
        buffer = io.BytesIO()
        pdf_status = pisa.CreatePDF(html_content, dest=buffer, encoding='utf-8')

        if pdf_status.err:
            return HttpResponse('Error generating Invoice Report PDF', status=500)

        pdf_data = buffer.getvalue()
        buffer.close()

        start_slug = data['start_date'].replace('-', '') if data['start_date'] else 'all'
        end_slug = data['end_date'].replace('-', '') if data['end_date'] else 'all'
        timestamp_str = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = f"Invoice_Report_{start_slug}_{end_slug}_{timestamp_str}.pdf"

        response = HttpResponse(pdf_data, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        messages.error(request, f"Error generating PDF report: {str(e)}")
        return redirect('admin_reports')


@csrf_exempt
def distributor_register(request):
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            company_name = request.POST.get('company_name', '').strip()
            password = request.POST.get('password', '').strip()

            # 1. Validate Name
            if not name:
                messages.error(request, "Please enter your full name.")
                return render(request, 'billing/register.html')

            # 2. Validate Email
            if not email:
                messages.error(request, "Please enter your email address.")
                return render(request, 'billing/register.html')

            if '@' not in email or '.' not in email:
                messages.error(request, "Please enter a valid email address.")
                return render(request, 'billing/register.html')

            if User.objects.filter(email=email).exists():
                messages.error(request, "An account with this email address already exists.")
                return render(request, 'billing/register.html')

            # 3. Validate Phone Number
            if not phone:
                messages.error(request, "Please enter your phone number.")
                return render(request, 'billing/register.html')

            clean_phone = ''.join(c for c in phone if c.isdigit())
            if len(clean_phone) < 10:
                messages.error(request, "Please enter a valid phone number (at least 10 digits).")
                return render(request, 'billing/register.html')

            if User.objects.filter(phone=phone).exists():
                messages.error(request, "An account with this phone number already exists.")
                return render(request, 'billing/register.html')

            # 4. Validate Company Name
            if not company_name:
                messages.error(request, "Please enter your company / outlet name.")
                return render(request, 'billing/register.html')

            # 5. Validate Password
            if not password:
                messages.error(request, "Please enter a password.")
                return render(request, 'billing/register.html')

            if len(password) < 6:
                messages.error(request, "Password must be at least 6 characters long.")
                return render(request, 'billing/register.html')

            # Complete registration after validation passes: Save to database
            dist_id = f"DIST-{random.randint(10000, 99999)}"

            User.objects.create_user(
                name=name,
                email=email,
                password=password,
                phone=phone,
                distributor_id=dist_id,
                company_name=company_name,
                usertype='distributor',
                today_sales=0.00,
                available_inventory=1000
            )

            messages.success(request, f"Registration successful! Your ID is {dist_id}. Please login.")
            return redirect('distributor_login')

        except Exception:
            messages.error(request, "Something went wrong. Please try again.")
            return render(request, 'billing/register.html')

    return render(request, 'billing/register.html')


@csrf_exempt
def generate_forgot_otp(request):
    if request.method == 'POST':
        try:
            
            identity = request.POST.get('identity', '').strip()
            user = None

            try:
                user = User.objects.get(email=identity)
            except User.DoesNotExist:
                try:
                    user = User.objects.get(phone=identity)
                except User.DoesNotExist:
                    pass

            if user:
                # Generate random 6-digit OTP
                otp_code = str(random.randint(100000, 999999))

                # Delete/invalidate old unverified OTPs for this identity
                OTP.objects.filter(identity=identity, is_verified=False).delete()

                # Store new OTP temporarily in database
                OTP.objects.create(identity=identity, otp=otp_code)
                request.session['reset_identity'] = identity

                return JsonResponse({'status': 'success', 'message': f'OTP generated and stored: {otp_code}', 'demo_otp': otp_code})
            else:
                return JsonResponse({'status': 'error', 'message': "Account doesn't exist..!"}, status=400)

        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Something went wrong.'}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid method.'}, status=405)


@csrf_exempt
def verify_reset_password(request):
    if request.method == 'POST':
        try:
            entered_otp = request.POST.get('otp', '').strip()
            identity = request.session.get('reset_identity', '').strip()
            new_password = request.POST.get('new_password', '').strip()

            if not identity:
                identity = request.POST.get('identity', '').strip()

            if not identity:
                return JsonResponse({'status': 'error', 'message': 'Session expired. Please generate OTP again.'}, status=400)

            # Retrieve latest unverified OTP record from database
            otp_record = OTP.objects.filter(identity=identity, is_verified=False).order_by('-created_at').first()

            if not otp_record:
                return JsonResponse({'status': 'error', 'message': 'Invalid OTP!'}, status=400)

            # Check 5-minute expiry (300 seconds)
            if timezone.now() - otp_record.created_at > timedelta(minutes=5):
                otp_record.delete()
                return JsonResponse({'status': 'error', 'message': 'OTP has expired!'}, status=400)

            # Validate OTP code
            if entered_otp == otp_record.otp:
                otp_record.is_verified = True
                otp_record.save()

                # Reset password if new password provided
                if new_password:
                    try:
                        user = User.objects.get(email=identity)
                    except User.DoesNotExist:
                        user = User.objects.get(phone=identity)
                    user.password = new_password
                    user.save()

                return JsonResponse({'status': 'success', 'message': 'OTP verified successfully!'})
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid OTP!'}, status=400)

        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Something went wrong.'}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid method.'}, status=405)


@csrf_exempt
def create_invoice(request):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('distributor_login')

        user = User.objects.get(id=user_id, usertype='distributor')
        products_qs = Product.objects.all().order_by('name')
        product_data = {
            str(p.id): {
                'name': p.name,
                'price': float(p.price),
                'gst_rate': float(p.gst_rate)
            } for p in products_qs
        }

        if request.method == 'POST':
            form = InvoiceCreationForm(request.POST)

            # Retrieve dynamic product rows
            product_ids = request.POST.getlist('product')
            quantities = request.POST.getlist('quantity')
            gst_rates = request.POST.getlist('gst')
            discount_rates = request.POST.getlist('discount')

            # Prepare submitted rows for preserving form input on validation error
            submitted_rows = []
            for i in range(len(product_ids)):
                submitted_rows.append({
                    'product_id': product_ids[i] if i < len(product_ids) else '',
                    'quantity': quantities[i] if i < len(quantities) else '1',
                    'gst': gst_rates[i] if i < len(gst_rates) else '0',
                    'discount': discount_rates[i] if i < len(discount_rates) else '0',
                })

            def render_form_with_error(error_msg):
                messages.error(request, error_msg)
                return render(request, 'billing/create-invoice.html', {
                    'user': user,
                    'profile': user,
                    'form': form,
                    'products': products_qs,
                    'product_data': product_data,
                    'submitted_rows': submitted_rows,
                })

            # 1. Validate Customer
            customer_id = request.POST.get('customer')
            if not customer_id:
                return render_form_with_error("Please select a valid customer.")

            try:
                customer = Customer.objects.get(id=customer_id)
            except (Customer.DoesNotExist, ValueError):
                return render_form_with_error("Selected customer is invalid.")

            # 2. Validate Product Rows
            if not product_ids:
                return render_form_with_error("Please select at least one valid product.")

            has_selected_product = any(bool(pid and pid.strip()) for pid in product_ids)
            if not has_selected_product:
                return render_form_with_error("Please select at least one valid product.")

            TWO_PLACES = Decimal('0.01')
            row_items = []
            overall_total = Decimal('0.00')

            for i in range(len(product_ids)):
                pid = product_ids[i].strip() if product_ids[i] else ''
                if not pid:
                    continue

                # Validate product existence
                try:
                    product_obj = Product.objects.get(id=pid)
                except (Product.DoesNotExist, ValueError):
                    return render_form_with_error("One or more selected products are invalid.")

                # Validate quantity
                qty_raw = quantities[i] if i < len(quantities) else '1'
                try:
                    qty = int(qty_raw)
                    if qty < 1:
                        return render_form_with_error(f"Quantity for '{product_obj.name}' must be at least 1.")
                except (ValueError, TypeError):
                    return render_form_with_error(f"Quantity for '{product_obj.name}' must be a valid whole number.")

                # Validate GST
                gst_raw = gst_rates[i] if i < len(gst_rates) else ''
                if gst_raw is not None and str(gst_raw).strip() != '':
                    try:
                        gst_val = Decimal(str(gst_raw).strip())
                        if gst_val < Decimal('0') or gst_val > Decimal('100'):
                            return render_form_with_error(f"GST rate for '{product_obj.name}' must be between 0 and 100%.")
                    except (InvalidOperation, ValueError, TypeError):
                        return render_form_with_error(f"GST rate for '{product_obj.name}' must be a valid number.")
                else:
                    gst_val = Decimal('0.00')

                # Validate Discount
                disc_raw = discount_rates[i] if i < len(discount_rates) else ''
                if disc_raw is not None and str(disc_raw).strip() != '':
                    try:
                        disc_val = Decimal(str(disc_raw).strip())
                        if disc_val < Decimal('0') or disc_val > Decimal('100'):
                            return render_form_with_error(f"Discount for '{product_obj.name}' must be between 0 and 100%.")
                    except (InvalidOperation, ValueError, TypeError):
                        return render_form_with_error(f"Discount for '{product_obj.name}' must be a valid number.")
                else:
                    disc_val = Decimal('0.00')

                # Server-side calculation using exact Decimal arithmetic
                unit_price = Decimal(str(product_obj.price)).quantize(TWO_PLACES)
                subtotal = unit_price * Decimal(qty)
                discount_amount = subtotal * (disc_val / Decimal('100'))
                taxable_value = max(Decimal('0.00'), subtotal - discount_amount)
                gst_amount = taxable_value * (gst_val / Decimal('100'))
                row_total = (taxable_value + gst_amount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                overall_total += row_total
                row_items.append({
                    'product': product_obj,
                    'quantity': qty,
                    'unit_price': unit_price,
                    'total_price': row_total,
                })

            if not row_items:
                return render_form_with_error("Please select at least one valid product.")

            # 3. Save Invoice and InvoiceItems within an atomic database transaction
            try:
                with transaction.atomic():
                    invoice_num = f"INV-{int(time.time())}-{random.randint(1000, 9999)}"
                    while Invoice.objects.filter(invoice_number=invoice_num).exists():
                        invoice_num = f"INV-{int(time.time())}-{random.randint(1000, 9999)}"

                    invoice = Invoice.objects.create(
                        customer=customer,
                        invoice_number=invoice_num,
                        total_amount=overall_total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                    )

                    for item in row_items:
                        InvoiceItem.objects.create(
                            invoice=invoice,
                            product=item['product'],
                            quantity=item['quantity'],
                            unit_price=item['unit_price'],
                            total_price=item['total_price']
                        )
            except Exception:
                return render_form_with_error("An error occurred while saving the invoice. Please try again.")

            request.session['latest_invoice_id'] = invoice.id
            messages.success(
                request,
                f"Invoice created successfully! (#{invoice.invoice_number}) "
                f"<a href=\"/invoice/{invoice.id}/pdf/\" target=\"_blank\" style=\"color:#3b82f6; text-decoration:underline; font-weight:600; margin-left:8px;\">Download PDF</a>"
            )
            return redirect('create_invoice')
        else:
            form = InvoiceCreationForm()

        latest_invoice_id = request.session.pop('latest_invoice_id', None)
        latest_invoice = None
        if latest_invoice_id:
            latest_invoice = Invoice.objects.filter(id=latest_invoice_id).first()

        return render(request, 'billing/create-invoice.html', {
            'user': user,
            'profile': user,
            'form': form,
            'products': products_qs,
            'product_data': product_data,
            'latest_invoice': latest_invoice,
        })
    except User.DoesNotExist:
        messages.error(request, "Access restricted to Distributors only..!")
        return redirect('distributor_login')
    except Exception as e:
        messages.error(request, f"An unexpected error occurred: {str(e)}")
        return redirect('distributor_dashboard')


def invoice_pdf(request, id):
    """Generate and return a professional PDF export for the selected invoice."""
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('distributor_login')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('distributor_login')

    try:
        invoice = Invoice.objects.select_related('customer').prefetch_related('items__product').get(id=id)
    except (Invoice.DoesNotExist, ValueError):
        raise Http404("Invoice not found.")

    context = {
        'invoice': invoice,
        'customer': invoice.customer,
        'items': invoice.items.all(),
        'distributor': user,
        'company_name': user.company_name or 'Advance Billing System',
        'qr_code_uri': generate_invoice_qr_base64(invoice),
        'qr_text': generate_invoice_qr_text(invoice),
    }

    try:
        html_content = render_to_string('billing/invoice_pdf.html', context)
        buffer = io.BytesIO()
        pdf_status = pisa.CreatePDF(html_content, dest=buffer, encoding='utf-8')

        if pdf_status.err:
            return HttpResponse('Error generating PDF', status=500)

        pdf_data = buffer.getvalue()
        buffer.close()

        response = HttpResponse(pdf_data, content_type='application/pdf')
        clean_inv_num = (invoice.invoice_number or str(invoice.id)).replace(' ', '_').replace('/', '_')
        filename = f"invoice_{clean_inv_num}.pdf"
        is_download = (
            request.GET.get('download') in ('1', 'true', 'yes') or
            (request.resolver_match and request.resolver_match.url_name == 'download_invoice_pdf')
        )
        disposition = 'attachment' if is_download else 'inline'
        response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
        return response
    except Exception:
        return HttpResponse('Error generating PDF', status=500)


def generate_invoice_qr_text(invoice):
    """
    Construct standardized text payload for invoice QR code:
    Invoice ID: <id>
    Customer: <name>
    Product Count: <count>
    Total Bill: Rs <amount>
    Invoice Date: <date>
    """
    inv_id = invoice.invoice_number or str(invoice.id)
    cust_name = invoice.customer.name if invoice.customer else "Unknown"

    if hasattr(invoice, '_prefetched_objects_cache') and 'items' in invoice._prefetched_objects_cache:
        prod_count = len(invoice.items.all())
    else:
        prod_count = invoice.items.count()

    total_val = invoice.total_amount if invoice.total_amount is not None else Decimal('0.00')
    total_str = f"Rs {total_val:,.2f}"

    lines = [
        f"Invoice ID: {inv_id}",
        f"Customer: {cust_name}",
        f"Product Count: {prod_count}",
        f"Total Bill: {total_str}",
    ]

    if invoice.created_at:
        inv_date = invoice.created_at.strftime('%d-%m-%Y')
        lines.append(f"Invoice Date: {inv_date}")

    return "\n".join(lines)


def generate_invoice_qr_base64(invoice):
    """
    Generate dynamic QR code in-memory and return base64 Data URI string.
    Avoids disk writes and duplicate permanent image accumulation.
    """
    qr_text = generate_invoice_qr_text(invoice)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(qr_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
    buffer.close()
    return f"data:image/png;base64,{b64_str}"


def invoice_list(request):
    """
    Retrieve existing invoices from database with select_related & prefetch_related,
    paginate them, compute product count, generate dynamic QR codes, and render the table.
    """
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('distributor_login')

        user = User.objects.get(id=user_id, usertype='distributor')

        search = request.GET.get('search', '').strip()
        invoices_qs = Invoice.objects.select_related('customer').prefetch_related('items').order_by('-created_at', '-id')

        if search:
            invoices_qs = invoices_qs.filter(
                Q(invoice_number__icontains=search) |
                Q(customer__name__icontains=search) |
                Q(customer__phone__icontains=search)
            )

        total_invoices = invoices_qs.count()

        paginator = Paginator(invoices_qs, 10)
        page_number = request.GET.get('page', 1)
        invoices_page = paginator.get_page(page_number)

        # Attach computed metadata and QR code data URI to items on the current page
        for inv in invoices_page:
            inv.product_count = len(inv.items.all())
            inv.qr_code_uri = generate_invoice_qr_base64(inv)
            inv.qr_text = generate_invoice_qr_text(inv)

        return render(request, 'billing/invoice-list.html', {
            'user': user,
            'profile': user,
            'invoices': invoices_page,
            'search': search,
            'total_invoices': total_invoices,
        })
    except User.DoesNotExist:
        messages.error(request, "Access restricted to Distributors only..!")
        return redirect('distributor_login')
    except Exception as e:
        messages.error(request, f"An unexpected error occurred: {str(e)}")
        return redirect('distributor_dashboard')


def invoice_qr_code(request, id):
    """
    Endpoint to view or download a standalone PNG QR code for an invoice.
    """
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('distributor_login')

    try:
        user = User.objects.get(id=user_id, usertype='distributor')
    except User.DoesNotExist:
        return redirect('distributor_login')

    try:
        invoice = Invoice.objects.select_related('customer').prefetch_related('items').get(id=id)
    except (Invoice.DoesNotExist, ValueError):
        raise Http404("Invoice not found.")

    qr_text = generate_invoice_qr_text(invoice)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )
    qr.add_data(qr_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    png_data = buffer.getvalue()
    buffer.close()

    response = HttpResponse(png_data, content_type='image/png')
    clean_num = (invoice.invoice_number or str(invoice.id)).replace(' ', '_').replace('/', '_')
    if request.GET.get('download') == '1':
        response['Content-Disposition'] = f'attachment; filename="qr_invoice_{clean_num}.png"'
    else:
        response['Content-Disposition'] = f'inline; filename="qr_invoice_{clean_num}.png"'
    return response

