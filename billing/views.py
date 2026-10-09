import random
import time
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator
from billing.models import User, OTP, Customer, Product, Invoice, InvoiceItem
from billing.forms import InvoiceCreationForm


def index(request):
    return render(request, 'billing/distributor-login.html')


@csrf_exempt
def distributor_login(request):
    if request.method == 'POST':
        identity = request.POST.get('identity', '').strip()
        password = request.POST.get('password', '').strip()
        mobile = request.POST.get('mobile', '').strip()

        try:
            user = None

            # 1. Search by mobile number
            if mobile:
                try:
                    user = User.objects.get(phone=mobile, usertype='distributor')
                except User.DoesNotExist:
                    pass

            # 2. Search by distributor ID
            if not user and identity:
                try:
                    user = User.objects.get(distributor_id=identity, usertype='distributor')
                except User.DoesNotExist:
                    pass

            # 3. Search by email
            if not user and identity:
                try:
                    user = User.objects.get(email=identity, usertype='distributor')
                except User.DoesNotExist:
                    pass

            if user:
                # Validate password
                if user.password == password:
                    request.session['user_id'] = user.id
                    request.session['email'] = user.email
                    request.session['name'] = user.company_name or user.name
                    request.session['usertype'] = 'distributor'
                    return redirect('distributor_dashboard')
                else:
                    messages.error(request, "Password doesn't match..!")
                    return render(request, 'billing/distributor-login.html')
            else:
                messages.error(request, "Distributor account doesn't exist..!")
                return render(request, 'billing/distributor-login.html')

        except Exception:
            messages.error(request, "Something went wrong. Please try again.")
            return render(request, 'billing/distributor-login.html')

    return render(request, 'billing/distributor-login.html')


@csrf_exempt
def admin_login(request):
    if request.method == 'POST':
        admin_identity = request.POST.get('admin_email', '').strip()
        password = request.POST.get('admin_password', '').strip()

        try:
            user = None
            try:
                user = User.objects.get(email=admin_identity, usertype='admin')
            except User.DoesNotExist:
                pass

            if user:
                if user.password == password:
                    request.session['user_id'] = user.id
                    request.session['email'] = user.email
                    request.session['name'] = user.name
                    request.session['usertype'] = 'admin'
                    return redirect('admin_dashboard')
                else:
                    messages.error(request, "Password doesn't match..!")
                    return render(request, 'billing/admin-login.html')
            else:
                messages.error(request, "Admin account doesn't exist..!")
                return render(request, 'billing/admin-login.html')

        except Exception:
            messages.error(request, "Something went wrong. Please try again.")
            return render(request, 'billing/admin-login.html')

    return render(request, 'billing/admin-login.html')


def logout_view(request):
    try:
        request.session.flush()
        messages.info(request, "Logged out successfully..!")
    except Exception:
        pass
    return redirect('index')


def distributor_dashboard(request):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('index')

        user = User.objects.get(id=user_id, usertype='distributor')
        return render(request, 'billing/distributor-dashboard.html', {'user': user, 'profile': user})
    except User.DoesNotExist:
        messages.error(request, "Access restricted to Distributors only..!")
        return redirect('index')
    except Exception:
        return redirect('index')


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

        user = User.objects.get(id=user_id, usertype='distributor')

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

        user = User.objects.get(id=user_id, usertype='distributor')

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

        user = User.objects.get(id=user_id, usertype='distributor')
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

        user = User.objects.get(id=user_id, usertype='distributor')
        product = Product.objects.get(id=id)

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



def admin_dashboard(request):
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return redirect('index')

        user = User.objects.get(id=user_id, usertype='admin')
        return render(request, 'billing/admin-dashboard.html', {'user': user})
    except User.DoesNotExist:
        messages.error(request, "Access restricted to Administrators only..!")
        return redirect('index')
    except Exception:
        return redirect('index')


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

            User.objects.create(
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

            messages.success(request, f"Invoice created successfully! (#{invoice.invoice_number})")
            return redirect('create_invoice')
        else:
            form = InvoiceCreationForm()

        return render(request, 'billing/create-invoice.html', {
            'user': user,
            'profile': user,
            'form': form,
            'products': products_qs,
            'product_data': product_data
        })
    except User.DoesNotExist:
        messages.error(request, "Access restricted to Distributors only..!")
        return redirect('distributor_login')
    except Exception as e:
        messages.error(request, f"An unexpected error occurred: {str(e)}")
        return redirect('distributor_dashboard')
