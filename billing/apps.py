from django.apps import AppConfig


class BillingConfig(AppConfig):
    name = 'billing'

    def ready(self):
        # Disconnect update_last_login because billing.models.User does not have a last_login column
        from django.contrib.auth.signals import user_logged_in
        user_logged_in.disconnect(dispatch_uid='update_last_login')
