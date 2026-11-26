import io
import json
import base64
from decimal import Decimal
import qrcode
from billing.models import Invoice


def _to_float(value, default=0.0):
    """Safely convert Decimal or numeric values to a 2-decimal float for JSON serialization."""
    if value is None:
        return default
    try:
        return round(float(Decimal(str(value))), 2)
    except Exception:
        return default


def fetch_saved_invoice(invoice_identifier):
    """
    Fetch an existing saved Invoice record from the database by primary key ID,
    invoice_number, or an existing Invoice instance.

    Raises:
        ValueError: If the identifier is empty, None, or invalid.
        Invoice.DoesNotExist: If no matching invoice exists in the database.
    """
    if invoice_identifier is None or isinstance(invoice_identifier, bool):
        raise ValueError("Invalid invoice identifier provided.")

    if isinstance(invoice_identifier, Invoice):
        if not invoice_identifier.pk:
            raise ValueError("Invoice instance has not been saved to the database.")
        return Invoice.objects.select_related('customer').prefetch_related('items__product').get(
            pk=invoice_identifier.pk
        )

    if isinstance(invoice_identifier, int):
        if invoice_identifier <= 0:
            raise ValueError("Invoice ID must be a positive integer.")
        return Invoice.objects.select_related('customer').prefetch_related('items__product').get(
            id=invoice_identifier
        )

    if isinstance(invoice_identifier, str):
        clean_id = invoice_identifier.strip()
        if not clean_id:
            raise ValueError("Invoice identifier cannot be empty.")

        qs = Invoice.objects.select_related('customer').prefetch_related('items__product')
        invoice = qs.filter(invoice_number__iexact=clean_id).first()
        if invoice:
            return invoice

        if clean_id.isdigit():
            return qs.get(id=int(clean_id))

        raise Invoice.DoesNotExist(f"Invoice '{clean_id}' does not exist.")

    raise ValueError("Unsupported invoice identifier type.")


def extract_invoice_data(invoice):
    """
    Extract structured, JSON-safe invoice data from a saved Invoice model instance,
    including related customer and product line items.
    """
    if not isinstance(invoice, Invoice) or not invoice.pk:
        raise ValueError("A saved Invoice instance is required.")

    # Safe customer extraction (avoiding any auth/sensitive fields)
    customer_obj = getattr(invoice, 'customer', None)
    customer_data = {
        'id': customer_obj.id if customer_obj else None,
        'name': (customer_obj.name or 'Unknown Customer') if customer_obj else 'Unknown Customer',
        'phone': (customer_obj.phone or '') if customer_obj else '',
        'email': (customer_obj.email or '') if customer_obj else '',
        'address': (customer_obj.address or '') if customer_obj else '',
    }

    # Safe product/line-item extraction
    items_data = []
    calc_subtotal = Decimal('0.00')
    calc_tax = Decimal('0.00')

    db_items = list(invoice.items.all())
    for idx, item in enumerate(db_items, start=1):
        product_obj = getattr(item, 'product', None)
        qty = int(item.quantity) if item.quantity is not None else 0
        unit_price = item.unit_price if item.unit_price is not None else Decimal('0.00')
        line_subtotal = Decimal(str(unit_price)) * Decimal(qty)
        calc_subtotal += line_subtotal

        gst_rate = (
            product_obj.gst_rate
            if (product_obj and product_obj.gst_rate is not None)
            else Decimal('0.00')
        )
        item_tax = (line_subtotal * (Decimal(str(gst_rate)) / Decimal('100'))).quantize(Decimal('0.01'))
        calc_tax += item_tax

        line_total = (
            item.total_price
            if item.total_price is not None
            else (line_subtotal + item_tax)
        )

        items_data.append({
            'sr_no': idx,
            'product_id': product_obj.id if product_obj else None,
            'product_name': product_obj.name if product_obj else 'Unknown Product',
            'category': product_obj.category if product_obj else '',
            'quantity': qty,
            'unit_price': _to_float(unit_price),
            'gst_rate': _to_float(gst_rate),
            'tax_amount': _to_float(item_tax),
            'total_price': _to_float(line_total),
        })

    payment_status = invoice.payment_status or 'paid'
    payment_status_display = dict(Invoice.PAYMENT_STATUS_CHOICES).get(
        payment_status, payment_status.title()
    )

    invoice_date = invoice.created_at.strftime('%Y-%m-%d') if invoice.created_at else None
    invoice_datetime = invoice.created_at.isoformat() if invoice.created_at else None

    total_amount = (
        _to_float(invoice.total_amount)
        if invoice.total_amount is not None
        else _to_float(calc_subtotal + calc_tax)
    )

    return {
        'invoice_id': invoice.id,
        'invoice_number': invoice.invoice_number or str(invoice.id),
        'invoice_date': invoice_date,
        'invoice_datetime': invoice_datetime,
        'payment_status': payment_status,
        'payment_status_display': payment_status_display,
        'customer': customer_data,
        'items': items_data,
        'product_count': len(items_data),
        'subtotal': _to_float(calc_subtotal),
        'tax_amount': _to_float(calc_tax),
        'total_amount': total_amount,
    }


