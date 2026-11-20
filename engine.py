"""Offline candidate matching. Nothing in this module authorizes payment."""
import csv
import hashlib
import io
import re
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation

FIELDS = ['record_id', 'supplier_name', 'invoice_number', 'invoice_date', 'amount', 'currency', 'document_type', 'document_text']
# Fictional, manually verified registry. Never infer identity from a similar name.
ALIASES = {'acme traders': 'SUP-001', 'acme traders pvt ltd': 'SUP-001', 'lotus office supplies': 'SUP-002'}

def name_key(value):
    return ' '.join(value.casefold().split())

def number_key(value):
    return re.sub(r'[^A-Z0-9]', '', value.upper())

def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript('''
    PRAGMA foreign_keys = ON;
    CREATE TABLE IF NOT EXISTS invoices (
      id TEXT PRIMARY KEY, supplier TEXT NOT NULL, supplier_id TEXT,
      number TEXT NOT NULL, day TEXT NOT NULL, amount TEXT NOT NULL,
      currency TEXT NOT NULL, kind TEXT NOT NULL, digest TEXT,
      status TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
    CREATE TABLE IF NOT EXISTS candidates (
      invoice_id TEXT NOT NULL REFERENCES invoices(id), other_id TEXT NOT NULL REFERENCES invoices(id),
      reason TEXT NOT NULL, UNIQUE(invoice_id, other_id, reason));
    CREATE TABLE IF NOT EXISTS decisions (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id TEXT NOT NULL REFERENCES invoices(id),
      decision TEXT NOT NULL, reviewer TEXT NOT NULL, reason TEXT NOT NULL,
      at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
    ''')
    return db

def validate(raw):
    if not isinstance(raw, dict):
        raise ValueError('Each invoice must be an object.')
    def field(key, maximum=200):
        value = raw.get(key, '')
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError('%s must be nonempty text (max %s characters).' % (key, maximum))
        if any(ord(c) < 32 for c in value):
            raise ValueError('%s contains control characters.' % key)
        return value.strip()
    rid = field('record_id', 64)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', rid):
        raise ValueError('record_id may contain letters, digits, hyphens and underscores only.')
    supplier = field('supplier_name')
    number = field('invoice_number', 100)
    if not number_key(number):
        raise ValueError('invoice_number needs letters or digits.')
    day = field('invoice_date', 10)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        raise ValueError('invoice_date must be YYYY-MM-DD.')
    date.fromisoformat(day)
    amount_text = field('amount', 24)
    if not re.fullmatch(r'\d{1,12}(\.\d{1,2})?', amount_text):
        raise ValueError('amount must be positive with at most two decimal places and no separators.')
    amount = Decimal(amount_text)
    if amount <= 0:
        raise ValueError('amount must be greater than zero.')
    currency = field('currency', 3)
    if currency not in ('INR', 'USD', 'EUR', 'GBP'):
        raise ValueError('Demo supports INR, USD, EUR and GBP only (two decimal places).')
    kind = field('document_type', 12)
    if kind not in ('INVOICE', 'CREDIT_NOTE'):
        raise ValueError('document_type must be INVOICE or CREDIT_NOTE. Use a positive credit-note amount.')
    text = raw.get('document_text', '')
    if not isinstance(text, str) or len(text) > 20000:
        raise ValueError('document_text must be text, up to 20,000 characters.')
    return dict(id=rid, supplier=supplier, supplier_id=ALIASES.get(name_key(supplier)), number=number,
                day=day, amount=str(amount.quantize(Decimal('0.01'))), currency=currency, kind=kind,
                digest=hashlib.sha256(text.encode()).hexdigest() if text else None)

def reasons(a, b):
    out = []
    # A byte-identical supplied text blob is useful even if metadata conflicts.
    if a['digest'] and a['digest'] == b['digest']:
        out.append('Identical supplied document text (SHA-256); verify original documents and metadata')
    if not a['supplier_id'] or a['supplier_id'] != b['supplier_id']:
        return out
    if a['currency'] != b['currency'] or a['kind'] != b['kind']:
        return out
    same_number = number_key(a['number']) == number_key(b['number'])
    same_value = a['amount'] == b['amount']
    days = abs((date.fromisoformat(a['day']) - date.fromisoformat(b['day'])).days)
    if same_number:
        out.append('Same verified supplier, document type, currency and normalized invoice number; amounts %s, dates %s' %
                   ('match' if same_value else 'differ', 'match' if days == 0 else 'differ'))
    elif same_value and days <= 7:
        out.append('Same verified supplier, document type, currency and amount within 7 days; invoice numbers differ (weak signal)')
    return out

