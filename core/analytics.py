"""Stateless bank statement parsing and financial analytics. No data is persisted."""
import io
import re
from collections import Counter
import numpy as np
import pandas as pd

CATEGORIES = {
    "Food delivery": [r"UBER\s*EATS", r"MR\s*D", r"PHIWO"],
    "Transport": [r"\bUBER\b", r"BOLT", r"GAUTRAIN", r"MYCITI"],
    "Groceries": [r"CHECKERS", r"SHOPRITE", r"PICK\s*N\s*PAY", r"PNP", r"WOOLWORTHS", r"SPAR"],
    "Restaurants": [r"KFC", r"MCDONALD", r"NANDO", r"STEERS", r"FISHER", r"WIMPY", r"DEBONAIRS"],
    "Utilities": [r"ELECTRICITY", r"WATER", r"ESKOM", r"PREPAID"],
    "Shopping": [r"TAKEALOT", r"AMAZON", r"SHEIN", r"TEMU", r"MR PRICE", r"ACKERMANS"],
    "Airtime & data": [r"AIRTIME", r"VODACOM", r"MTN", r"TELKOM", r"CELL C"],
    "Bank fees": [r"TRANSACTION CHARGE", r"BANK CHARGE", r"SERVICE FEE", r"MONTHLY FEE"],
    "Transfers": [r"PAYSHAP", r"TRANSFER", r"\bTRF\b", r"\bEFT\b"],
}