def prepare_invoice_qr_payload(invoice_identifier):
    """
    Fetch saved invoice data and serialize it into a structured, non-empty JSON QR payload.

    Returns:
        tuple: (payload_dict, payload_json_str)
    """
    invoice = fetch_saved_invoice(invoice_identifier)
    data = extract_invoice_data(invoice)

    payload_dict = {
        'invoice_id': data['invoice_id'],
        'invoice_number': data['invoice_number'],
        'invoice_date': data['invoice_date'],
        'payment_status': data['payment_status'],
        'customer': {
            'name': data['customer']['name'],
            'phone': data['customer']['phone'],
        },
        'items': [
            {
                'name': item['product_name'],
                'category': item['category'],
                'quantity': item['quantity'],
                'unit_price': item['unit_price'],
                'gst_rate': item['gst_rate'],
                'total': item['total_price'],
            }
            for item in data['items']
        ],
        'product_count': data['product_count'],
        'subtotal': data['subtotal'],
        'tax_amount': data['tax_amount'],
        'total_amount': data['total_amount'],
    }

    payload_json = json.dumps(payload_dict, ensure_ascii=False, separators=(',', ':'))
    if not payload_json or not payload_json.strip():
        raise ValueError("Prepared QR payload is empty.")

    return payload_dict, payload_json


def create_qr_png_bytes(payload_text, box_size=8, border=3):
    """
    Generate a PNG QR code image in-memory from the given payload string.
    """
    if not payload_text or not isinstance(payload_text, str) or not payload_text.strip():
        raise ValueError("Cannot generate QR code from an empty payload.")

    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(payload_text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        try:
            img.save(buffer, format="PNG")
            png_bytes = buffer.getvalue()
        finally:
            buffer.close()

        if not png_bytes:
            raise RuntimeError("Generated QR image buffer is empty.")
        return png_bytes
    except Exception as exc:
        raise RuntimeError(f"QR code generation failed: {exc}") from exc


def generate_invoice_qr_code(invoice_identifier, box_size=8, border=3):
    """
    End-to-end pipeline for Task 1:
    1. Validate invoice identifier & fetch saved invoice from DB.
    2. Extract invoice, customer, product, and total details.
    3. Prepare structured JSON QR payload.
    4. Generate scannable QR code PNG bytes and base64 Data URI.
    5. Handle invalid IDs, missing records, and QR generation failures safely.
    """
    result = {
        'is_success': False,
        'invoice_id': None,
        'invoice_number': None,
        'invoice_data': None,
        'payload': None,
        'payload_json': None,
        'qr_png_bytes': None,
        'qr_base64': None,
        'error': None,
    }

    try:
        invoice = fetch_saved_invoice(invoice_identifier)
        invoice_data = extract_invoice_data(invoice)
        payload_dict, payload_json = prepare_invoice_qr_payload(invoice)
        png_bytes = create_qr_png_bytes(payload_json, box_size=box_size, border=border)
        b64_str = base64.b64encode(png_bytes).decode('utf-8')

        result.update({
            'is_success': True,
            'invoice_id': invoice_data['invoice_id'],
            'invoice_number': invoice_data['invoice_number'],
            'invoice_data': invoice_data,
            'payload': payload_dict,
            'payload_json': payload_json,
            'qr_png_bytes': png_bytes,
            'qr_base64': f"data:image/png;base64,{b64_str}",
            'error': None,
        })
    except Invoice.DoesNotExist:
        result['error'] = "Invoice not found in the database."
    except ValueError as exc:
        result['error'] = str(exc)
    except Exception as exc:
        result['error'] = f"Failed to generate invoice QR code: {exc}"

    return result
