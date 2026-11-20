"""Run only fictional, manually entered examples. No network or payments."""
import json
from test_linking_preview import INVOICE, CREDIT
from linking_preview import preview

examples = {
    'valid_single_credit': preview(CREDIT, 'INV-1042', [INVOICE]),
    'resend_unresolved': preview(CREDIT, 'INV-1042', [INVOICE, dict(INVOICE, record_id='RESEND')]),
    'missing_reference': preview(CREDIT, '', [INVOICE]),
    'different_supplier': preview(dict(CREDIT, supplier_name='Lotus Office Supplies'), 'INV-1042', [INVOICE]),
    'different_currency': preview(dict(CREDIT, currency='USD'), 'INV-1042', [INVOICE]),
}
print(json.dumps(examples, indent=2))
