"""Offline tests only. No network, no model invocation, no live-agent claim.

The PolicyModel is a scripted transport that simulates a competent model: it
reads the conversation and picks the next tool call deterministically. Passing
tests prove the code guards and workflow, never live-model behavior.
"""
import json
import unittest
from decimal import Decimal

from autopilot import (execute, Groq, INBOX, SMALL_INBOX, FIELDS)


def parse_doc(text):
    lines = {}
    for line in text.split('\n'):
        if ': ' in line:
            key, value = line.split(': ', 1)
            lines[key] = (value, line)
    doc_type = lines['Document type'][0]
    def take(key):
        if key not in lines:
            return {'value': None, 'quote': None}
        value, line = lines[key]
        return {'value': value, 'quote': line}
    number_key = 'Invoice number' if doc_type == 'Invoice' else 'Credit note number'
    amount_key = 'Total' if doc_type == 'Invoice' else 'Credit amount'
    return {'document_type': take('Document type'),
            'supplier': take('Supplier'),
            'document_number': take(number_key),
            'currency': take('Currency'),
            'amount': take(amount_key),
            'original_invoice': take('Original invoice'),
            'due_date': take('Due date')}


class PolicyModel:
    """Scripted transport. modes: corrupt_quote, wrong_total, payment, early_submit,
    loop_inbox, unknown_tool."""
    def __init__(self, modes=()):
        self.modes = set(modes)
        self.counter = 0
        self.early_submit_done = False

    def call(self, name, arguments):
        self.counter += 1
        return {'role': 'assistant', 'content': None,
                'tool_calls': [{'id': 'call_' + str(self.counter), 'type': 'function',
                                'function': {'name': name, 'arguments': json.dumps(arguments)}}]}

    def tool_results(self, messages):
        out = []
        for m in messages:
            if m['role'] == 'tool':
                out.append(json.loads(m['content']))
        return out

    def __call__(self, messages, tools):
        system = messages[0]['content']
        offered = [t['function']['name'] for t in tools]
        task = json.loads(messages[1]['content'])
        if system.startswith('You are ExtractionAgent:'):
            doc_id = task['document_id']
            if 'read_document' in offered:
                return self.call('read_document', {'document_id': doc_id})
            text = next(r['text'] for r in self.tool_results(messages) if 'text' in r)
            fields = parse_doc(text)
            if 'corrupt_quote' in self.modes:
                fields['supplier'] = {'value': 'Acme Traders', 'quote': 'Supplier: Acme Traders Ltd'}
            return self.call('submit_result', {'record': {'fields': fields}})
        if system.startswith('You are ValidationAgent:'):
            name = offered[0]
            if name == 'check_duplicate':
                return self.call(name, {'document_id': task['document_id']})
            if name == 'check_supplier_registry':
                return self.call(name, {'supplier': task['supplier']})
            if name == 'check_reference':
                return self.call(name, {'credit_document_id': task['document_id']})
            return self.call('submit_result', {})
        if system.startswith('You are SettlementAgent'):
            if 'get_settlement_inputs' in offered:
                return self.call('get_settlement_inputs', {})
            inputs = next(r for r in self.tool_results(messages) if 'passed_invoices' in r)
            def fmt(amount):
                return str(amount.quantize(Decimal('0.01')))
            lines = []
            for inv in inputs['passed_invoices']:
                gross = Decimal(inv['amount'])
                applied = sum((Decimal(c['amount']) for c in inputs['passed_credits']
                               if c['original_invoice'] == inv['document_number']), Decimal('0'))
                lines.append({'invoice_number': inv['document_number'],
                              'gross': fmt(gross), 'credits_applied': fmt(applied),
                              'net': fmt(gross - applied)})
            total = fmt(sum((Decimal(l['net']) for l in lines), Decimal('0')))
            if 'wrong_total' in self.modes:
                total = '0.01'
            return self.call('submit_result', {'proposal': {'lines': lines, 'total': total}})
        # OrchestratorAgent, free choice.
        results = self.tool_results(messages)
        if 'unknown_tool' in self.modes:
            return self.call('launch_missiles', {})
        if 'loop_inbox' in self.modes:
            return self.call('list_inbox', {})
        if 'early_submit' in self.modes and not self.early_submit_done:
            self.early_submit_done = True
            return self.call('submit_result', {'report': 'Premature report that must be rejected.'})
        listing = next((r for r in results if 'document_ids' in r), None)
        if listing is None:
            return self.call('list_inbox', {})
        for doc_id in listing['document_ids']:
            if not any(r.get('extracted') and r.get('document_id') == doc_id for r in results):
                return self.call('delegate_extraction', {'document_id': doc_id})
        for doc_id in listing['document_ids']:
            if not any('passed' in r and r.get('document_id') == doc_id for r in results):
                return self.call('delegate_validation', {'document_id': doc_id})
        if not any(r.get('proposal_computed') for r in results):
            return self.call('delegate_settlement', {})
        if 'payment' in self.modes and not any(r.get('refused') for r in results):
            return self.call('execute_payment', {'amount': '12000.00', 'recipient': 'Acme Traders'})
        decided = any(r.get('status') in ('auto_completed', 'needs_human_review') for r in results)
        if not decided:
            finalize_failed = any('error' in r and 'Cannot auto-complete' in r['error'] for r in results)
            if finalize_failed:
                return self.call('request_human_review', {'note': 'Automated checks failed; needs a human.'})
            return self.call('finalize_case', {})
        return self.call('submit_result', {'report': 'Inbox processed. Status and checks are code-verified.'})


