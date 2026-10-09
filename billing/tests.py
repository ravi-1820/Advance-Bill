from django.test import TestCase, Client
from django.urls import reverse
from billing.models import User, Customer, Product, Invoice, InvoiceItem
from billing.forms import InvoiceCreationForm


class InvoiceCreationFormTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="John Doe",
            email="john@example.com",
            phone="9876543210",
            address="123 Main St"
        )
        self.product = Product.objects.create(
            name="Laptop",
            category="Electronics",
            price=50000.00,
            stock=10,
            gst_rate=18.00
        )

    def test_form_valid_data(self):
        form = InvoiceCreationForm(data={
            'customer': self.customer.id,
            'product': self.product.id,
            'quantity': 2,
            'gst': 18,
            'discount': 10
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['customer'], self.customer)
        self.assertEqual(form.cleaned_data['product'], self.product)
        self.assertEqual(form.cleaned_data['quantity'], 2)
        self.assertEqual(form.cleaned_data['gst'], 18)
        self.assertEqual(form.cleaned_data['discount'], 10)

    def test_form_missing_customer(self):
        form = InvoiceCreationForm(data={
            'customer': '',
            'product': self.product.id,
            'quantity': 1
        })
        self.assertFalse(form.is_valid())
        self.assertIn('customer', form.errors)

    def test_form_missing_product(self):
        form = InvoiceCreationForm(data={
            'customer': self.customer.id,
            'product': '',
            'quantity': 1
        })
        self.assertFalse(form.is_valid())
        self.assertIn('product', form.errors)

    def test_form_invalid_quantity(self):
        form_zero = InvoiceCreationForm(data={
            'customer': self.customer.id,
            'product': self.product.id,
            'quantity': 0
        })
        self.assertFalse(form_zero.is_valid())
        self.assertIn('quantity', form_zero.errors)

        form_neg = InvoiceCreationForm(data={
            'customer': self.customer.id,
            'product': self.product.id,
            'quantity': -5
        })
        self.assertFalse(form_neg.is_valid())
        self.assertIn('quantity', form_neg.errors)

    def test_form_negative_gst_or_discount(self):
        form_neg_gst = InvoiceCreationForm(data={
            'customer': self.customer.id,
            'product': self.product.id,
            'quantity': 1,
            'gst': -5
        })
        self.assertFalse(form_neg_gst.is_valid())
        self.assertIn('gst', form_neg_gst.errors)

        form_neg_disc = InvoiceCreationForm(data={
            'customer': self.customer.id,
            'product': self.product.id,
            'quantity': 1,
            'discount': -10
        })
        self.assertFalse(form_neg_disc.is_valid())
        self.assertIn('discount', form_neg_disc.errors)

    def test_dropdown_dynamic_records(self):
        # Adding a second customer and product to verify dynamic fetching from DB
        customer2 = Customer.objects.create(name="Jane Smith", phone="9123456780")
        product2 = Product.objects.create(name="Wireless Mouse", category="Accessories", price=800.00, stock=50)

        form = InvoiceCreationForm()
        customer_choices = [c[1] for c in form.fields['customer'].choices]
        product_choices = [p[1] for p in form.fields['product'].choices]

        self.assertIn("John Doe", customer_choices)
        self.assertIn("Jane Smith", customer_choices)
        self.assertIn("Laptop", product_choices)
        self.assertIn("Wireless Mouse", product_choices)


class InvoiceCreationViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.distributor = User.objects.create(
            name="Test Distributor",
            email="dist@test.com",
            password="pass123",
            phone="9876543210",
            distributor_id="DIST-99999",
            usertype="distributor"
        )
        self.customer = Customer.objects.create(
            name="Alice Corp",
            email="alice@corp.com",
            phone="9898989898",
            address="789 Park Ave"
        )
        self.product = Product.objects.create(
            name="Smartphone",
            category="Mobile",
            price=25000.00,
            stock=20,
            gst_rate=12.00
        )
        self.product_item = Product.objects.create(
            name="Mechanical Keyboard",
            category="Accessories",
            price=1000.00,
            stock=15,
            gst_rate=18.00
        )

    def test_view_get_unauthenticated(self):
        response = self.client.get(reverse('create_invoice'))
        self.assertEqual(response.status_code, 302)

    def test_view_get_authenticated(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        response = self.client.get(reverse('create_invoice'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice Corp")
        self.assertContains(response, "Smartphone")
        self.assertIn('product_data', response.context)

    def test_view_post_creates_invoice_and_item_without_discount_gst(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        response = self.client.post(reverse('create_invoice'), {
            'customer': self.customer.id,
            'product': self.product.id,
            'quantity': 3
        })
        self.assertEqual(response.status_code, 302)

        # Check database records
        invoice = Invoice.objects.filter(customer=self.customer).first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.total_amount, 75000.00)

        invoice_item = InvoiceItem.objects.filter(invoice=invoice).first()
        self.assertIsNotNone(invoice_item)
        self.assertEqual(invoice_item.product, self.product)
        self.assertEqual(invoice_item.quantity, 3)
        self.assertEqual(invoice_item.unit_price, 25000.00)
        self.assertEqual(invoice_item.total_price, 75000.00)

    def test_view_post_creates_invoice_with_discount_and_gst_calc(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        # Test Case: Price = 1000, Quantity = 2, GST = 18%, Discount = 10%
        # Subtotal = 2000, Discount = 200, Taxable = 1800, GST = 324, Total = 2124
        response = self.client.post(reverse('create_invoice'), {
            'customer': self.customer.id,
            'product': self.product_item.id,
            'quantity': 2,
            'gst': 18,
            'discount': 10
        })
        self.assertEqual(response.status_code, 302)

        invoice = Invoice.objects.filter(customer=self.customer).order_by('-id').first()
        self.assertIsNotNone(invoice)
        self.assertEqual(float(invoice.total_amount), 2124.00)

        invoice_item = InvoiceItem.objects.filter(invoice=invoice).first()
        self.assertIsNotNone(invoice_item)
        self.assertEqual(float(invoice_item.total_price), 2124.00)

    def test_view_post_creates_invoice_with_multiple_product_rows(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        # Product A: Price = 1000, Qty = 2, GST = 18%, Discount = 10% -> 2124.00
        # Product B: Price = 500, Qty = 3, GST = 5%, Discount = 0% -> 1575.00
        product_b = Product.objects.create(
            name="USB-C Cable",
            category="Accessories",
            price=500.00,
            stock=50,
            gst_rate=5.00
        )

        response = self.client.post(reverse('create_invoice'), {
            'customer': self.customer.id,
            'product': [self.product_item.id, product_b.id],
            'quantity': [2, 3],
            'gst': [18, 5],
            'discount': [10, 0]
        })
        self.assertEqual(response.status_code, 302)

        # 1. Exactly one Invoice created for customer
        invoices = Invoice.objects.filter(customer=self.customer).order_by('-id')
        invoice = invoices.first()
        self.assertIsNotNone(invoice)

        # 2. Overall invoice total = 2124.00 + 1575.00 = 3699.00
        self.assertEqual(float(invoice.total_amount), 3699.00)

        # 3. Two InvoiceItem records created under the same Invoice
        items = InvoiceItem.objects.filter(invoice=invoice).order_by('id')
        self.assertEqual(items.count(), 2)

        # Verify Item 1
        item1 = items[0]
        self.assertEqual(item1.product, self.product_item)
        self.assertEqual(item1.quantity, 2)
        self.assertEqual(float(item1.unit_price), 1000.00)
        self.assertEqual(float(item1.total_price), 2124.00)

        # Verify Item 2
        item2 = items[1]
        self.assertEqual(item2.product, product_b)
        self.assertEqual(item2.quantity, 3)
        self.assertEqual(float(item2.unit_price), 500.00)
        self.assertEqual(float(item2.total_price), 1575.00)

    def test_invalid_customer_rejected(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        initial_count = Invoice.objects.count()
        response = self.client.post(reverse('create_invoice'), {
            'customer': 99999,
            'product': self.product.id,
            'quantity': 1
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Invoice.objects.count(), initial_count)
        self.assertContains(response, "Selected customer is invalid")

    def test_invalid_product_rejected(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        initial_count = Invoice.objects.count()
        response = self.client.post(reverse('create_invoice'), {
            'customer': self.customer.id,
            'product': 99999,
            'quantity': 1
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Invoice.objects.count(), initial_count)
        self.assertContains(response, "One or more selected products are invalid")

    def test_invalid_quantity_rejected(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        initial_count = Invoice.objects.count()
        response = self.client.post(reverse('create_invoice'), {
            'customer': self.customer.id,
            'product': self.product.id,
            'quantity': 0
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Invoice.objects.count(), initial_count)
        self.assertContains(response, "must be at least 1")

    def test_invalid_gst_rejected(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        initial_count = Invoice.objects.count()
        response = self.client.post(reverse('create_invoice'), {
            'customer': self.customer.id,
            'product': self.product.id,
            'quantity': 1,
            'gst': 150
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Invoice.objects.count(), initial_count)
        self.assertContains(response, "must be between 0 and 100%")

    def test_invalid_discount_rejected(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        initial_count = Invoice.objects.count()
        response = self.client.post(reverse('create_invoice'), {
            'customer': self.customer.id,
            'product': self.product.id,
            'quantity': 1,
            'discount': -5
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Invoice.objects.count(), initial_count)
        self.assertContains(response, "must be between 0 and 100%")

    def test_no_product_rows_rejected(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        initial_count = Invoice.objects.count()
        response = self.client.post(reverse('create_invoice'), {
            'customer': self.customer.id,
            'product': '',
            'quantity': 1
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Invoice.objects.count(), initial_count)
        self.assertContains(response, "Please select at least one valid product")

    def test_atomic_transaction_rollback_on_failure(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        initial_invoices = Invoice.objects.count()
        initial_items = InvoiceItem.objects.count()

        from unittest.mock import patch

        with patch('billing.models.InvoiceItem.objects.create', side_effect=RuntimeError("Simulated DB error")):
            response = self.client.post(reverse('create_invoice'), {
                'customer': self.customer.id,
                'product': self.product.id,
                'quantity': 2
            })
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "An error occurred while saving the invoice")

        # Confirm atomic rollback left no partial invoice or item
        self.assertEqual(Invoice.objects.count(), initial_invoices)
        self.assertEqual(InvoiceItem.objects.count(), initial_items)

    def test_success_message_displayed_after_creation(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        response = self.client.post(reverse('create_invoice'), {
            'customer': self.customer.id,
            'product': self.product.id,
            'quantity': 1
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invoice created successfully!")

