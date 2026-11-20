import copy
import json
import unittest
from linking_preview import preview

INVOICE = dict(record_id='INV_RECORD', supplier_name='Acme Traders', invoice_number='INV-1042', invoice_date='2026-11-20', amount='10000', currency='INR', document_type='INVOICE', document_text='Fictional invoice')
CREDIT = dict(record_id='CN_RECORD', supplier_name='Acme Traders', invoice_number='CN-88', invoice_date='2026-11-20', amount='2000', currency='INR', document_type='CREDIT_NOTE', document_text='Fictional credit note')

class Tests(unittest.TestCase):
    def call(self, credit=None, ref='INV-1042', invoices=None):
        return preview(credit or CREDIT, ref, [INVOICE] if invoices is None else invoices)
    def test_valid(self):
        out=self.call()
        self.assertEqual(out['status'], 'LINK_PROPOSAL_REQUIRES_REVIEW')
        self.assertEqual(out['illustrative_difference'],'8000.00')
        self.assertFalse(out['approved']); self.assertFalse(out['payment_authorized'])
    def test_reference_format(self):
        self.assertEqual(self.call(ref=' inv 1042 ')['illustrative_difference'],'8000.00')
    def test_missing_reference(self):
        self.assertEqual(self.call(ref='')['reason'],'MISSING_REFERENCE')
    def test_invalid_reference(self):
        self.assertEqual(self.call(ref='---')['reason'],'INVALID_REFERENCE')
    def test_unknown_reference(self):
        self.assertEqual(self.call(ref='INV-999')['status'],'NEEDS_REVIEW')
    def test_other_supplier(self):
        self.assertEqual(self.call(credit=dict(CREDIT,supplier_name='Lotus Office Supplies'))['status'],'NEEDS_REVIEW')
    def test_unverified_supplier(self):
        self.assertEqual(self.call(credit=dict(CREDIT,supplier_name='Acme Unknown'))['reason'],'UNVERIFIED_SUPPLIER')
    def test_currency_mismatch(self):
        self.assertEqual(self.call(credit=dict(CREDIT,currency='USD'))['status'],'NEEDS_REVIEW')
    def test_resend_ambiguity(self):
        self.assertEqual(self.call(invoices=[INVOICE,dict(INVOICE,record_id='RESEND')])['reason'],'AMBIGUOUS_REFERENCE_RESOLVE_RESENDS_FIRST')
    def test_credit_above_invoice(self):
        self.assertEqual(self.call(credit=dict(CREDIT,amount='10001'))['status'],'NEEDS_REVIEW')
    def test_full_credit(self):
        self.assertEqual(self.call(credit=dict(CREDIT,amount='10000'))['illustrative_difference'],'0.00')
    def test_wrong_document_type(self):
        with self.assertRaises(ValueError): self.call(credit=INVOICE)
    def test_invalid_amount(self):
        with self.assertRaises(ValueError): self.call(credit=dict(CREDIT,amount='NaN'))
    def test_input_not_mutated(self):
        a,b=copy.deepcopy(CREDIT),copy.deepcopy(INVOICE)
        self.call(a,invoices=[b]); self.assertEqual(a,CREDIT); self.assertEqual(b,INVOICE)
    def test_duplicate_record_ids(self):
        with self.assertRaises(ValueError): self.call(invoices=[INVOICE,INVOICE])

if __name__ == '__main__':
    unittest.main()