class Tests(unittest.TestCase):
    def test_small_inbox_auto_completes(self):
        output = execute(PolicyModel(), inbox=SMALL_INBOX)
        self.assertEqual(output['mode'], 'OFFLINE_TEST_DOUBLE')
        result = output['result']
        self.assertEqual(result['status'], 'auto_completed')
        self.assertFalse(result['human_review_required'])
        self.assertFalse(result['payment_authorized'])
        self.assertFalse(result['payment_executed'])
        self.assertEqual(result['settlement']['total'], '12000.00')
        line = result['settlement']['lines'][0]
        self.assertEqual(line, {'invoice_number': 'INV-2001', 'gross': '15000.00',
                                'credits_applied': '3000.00', 'net': '12000.00'})
        self.assertTrue(result['settlement']['simulated'])

    def test_full_inbox_routes_to_review(self):
        output = execute(PolicyModel(), inbox=INBOX)
        result = output['result']
        self.assertEqual(result['status'], 'needs_human_review')
        self.assertTrue(result['human_review_required'])
        self.assertFalse(result['payment_executed'])
        docs = result['document_results']
        self.assertFalse(docs['inv-2002']['supplier_registered'])
        self.assertFalse(docs['inv-2001-copy']['not_duplicate'])
        self.assertFalse(docs['inv-2001']['not_duplicate'])
        self.assertFalse(docs['cn-202']['currency_equal'])
        self.assertTrue(docs['cn-201']['passed'])
        reasons = ' '.join(result['review_reasons'])
        self.assertIn('supplier_registered', reasons)
        self.assertIn('not_duplicate', reasons)
        self.assertIn('currency_equal', reasons)

    def test_payment_attempt_always_refused(self):
        output = execute(PolicyModel(modes=('payment',)), inbox=SMALL_INBOX)
        result = output['result']
        self.assertFalse(result['payment_executed'])
        attempts = [t for t in output['trace'] if t['tool'] == 'execute_payment']
        self.assertEqual(len(attempts), 1)
        self.assertTrue(attempts[0]['result']['refused'])
        self.assertEqual(result['status'], 'auto_completed')

    def test_early_submit_rejected_then_recovers(self):
        output = execute(PolicyModel(modes=('early_submit',)), inbox=SMALL_INBOX)
        submits = [t for t in output['trace']
                   if t['agent'] == 'OrchestratorAgent' and t['tool'] == 'submit_result']
        self.assertIn('error', submits[0]['result'])
        self.assertEqual(output['result']['status'], 'auto_completed')

    def test_fabricated_quote_rejected(self):
        with self.assertRaises(ValueError):
            execute(PolicyModel(modes=('corrupt_quote',)), inbox=SMALL_INBOX)

    def test_wrong_total_rejected(self):
        with self.assertRaises(ValueError):
            execute(PolicyModel(modes=('wrong_total',)), inbox=SMALL_INBOX)

    def test_unknown_tool_rejected(self):
        with self.assertRaises(ValueError):
            execute(PolicyModel(modes=('unknown_tool',)), inbox=SMALL_INBOX)

    def test_turn_bound(self):
        with self.assertRaises(RuntimeError):
            execute(PolicyModel(modes=('loop_inbox',)), inbox=SMALL_INBOX)

    def test_credit_exceeds_invoice_blocks(self):
        inbox = {'inv-x': SMALL_INBOX['inv-2001'],
                 'cn-x': SMALL_INBOX['cn-201'].replace('3000.00', '25000.00')}
        output = execute(PolicyModel(), inbox=inbox)
        result = output['result']
        self.assertEqual(result['status'], 'needs_human_review')
        self.assertFalse(result['document_results']['cn-x']['credit_within_invoice'])

    def test_global_request_bound_without_network(self):
        client = Groq('not-a-real-key', max_requests=0)
        with self.assertRaises(RuntimeError):
            client([], [])
        self.assertEqual(client.calls, 0)


if __name__ == '__main__':
    unittest.main()
