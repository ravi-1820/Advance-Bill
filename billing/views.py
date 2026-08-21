import random
import time
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from billing.models import User


def index(request):
    return render(request, 'billing/index.html')


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
                    return redirect('index')
            else:
                messages.error(request, "Distributor account doesn't exist..!")
                return redirect('index')

        except Exception:
            messages.error(request, "Something went wrong. Please try again.")
            return redirect('index')

    return redirect('index')


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


@csrf_exempt
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
                otp = str(random.randint(100000, 999999))
                request.session['forgot_otp'] = otp
                request.session['forgot_user_id'] = user.id
                request.session['forgot_otp_time'] = time.time()
                return JsonResponse({'status': 'success', 'message': f'OTP sent: {otp}', 'demo_otp': otp})
            else:
                return JsonResponse({'status': 'error', 'message': "Account doesn't exist..!"}, status=400)

        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Something went wrong.'}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid method.'}, status=405)


@csrf_exempt
def verify_reset_password(request):
    if request.method == 'POST':
        try:
            otp = request.POST.get('otp', '').strip()
            new_password = request.POST.get('new_password', '').strip()

            session_otp = request.session.get('forgot_otp')
            user_id = request.session.get('forgot_user_id')

            if not session_otp or not user_id:
                return JsonResponse({'status': 'error', 'message': 'OTP session expired.'}, status=400)

            if otp == session_otp:
                try:
                    user = User.objects.get(id=user_id)
                    user.password = new_password
                    user.save()

                    try:
                        del request.session['forgot_otp']
                        del request.session['forgot_user_id']
                    except KeyError:
                        pass

                    return JsonResponse({'status': 'success', 'message': 'Password reset successful!'})
                except User.DoesNotExist:
                    return JsonResponse({'status': 'error', 'message': "User doesn't exist..!"}, status=400)
            else:
                return JsonResponse({'status': 'error', 'message': "OTP code doesn't match..!"}, status=400)

        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Something went wrong.'}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid method.'}, status=405)
