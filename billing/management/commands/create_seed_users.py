from django.core.management.base import BaseCommand
from billing.models import User

class Command(BaseCommand):
    help = 'Creates default development seed users for Admin and Distributor'

    def handle(self, *args, **options):
        # 1. Create Admin User
        admin_email = 'admin@advancebilling.com'
        admin_password = 'admin123'

        admin_user, created_admin = User.objects.get_or_create(
            email=admin_email,
            defaults={
                'name': 'Master Administrator',
                'password': admin_password,
                'usertype': 'admin'
            }
        )
        if not created_admin:
            admin_user.password = admin_password
            admin_user.usertype = 'admin'
            admin_user.save()
        self.stdout.write(self.style.SUCCESS(f"Admin user '{admin_email}' created/updated successfully."))

        # 2. Create Distributor User
        dist_id = 'DIST-77492'
        dist_mobile = '94095369850'
        dist_password = 'distributor123'
        dist_company = 'Apex Distributors'
        dist_email = 'distributor@advancebilling.com'

        dist_user, created_dist = User.objects.get_or_create(
            email=dist_email,
            defaults={
                'name': 'Apex Distributor',
                'password': dist_password,
                'phone': dist_mobile,
                'distributor_id': dist_id,
                'company_name': dist_company,
                'usertype': 'distributor',
                'today_sales': 112850.00,
                'available_inventory': 2840
            }
        )
        if not created_dist:
            dist_user.password = dist_password
            dist_user.phone = dist_mobile
            dist_user.distributor_id = dist_id
            dist_user.company_name = dist_company
            dist_user.usertype = 'distributor'
            dist_user.save()

        self.stdout.write(self.style.SUCCESS(f"Distributor user '{dist_id}' created/updated successfully."))
