import random
import time
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from billing.models import User, OTP


def index(request):
    return render(request, 'billing/index.html')


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
                    return redirect('index')
            else:
                messages.error(request, "Distributor account doesn't exist..!")
                return redirect('index')

        except Exception:
            messages.error(request, "Something went wrong. Please try again.")
            return redirect('index')

    return redirect('index')


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
                    return redirect('index')
            else:
                messages.error(request, "Admin account doesn't exist..!")
                return redirect('index')

        except Exception:
            messages.error(request, "Something went wrong. Please try again.")
            return redirect('index')

    return redirect('index')


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


def distributor_register(request):
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            password = request.POST.get('password', '').strip()
            company_name = request.POST.get('company_name', '').strip() or name

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

            messages.success(request, f"Registration successful! Your ID is {dist_id}")
            return redirect('index')

        except Exception:
            messages.error(request, "Registration failed! Email or Phone might already exist.")
            return redirect('index')

    return redirect('index')


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