def normalize_merchant(description):
    s = str(description).upper().strip()
    s = re.sub(r"\b(?:CARD\s*(?:NO\.?|NUMBER)?|REF(?:ERENCE)?|ACCOUNT|ACCT)\s*[:.#-]?\s*[\w-]+", " ", s)
    s = re.sub(r"\b\d{5,}\b", " ", s)
    s = re.sub(r"\b(?:POS PURCHASE|DEBIT ORDER|PREPAID DEBIT|DIGITAL TRANSF DT|INETBNK TRF CREDIT|CREDIT|DEBIT|PURCHASE|PAYMENT|DL)\b", " ", s)
    s = re.sub(r"[^A-Z0-9 &]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if re.search(r"UBER\s*EATS", s): return "Uber Eats"
    if re.search(r"\bUBER\b", s): return "Uber"
    if "CHECKERS" in s: return "Checkers"
    if "KFC" in s: return "KFC"
    if "PAYSHAP" in s: return "PayShap"
    if "ELECTRICITY" in s: return "Electricity"
    if "TRANSACTION CHARGE" in s: return "Bank transaction fee"
    if "ABSA BANK TRANSFER" in s: return "ABSA bank transfer"
    if "REAL FISHER" in s: return "Real Fisher"
    if "PHIWO" in s: return "Phiwo"
    if "KEC PARADE" in s: return "KEC Parade"
    return (s[:48].title() if s else "Unknown")

def category_for(description):
    s = str(description).upper()
    for cat, patterns in CATEGORIES.items():
        if any(re.search(p, s) for p in patterns): return cat
    return "Other"

def parse_date(series):
    s = series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    compact = s.str.fullmatch(r"\d{8}")
    out = pd.to_datetime(s.where(compact), format="%Y%m%d", errors="coerce")
    rest = pd.to_datetime(s.where(~compact), errors="coerce", dayfirst=True)
    return out.fillna(rest)

def read_statement(file):
    data = file.getvalue() if hasattr(file, "getvalue") else file.read()
    last_error = None
    for encoding in ("utf-8-sig", "cp1252"):
        for skip in (0, 1, 2, 3, 4, 5):
            try:
                df = pd.read_csv(io.BytesIO(data), encoding=encoding, skiprows=skip, sep=None, engine="python", dtype=str)
                df.columns = [str(c).strip().lower().replace(" ", "") for c in df.columns]
                aliases = {"transactiondate": "date", "details": "description", "narrative": "description", "transactionamount": "amount", "runningbalance": "balance"}
                df = df.rename(columns=aliases)
                if {"date", "description", "amount"}.issubset(df.columns):
                    return clean_statement(df)
            except (UnicodeError, pd.errors.ParserError, ValueError) as exc:
                last_error = exc
    raise ValueError("Could not find Date, Description and Amount columns. Export a CSV with these headers.") from last_error

def clean_statement(df):
    df = df.copy()
    df["Date"] = parse_date(df["date"])
    for name in ("amount", "balance"):
        if name in df:
            value = df[name].astype(str).str.replace(r"[R,\s]", "", regex=True).str.replace("−", "-")
            value = value.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
            df[name.title()] = pd.to_numeric(value, errors="coerce")
        else:
            df[name.title()] = np.nan
    df["Description"] = df["description"].fillna("").astype(str).str.strip()
    df = df.dropna(subset=["Date", "Amount"])
    df = df[df["Description"].ne("")].copy()
    df["Merchant"] = df["Description"].map(normalize_merchant)
    df["Category"] = df["Description"].map(category_for)
    df["Type"] = np.where(df["Amount"] > 0, "Credit", np.where(df["Amount"] < 0, "Debit", "Zero"))
    # Preserve repeated legitimate transactions. Only remove exact rows repeated across uploaded files.
    df = df.drop_duplicates(subset=["Date", "Description", "Amount", "Balance"])
    labels = []
    for source in ("label", "category", "type", "transactiontype"):
        if source in df:
            column = f"Statement {source}"
            df[column] = df[source].fillna("").astype(str).str.strip()
            labels.append(column)
    return df[["Date", "Description", "Amount", "Balance", "Merchant", "Category", "Type", *labels]].sort_values("Date", kind="stable").reset_index(drop=True)

def payments_since(df, reference="muma", start=None):
    descriptions = df.Description.fillna("").str.replace(r"\s+", " ", regex=True).str.casefold()
    reference = " ".join(reference.split()).casefold()
    matches = descriptions.str.contains(r"(?<!\w)" + re.escape(reference) + r"(?!\w)", regex=True) if reference else pd.Series(False, index=df.index)
    if start is not None:
        matches &= df.Date.ge(pd.Timestamp(start))
    return df[matches].sort_values("Date", kind="stable").copy()

def savings_plan(df, categories, reduction=20):
    if not 0 <= reduction <= 100:
        raise ValueError("Reduction must be between 0 and 100 percent.")
    debits = df[(df.Amount < 0) & df.Category.isin(categories) & ~df.Category.eq("Transfers")].copy()
    debits["Spent (R)"] = -debits.Amount
    plan = debits.groupby(["Category", "Merchant"], as_index=False).agg(
        Transactions=("Amount", "size"), **{"Spent (R)": ("Spent (R)", "sum")}
    )
    plan["Target saving (R)"] = (plan["Spent (R)"] * reduction / 100).round(2)
    plan["Budget after cut (R)"] = plan["Spent (R)"] - plan["Target saving (R)"]
    return plan.sort_values("Target saving (R)", ascending=False).reset_index(drop=True)

def combine_statements(files):
    frames = [read_statement(f) for f in files]
    if not frames: return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    # Exact duplicates are ambiguous when a statement lacks unique transaction IDs.
    return combined.drop_duplicates(subset=["Date", "Description", "Amount", "Balance"]).sort_values("Date", kind="stable").reset_index(drop=True)

def recurring_transactions(df):
    """Find likely recurring debits with at least three occurrences and regular gaps."""
    debits = df[df.Amount < 0].copy()
    results = []
    for merchant, g in debits.groupby("Merchant"):
        dates = pd.Series(sorted(g.Date.dt.normalize().unique()))
        if len(dates) < 3: continue
        gaps = dates.diff().dropna().dt.days.to_numpy()
        if not len(gaps): continue
        median = float(np.median(gaps))
        cadence = None
        for label, low, high in (("Weekly", 5, 9), ("Fortnightly", 12, 17), ("Monthly", 25, 35)):
            if low <= median <= high and (np.abs(gaps - median) <= max(3, median * .22)).mean() >= .65:
                cadence = label
                break
        if cadence:
            amounts = -g.Amount
            results.append({"Merchant": merchant, "Frequency": cadence, "Transactions": len(g), "Typical amount (R)": round(float(amounts.median()), 2), "Last seen": g.Date.max().date(), "Consistency": round(float((np.abs(gaps - median) <= max(3, median * .22)).mean()) * 100)})
    return pd.DataFrame(results, columns=["Merchant", "Frequency", "Transactions", "Typical amount (R)", "Last seen", "Consistency"])

def anomalies(df):
    """Robust merchant-relative anomalies plus unusually large overall debits."""
    debit = df[df.Amount < 0].copy()
    debit["Spend"] = -debit.Amount
    if debit.empty: return debit.assign(Reason=pd.Series(dtype=str))
    overall_threshold = float(debit.Spend.quantile(.95)) if len(debit) >= 8 else float("inf")
    flags = []
    for merchant, group in debit.groupby("Merchant"):
        vals = group.Spend.to_numpy()
        med = np.median(vals)
        mad = np.median(np.abs(vals - med))
        for idx, row in group.iterrows():
            reasons = []
            if len(vals) >= 4 and mad > 0 and (row.Spend - med) / (1.4826 * mad) > 3.5:
                reasons.append("High compared with this merchant")
            if len(debit) >= 8 and row.Spend >= overall_threshold:
                reasons.append("Top 5% of debit amounts")
            if reasons: flags.append((idx, "; ".join(reasons)))
    if not flags: return debit.iloc[0:0].assign(Reason=pd.Series(dtype=str))
    indexes, reasons = zip(*flags)
    result = debit.loc[list(indexes)].copy()
    result["Reason"] = reasons
    return result.sort_values("Spend", ascending=False)

def insights(df):
    if df.empty: return []
    expenses = df[(df.Amount < 0) & (~df.Category.isin(["Transfers"]))].copy()
    if expenses.empty: return ["No categorised spending transactions in this selection."]
    lines = []
    merchants = expenses.groupby("Merchant").Amount.sum().abs().sort_values(ascending=False)
    lines.append(f"Largest spending merchant: {merchants.index[0]} (R {merchants.iloc[0]:,.2f}).")
    weekdays = expenses.groupby(expenses.Date.dt.day_name()).Amount.sum().abs().sort_values(ascending=False)
    lines.append(f"Highest total spending day of the week: {weekdays.index[0]} (R {weekdays.iloc[0]:,.2f} across the selected period).")
    monthly = expenses.groupby(expenses.Date.dt.to_period("M")).Amount.sum().abs()
    if len(monthly) >= 2 and monthly.iloc[-2] > 0:
        pct = (monthly.iloc[-1] / monthly.iloc[-2] - 1) * 100
        lines.append(f"Last calendar month's recorded spending was {abs(pct):.1f}% {'higher' if pct >= 0 else 'lower'} than the prior month. Partial months may distort comparisons.")
    recurring = recurring_transactions(df)
    if not recurring.empty: lines.append(f"Found {len(recurring)} merchant(s) with potentially recurring debit patterns.")
    return lines
