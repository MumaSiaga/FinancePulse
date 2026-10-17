import io
from core.analytics import read_statement, normalize_merchant, recurring_transactions, payments_since, combine_statements, savings_plan

def test_csv():
    raw = b'Date,Description,Amount,Balance\n20260717,POS PURCHASE 12345678 DL Uber Eats CARD NO. 8584,-222.00,1015.53\n20260718,INETBNK TRF CREDIT ABSA BANK Transfer from 9367,100.00,1115.53\n'
    df = read_statement(io.BytesIO(raw))
    assert len(df) == 2
    assert df.iloc[0].Merchant == 'Uber Eats'
    assert df.iloc[0].Category == 'Food delivery'
    assert df.iloc[1].Amount == 100

def test_uber_separate():
    assert normalize_merchant('DL UBER CARD NO. 8584') == 'Uber'
    assert normalize_merchant('DL UBER EATS CARD NO. 8584') == 'Uber Eats'

def test_recurring():
    raw = b'Date,Description,Amount,Balance\n20260701,Netflix,-99,901\n20260801,Netflix,-99,802\n20260901,Netflix,-99,703\n'
    df = read_statement(io.BytesIO(raw))
    result = recurring_transactions(df)
    assert result.iloc[0].Frequency == 'Monthly'

def test_payment_reference_full_history():
    raw = b'Date,Description,Amount\n20260731,PayShap To ShapID REF: muma,-10\n20260801,PayShap To ShapID REF:  muma,-20\n20260902,PAYSHAP TO SHAPID REF: MUMA extra,-5\n20261001,PayShap To ShapID REF: other,-30\n20261002,PAYMENT,-40\n20261003,PayShap To ShapID REF: mumandafhadzi,-50\n20261004,REF: muma.,-60\n20261005,REF: amuma,-70\n'
    df = read_statement(io.BytesIO(raw))
    result = payments_since(df)
    assert result.Amount.tolist() == [-10, -20, -5, -60]
    assert payments_since(df, start="2026-08-01").Amount.tolist() == [-20, -5, -60]
    assert payments_since(df, "").empty
    assert payments_since(df, "PAYMENT").Amount.tolist() == [-40]


def test_labels_survive_mixed_uploads():
    labelled = io.BytesIO(b'Date,Description,Amount,Transaction Type\n20260801,Example,-20,Payments\n')
    unlabelled = io.BytesIO(b'Date,Description,Amount\n20260901,PAYMENT,-10\n')
    df = combine_statements([labelled, unlabelled])
    assert df['Statement transactiontype'].iloc[0] == 'Payments'

def test_savings_plan_uses_only_chosen_debits():
    raw = b'Date,Description,Amount\n20260701,UBER EATS,-100\n20260702,UBER EATS,-50\n20260703,UBER EATS,20\n20260704,KFC,-200\n20260705,PAYSHAP,-1000\n'
    df = read_statement(io.BytesIO(raw))
    plan = savings_plan(df, ['Food delivery', 'Transfers'], 20)
    assert len(plan) == 1
    assert plan.iloc[0]['Transactions'] == 2
    assert plan.iloc[0]['Spent (R)'] == 150
    assert plan.iloc[0]['Target saving (R)'] == 30
    assert plan.iloc[0]['Budget after cut (R)'] == 120
    assert savings_plan(df, []).empty
    assert savings_plan(df, ['Food delivery'], 0)['Target saving (R)'].sum() == 0
    assert savings_plan(df, ['Food delivery'], 100)['Budget after cut (R)'].sum() == 0
