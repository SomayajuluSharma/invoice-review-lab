"""Offline tests only. No network, no model invocation, no live-agent claim."""
import json
import unittest
from agent_demo import execute, FIXTURES, Groq


def tool(name, arguments, call_id='call_1'):
    return {'role': 'assistant', 'content': None,
            'tool_calls': [{'id': call_id, 'type': 'function',
                            'function': {'name': name, 'arguments': json.dumps(arguments)}}]}


def records():
    mappings = {
        'invoice': {'document_type': ('Invoice', 'Document type: Invoice'),
                    'supplier': ('Acme Traders', 'Supplier: Acme Traders'),
                    'document_number': ('INV-1042', 'Invoice number: INV-1042'),
                    'currency': ('INR', 'Currency: INR'),
                    'amount': ('10000.00', 'Total: 10000.00'),
                    'original_invoice': (None, None)},
        'credit': {'document_type': ('Credit note', 'Document type: Credit note'),
                   'supplier': ('Acme Traders', 'Supplier: Acme Traders'),
                   'document_number': ('CN-88', 'Credit note number: CN-88'),
                   'currency': ('INR', 'Currency: INR'),
                   'amount': ('2000.00', 'Credit amount: 2000.00'),
                   'original_invoice': ('INV-1042', 'Original invoice: INV-1042')},
    }
    return [{'document_id': doc, 'fields': {k: {'value': value, 'quote': quote}
             for k, (value, quote) in fields.items()}} for doc, fields in mappings.items()]


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []
        self.schemas = []
    def __call__(self, messages, tools):
        self.messages.append(json.loads(json.dumps(messages)))
        self.schemas.append(json.loads(json.dumps(tools)))
        return next(self.responses)


def happy_responses():
    return [
        {'role': 'assistant', 'content': None, 'tool_calls': [
            tool('read_document', {'document_id': 'invoice'}, 'c1')['tool_calls'][0],
            tool('read_document', {'document_id': 'credit'}, 'c2')['tool_calls'][0]]},
        tool('submit_result', {'records': records()}),
        tool('check_reference', {'credit_document_id': 'credit', 'invoice_document_id': 'invoice'}),
        tool('submit_result', {'credit_document_id': 'credit', 'invoice_document_id': 'invoice'}),
        tool('get_review_packet', {}),
        tool('submit_result', {'summary': 'The checked credit references the invoice. Human review is required. No payment is authorized.'}),
    ]


class Tests(unittest.TestCase):
    def test_explicit_offline_mode_and_handoffs(self):
        model = FakeModel(happy_responses())
        result = execute(model)
        self.assertEqual(result['mode'], 'OFFLINE_TEST_DOUBLE')
        self.assertIsNone(result['model'])
        self.assertTrue(result['result']['human_review_required'])
        self.assertFalse(result['result']['payment_authorized'])
        self.assertEqual({x['agent'] for x in result['trace']},
                         {'ExtractionAgent', 'ReferenceAgent', 'ExceptionSummaryAgent'})
        self.assertEqual(len(model.messages), 6)
        self.assertIn('INV-1042', json.dumps(model.messages[2]))
        self.assertIn('tool', json.dumps(model.messages[1]))
    def test_nested_extraction_schema(self):
        model = FakeModel(happy_responses())
        execute(model)
        extraction = model.schemas[1][0]['function']['parameters']['properties']['records']['items']
        self.assertEqual(extraction['required'], ['document_id', 'fields'])
        self.assertFalse(extraction['additionalProperties'])
        self.assertIn('amount', extraction['properties']['fields']['required'])
        self.assertEqual(extraction['properties']['fields']['properties']['amount']['required'], ['value', 'quote'])
    def test_fabricated_quote_rejected(self):
        responses = happy_responses()
        payload = records()
        payload[0]['fields']['amount'] = {'value': '99999', 'quote': 'Total: 99999'}
        responses[1] = tool('submit_result', {'records': payload})
        with self.assertRaisesRegex(ValueError, 'evidence'):
            execute(FakeModel(responses))
    def test_unknown_tool_rejected(self):
        with self.assertRaisesRegex(ValueError, 'not allowed'):
            execute(FakeModel([tool('send_payment', {})]))
    def test_plain_text_not_false_success(self):
        with self.assertRaisesRegex(ValueError, 'no evidence tool'):
            execute(FakeModel([{'role': 'assistant', 'content': 'All done'}]))
    def test_link_requires_validation_tool(self):
        responses = happy_responses()
        del responses[2]
        with self.assertRaisesRegex(ValueError, 'check_reference'):
            execute(FakeModel(responses))
    def test_summary_requires_packet(self):
        responses = happy_responses()
        del responses[4]
        with self.assertRaisesRegex(ValueError, 'Read packet'):
            execute(FakeModel(responses))
    def test_mismatch_never_becomes_supported(self):
        responses = happy_responses()
        fixture = dict(FIXTURES, credit=FIXTURES['credit'].replace('INR', 'USD'))
        payload = records()
        payload[1]['fields']['currency'] = {'value': 'USD', 'quote': 'Currency: USD'}
        responses[1] = tool('submit_result', {'records': payload})
        result = execute(FakeModel(responses), fixture)
        self.assertFalse(result['result']['verified_reference_check']['proposal_supported'])
    def test_global_network_call_bound_without_request(self):
        client = Groq('test-non-secret-placeholder')
        client.calls = 12
        with self.assertRaisesRegex(RuntimeError, '12-request'):
            client([], [])


if __name__ == '__main__':
    unittest.main()