def import_rows(db, raws):
    if not isinstance(raws, list) or not 1 <= len(raws) <= 200:
        raise ValueError('Import 1 to 200 invoices at a time.')
    rows = [validate(raw) for raw in raws]
    ids = [r['id'] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('Repeated record_id in this batch. No records imported.')
    for rid in ids:
        if db.execute('SELECT 1 FROM invoices WHERE id=?', (rid,)).fetchone():
            raise ValueError('record_id %s already exists. No records imported.' % rid)
    with db:
        for row in rows:
            existing = [dict(r) for r in db.execute('SELECT * FROM invoices ORDER BY created_at,id')]
            row['status'] = 'NEEDS_REVIEW' if not row['supplier_id'] else 'NO_CANDIDATE'
            matches = [(old['id'], reason) for old in existing for reason in reasons(row, old)]
            if matches:
                row['status'] = 'NEEDS_REVIEW'
            db.execute('''INSERT INTO invoices(id,supplier,supplier_id,number,day,amount,currency,kind,digest,status)
              VALUES(:id,:supplier,:supplier_id,:number,:day,:amount,:currency,:kind,:digest,:status)''', row)
            for other, reason in matches:
                db.execute('INSERT INTO candidates VALUES(?,?,?)', (row['id'], other, reason))
                # A new relation reopens both sides. Earlier decisions remain in the audit.
                db.execute("UPDATE invoices SET status='NEEDS_REVIEW' WHERE id IN (?,?)", (row['id'], other))
    return snapshot(db)

def review(db, rid, decision, reviewer, reason):
    if decision not in ('CONFIRMED_DUPLICATE', 'DISTINCT_DOCUMENT', 'NEED_MORE_INFO'):
        raise ValueError('Choose a supported review decision.')
    if not isinstance(reviewer, str) or not 1 <= len(reviewer.strip()) <= 100:
        raise ValueError('Reviewer name is required (max 100 characters).')
    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 1000:
        raise ValueError('A reason of 10 to 1000 characters is required.')
    row = db.execute('SELECT * FROM invoices WHERE id=?', (rid,)).fetchone()
    if row is None:
        raise ValueError('Invoice not found.')
    if row['status'] != 'NEEDS_REVIEW':
        raise ValueError('Only an item in NEEDS_REVIEW can receive a decision.')
    with db:
        db.execute('INSERT INTO decisions(invoice_id,decision,reviewer,reason) VALUES(?,?,?,?)',
                   (rid, decision, reviewer.strip(), reason.strip()))
        status = 'NEEDS_REVIEW' if decision == 'NEED_MORE_INFO' else decision
        db.execute('UPDATE invoices SET status=? WHERE id=?', (status, rid))
    return snapshot(db)

def snapshot(db):
    return { 'invoices': [dict(r) for r in db.execute('SELECT * FROM invoices ORDER BY created_at,id')],
             'candidates': [dict(r) for r in db.execute('SELECT * FROM candidates ORDER BY invoice_id,other_id,reason')],
             'decisions': [dict(r) for r in db.execute('SELECT * FROM decisions ORDER BY event_id')],
             'registry': ALIASES }

def parse_csv(text):
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or set(reader.fieldnames) != set(FIELDS) or len(reader.fieldnames) != len(FIELDS):
        raise ValueError('CSV headers must be exactly: ' + ','.join(FIELDS))
    rows = list(reader)
    if any(None in r or None in r.values() for r in rows):
        raise ValueError('CSV has missing or extra cells.')
    return rows

def extract_text(text):
    """Deliberately limited fixture parser. Not OCR or AI."""
    if not isinstance(text, str) or len(text) > 20000:
        raise ValueError('Use up to 20,000 characters of fixture text.')
    labels = {'Record ID': 'record_id', 'Supplier': 'supplier_name', 'Invoice Number': 'invoice_number',
              'Date': 'invoice_date', 'Amount': 'amount', 'Currency': 'currency', 'Type': 'document_type'}
    out = {}
    for line in text.splitlines():
        label, sep, value = line.partition(':')
        if sep and label.strip() in labels:
            key = labels[label.strip()]
            if key in out:
                raise ValueError('Repeated label: ' + label)
            out[key] = value.strip()
    missing = set(labels.values()) - set(out)
    if missing:
        raise ValueError('Missing fixture labels: ' + ', '.join(sorted(missing)))
    out['document_text'] = text
    validate(out)
    return out
