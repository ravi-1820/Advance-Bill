import io
from datetime import timedelta
from decimal import Decimal
from pypdf import PdfReader
from django.utils import timezone
from django.core import mail
from django.test import TestCase, Client
from django.urls import reverse
from billing.models import User, Customer, Product, Invoice, InvoiceItem, OTP
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


class PDFGenerationLibraryTest(TestCase):
    """Smoke test to verify that the configured PDF library functions properly."""

    def test_xhtml2pdf_import_and_render_memory(self):
        import io
        from xhtml2pdf import pisa

        html_content = "<html><body><h1>Smoke Test PDF</h1><p>Invoice PDF Engine Ready</p></body></html>"
        output_buffer = io.BytesIO()
        pdf_status = pisa.CreatePDF(html_content, dest=output_buffer)

        self.assertFalse(pdf_status.err)
        pdf_bytes = output_buffer.getvalue()
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))
        self.assertGreater(len(pdf_bytes), 500)


class InvoicePDFExportViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.distributor = User.objects.create(
            name="John Distributor",
            email="dist@test.com",
            password="pass",
            phone="9876543210",
            distributor_id="DIST-11223",
            company_name="Apex Global Distribution",
            usertype="distributor"
        )
        self.customer = Customer.objects.create(
            name="Bob Smith",
            email="bob@example.com",
            phone="9123456789",
            address="456 Elm Street"
        )
        self.product1 = Product.objects.create(
            name="Gaming Mouse",
            category="Accessories",
            price=1500.00,
            stock=30,
            gst_rate=18.00
        )
        self.product2 = Product.objects.create(
            name="Mechanical Keyboard",
            category="Accessories",
            price=3500.00,
            stock=20,
            gst_rate=18.00
        )
        self.invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_number="INV-202610-001",
            total_amount=6500.00
        )
        self.item1 = InvoiceItem.objects.create(
            invoice=self.invoice,
            product=self.product1,
            quantity=2,
            unit_price=1500.00,
            total_price=3000.00
        )
        self.item2 = InvoiceItem.objects.create(
            invoice=self.invoice,
            product=self.product2,
            quantity=1,
            unit_price=3500.00,
            total_price=3500.00
        )

    def test_pdf_export_unauthenticated_redirects(self):
        response = self.client.get(reverse('invoice_pdf', args=[self.invoice.id]))
        self.assertEqual(response.status_code, 302)

    def test_pdf_export_authenticated_returns_pdf(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        response = self.client.get(reverse('invoice_pdf', args=[self.invoice.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('inline;', response['Content-Disposition'])
        self.assertIn('INV-202610-001', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertGreater(len(response.content), 1000)

    def test_pdf_export_download_parameter(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        response = self.client.get(reverse('invoice_pdf', args=[self.invoice.id]) + '?download=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])

    def test_pdf_export_nonexistent_invoice_404(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        response = self.client.get(reverse('invoice_pdf', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_download_invoice_pdf_named_route(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        response = self.client.get(reverse('download_invoice_pdf', args=[self.invoice.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('invoice_INV-202610-001.pdf', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF-'))

    def test_download_invoice_pdf_nonexistent_404(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        response = self.client.get(reverse('download_invoice_pdf', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_invoice_list_contains_download_pdf_button(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        response = self.client.get(reverse('invoice_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Download PDF')
        self.assertContains(response, reverse('download_invoice_pdf', args=[self.invoice.id]))


class InvoiceQRCodeAndListPaginationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.distributor = User.objects.create(
            name="Test Distributor",
            email="distributor@test.com",
            password="pass123",
            phone="9876543210",
            distributor_id="DIST-9999",
            company_name="Test POS",
            usertype="distributor"
        )
        self.customer = Customer.objects.create(
            name="Ravi Suthar",
            email="ravi@example.com",
            phone="9876500000",
            address="Ahmedabad, Gujarat"
        )
        self.product1 = Product.objects.create(
            name="Leather Shoes",
            category="Footwear",
            price=2500.00,
            stock=20,
            gst_rate=18.00
        )
        self.product2 = Product.objects.create(
            name="Shoe Polish",
            category="Accessories",
            price=500.00,
            stock=50,
            gst_rate=18.00
        )
        self.invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_number="INV-1001",
            total_amount=5500.00
        )
        self.item1 = InvoiceItem.objects.create(
            invoice=self.invoice,
            product=self.product1,
            quantity=2,
            unit_price=2500.00,
            total_price=5000.00
        )
        self.item2 = InvoiceItem.objects.create(
            invoice=self.invoice,
            product=self.product2,
            quantity=1,
            unit_price=500.00,
            total_price=500.00
        )

    def login_distributor(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session['name'] = self.distributor.company_name
        session.save()

    def test_qr_text_generation_content(self):
        from billing.views import generate_invoice_qr_text
        qr_text = generate_invoice_qr_text(self.invoice)
        self.assertIn("Invoice ID: INV-1001", qr_text)
        self.assertIn("Customer: Ravi Suthar", qr_text)
        self.assertIn("Product Count: 2", qr_text)
        self.assertIn("Total Bill: Rs 5,500.00", qr_text)
        self.assertIn("Invoice Date:", qr_text)

    def test_qr_base64_generation(self):
        from billing.views import generate_invoice_qr_base64
        qr_uri = generate_invoice_qr_base64(self.invoice)
        self.assertTrue(qr_uri.startswith("data:image/png;base64,"))
        self.assertGreater(len(qr_uri), 100)

    def test_invoice_list_unauthenticated_redirects(self):
        response = self.client.get(reverse('invoice_list'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith(reverse('distributor_login')) or response.url == reverse('distributor_login'))

    def test_invoice_list_authenticated_displays_invoices(self):
        self.login_distributor()
        response = self.client.get(reverse('invoice_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'billing/invoice-list.html')
        self.assertContains(response, "INV-1001")
        self.assertContains(response, "Ravi Suthar")
        self.assertContains(response, "5500.00")
        self.assertContains(response, "data:image/png;base64,")

    def test_invoice_list_empty_state(self):
        InvoiceItem.objects.all().delete()
        Invoice.objects.all().delete()
        self.login_distributor()
        response = self.client.get(reverse('invoice_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No invoices have been generated yet")

    def test_invoice_list_search_filtering(self):
        self.login_distributor()
        # Search match
        res_found = self.client.get(reverse('invoice_list') + '?search=Ravi')
        self.assertEqual(res_found.status_code, 200)
        self.assertContains(res_found, "INV-1001")

        # Search no match
        res_not_found = self.client.get(reverse('invoice_list') + '?search=NonExistentCustomer')
        self.assertEqual(res_not_found.status_code, 200)
        self.assertContains(res_not_found, "No invoices found matching")

    def test_invoice_list_pagination(self):
        self.login_distributor()
        # Create 14 additional invoices to exceed page size of 10
        for i in range(1, 15):
            inv = Invoice.objects.create(
                customer=self.customer,
                invoice_number=f"INV-PAG-{i:03d}",
                total_amount=100.00 * i
            )
            InvoiceItem.objects.create(
                invoice=inv,
                product=self.product1,
                quantity=1,
                unit_price=100.00,
                total_price=100.00
            )

        # Page 1
        res_p1 = self.client.get(reverse('invoice_list') + '?page=1')
        self.assertEqual(res_p1.status_code, 200)
        self.assertEqual(len(res_p1.context['invoices']), 10)
        self.assertTrue(res_p1.context['invoices'].has_next())

        # Page 2
        res_p2 = self.client.get(reverse('invoice_list') + '?page=2')
        self.assertEqual(res_p2.status_code, 200)
        self.assertEqual(len(res_p2.context['invoices']), 5)
        self.assertTrue(res_p2.context['invoices'].has_previous())

        # Invalid page safely handled (returns last page or page 1)
        res_invalid = self.client.get(reverse('invoice_list') + '?page=999')
        self.assertEqual(res_invalid.status_code, 200)
        self.assertEqual(res_invalid.context['invoices'].number, 2)

    def test_invoice_qr_code_direct_endpoint(self):
        self.login_distributor()
        response = self.client.get(reverse('invoice_qr_code', args=[self.invoice.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertIn('inline;', response['Content-Disposition'])

        res_download = self.client.get(reverse('invoice_qr_code', args=[self.invoice.id]) + '?download=1')
        self.assertEqual(res_download.status_code, 200)
        self.assertIn('attachment;', res_download['Content-Disposition'])

    def test_invoice_qr_code_nonexistent_invoice_404(self):
        self.login_distributor()
        response = self.client.get(reverse('invoice_qr_code', args=[99999]))
        self.assertEqual(response.status_code, 404)


class InvoicePDFQREmbeddingTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.distributor = User.objects.create(
            name="Distributor One",
            email="dist@test.com",
            password="pass",
            phone="9876543210",
            distributor_id="DIST-001",
            company_name="Apex Footwear",
            usertype="distributor"
        )
        self.customer_a = Customer.objects.create(name="Customer Alpha", phone="9000000001")
        self.customer_b = Customer.objects.create(name="Customer Beta", phone="9000000002")

        self.product = Product.objects.create(name="Sneakers", category="Shoes", price=1200.00, stock=50)

        # Invoice A
        self.invoice_a = Invoice.objects.create(
            customer=self.customer_a,
            invoice_number="INV-ALPHA-101",
            total_amount=2400.00
        )
        InvoiceItem.objects.create(
            invoice=self.invoice_a,
            product=self.product,
            quantity=2,
            unit_price=1200.00,
            total_price=2400.00
        )

        # Invoice B
        self.invoice_b = Invoice.objects.create(
            customer=self.customer_b,
            invoice_number="INV-BETA-202",
            total_amount=3600.00
        )
        InvoiceItem.objects.create(
            invoice=self.invoice_b,
            product=self.product,
            quantity=3,
            unit_price=1200.00,
            total_price=3600.00
        )

    def login_distributor(self):
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

    def test_pdf_contains_dynamic_qr_code(self):
        self.login_distributor()
        response = self.client.get(reverse('invoice_pdf', args=[self.invoice_a.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF-'))
        # PDF is generated with substantial binary payload containing the embedded QR image stream
        self.assertGreater(len(response.content), 2000)

    def test_multiple_invoices_generate_different_qr_and_pdfs(self):
        self.login_distributor()
        from billing.views import generate_invoice_qr_text, generate_invoice_qr_base64

        qr_text_a = generate_invoice_qr_text(self.invoice_a)
        qr_text_b = generate_invoice_qr_text(self.invoice_b)
        self.assertIn("INV-ALPHA-101", qr_text_a)
        self.assertIn("Customer Alpha", qr_text_a)
        self.assertIn("INV-BETA-202", qr_text_b)
        self.assertIn("Customer Beta", qr_text_b)
        self.assertNotEqual(qr_text_a, qr_text_b)

        qr_uri_a = generate_invoice_qr_base64(self.invoice_a)
        qr_uri_b = generate_invoice_qr_base64(self.invoice_b)
        self.assertNotEqual(qr_uri_a, qr_uri_b)

        # Generate PDF for both invoices
        pdf_a = self.client.get(reverse('invoice_pdf', args=[self.invoice_a.id]))
        pdf_b = self.client.get(reverse('invoice_pdf', args=[self.invoice_b.id]))
        self.assertEqual(pdf_a.status_code, 200)
        self.assertEqual(pdf_b.status_code, 200)
        self.assertNotEqual(pdf_a.content, pdf_b.content)

    def test_pdf_export_preserves_invoice_details(self):
        self.login_distributor()
        response = self.client.get(reverse('invoice_pdf', args=[self.invoice_a.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('INV-ALPHA-101', response['Content-Disposition'])


class DistributorRegistrationAPITest(TestCase):
    def setUp(self):
        self.endpoint = reverse('api_register_distributor')
        self.valid_payload = {
            "email": "distributor@example.com",
            "password": "StrongPassword123!",
            "password_confirm": "StrongPassword123!",
            "name": "Test Distributor",
            "phone": "9876543210",
            "company_name": "ABC Distributors",
            "usertype": "distributor"
        }
        # Pre-existing users for testing duplicates and existing login
        self.existing_legacy_distributor = User.objects.create(
            name="Legacy Distributor",
            email="legacy.dist@example.com",
            password="legacy_plain_password",
            phone="9111111111",
            distributor_id="DIST-11111",
            company_name="Legacy Corp",
            usertype="distributor"
        )
        self.existing_admin = User.objects.create(
            name="Admin User",
            email="admin@example.com",
            password="admin_plain_password",
            phone="9222222222",
            company_name="Master Admin",
            usertype="admin"
        )

    def test_valid_distributor_registration(self):
        response = self.client.post(self.endpoint, data=self.valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('message'), "Distributor registered successfully.")
        self.assertIn('data', data)
        self.assertEqual(data['data']['email'], "distributor@example.com")
        self.assertEqual(data['data']['name'], "Test Distributor")
        self.assertEqual(data['data']['company_name'], "ABC Distributors")
        self.assertEqual(data['data']['usertype'], "distributor")

    def test_duplicate_email_registration(self):
        self.client.post(self.endpoint, data=self.valid_payload, content_type='application/json')
        response = self.client.post(self.endpoint, data=self.valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn("already exists", data.get('message', '').lower())

    def test_invalid_email_address(self):
        payload = self.valid_payload.copy()
        payload['email'] = "invalid-email-format"
        response = self.client.post(self.endpoint, data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('email', data.get('errors', {}))

    def test_missing_required_fields(self):
        for required_field in ['email', 'password', 'password_confirm', 'name', 'phone', 'company_name']:
            payload = self.valid_payload.copy()
            del payload[required_field]
            response = self.client.post(self.endpoint, data=payload, content_type='application/json')
            self.assertEqual(response.status_code, 400, f"Expected 400 when missing {required_field}")
            data = response.json()
            self.assertFalse(data.get('success'))
            self.assertIn(required_field, data.get('errors', {}))

    def test_password_and_confirmation_mismatch(self):
        payload = self.valid_payload.copy()
        payload['password_confirm'] = "DifferentPassword123!"
        response = self.client.post(self.endpoint, data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('password_confirm', data.get('errors', {}))

    def test_weak_password_validation(self):
        payload = self.valid_payload.copy()
        payload['password'] = "123"
        payload['password_confirm'] = "123"
        response = self.client.post(self.endpoint, data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('password', data.get('errors', {}))

    def test_invalid_phone_number_according_to_existing_rules(self):
        # Less than 10 digits
        payload = self.valid_payload.copy()
        payload['phone'] = "12345"
        response = self.client.post(self.endpoint, data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('phone', data.get('errors', {}))

        # Duplicate phone number
        payload['phone'] = self.existing_legacy_distributor.phone
        response = self.client.post(self.endpoint, data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('phone', data.get('errors', {}))

    def test_distributor_role_assignment(self):
        response = self.client.post(self.endpoint, data=self.valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="distributor@example.com")
        self.assertEqual(user.usertype, "distributor")

    def test_attempt_to_register_as_admin(self):
        payload = self.valid_payload.copy()
        payload['email'] = "attacker@example.com"
        payload['phone'] = "9333333333"
        payload['usertype'] = "admin"
        response = self.client.post(self.endpoint, data=payload, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="attacker@example.com")
        self.assertEqual(user.usertype, "distributor")
        self.assertNotEqual(user.usertype, "admin")

    def test_password_hashing_verification(self):
        raw_password = "StrongPassword123!"
        response = self.client.post(self.endpoint, data=self.valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="distributor@example.com")
        self.assertNotEqual(user.password, raw_password)
        self.assertTrue(user.password.startswith("pbkdf2_sha256$") or user.password.startswith("argon2") or user.password.startswith("bcrypt"))
        self.assertTrue(user.check_password(raw_password))

    def test_api_response_does_not_expose_passwords(self):
        response = self.client.post(self.endpoint, data=self.valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        response_text = response.content.decode('utf-8')
        self.assertNotIn("StrongPassword123!", response_text)
        self.assertNotIn("password_confirm", response.json().get('data', {}))
        self.assertNotIn("password", response.json().get('data', {}))

    def test_newly_registered_distributor_exists_in_database(self):
        response = self.client.post(self.endpoint, data=self.valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(email="distributor@example.com").exists())
        user = User.objects.get(email="distributor@example.com")
        self.assertEqual(user.name, "Test Distributor")
        self.assertEqual(user.company_name, "ABC Distributors")
        self.assertEqual(user.phone, "9876543210")
        self.assertTrue(user.distributor_id.startswith("DIST-"))

    def test_existing_login_functionality_still_works(self):
        # 1. Existing legacy user with plain text password logs in
        login_response = self.client.post(reverse('distributor_login'), data={
            'identity': self.existing_legacy_distributor.email,
            'password': 'legacy_plain_password'
        })
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(self.client.session.get('user_id'), self.existing_legacy_distributor.id)

        # 2. Newly registered distributor with hashed password logs in
        self.client.post(self.endpoint, data=self.valid_payload, content_type='application/json')
        new_dist = User.objects.get(email="distributor@example.com")

        new_login_response = self.client.post(reverse('distributor_login'), data={
            'identity': new_dist.email,
            'password': "StrongPassword123!"
        })
        self.assertEqual(new_login_response.status_code, 302)
        self.assertEqual(self.client.session.get('user_id'), new_dist.id)

    def test_existing_admin_functionality_remains_unaffected(self):
        # Existing admin logs in via admin login
        admin_response = self.client.post(reverse('admin_login'), data={
            'admin_email': self.existing_admin.email,
            'admin_password': 'admin_plain_password'
        })
        self.assertEqual(admin_response.status_code, 302)
        self.assertEqual(self.client.session.get('user_id'), self.existing_admin.id)
        self.assertEqual(self.client.session.get('usertype'), 'admin')


class DistributorRegistrationFrontendTest(TestCase):
    def test_registration_page_get_status_200(self):
        response = self.client.get(reverse('distributor_register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'billing/register.html')

        alt_response = self.client.get(reverse('register'))
        self.assertEqual(alt_response.status_code, 200)

    def test_registration_page_contains_required_fields(self):
        response = self.client.get(reverse('distributor_register'))
        content = response.content.decode('utf-8')
        self.assertIn('name="name"', content)
        self.assertIn('name="email"', content)
        self.assertIn('name="phone"', content)
        self.assertIn('name="company_name"', content)
        self.assertIn('name="password"', content)
        self.assertIn('name="password_confirm"', content)

    def test_registration_page_contains_password_visibility_toggles(self):
        response = self.client.get(reverse('distributor_register'))
        content = response.content.decode('utf-8')
        self.assertIn("togglePasswordVisibility('reg-pass'", content)
        self.assertIn("togglePasswordVisibility('reg-pass-confirm'", content)

    def test_registration_page_contains_api_target_and_elements(self):
        response = self.client.get(reverse('distributor_register'))
        content = response.content.decode('utf-8')
        self.assertIn('/api/register/distributor/', content)
        self.assertIn('id="distributorRegisterForm"', content)
        self.assertIn('id="btn-submit-registration"', content)
        self.assertIn('id="btn-spinner"', content)
        self.assertIn('id="alert-banner-error"', content)
        self.assertIn('id="alert-banner-success"', content)
        self.assertIn('id="feedback-name"', content)
        self.assertIn('id="feedback-email"', content)
        self.assertIn('id="feedback-phone"', content)
        self.assertIn('id="feedback-company"', content)
        self.assertIn('id="feedback-password"', content)
        self.assertIn('id="feedback-password-confirm"', content)

    def test_registration_page_responsive_meta_tag(self):
        response = self.client.get(reverse('distributor_register'))
        content = response.content.decode('utf-8')
        self.assertIn('name="viewport"', content)
        self.assertIn('width=device-width, initial-scale=1.0', content)

    def test_registration_page_links_to_login(self):
        response = self.client.get(reverse('distributor_register'))
        content = response.content.decode('utf-8')
        self.assertIn(reverse('distributor_login'), content)

    def test_form_fallback_post_submission(self):
        response = self.client.post(reverse('distributor_register'), data={
            'name': 'Fallback Distributor',
            'email': 'fallback@example.com',
            'phone': '9876543210',
            'company_name': 'Fallback Corp',
            'password': 'SecurePassword123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email='fallback@example.com').exists())
        user = User.objects.get(email='fallback@example.com')
        self.assertTrue(user.check_password('SecurePassword123!'))
        self.assertEqual(user.usertype, 'distributor')


class AdminPasswordRecoveryAPITest(TestCase):
    def setUp(self):
        self.client = Client()
        self.recovery_url = reverse('api_password_recovery')
        self.reset_url = reverse('api_password_reset')

        self.admin_user = User.objects.create_superuser(
            email="admin@billing.com",
            password="OriginalAdminPassword123!",
            name="System Administrator"
        )
        self.distributor_user = User.objects.create_user(
            email="distributor@billing.com",
            password="DistributorPassword123!",
            name="Retail Distributor",
            company_name="Retail Ltd",
            phone="9876543210",
            usertype="distributor"
        )

    def test_valid_admin_email_accepted_for_recovery_initiation(self):
        response = self.client.post(self.recovery_url, data={'email': 'admin@billing.com'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data['success'])
        self.assertEqual(json_data['message'], "If the account is eligible, password recovery instructions will be provided.")
        self.assertIn('data', json_data)
        self.assertIn('reset_token', json_data['data'])

    def test_invalid_email_format_is_rejected(self):
        response = self.client.post(self.recovery_url, data={'email': 'not-an-email'}, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        json_data = response.json()
        self.assertFalse(json_data['success'])
        self.assertIn('errors', json_data)

    def test_non_admin_distributor_cannot_recover_through_admin_workflow(self):
        response = self.client.post(self.recovery_url, data={'email': 'distributor@billing.com'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data['success'])
        self.assertEqual(json_data['message'], "If the account is eligible, password recovery instructions will be provided.")
        # Does not return reset_token for non-admin accounts
        self.assertNotIn('data', json_data)

    def test_unknown_email_does_not_reveal_account_existence(self):
        response = self.client.post(self.recovery_url, data={'email': 'nonexistent@billing.com'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data['success'])
        self.assertEqual(json_data['message'], "If the account is eligible, password recovery instructions will be provided.")
        self.assertNotIn('data', json_data)

    def test_password_reset_requires_valid_recovery_authorization(self):
        response = self.client.post(self.reset_url, data={
            'email': 'admin@billing.com',
            'new_password': 'BrandNewAdminPassword123!',
            'confirm_password': 'BrandNewAdminPassword123!'
        }, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        json_data = response.json()
        self.assertFalse(json_data['success'])
        self.assertIn('Password reset requires a valid recovery authorization mechanism.', str(json_data))

    def test_password_reset_with_invalid_or_expired_token_is_rejected(self):
        response = self.client.post(self.reset_url, data={
            'email': 'admin@billing.com',
            'reset_token': 'invalid.token.signature',
            'new_password': 'BrandNewAdminPassword123!',
            'confirm_password': 'BrandNewAdminPassword123!'
        }, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        json_data = response.json()
        self.assertFalse(json_data['success'])

    def test_password_reset_confirmation_mismatch_is_rejected(self):
        recovery_resp = self.client.post(self.recovery_url, data={'email': 'admin@billing.com'}, content_type='application/json')
        token = recovery_resp.json()['data']['reset_token']

        response = self.client.post(self.reset_url, data={
            'email': 'admin@billing.com',
            'reset_token': token,
            'new_password': 'BrandNewAdminPassword123!',
            'confirm_password': 'MismatchedPassword999!'
        }, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        json_data = response.json()
        self.assertFalse(json_data['success'])
        self.assertEqual(json_data['message'], "Password confirmation does not match.")

    def test_weak_password_rejected_by_configured_validators(self):
        recovery_resp = self.client.post(self.recovery_url, data={'email': 'admin@billing.com'}, content_type='application/json')
        token = recovery_resp.json()['data']['reset_token']

        # Password entirely numeric and too short
        response = self.client.post(self.reset_url, data={
            'email': 'admin@billing.com',
            'reset_token': token,
            'new_password': '123',
            'confirm_password': '123'
        }, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        json_data = response.json()
        self.assertFalse(json_data['success'])

    def test_successful_password_reset_updates_hash_and_allows_login(self):
        recovery_resp = self.client.post(self.recovery_url, data={'email': 'admin@billing.com'}, content_type='application/json')
        token = recovery_resp.json()['data']['reset_token']
        new_pwd = "BrandNewAdminPassword123!"

        reset_resp = self.client.post(self.reset_url, data={
            'email': 'admin@billing.com',
            'reset_token': token,
            'new_password': new_pwd,
            'confirm_password': new_pwd
        }, content_type='application/json')
        self.assertEqual(reset_resp.status_code, 200)
        self.assertTrue(reset_resp.json()['success'])
        self.assertEqual(reset_resp.json()['message'], "Password has been reset successfully.")

        # Verify password in DB is hashed and matches new password
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.check_password(new_pwd))
        self.assertFalse(self.admin_user.check_password("OriginalAdminPassword123!"))
        self.assertTrue(self.admin_user.password.startswith("pbkdf2_sha256$"))

        # Verify admin login with new password succeeds
        login_resp = self.client.post(reverse('admin_login'), data={
            'admin_email': 'admin@billing.com',
            'admin_password': new_pwd
        })
        self.assertEqual(login_resp.status_code, 302)
        self.assertEqual(self.client.session.get('usertype'), 'admin')
        self.assertEqual(self.client.session.get('user_id'), self.admin_user.id)

        # Verify admin login with old password fails
        bad_login_client = Client()
        bad_login_resp = bad_login_client.post(reverse('admin_login'), data={
            'admin_email': 'admin@billing.com',
            'admin_password': "OriginalAdminPassword123!"
        })
        self.assertEqual(bad_login_resp.status_code, 200)
        self.assertIsNone(bad_login_client.session.get('user_id'))

    def test_token_cannot_be_reused_after_successful_reset(self):
        recovery_resp = self.client.post(self.recovery_url, data={'email': 'admin@billing.com'}, content_type='application/json')
        token = recovery_resp.json()['data']['reset_token']
        new_pwd1 = "BrandNewAdminPassword123!"

        # First reset succeeds
        self.client.post(self.reset_url, data={
            'email': 'admin@billing.com',
            'reset_token': token,
            'new_password': new_pwd1,
            'confirm_password': new_pwd1
        }, content_type='application/json')

        # Replay attempt with same token must be rejected
        new_pwd2 = "AnotherNewPassword456!"
        replay_resp = self.client.post(self.reset_url, data={
            'email': 'admin@billing.com',
            'reset_token': token,
            'new_password': new_pwd2,
            'confirm_password': new_pwd2
        }, content_type='application/json')
        self.assertEqual(replay_resp.status_code, 400)
        self.assertFalse(replay_resp.json()['success'])

    def test_admin_privileges_and_distributor_accounts_remain_unchanged(self):
        recovery_resp = self.client.post(self.recovery_url, data={'email': 'admin@billing.com'}, content_type='application/json')
        token = recovery_resp.json()['data']['reset_token']
        new_pwd = "BrandNewAdminPassword123!"

        self.client.post(self.reset_url, data={
            'email': 'admin@billing.com',
            'reset_token': token,
            'new_password': new_pwd,
            'confirm_password': new_pwd
        }, content_type='application/json')

        self.admin_user.refresh_from_db()
        self.assertEqual(self.admin_user.usertype, 'admin')

        # Distributor remains untouched
        self.distributor_user.refresh_from_db()
        self.assertEqual(self.distributor_user.usertype, 'distributor')
        self.assertTrue(self.distributor_user.check_password("DistributorPassword123!"))


class ProductCRUDOperationsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.distributor = User.objects.create(
            name="John Dist",
            email="dist@testcrud.com",
            password="pass",
            phone="9876543210",
            distributor_id="DIST-99112",
            company_name="Apex POS",
            usertype="distributor"
        )
        self.admin = User.objects.create_superuser(
            email="admin@testcrud.com",
            password="admin_pass",
            name="Admin User"
        )
        # Login distributor session
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

    def test_create_product_success(self):
        response = self.client.post(reverse('add_product'), {
            'name': 'Wireless Barcode Scanner',
            'category': 'Hardware',
            'price': '4500.00',
            'stock': '25',
            'gst_rate': '18.0'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Product.objects.filter(name='Wireless Barcode Scanner').exists())
        product = Product.objects.get(name='Wireless Barcode Scanner')
        self.assertEqual(product.price, 4500.00)
        self.assertEqual(product.stock, 25)

    def test_create_product_missing_name_rejected(self):
        response = self.client.post(reverse('add_product'), {
            'name': '',
            'category': 'Hardware',
            'price': '4500.00',
            'stock': '25'
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(category='Hardware').exists())

    def test_create_product_invalid_price_rejected(self):
        response = self.client.post(reverse('add_product'), {
            'name': 'Free Scanner',
            'category': 'Hardware',
            'price': '-50.00',
            'stock': '25'
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(name='Free Scanner').exists())

    def test_create_product_negative_stock_rejected(self):
        response = self.client.post(reverse('add_product'), {
            'name': 'Negative Stock Scanner',
            'category': 'Hardware',
            'price': '500.00',
            'stock': '-5'
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(name='Negative Stock Scanner').exists())

    def test_product_list_display_and_search(self):
        p1 = Product.objects.create(name="POS Thermal Printer", category="Printers", price=7500.00, stock=10)
        p2 = Product.objects.create(name="Cash Drawer Metal", category="Security", price=3200.00, stock=15)

        # 1. Full list display
        response = self.client.get(reverse('product_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "POS Thermal Printer")
        self.assertContains(response, "Cash Drawer Metal")

        # 2. Search query by name
        search_resp = self.client.get(reverse('product_list'), {'search': 'Thermal'})
        self.assertEqual(search_resp.status_code, 200)
        self.assertContains(search_resp, "POS Thermal Printer")
        self.assertNotContains(search_resp, "Cash Drawer Metal")

    def test_product_list_empty(self):
        Product.objects.all().delete()
        response = self.client.get(reverse('product_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['products']), 0)

    def test_edit_product_prefilled_and_update_success(self):
        product = Product.objects.create(name="Receipt Paper Rolls", category="Consumables", price=120.00, stock=100)

        # GET request returns pre-filled values
        get_resp = self.client.get(reverse('edit_product', args=[product.id]))
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.context['name'], "Receipt Paper Rolls")
        self.assertEqual(get_resp.context['price'], 120.00)

        # POST updates the product without creating duplicates
        post_resp = self.client.post(reverse('edit_product', args=[product.id]), {
            'name': 'Premium Receipt Paper Rolls',
            'category': 'Consumables',
            'price': '150.00',
            'stock': '80',
            'gst_rate': '12.0'
        }, follow=True)
        self.assertEqual(post_resp.status_code, 200)

        # Confirm update in DB
        product.refresh_from_db()
        self.assertEqual(product.name, 'Premium Receipt Paper Rolls')
        self.assertEqual(product.price, 150.00)
        self.assertEqual(product.stock, 80)
        self.assertEqual(Product.objects.count(), 1)

    def test_edit_product_invalid_price_rejected(self):
        product = Product.objects.create(name="Receipt Paper Rolls", category="Consumables", price=120.00, stock=100)
        response = self.client.post(reverse('edit_product', args=[product.id]), {
            'name': 'Receipt Paper Rolls',
            'category': 'Consumables',
            'price': '0',
            'stock': '100'
        })
        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.price, 120.00)

    def test_delete_eligible_product_success(self):
        product = Product.objects.create(name="Obsolete Model", category="Hardware", price=100.00, stock=1)
        response = self.client.post(reverse('delete_product', args=[product.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(id=product.id).exists())

    def test_delete_product_with_associated_invoice_item_prevented(self):
        customer = Customer.objects.create(name="VIP Customer", phone="9876543210")
        product = Product.objects.create(name="Billed Item", category="Goods", price=500.00, stock=10)
        invoice = Invoice.objects.create(customer=customer, invoice_number="INV-HIST-001", total_amount=500.00)
        item = InvoiceItem.objects.create(invoice=invoice, product=product, quantity=1, unit_price=500.00, total_price=500.00)

        # Attempt to delete product associated with an invoice
        response = self.client.post(reverse('delete_product', args=[product.id]), follow=True)
        self.assertEqual(response.status_code, 200)

        # Confirm product and invoice item still exist intact
        self.assertTrue(Product.objects.filter(id=product.id).exists())
        self.assertTrue(InvoiceItem.objects.filter(id=item.id).exists())
        self.assertTrue(Invoice.objects.filter(id=invoice.id).exists())

    def test_product_operations_require_authentication(self):
        unauth_client = Client()

        resp_add = unauth_client.get(reverse('add_product'))
        self.assertEqual(resp_add.status_code, 302)

        resp_list = unauth_client.get(reverse('product_list'))
        self.assertEqual(resp_list.status_code, 302)

        product = Product.objects.create(name="Test Auth", category="Hardware", price=100.00, stock=1)
        resp_edit = unauth_client.get(reverse('edit_product', args=[product.id]))
        self.assertEqual(resp_edit.status_code, 302)

        resp_del = unauth_client.post(reverse('delete_product', args=[product.id]))
        self.assertEqual(resp_del.status_code, 302)
        self.assertTrue(Product.objects.filter(id=product.id).exists())

    def test_admin_user_can_manage_products(self):
        admin_client = Client()
        session = admin_client.session
        session['user_id'] = self.admin.id
        session['usertype'] = 'admin'
        session.save()

        # Admin creates product
        add_resp = admin_client.post(reverse('add_product'), {
            'name': 'Admin Created Product',
            'category': 'Admin Hardware',
            'price': '9999.00',
            'stock': '5',
            'gst_rate': '18.0'
        }, follow=True)
        self.assertEqual(add_resp.status_code, 200)
        self.assertTrue(Product.objects.filter(name='Admin Created Product').exists())


class OTPEmailVerificationAndRecoveryTest(TestCase):
    def setUp(self):
        self.client = Client()
        mail.outbox = []
        self.admin = User.objects.create_superuser(
            email="security.admin@billing.com",
            password="InitialAdminPass123!",
            name="Security Admin"
        )
        self.distributor = User.objects.create_user(
            email="dist.user@billing.com",
            password="DistUserPass123!",
            name="Standard Distributor",
            usertype="distributor"
        )

    def test_otp_generation_and_email_delivery(self):
        response = self.client.post(reverse('api_password_recovery'), {
            'email': 'security.admin@billing.com'
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # 1. Verify OTP record in DB
        otp_rec = OTP.objects.filter(identity='security.admin@billing.com').first()
        self.assertIsNotNone(otp_rec)
        self.assertEqual(len(otp_rec.otp), 6)
        self.assertTrue(otp_rec.otp.isdigit())

        # 2. Verify Email Delivery
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, ['security.admin@billing.com'])
        self.assertIn("Admin Password Recovery", sent_email.subject)
        self.assertIn(otp_rec.otp, sent_email.body)
        self.assertIn("5 minutes", sent_email.body)

    def test_otp_not_exposed_in_api_response(self):
        response = self.client.post(reverse('api_password_recovery'), {
            'email': 'security.admin@billing.com'
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)

        otp_rec = OTP.objects.filter(identity='security.admin@billing.com').first()
        self.assertNotIn(otp_rec.otp, response.content.decode('utf-8'))

    def test_otp_verification_correct_code_returns_reset_token(self):
        # 1. Initiate recovery
        self.client.post(reverse('api_password_recovery'), {
            'email': 'security.admin@billing.com'
        }, content_type='application/json')
        otp_code = mail.outbox[0].body.split(": ")[1].split("\n")[0].strip()

        # 2. Verify OTP
        verify_resp = self.client.post(reverse('api_verify_otp'), {
            'email': 'security.admin@billing.com',
            'otp': otp_code
        }, content_type='application/json')
        self.assertEqual(verify_resp.status_code, 200)
        json_data = verify_resp.json()
        self.assertTrue(json_data['success'])
        self.assertIn('data', json_data)
        self.assertIn('reset_token', json_data['data'])

        # Confirm marked as verified
        otp_rec = OTP.objects.get(identity='security.admin@billing.com')
        self.assertTrue(otp_rec.is_verified)

    def test_otp_verification_incorrect_code_rejected(self):
        self.client.post(reverse('api_password_recovery'), {
            'email': 'security.admin@billing.com'
        }, content_type='application/json')

        verify_resp = self.client.post(reverse('api_verify_otp'), {
            'email': 'security.admin@billing.com',
            'otp': '000000'
        }, content_type='application/json')
        self.assertEqual(verify_resp.status_code, 400)
        self.assertFalse(verify_resp.json()['success'])

    def test_otp_verification_expired_rejected(self):
        self.client.post(reverse('api_password_recovery'), {
            'email': 'security.admin@billing.com'
        }, content_type='application/json')
        otp_rec = OTP.objects.get(identity='security.admin@billing.com')

        # Backdate OTP created_at by 6 minutes
        otp_rec.created_at = timezone.now() - timedelta(minutes=6)
        otp_rec.save()

        verify_resp = self.client.post(reverse('api_verify_otp'), {
            'email': 'security.admin@billing.com',
            'otp': otp_rec.otp
        }, content_type='application/json')
        self.assertEqual(verify_resp.status_code, 400)
        self.assertIn("expired", verify_resp.json()['message'].lower())

    def test_otp_verification_already_used_rejected(self):
        self.client.post(reverse('api_password_recovery'), {
            'email': 'security.admin@billing.com'
        }, content_type='application/json')
        otp_rec = OTP.objects.get(identity='security.admin@billing.com')
        otp_code = otp_rec.otp

        # First verification succeeds
        first_resp = self.client.post(reverse('api_verify_otp'), {
            'email': 'security.admin@billing.com',
            'otp': otp_code
        }, content_type='application/json')
        self.assertEqual(first_resp.status_code, 200)

        # Second verification with same OTP must be rejected
        second_resp = self.client.post(reverse('api_verify_otp'), {
            'email': 'security.admin@billing.com',
            'otp': otp_code
        }, content_type='application/json')
        self.assertEqual(second_resp.status_code, 400)
        self.assertIn("already been used", second_resp.json()['message'])

    def test_otp_verification_non_admin_rejected(self):
        # Distributor tries to verify OTP
        OTP.objects.create(identity='dist.user@billing.com', otp='112233')
        verify_resp = self.client.post(reverse('api_verify_otp'), {
            'email': 'dist.user@billing.com',
            'otp': '112233'
        }, content_type='application/json')
        self.assertEqual(verify_resp.status_code, 400)

    def test_complete_end_to_end_password_recovery_workflow(self):
        # Step 1: Admin requests password recovery
        recovery_resp = self.client.post(reverse('api_password_recovery'), {
            'email': 'security.admin@billing.com'
        }, content_type='application/json')
        self.assertEqual(recovery_resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

        # Step 2: Retrieve OTP from received email
        body = mail.outbox[0].body
        otp_code = body.split(": ")[1].split("\n")[0].strip()

        # Step 3: Verify OTP and obtain reset token
        verify_resp = self.client.post(reverse('api_verify_otp'), {
            'email': 'security.admin@billing.com',
            'otp': otp_code
        }, content_type='application/json')
        self.assertEqual(verify_resp.status_code, 200)
        reset_token = verify_resp.json()['data']['reset_token']

        # Step 4: Reset password with valid token
        new_password = "ComplexSecureAdminPassword2026!"
        reset_resp = self.client.post(reverse('api_password_reset'), {
            'email': 'security.admin@billing.com',
            'reset_token': reset_token,
            'new_password': new_password,
            'confirm_password': new_password
        }, content_type='application/json')
        self.assertEqual(reset_resp.status_code, 200)
        self.assertTrue(reset_resp.json()['success'])

        # Step 5: Verify new password works for Admin login
        login_resp = self.client.post(reverse('admin_login'), {
            'admin_email': 'security.admin@billing.com',
            'admin_password': new_password
        })
        self.assertEqual(login_resp.status_code, 302)
        self.assertEqual(self.client.session.get('usertype'), 'admin')

        # Step 6: Verify old password fails
        bad_client = Client()
        bad_resp = bad_client.post(reverse('admin_login'), {
            'admin_email': 'security.admin@billing.com',
            'admin_password': "InitialAdminPass123!"
        })
        self.assertEqual(bad_resp.status_code, 200)
        self.assertIsNone(bad_client.session.get('user_id'))


class ProductManagementFrontendAndAPITest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user(
            email="admin_pm@billing.com",
            password="AdminPassword123!",
            name="Admin PM",
            usertype="admin"
        )
        self.distributor_user = User.objects.create_user(
            email="dist_pm@billing.com",
            password="DistPassword123!",
            name="Dist PM",
            usertype="distributor"
        )
        self.product1 = Product.objects.create(
            name="Alpha Thermal Paper Roll",
            category="POS Supplies",
            price=120.00,
            stock=50,
            gst_rate=18.00
        )
        self.product2 = Product.objects.create(
            name="Beta Barcode Scanner",
            category="Hardware",
            price=2500.00,
            stock=15,
            gst_rate=18.00
        )

    def test_admin_products_view_anonymous_redirect(self):
        resp = self.client.get(reverse('admin_products'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin-login/', resp.url)

    def test_admin_products_view_distributor_denied(self):
        session = self.client.session
        session['user_id'] = self.distributor_user.id
        session['usertype'] = 'distributor'
        session.save()

        resp = self.client.get(reverse('admin_products'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin-login/', resp.url)

    def test_admin_products_view_admin_success(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session['usertype'] = 'admin'
        session.save()

        resp = self.client.get(reverse('admin_products'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'billing/admin-products.html')
        self.assertContains(resp, "Product Management")
        self.assertContains(resp, "Alpha Thermal Paper Roll")
        self.assertContains(resp, "Beta Barcode Scanner")

    def test_admin_products_view_search_and_filter(self):
        session = self.client.session
        session['user_id'] = self.admin_user.id
        session['usertype'] = 'admin'
        session.save()

        # Search by keyword
        resp_search = self.client.get(reverse('admin_products'), {'search': 'Scanner'})
        self.assertEqual(resp_search.status_code, 200)
        self.assertContains(resp_search, "Beta Barcode Scanner")
        self.assertNotContains(resp_search, "Alpha Thermal Paper Roll")

        # Filter by category
        resp_cat = self.client.get(reverse('admin_products'), {'category': 'POS Supplies'})
        self.assertEqual(resp_cat.status_code, 200)
        self.assertContains(resp_cat, "Alpha Thermal Paper Roll")
        self.assertNotContains(resp_cat, "Beta Barcode Scanner")

    def test_api_products_list_and_search(self):
        resp = self.client.get(reverse('api_products'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 2)

        # Search query
        resp_search = self.client.get(reverse('api_products'), {'search': 'Alpha'})
        self.assertEqual(resp_search.status_code, 200)
        self.assertEqual(resp_search.json()['count'], 1)
        self.assertEqual(resp_search.json()['data'][0]['name'], "Alpha Thermal Paper Roll")

    def test_api_product_create_success(self):
        payload = {
            "name": "Wireless Laser Printer",
            "category": "Hardware",
            "price": "8999.00",
            "stock": 10,
            "gst_rate": "18.00"
        }
        resp = self.client.post(
            reverse('api_products'),
            payload,
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['name'], "Wireless Laser Printer")
        self.assertEqual(float(data['data']['price']), 8999.00)
        self.assertEqual(data['data']['stock'], 10)
        self.assertTrue(Product.objects.filter(name="Wireless Laser Printer").exists())

    def test_api_product_create_validation_failures(self):
        # 1. Missing name
        resp = self.client.post(
            reverse('api_products'),
            {"name": "", "category": "Hardware", "price": "100.00", "stock": 5, "gst_rate": "18.00"},
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])

        # 2. Invalid price <= 0
        resp_price = self.client.post(
            reverse('api_products'),
            {"name": "Bad Price Item", "category": "General", "price": "-10.00", "stock": 5, "gst_rate": "18.00"},
            content_type='application/json'
        )
        self.assertEqual(resp_price.status_code, 400)

        # 3. Negative stock
        resp_stock = self.client.post(
            reverse('api_products'),
            {"name": "Bad Stock Item", "category": "General", "price": "100.00", "stock": -1, "gst_rate": "18.00"},
            content_type='application/json'
        )
        self.assertEqual(resp_stock.status_code, 400)

        # 4. Invalid GST rate > 100
        resp_gst = self.client.post(
            reverse('api_products'),
            {"name": "Bad GST Item", "category": "General", "price": "100.00", "stock": 5, "gst_rate": "150.00"},
            content_type='application/json'
        )
        self.assertEqual(resp_gst.status_code, 400)

    def test_api_product_detail_and_update(self):
        # GET detail
        resp = self.client.get(reverse('api_product_detail', kwargs={'id': self.product1.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['name'], self.product1.name)
        self.assertEqual(resp.json()['data']['invoice_items_count'], 0)

        # PUT update
        update_payload = {
            "name": "Alpha Thermal Paper Roll (Super)",
            "category": "POS Premium Supplies",
            "price": "150.00",
            "stock": 75,
            "gst_rate": "12.00"
        }
        put_resp = self.client.put(
            reverse('api_product_detail', kwargs={'id': self.product1.id}),
            update_payload,
            content_type='application/json'
        )
        self.assertEqual(put_resp.status_code, 200)
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.name, "Alpha Thermal Paper Roll (Super)")
        self.assertEqual(self.product1.category, "POS Premium Supplies")
        self.assertEqual(float(self.product1.price), 150.00)
        self.assertEqual(self.product1.stock, 75)

    def test_api_product_delete_standalone_success(self):
        product = Product.objects.create(
            name="Temporary Test Item",
            category="Test",
            price=50.00,
            stock=1,
            gst_rate=0.00
        )
        del_resp = self.client.delete(reverse('api_product_detail', kwargs={'id': product.id}))
        self.assertEqual(del_resp.status_code, 200)
        self.assertTrue(del_resp.json()['success'])
        self.assertFalse(Product.objects.filter(id=product.id).exists())

    def test_api_product_delete_protection_with_historical_invoices(self):
        # Create customer and invoice with InvoiceItem referencing self.product2
        customer = Customer.objects.create(name="Store Buyer", phone="9988776655")
        invoice = Invoice.objects.create(
            customer=customer,
            invoice_number="INV-TEST-0099",
            total_amount=2500.00
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            product=self.product2,
            quantity=1,
            unit_price=2500.00,
            total_price=2500.00
        )

        # Attempt DELETE via REST API
        del_resp = self.client.delete(reverse('api_product_detail', kwargs={'id': self.product2.id}))
        self.assertEqual(del_resp.status_code, 400)
        self.assertFalse(del_resp.json()['success'])
        self.assertIn("historical invoice records", del_resp.json()['message'])
        # Verify product still exists in DB
        self.assertTrue(Product.objects.filter(id=self.product2.id).exists())


class AdminRegistrationAndProductValidationModuleTest(TestCase):
    """
    Task 2: Complete Functional, Validation, Security and Regression Test Suite
    Module 1: Admin User Registration
    Module 2: Product Management
    Regression: Existing Authentication and Billing Workflows
    """

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            email="super.admin@enterprise.com",
            password="AdminComplexPass2026!",
            name="Super Admin",
            usertype="admin"
        )
        self.distributor = User.objects.create_user(
            email="pos.distributor@enterprise.com",
            password="DistributorPass2026!",
            name="POS Distributor",
            usertype="distributor"
        )
        self.product = Product.objects.create(
            name="Omni Thermal Barcode Scanner",
            category="POS Peripherals",
            price=3200.00,
            stock=25,
            gst_rate=18.00
        )
        self.customer = Customer.objects.create(
            name="Metro Retail Hub",
            email="metro@retailhub.com",
            phone="9876501234",
            address="789 Market Road"
        )

    # =========================================================================
    # MODULE 1: ADMIN USER REGISTRATION VALIDATION & TESTING
    # =========================================================================

    def test_admin_registration_unauthorized_anonymous(self):
        """Anonymous requests to /api/register/ must return 401 Unauthorized."""
        payload = {
            "name": "New Admin",
            "email": "new.admin@enterprise.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "usertype": "admin"
        }
        resp = self.client.post(
            reverse('api_register'),
            payload,
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 401)

    def test_admin_registration_unauthorized_distributor(self):
        """Distributor (non-admin) requests must return 403 Forbidden."""
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        payload = {
            "name": "Intruder Admin",
            "email": "intruder.admin@enterprise.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "usertype": "admin"
        }
        resp = self.client.post(
            reverse('api_register'),
            payload,
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_registration_successful(self):
        """Authenticated Admin can successfully register a new Admin user."""
        session = self.client.session
        session['user_id'] = self.admin.id
        session['usertype'] = 'admin'
        session.save()

        payload = {
            "name": "Operations Admin",
            "email": "ops.admin@enterprise.com",
            "phone": "9811223344",
            "password": "StrongAdminPassword2026!",
            "password_confirm": "StrongAdminPassword2026!",
            "usertype": "admin"
        }
        resp = self.client.post(
            reverse('api_register'),
            payload,
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['usertype'], 'admin')
        self.assertEqual(data['data']['email'], 'ops.admin@enterprise.com')

        # Verify password is NEVER exposed in response
        self.assertNotIn('password', data['data'])
        if 'user' in data:
            self.assertNotIn('password', data['user'])

        # Verify password is cryptographically hashed in DB
        created_user = User.objects.get(email="ops.admin@enterprise.com")
        self.assertEqual(created_user.usertype, 'admin')
        self.assertTrue(created_user.check_password("StrongAdminPassword2026!"))
        self.assertNotEqual(created_user.password, "StrongAdminPassword2026!")

    def test_admin_registration_empty_payload(self):
        """Empty form submission must fail with HTTP 400 and field error messages."""
        session = self.client.session
        session['user_id'] = self.admin.id
        session.save()

        resp = self.client.post(reverse('api_register'), {}, content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn('email', data['errors'])
        self.assertIn('password', data['errors'])
        self.assertIn('password_confirm', data['errors'])

    def test_admin_registration_invalid_email_format(self):
        """Invalid email formats must be rejected with 400 Bad Request."""
        session = self.client.session
        session['user_id'] = self.admin.id
        session.save()

        bad_emails = ["not-an-email", "admin@", "admin@domain", "@nodomain.com"]
        for bad_mail in bad_emails:
            payload = {
                "name": "Test Admin",
                "email": bad_mail,
                "password": "ValidPassword123!",
                "password_confirm": "ValidPassword123!",
                "usertype": "admin"
            }
            resp = self.client.post(reverse('api_register'), payload, content_type='application/json')
            self.assertEqual(resp.status_code, 400, f"Failed to reject invalid email: {bad_mail}")
            self.assertIn('email', resp.json()['errors'])

    def test_admin_registration_duplicate_email(self):
        """Registering an email that already exists must fail with clear error."""
        session = self.client.session
        session['user_id'] = self.admin.id
        session.save()

        payload = {
            "name": "Duplicate Admin",
            "email": self.admin.email,  # already exists
            "password": "ValidPassword123!",
            "password_confirm": "ValidPassword123!",
            "usertype": "admin"
        }
        resp = self.client.post(reverse('api_register'), payload, content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already exists", str(resp.json()['errors']['email']))

    def test_admin_registration_password_mismatch(self):
        """Mismatched password and confirm password must fail validation."""
        session = self.client.session
        session['user_id'] = self.admin.id
        session.save()

        payload = {
            "name": "Test Admin",
            "email": "unique.mismatch@enterprise.com",
            "password": "PasswordAlpha123!",
            "password_confirm": "PasswordBeta456!",
            "usertype": "admin"
        }
        resp = self.client.post(reverse('api_register'), payload, content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('password_confirm', resp.json()['errors'])

    def test_admin_registration_weak_password_validation(self):
        """Weak passwords must be rejected by Django password validators."""
        session = self.client.session
        session['user_id'] = self.admin.id
        session.save()

        payload = {
            "name": "Weak Admin",
            "email": "weak.password@enterprise.com",
            "password": "123",
            "password_confirm": "123",
            "usertype": "admin"
        }
        resp = self.client.post(reverse('api_register'), payload, content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('password', resp.json()['errors'])

    def test_admin_registration_frontend_dashboard_modal_rendered(self):
        """Admin Dashboard must render registration modal and button for authenticated Admin."""
        session = self.client.session
        session['user_id'] = self.admin.id
        session['usertype'] = 'admin'
        session.save()

        resp = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Register New Admin")
        self.assertContains(resp, "adminRegisterModal")
        self.assertContains(resp, "adminRegEmail")
        self.assertContains(resp, "adminRegPassword")

    # =========================================================================
    # MODULE 2: PRODUCT MANAGEMENT VALIDATION & TESTING
    # =========================================================================

    def test_product_add_valid_data(self):
        """Add product with valid data through REST API."""
        payload = {
            "name": "Thermal Receipt Printer Roll 80mm",
            "category": "Paper & Stationary",
            "price": "95.50",
            "stock": 100,
            "gst_rate": "18.00"
        }
        resp = self.client.post(reverse('api_products'), payload, content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['name'], "Thermal Receipt Printer Roll 80mm")
        self.assertEqual(float(data['data']['price']), 95.50)
        self.assertEqual(data['data']['stock'], 100)
        self.assertEqual(float(data['data']['gst_rate']), 18.00)

    def test_product_add_missing_and_invalid_data(self):
        """Reject products with missing fields, negative price, negative stock, invalid GST."""
        # 1. Missing name
        r1 = self.client.post(reverse('api_products'), {
            "name": "", "category": "Hardware", "price": "100.00", "stock": 5, "gst_rate": "18.00"
        }, content_type='application/json')
        self.assertEqual(r1.status_code, 400)

        # 2. Price <= 0
        r2 = self.client.post(reverse('api_products'), {
            "name": "Free Item", "category": "Hardware", "price": "0.00", "stock": 5, "gst_rate": "18.00"
        }, content_type='application/json')
        self.assertEqual(r2.status_code, 400)

        # 3. Negative stock
        r3 = self.client.post(reverse('api_products'), {
            "name": "Negative Stock", "category": "Hardware", "price": "50.00", "stock": -5, "gst_rate": "18.00"
        }, content_type='application/json')
        self.assertEqual(r3.status_code, 400)

        # 4. GST rate > 100
        r4 = self.client.post(reverse('api_products'), {
            "name": "Crazy GST", "category": "Hardware", "price": "50.00", "stock": 10, "gst_rate": "120.00"
        }, content_type='application/json')
        self.assertEqual(r4.status_code, 400)

    def test_product_edit_update_existing(self):
        """Update existing product details via REST API."""
        update_data = {
            "name": "Omni Thermal Barcode Scanner (v2 Pro)",
            "category": "High-Speed POS Peripherals",
            "price": "3600.00",
            "stock": 40,
            "gst_rate": "18.00"
        }
        resp = self.client.put(
            reverse('api_product_detail', kwargs={'id': self.product.id}),
            update_data,
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Omni Thermal Barcode Scanner (v2 Pro)")
        self.assertEqual(float(self.product.price), 3600.00)
        self.assertEqual(self.product.stock, 40)

    def test_product_delete_standalone(self):
        """Delete standalone product not linked to any invoice."""
        temp_prod = Product.objects.create(
            name="Temporary Discontinued Cable",
            category="Cables",
            price=150.00,
            stock=5,
            gst_rate=18.00
        )
        resp = self.client.delete(reverse('api_product_detail', kwargs={'id': temp_prod.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Product.objects.filter(id=temp_prod.id).exists())

    def test_product_delete_blocked_when_used_in_invoice(self):
        """Protect historical records: Delete must be rejected if referenced in InvoiceItem."""
        invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_number="INV-PROTECT-101",
            total_amount=3200.00
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=1,
            unit_price=3200.00,
            total_price=3200.00
        )

        resp = self.client.delete(reverse('api_product_detail', kwargs={'id': self.product.id}))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("historical invoice records", resp.json()['message'])
        # Ensure product was not deleted
        self.assertTrue(Product.objects.filter(id=self.product.id).exists())

    def test_product_search_and_pagination(self):
        """Search products and check paginated output."""
        # Create 15 products to trigger pagination
        for i in range(15):
            Product.objects.create(
                name=f"Bulk Gadget #{i:02d}",
                category="Gadgets",
                price=100.00 + i,
                stock=10 + i,
                gst_rate=18.00
            )

        session = self.client.session
        session['user_id'] = self.admin.id
        session['usertype'] = 'admin'
        session.save()

        # Page 1
        resp_p1 = self.client.get(reverse('admin_products'), {'page': 1})
        self.assertEqual(resp_p1.status_code, 200)
        self.assertTrue(resp_p1.context['products'].has_next())

        # Page 2
        resp_p2 = self.client.get(reverse('admin_products'), {'page': 2})
        self.assertEqual(resp_p2.status_code, 200)

        # Search query
        resp_search = self.client.get(reverse('admin_products'), {'search': 'Gadget #05'})
        self.assertEqual(resp_search.status_code, 200)
        self.assertContains(resp_search, "Bulk Gadget #05")

    def test_product_unauthorized_admin_page_access(self):
        """Non-admin and anonymous requests to /admin-products/ must be redirected."""
        # Anonymous
        r_anon = self.client.get(reverse('admin_products'))
        self.assertEqual(r_anon.status_code, 302)
        self.assertIn('/admin-login/', r_anon.url)

        # Distributor
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()
        r_dist = self.client.get(reverse('admin_products'))
        self.assertEqual(r_dist.status_code, 302)
        self.assertIn('/admin-login/', r_dist.url)

    # =========================================================================
    # MODULE 3: REGRESSION TESTING (EXISTING BILLING & AUTH WORKFLOWS)
    # =========================================================================

    def test_regression_admin_login(self):
        """Existing Admin Login workflow functions without issue."""
        resp = self.client.post(reverse('admin_login'), {
            'admin_email': 'super.admin@enterprise.com',
            'admin_password': 'AdminComplexPass2026!'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin-dashboard/', resp.url)
        self.assertEqual(self.client.session.get('user_id'), self.admin.id)
        self.assertEqual(self.client.session.get('usertype'), 'admin')

    def test_regression_invoice_pdf_and_qr_generation(self):
        """Existing Invoice PDF download and dynamic QR endpoints continue working seamlessly."""
        invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_number="INV-REGRESS-202",
            total_amount=3200.00
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            product=self.product,
            quantity=1,
            unit_price=3200.00,
            total_price=3200.00
        )

        # Authenticate as distributor or admin
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()

        # 1. Test Invoice QR Code
        qr_resp = self.client.get(reverse('invoice_qr_code', kwargs={'id': invoice.id}))
        self.assertEqual(qr_resp.status_code, 200)
        self.assertEqual(qr_resp['Content-Type'], 'image/png')

        # 2. Test Invoice PDF Export
        pdf_resp = self.client.get(reverse('invoice_pdf', kwargs={'id': invoice.id}))
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertEqual(pdf_resp['Content-Type'], 'application/pdf')


class AdminDedicatedReportsSectionTest(TestCase):
    """
    Task 3: Functional, Validation, Security and Calculation Tests for
    Dedicated Reports Section in Admin Dashboard.
    """

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            email="reports.admin@enterprise.com",
            password="AdminReportPass2026!",
            name="Reports Admin",
            usertype="admin"
        )
        self.distributor = User.objects.create_user(
            email="reports.dist@enterprise.com",
            password="DistReportPass2026!",
            name="Reports Dist",
            usertype="distributor"
        )
        self.product_a = Product.objects.create(
            name="Thermal POS Printer 80mm",
            category="Hardware",
            price=4500.00,
            stock=30,
            gst_rate=18.00
        )
        self.product_b = Product.objects.create(
            name="Thermal Receipt Paper Roll (Box of 50)",
            category="Supplies",
            price=1500.00,
            stock=100,
            gst_rate=12.00
        )
        self.customer_1 = Customer.objects.create(
            name="Grand Horizon Mart",
            email="horizon@mart.com",
            phone="9876543210"
        )
        self.customer_2 = Customer.objects.create(
            name="Apex Supermarket",
            email="apex@supermarket.com",
            phone="9123456789"
        )

        # Create historical invoice records across different dates
        # Invoice 1: Today
        self.inv_1 = Invoice.objects.create(
            customer=self.customer_1,
            invoice_number="INV-REP-001",
            total_amount=10500.00
        )
        InvoiceItem.objects.create(
            invoice=self.inv_1,
            product=self.product_a,
            quantity=2,
            unit_price=4500.00,
            total_price=9000.00
        )
        InvoiceItem.objects.create(
            invoice=self.inv_1,
            product=self.product_b,
            quantity=1,
            unit_price=1500.00,
            total_price=1500.00
        )

        # Invoice 2: 5 days ago (in this week & month)
        self.inv_2 = Invoice.objects.create(
            customer=self.customer_2,
            invoice_number="INV-REP-002",
            total_amount=6000.00
        )
        InvoiceItem.objects.create(
            invoice=self.inv_2,
            product=self.product_b,
            quantity=4,
            unit_price=1500.00,
            total_price=6000.00
        )
        # Manually backdate inv_2 to 5 days ago
        Invoice.objects.filter(id=self.inv_2.id).update(created_at=timezone.now() - timedelta(days=5))

        # Invoice 3: 40 days ago (older than week and month)
        self.inv_3 = Invoice.objects.create(
            customer=self.customer_1,
            invoice_number="INV-REP-003",
            total_amount=4500.00
        )
        InvoiceItem.objects.create(
            invoice=self.inv_3,
            product=self.product_a,
            quantity=1,
            unit_price=4500.00,
            total_price=4500.00
        )
        Invoice.objects.filter(id=self.inv_3.id).update(created_at=timezone.now() - timedelta(days=40))

    def authenticate_admin(self):
        session = self.client.session
        session['user_id'] = self.admin.id
        session['usertype'] = 'admin'
        session.save()

    def test_reports_page_unauthorized_access(self):
        """Anonymous and distributor users must be denied access to reports."""
        # 1. Anonymous access
        r_anon = self.client.get(reverse('admin_reports'))
        self.assertEqual(r_anon.status_code, 302)
        self.assertIn('/admin-login/', r_anon.url)

        # 2. Distributor access
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()
        r_dist = self.client.get(reverse('admin_reports'))
        self.assertEqual(r_dist.status_code, 302)
        self.assertIn('/admin-login/', r_dist.url)

    def test_reports_page_loading_success_admin(self):
        """Authenticated Admin can load reports dashboard and see accurate aggregate figures."""
        self.authenticate_admin()
        resp = self.client.get(reverse('admin_reports'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'billing/admin-reports.html')
        self.assertContains(resp, "Sales &amp; Analytics Reports")
        self.assertContains(resp, "Total Invoices")
        self.assertContains(resp, "Total Revenue")

        # Verify context calculations for 'all' scope
        # Total invoices: 3
        self.assertEqual(resp.context['total_invoices'], 3)
        # Total sales: 10500 + 6000 + 4500 = 21000
        self.assertEqual(float(resp.context['total_sales']), 21000.00)
        # Total units sold: 2 + 1 + 4 + 1 = 8 units
        self.assertEqual(resp.context['total_units_sold'], 8)
        # Avg invoice value: 21000 / 3 = 7000
        self.assertEqual(float(resp.context['avg_invoice_value']), 7000.00)

    def test_reports_date_filter_today(self):
        """Filtering by 'today' only includes invoices created today."""
        self.authenticate_admin()
        resp = self.client.get(reverse('admin_reports'), {'preset': 'today'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_invoices'], 1)
        self.assertEqual(float(resp.context['total_sales']), 10500.00)
        self.assertEqual(resp.context['total_units_sold'], 3)

    def test_reports_date_filter_week(self):
        """Filtering by 'week' includes invoices created in the last 7 days."""
        self.authenticate_admin()
        resp = self.client.get(reverse('admin_reports'), {'preset': 'week'})
        self.assertEqual(resp.status_code, 200)
        # inv_1 (today) + inv_2 (5 days ago) = 2 invoices
        self.assertEqual(resp.context['total_invoices'], 2)
        # 10500 + 6000 = 16500
        self.assertEqual(float(resp.context['total_sales']), 16500.00)
        self.assertEqual(resp.context['total_units_sold'], 7)

    def test_reports_date_filter_custom_range(self):
        """Custom date range accurately filters records between start_date and end_date."""
        self.authenticate_admin()
        today_str = timezone.now().strftime('%Y-%m-%d')
        start_6_days_ago = (timezone.now() - timedelta(days=6)).strftime('%Y-%m-%d')

        resp = self.client.get(reverse('admin_reports'), {
            'preset': 'custom',
            'start_date': start_6_days_ago,
            'end_date': today_str
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_invoices'], 2)
        self.assertEqual(float(resp.context['total_sales']), 16500.00)

    def test_reports_product_wise_breakdown(self):
        """Product-wise sales performance table computes real units sold and total revenue."""
        self.authenticate_admin()
        resp = self.client.get(reverse('admin_reports'), {'preset': 'all'})
        self.assertEqual(resp.status_code, 200)
        product_sales = resp.context['product_sales']
        self.assertTrue(len(product_sales) > 0)

        # product_a revenue: 9000 (inv_1) + 4500 (inv_3) = 13500, units: 3
        # product_b revenue: 1500 (inv_1) + 6000 (inv_2) = 7500, units: 5
        prod_a_stat = next(p for p in product_sales if p['product__name'] == "Thermal POS Printer 80mm")
        self.assertEqual(prod_a_stat['units_sold'], 3)
        self.assertEqual(float(prod_a_stat['total_revenue']), 13500.00)

        prod_b_stat = next(p for p in product_sales if p['product__name'] == "Thermal Receipt Paper Roll (Box of 50)")
        self.assertEqual(prod_b_stat['units_sold'], 5)
        self.assertEqual(float(prod_b_stat['total_revenue']), 7500.00)

    def test_reports_search_and_pagination(self):
        """Search by customer name and invoice number works correctly."""
        self.authenticate_admin()
        # Search for 'Apex'
        resp_search = self.client.get(reverse('admin_reports'), {'search': 'Apex'})
        self.assertEqual(resp_search.status_code, 200)
        self.assertEqual(resp_search.context['total_invoices'], 1)
        self.assertContains(resp_search, "Apex Supermarket")
        self.assertNotContains(resp_search, "Grand Horizon Mart")

        # Search for 'INV-REP-001'
        resp_inv = self.client.get(reverse('admin_reports'), {'search': 'INV-REP-001'})
        self.assertEqual(resp_inv.status_code, 200)
        self.assertEqual(resp_inv.context['total_invoices'], 1)
        self.assertContains(resp_inv, "INV-REP-001")

    def test_reports_pdf_download_success(self):
        """Download PDF report generates valid PDF with correct Content-Type and headers."""
        self.authenticate_admin()
        resp = self.client.get(reverse('admin_reports_pdf'), {'preset': 'all'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', resp['Content-Disposition'])
        self.assertIn('Invoice_Report_', resp['Content-Disposition'])
        # Verify valid PDF byte structure starts with %PDF
        self.assertTrue(resp.content.startswith(b'%PDF'))


class ReportDateRangeFilterFormTest(TestCase):
    """
    Test suite for the Date Range Report Generation Form and filtering functionality.
    Validates:
    - ORM date-range filtering (inclusive of start and end dates)
    - Handling of empty date fields without 500 error
    - Validation when end_date < start_date
    - Error message feedback
    - Frontend form elements presence (Start Date, End Date, Generate Report, Reset)
    - Security / Authorization constraints
    """

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            email="reportadmin@billing.com",
            password="AdminPassword123!",
            name="Report Admin"
        )
        self.distributor = User.objects.create_user(
            email="dist_reporter@billing.com",
            password="DistPassword123!",
            name="Dist Reporter",
            usertype="distributor"
        )
        self.customer = Customer.objects.create(
            name="Range Test Customer",
            email="rangetest@customer.com",
            phone="9876543210",
            address="100 Test Blvd, Suite 2"
        )
        self.product = Product.objects.create(
            name="Filter Test Product",
            category="Electronics",
            price=Decimal('200.00'),
            stock=100
        )

        now = timezone.now()
        # Create Invoices with specific created_at timestamps
        # Inv 1: 15 days ago
        self.inv_old = Invoice.objects.create(
            invoice_number="INV-RANGE-001",
            customer=self.customer,
            total_amount=Decimal('400.00')
        )
        Invoice.objects.filter(id=self.inv_old.id).update(created_at=now - timedelta(days=15))

        # Inv 2: 7 days ago
        self.inv_mid = Invoice.objects.create(
            invoice_number="INV-RANGE-002",
            customer=self.customer,
            total_amount=Decimal('600.00')
        )
        Invoice.objects.filter(id=self.inv_mid.id).update(created_at=now - timedelta(days=7))

        # Inv 3: 5 days ago
        self.inv_target = Invoice.objects.create(
            invoice_number="INV-RANGE-003",
            customer=self.customer,
            total_amount=Decimal('800.00')
        )
        Invoice.objects.filter(id=self.inv_target.id).update(created_at=now - timedelta(days=5))

        # Inv 4: Today
        self.inv_today = Invoice.objects.create(
            invoice_number="INV-RANGE-004",
            customer=self.customer,
            total_amount=Decimal('1000.00')
        )
        Invoice.objects.filter(id=self.inv_today.id).update(created_at=now)

    def authenticate_admin(self):
        session = self.client.session
        session['user_id'] = self.admin.id
        session['usertype'] = 'admin'
        session.save()

    def test_inclusive_date_range_filtering(self):
        """Invoices between start_date and end_date (inclusive) are accurately retrieved."""
        self.authenticate_admin()
        now = timezone.now()
        start_date = (now - timedelta(days=8)).strftime('%Y-%m-%d')
        end_date = (now - timedelta(days=4)).strftime('%Y-%m-%d')

        resp = self.client.get(reverse('admin_reports'), {
            'start_date': start_date,
            'end_date': end_date
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_invoices'], 2)
        invoice_numbers = [inv.invoice_number for inv in resp.context['invoices']]
        self.assertIn("INV-RANGE-002", invoice_numbers)
        self.assertIn("INV-RANGE-003", invoice_numbers)
        self.assertNotIn("INV-RANGE-001", invoice_numbers)
        self.assertNotIn("INV-RANGE-004", invoice_numbers)
        self.assertEqual(float(resp.context['total_sales']), 1400.00)

    def test_invalid_date_range_end_before_start(self):
        """End date earlier than start date returns validation error and empty results."""
        self.authenticate_admin()
        now = timezone.now()
        start_date = now.strftime('%Y-%m-%d')
        end_date = (now - timedelta(days=5)).strftime('%Y-%m-%d')

        resp = self.client.get(reverse('admin_reports'), {
            'start_date': start_date,
            'end_date': end_date
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_invoices'], 0)
        self.assertContains(resp, "End date cannot be earlier than start date.")
        self.assertEqual(resp.context['date_error'], "End date cannot be earlier than start date.")

    def test_empty_date_fields_handling(self):
        """Empty date strings do not raise 500 error and default cleanly."""
        self.authenticate_admin()
        # Both empty
        resp = self.client.get(reverse('admin_reports'), {
            'start_date': '',
            'end_date': ''
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_invoices'], 4)

        # Only start date provided
        now = timezone.now()
        start_date = (now - timedelta(days=6)).strftime('%Y-%m-%d')
        resp_start = self.client.get(reverse('admin_reports'), {
            'start_date': start_date,
            'end_date': ''
        })
        self.assertEqual(resp_start.status_code, 200)
        self.assertEqual(resp_start.context['total_invoices'], 2) # Inv 3 and Inv 4

        # Only end date provided
        end_date = (now - timedelta(days=6)).strftime('%Y-%m-%d')
        resp_end = self.client.get(reverse('admin_reports'), {
            'start_date': '',
            'end_date': end_date
        })
        self.assertEqual(resp_end.status_code, 200)
        self.assertEqual(resp_end.context['total_invoices'], 2) # Inv 1 and Inv 2

    def test_no_invoices_in_date_range(self):
        """When no records fall in date range, empty state is displayed with 0 invoices."""
        self.authenticate_admin()
        resp = self.client.get(reverse('admin_reports'), {
            'start_date': '2020-01-01',
            'end_date': '2020-01-31'
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_invoices'], 0)
        self.assertEqual(resp.context['total_sales'], Decimal('0.00'))
        self.assertContains(resp, "No invoices found")

    def test_frontend_report_form_elements_present(self):
        """Verify presence of Start Date, End Date, Generate Report button, and Reset option."""
        self.authenticate_admin()
        resp = self.client.get(reverse('admin_reports'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        # Form elements
        self.assertIn('name="start_date"', content)
        self.assertIn('id="start_date"', content)
        self.assertIn('name="end_date"', content)
        self.assertIn('id="end_date"', content)
        self.assertIn('Start Date', content)
        self.assertIn('End Date', content)
        self.assertIn('Generate Report', content)
        self.assertIn('Reset', content)
        self.assertIn(reverse('admin_reports'), content)

    def test_unauthenticated_and_unauthorized_access(self):
        """Unauthenticated or distributor users cannot access admin reports."""
        # Unauthenticated
        resp_unauth = self.client.get(reverse('admin_reports'))
        self.assertEqual(resp_unauth.status_code, 302)
        self.assertIn(reverse('admin_login'), resp_unauth.url)

        # Distributor
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()
        resp_dist = self.client.get(reverse('admin_reports'))
        self.assertEqual(resp_dist.status_code, 302)
        self.assertIn(reverse('admin_login'), resp_dist.url)


class DateRangeInvoiceCountAndCollectedAmountTest(TestCase):
    """
    Test suite for Task 2: Display Total Number of Invoices and Total Amount Collected
    Within the Selected Date Range.
    Tests:
    - Date range containing multiple paid invoices.
    - Date range containing unpaid invoices.
    - Date range containing failed payments.
    - Date range with no invoices.
    - Date range containing both paid and unpaid/failed invoices.
    - Accurate calculation using Django ORM Count and Sum.
    - Exclusion of pending, failed, or unpaid invoices from collected amounts.
    - Frontend summary cards rendering and currency formatting (₹).
    - Preserves Task 1 date-range filtering functionality.
    """

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            email="analytics.admin@billing.com",
            password="AdminPassword123!",
            name="Analytics Admin"
        )
        self.customer = Customer.objects.create(
            name="Retail Partner Corp",
            email="partner@retail.com",
            phone="9123456780",
            address="456 Market St, Floor 3"
        )
        self.product = Product.objects.create(
            name="Retail POS Terminal",
            category="Hardware",
            price=Decimal('500.00'),
            stock=50
        )

        self.now = timezone.now()
        # Setup specific date benchmarks
        self.target_date = self.now - timedelta(days=3)
        self.start_str = (self.target_date - timedelta(days=1)).strftime('%Y-%m-%d')
        self.end_str = (self.target_date + timedelta(days=1)).strftime('%Y-%m-%d')

    def authenticate_admin(self):
        session = self.client.session
        session['user_id'] = self.admin.id
        session['usertype'] = 'admin'
        session.save()

    def test_date_range_multiple_paid_invoices(self):
        """Date range containing multiple paid invoices computes total invoices and total collected amount correctly."""
        self.authenticate_admin()
        # Create 3 paid invoices within target date range
        inv1 = Invoice.objects.create(
            invoice_number="INV-PAID-01",
            customer=self.customer,
            total_amount=Decimal('500.00'),
            payment_status="paid"
        )
        Invoice.objects.filter(id=inv1.id).update(created_at=self.target_date)

        inv2 = Invoice.objects.create(
            invoice_number="INV-PAID-02",
            customer=self.customer,
            total_amount=Decimal('350.50'),
            payment_status="paid"
        )
        Invoice.objects.filter(id=inv2.id).update(created_at=self.target_date)

        inv3 = Invoice.objects.create(
            invoice_number="INV-PAID-03",
            customer=self.customer,
            total_amount=Decimal('150.00'),
            payment_status="paid"
        )
        Invoice.objects.filter(id=inv3.id).update(created_at=self.target_date)

        # Invoice outside date range (should not be counted)
        inv_outside = Invoice.objects.create(
            invoice_number="INV-PAID-OUTSIDE",
            customer=self.customer,
            total_amount=Decimal('999.00'),
            payment_status="paid"
        )
        Invoice.objects.filter(id=inv_outside.id).update(created_at=self.now - timedelta(days=20))

        resp = self.client.get(reverse('admin_reports'), {
            'start_date': self.start_str,
            'end_date': self.end_str
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_invoices'], 3)
        self.assertEqual(resp.context['total_amount_collected'], Decimal('1000.50'))
        self.assertContains(resp, "Total Invoices")
        self.assertContains(resp, "Total Amount Collected")
        self.assertContains(resp, "1000.50")

    def test_date_range_unpaid_invoices_excluded_from_collected_amount(self):
        """Unpaid invoices increment total invoice count but are strictly excluded from collected amount."""
        self.authenticate_admin()
        inv_unpaid1 = Invoice.objects.create(
            invoice_number="INV-UNPAID-01",
            customer=self.customer,
            total_amount=Decimal('400.00'),
            payment_status="unpaid"
        )
        Invoice.objects.filter(id=inv_unpaid1.id).update(created_at=self.target_date)

        inv_unpaid2 = Invoice.objects.create(
            invoice_number="INV-UNPAID-02",
            customer=self.customer,
            total_amount=Decimal('600.00'),
            payment_status="unpaid"
        )
        Invoice.objects.filter(id=inv_unpaid2.id).update(created_at=self.target_date)

        resp = self.client.get(reverse('admin_reports'), {
            'start_date': self.start_str,
            'end_date': self.end_str
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_invoices'], 2)
        self.assertEqual(resp.context['total_amount_collected'], Decimal('0.00'))

    def test_date_range_failed_payments_excluded_from_collected_amount(self):
        """Failed invoices are counted in total invoices but excluded from collected amount."""
        self.authenticate_admin()
        inv_failed = Invoice.objects.create(
            invoice_number="INV-FAILED-01",
            customer=self.customer,
            total_amount=Decimal('750.00'),
            payment_status="failed"
        )
        Invoice.objects.filter(id=inv_failed.id).update(created_at=self.target_date)

        resp = self.client.get(reverse('admin_reports'), {
            'start_date': self.start_str,
            'end_date': self.end_str
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_invoices'], 1)
        self.assertEqual(resp.context['total_amount_collected'], Decimal('0.00'))

    def test_date_range_with_no_invoices(self):
        """Date range with no matching invoices safely returns 0 invoices and ₹0.00 collected amount."""
        self.authenticate_admin()
        resp = self.client.get(reverse('admin_reports'), {
            'start_date': '2021-01-01',
            'end_date': '2021-01-10'
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_invoices'], 0)
        self.assertEqual(resp.context['total_amount_collected'], Decimal('0.00'))
        self.assertContains(resp, "0.00")

    def test_date_range_mixed_paid_unpaid_pending_and_failed(self):
        """Mixed status invoices: count includes all invoices, collected amount sums ONLY paid invoices."""
        self.authenticate_admin()
        # Paid: 500 + 300 = 800
        inv_p1 = Invoice.objects.create(
            invoice_number="INV-MIX-P1",
            customer=self.customer,
            total_amount=Decimal('500.00'),
            payment_status="paid"
        )
        Invoice.objects.filter(id=inv_p1.id).update(created_at=self.target_date)

        inv_p2 = Invoice.objects.create(
            invoice_number="INV-MIX-P2",
            customer=self.customer,
            total_amount=Decimal('300.00'),
            payment_status="paid"
        )
        Invoice.objects.filter(id=inv_p2.id).update(created_at=self.target_date)

        # Unpaid: 200
        inv_u = Invoice.objects.create(
            invoice_number="INV-MIX-U1",
            customer=self.customer,
            total_amount=Decimal('200.00'),
            payment_status="unpaid"
        )
        Invoice.objects.filter(id=inv_u.id).update(created_at=self.target_date)

        # Pending: 150
        inv_pen = Invoice.objects.create(
            invoice_number="INV-MIX-PEN",
            customer=self.customer,
            total_amount=Decimal('150.00'),
            payment_status="pending"
        )
        Invoice.objects.filter(id=inv_pen.id).update(created_at=self.target_date)

        # Failed: 100
        inv_f = Invoice.objects.create(
            invoice_number="INV-MIX-F1",
            customer=self.customer,
            total_amount=Decimal('100.00'),
            payment_status="failed"
        )
        Invoice.objects.filter(id=inv_f.id).update(created_at=self.target_date)

        resp = self.client.get(reverse('admin_reports'), {
            'start_date': self.start_str,
            'end_date': self.end_str
        })
        self.assertEqual(resp.status_code, 200)
        # Total invoices = 2 paid + 1 unpaid + 1 pending + 1 failed = 5
        self.assertEqual(resp.context['total_invoices'], 5)
        # Collected amount = 500 + 300 = 800 (unpaid, pending, and failed excluded)
        self.assertEqual(resp.context['total_amount_collected'], Decimal('800.00'))
        self.assertContains(resp, "800.00")

    def test_frontend_summary_cards_rendered(self):
        """Verify summary cards for Total Invoices and Total Amount Collected are rendered above records."""
        self.authenticate_admin()
        inv = Invoice.objects.create(
            invoice_number="INV-CARD-TEST",
            customer=self.customer,
            total_amount=Decimal('1250.75'),
            payment_status="paid"
        )
        Invoice.objects.filter(id=inv.id).update(created_at=self.target_date)

        resp = self.client.get(reverse('admin_reports'), {
            'start_date': self.start_str,
            'end_date': self.end_str
        })
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        # Check card labels and currency formatting
        self.assertIn("Total Invoices", content)
        self.assertIn("Total Amount Collected", content)
        self.assertIn("₹", content)
        self.assertIn("1250.75", content)


class DateRangeReportPDFDownloadTest(TestCase):
    """
    Test suite for Task 3: Download Generated Report as PDF using xhtml2pdf.
    Tests:
    - Download PDF with a valid date range and multiple invoices.
    - PDF contains header details (business name, Report Title: Invoice Report, dates).
    - PDF contains summary section (Total Invoices, Total Amount Collected).
    - PDF contains invoice details table (Sr. No, Invoice #, Customer, Date, Amount, Status).
    - Download PDF when no invoices are available (renders empty-state message).
    - Unpaid and failed invoices excluded from collected amount in PDF.
    - Preserves selected date range query parameters in download button.
    - Security and authorization (anonymous and distributor redirected).
    """

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            email="pdf.admin@billing.com",
            password="AdminPassword123!",
            name="PDF Report Admin",
            company_name="Advance Billing Tech"
        )
        self.distributor = User.objects.create_user(
            email="pdf.dist@billing.com",
            password="DistPassword123!",
            name="PDF Distributor",
            usertype="distributor"
        )
        self.customer = Customer.objects.create(
            name="Global Enterprises Ltd",
            email="global@corp.com",
            phone="9823456789",
            address="789 Industrial Area, Tech Park"
        )

        self.now = timezone.now()
        self.target_date = self.now - timedelta(days=2)
        self.start_str = (self.target_date - timedelta(days=1)).strftime('%Y-%m-%d')
        self.end_str = (self.target_date + timedelta(days=1)).strftime('%Y-%m-%d')

    def authenticate_admin(self):
        session = self.client.session
        session['user_id'] = self.admin.id
        session['usertype'] = 'admin'
        session.save()

    def test_download_pdf_valid_date_range_multiple_invoices(self):
        """Valid date range PDF download returns valid binary PDF with expected content and headers."""
        self.authenticate_admin()
        # Create 2 invoices in range
        inv1 = Invoice.objects.create(
            invoice_number="INV-PDF-101",
            customer=self.customer,
            total_amount=Decimal('1500.00'),
            payment_status="paid"
        )
        Invoice.objects.filter(id=inv1.id).update(created_at=self.target_date)

        inv2 = Invoice.objects.create(
            invoice_number="INV-PDF-102",
            customer=self.customer,
            total_amount=Decimal('850.50'),
            payment_status="paid"
        )
        Invoice.objects.filter(id=inv2.id).update(created_at=self.target_date)

        # 1 invoice outside range
        inv_outside = Invoice.objects.create(
            invoice_number="INV-PDF-OUTSIDE",
            customer=self.customer,
            total_amount=Decimal('9999.00'),
            payment_status="paid"
        )
        Invoice.objects.filter(id=inv_outside.id).update(created_at=self.now - timedelta(days=25))

        resp = self.client.get(reverse('admin_reports_pdf'), {
            'start_date': self.start_str,
            'end_date': self.end_str
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', resp['Content-Disposition'])
        self.assertIn('Invoice_Report_', resp['Content-Disposition'])

        # Verify PDF starts with %PDF magic bytes
        self.assertTrue(resp.content.startswith(b'%PDF'))

        # Inspect generated PDF text using pypdf
        reader = PdfReader(io.BytesIO(resp.content))
        self.assertGreater(len(reader.pages), 0)
        extracted_text = ""
        for page in reader.pages:
            extracted_text += page.extract_text() or ""

        # Verify Header Section
        self.assertIn("Invoice Report", extracted_text)
        self.assertIn(self.start_str, extracted_text)
        self.assertIn(self.end_str, extracted_text)

        # Verify Summary Section
        self.assertIn("2", extracted_text) # total_invoices = 2
        self.assertIn("2350.50", extracted_text) # 1500.00 + 850.50 = 2350.50

        # Verify Invoice Details Table
        self.assertIn("INV-PDF-101", extracted_text)
        self.assertIn("INV-PDF-102", extracted_text)
        self.assertNotIn("INV-PDF-OUTSIDE", extracted_text)
        self.assertIn("Global Enterprises Ltd", extracted_text)
        self.assertIn("Paid", extracted_text)

    def test_download_pdf_empty_results_renders_clean_message(self):
        """When date range has 0 invoices, PDF still renders cleanly with empty message."""
        self.authenticate_admin()
        resp = self.client.get(reverse('admin_reports_pdf'), {
            'start_date': '2021-01-01',
            'end_date': '2021-01-05'
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF'))

        reader = PdfReader(io.BytesIO(resp.content))
        extracted_text = ""
        for page in reader.pages:
            extracted_text += page.extract_text() or ""

        self.assertIn("Invoice Report", extracted_text)
        self.assertIn("No invoice records found", extracted_text)
        self.assertIn("0.00", extracted_text)

    def test_download_pdf_unpaid_and_failed_excluded_from_collected_amount(self):
        """Unpaid and failed payments in range are listed in table but excluded from summary collected amount in PDF."""
        self.authenticate_admin()
        inv_paid = Invoice.objects.create(
            invoice_number="INV-PDF-PAID",
            customer=self.customer,
            total_amount=Decimal('600.00'),
            payment_status="paid"
        )
        Invoice.objects.filter(id=inv_paid.id).update(created_at=self.target_date)

        inv_unpaid = Invoice.objects.create(
            invoice_number="INV-PDF-UNPAID",
            customer=self.customer,
            total_amount=Decimal('400.00'),
            payment_status="unpaid"
        )
        Invoice.objects.filter(id=inv_unpaid.id).update(created_at=self.target_date)

        inv_failed = Invoice.objects.create(
            invoice_number="INV-PDF-FAILED",
            customer=self.customer,
            total_amount=Decimal('300.00'),
            payment_status="failed"
        )
        Invoice.objects.filter(id=inv_failed.id).update(created_at=self.target_date)

        resp = self.client.get(reverse('admin_reports_pdf'), {
            'start_date': self.start_str,
            'end_date': self.end_str
        })
        self.assertEqual(resp.status_code, 200)

        reader = PdfReader(io.BytesIO(resp.content))
        extracted_text = ""
        for page in reader.pages:
            extracted_text += page.extract_text() or ""

        # Total count = 3
        self.assertIn("3", extracted_text)
        # Total collected = 600.00 (400 and 300 excluded)
        self.assertIn("600.00", extracted_text)
        self.assertNotIn("1300.00", extracted_text)
        # Table lists all 3 with statuses
        self.assertIn("INV-PDF-PAID", extracted_text)
        self.assertIn("INV-PDF-UNPAID", extracted_text)
        self.assertIn("INV-PDF-FAILED", extracted_text)

    def test_frontend_download_pdf_button_preserves_date_range(self):
        """Frontend Reports view provides Download PDF button preserving start_date and end_date."""
        self.authenticate_admin()
        resp = self.client.get(reverse('admin_reports'), {
            'start_date': self.start_str,
            'end_date': self.end_str
        })
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        # Check button label and preserved parameters
        self.assertIn("Download PDF", content)
        self.assertIn(f"start_date={self.start_str}", content)
        self.assertIn(f"end_date={self.end_str}", content)
        self.assertIn(reverse('admin_reports_pdf'), content)

    def test_pdf_endpoint_access_restrictions(self):
        """Unauthenticated and non-admin users cannot download reports PDF."""
        # Unauthenticated
        resp_anon = self.client.get(reverse('admin_reports_pdf'))
        self.assertEqual(resp_anon.status_code, 302)
        self.assertIn(reverse('admin_login'), resp_anon.url)

        # Distributor
        session = self.client.session
        session['user_id'] = self.distributor.id
        session['usertype'] = 'distributor'
        session.save()
        resp_dist = self.client.get(reverse('admin_reports_pdf'))
        self.assertEqual(resp_dist.status_code, 302)
        self.assertIn(reverse('admin_login'), resp_dist.url)















