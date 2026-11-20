"""Local, single-credit linking preview. No ledger writes or payment actions."""
from decimal import Decimal
import engine


def preview(credit_raw, reference, invoice_raws):
    """Return a proposal, never an approved link. Inputs are manually supplied.

    Narrow scope: one credit against one invoice, no payments, tax, prior credits,
    FX, allocations, or live accounting state. Ambiguous matches stay unresolved.
    """
    credit = engine.validate(credit_raw)
    invoices = [engine.validate(row) for row in invoice_raws]
    if credit['kind'] != 'CREDIT_NOTE':
        raise ValueError('Source must be a credit note')
    if any(row['kind'] != 'INVOICE' for row in invoices):
        raise ValueError('Targets must be invoices')
    if len({row['id'] for row in invoices}) != len(invoices):
        raise ValueError('Repeated target record ID')
    base = {'credit_record_id': credit['id'], 'approved': False,
            'payment_authorized': False, 'scope': 'SINGLE_CREDIT_FICTIONAL_PREVIEW'}
    def hold(reason):
        return dict(base, status='NEEDS_REVIEW', reason=reason)
    if not isinstance(reference, str) or not reference.strip():
        return hold('MISSING_REFERENCE')
    if len(reference) > 100 or any(ord(c) < 32 for c in reference):
        return hold('INVALID_REFERENCE')
    key = engine.number_key(reference)
    if not key:
        return hold('INVALID_REFERENCE')
    if not credit['supplier_id']:
        return hold('UNVERIFIED_SUPPLIER')
    matches = [row for row in invoices
               if engine.number_key(row['number']) == key
               and row['supplier_id'] == credit['supplier_id']
               and row['currency'] == credit['currency']]
    if not matches:
        return hold('NO_SAME_SUPPLIER_CURRENCY_REFERENCE_MATCH')
    if len(matches) != 1:
        return hold('AMBIGUOUS_REFERENCE_RESOLVE_RESENDS_FIRST')
    invoice = matches[0]
    amount = Decimal(invoice['amount']) - Decimal(credit['amount'])
    if amount < 0:
        return hold('CREDIT_EXCEEDS_INVOICE_IN_THIS_SCENARIO')
    return dict(base, status='LINK_PROPOSAL_REQUIRES_REVIEW',
                invoice_record_id=invoice['id'], invoice_number=invoice['number'],
                reference_supplied=reference, supplier_id=credit['supplier_id'],
                currency=credit['currency'], invoice_amount=invoice['amount'],
                credit_amount=credit['amount'],
                illustrative_difference=str(amount.quantize(Decimal('0.01'))),
                caveat='Not an open balance. Ignores tax, payments and earlier credits.')
