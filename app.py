from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
from core.analytics import combine_statements, recurring_transactions, anomalies, insights, payments_since, savings_plan

st.set_page_config(page_title="Pulse | Finance Intelligence", page_icon=":material/account_balance_wallet:", layout="wide")
pio.templates["pulse"] = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="#151F25", plot_bgcolor="#151F25",
        font=dict(family="Inter, sans-serif", color="#CFDCD9", size=12),
        colorway=["#69D6B5", "#8CB9DC", "#E4C58A", "#B2A1D9", "#F09894", "#7FC4CD"],
        title=dict(font=dict(size=17, color="#EAF1F0"), x=0.03),
        xaxis=dict(gridcolor="#25343A", zeroline=False, showline=False),
        yaxis=dict(gridcolor="#25343A", zeroline=False, showline=False),
        legend=dict(orientation="h", y=-0.22, title_text=""),
        margin=dict(l=20, r=20, t=60, b=35),
        hoverlabel=dict(bgcolor="#22343A", font_color="#EAF1F0"),
        barcornerradius=5,
    )
)
money_columns = {
    name: st.column_config.NumberColumn(format="R %.2f")
    for name in ("Amount", "Balance", "Spend", "Paid", "Received", "Spent (R)",
                 "Target saving (R)", "Budget after cut (R)", "Typical amount (R)")
}
st.caption("PULSE / PERSONAL FINANCE")
st.title("Your financial overview")
with st.sidebar:
    st.subheader(":material/account_balance_wallet: Pulse finance")
    st.header("Statements", icon=":material/upload_file:")
    uploads = st.file_uploader("Upload one or more CSV statements", type="csv", accept_multiple_files=True, help="CSV columns: Date, Description, Amount, optional Balance")
    st.caption(":material/lock: Session only · uploads are not saved. Download results to keep a copy.")
if not uploads:
    st.subheader("Bring your finances into focus", icon=":material/insert_chart:")
    st.write("Export your bank statement as CSV, then upload it in the sidebar. Upload overlapping months together to combine your history.")
    st.code("Date,Description,Amount,Balance\n20260717,POS PURCHASE DL UBER EATS CARD NO. 8584,-222.00,1015.53\n20260718,INETBNK TRF CREDIT ABSA BANK Transfer from 9367,100.00,1115.53", language="csv")
    st.stop()
try:
    df = combine_statements(uploads)
except Exception as e:
    st.error(f"Could not import CSV: {e}")
    st.stop()
if df.empty:
    st.warning("No valid transactions found.")
    st.stop()
with st.sidebar:
    st.header("Your selection", icon=":material/tune:")
    start, end = df.Date.min().date(), df.Date.max().date()
    period = st.date_input("Date range", (start, end), min_value=start, max_value=end)
    cats = st.multiselect("Categories", sorted(df.Category.unique()), default=sorted(df.Category.unique()))
    merchants = st.multiselect("Merchants", sorted(df.Merchant.unique()), default=[])
    search = st.text_input("Search description or merchant")
    exclude_transfers = st.checkbox("Exclude transfers from spending", value=True)
if not isinstance(period, (list, tuple)) or len(period) != 2:
    st.info("Select both dates in the date range.")
    st.stop()
filtered = df[df.Date.dt.date.between(period[0], period[1]) & df.Category.isin(cats)].copy()
if merchants: filtered = filtered[filtered.Merchant.isin(merchants)]
if search:
    filtered = filtered[filtered.Description.str.contains(search, case=False, regex=False) | filtered.Merchant.str.contains(search, case=False, regex=False)]
if filtered.empty:
    st.warning("No transactions match these filters. The payments tracker below still uses your full history.")
spend_df = filtered[(filtered.Amount < 0) & (~filtered.Category.eq("Transfers") if exclude_transfers else True)].copy()
spend_df["Spend"] = -spend_df.Amount
income = filtered.loc[filtered.Amount > 0, "Amount"].sum()
expenses = spend_df.Spend.sum()
last_balance = filtered.loc[filtered.Balance.notna(), "Balance"]
st.subheader("At a glance")
st.caption(f"{period[0]:%d %b %Y} — {period[1]:%d %b %Y} · {len(filtered):,} transactions · {len(uploads)} statement(s)")
c1,c2,c3 = st.columns(3)
c1.metric("Money in", f"R {income:,.2f}", border=True)
c2.metric("Money out", f"R {-filtered.Amount.clip(upper=0).sum():,.2f}", border=True)
c3.metric("Net cash flow", f"R {filtered.Amount.sum():,.2f}", border=True)
st.caption("Money in and out include transfers. Spending charts follow the transfer setting in the sidebar.")

def line_fig(data, x, y, title):
    fig = px.line(data, x=x, y=y, markers=True, title=title, template="pulse")
    fig.update_layout(margin=dict(l=10,r=10,t=55,b=10), height=370, hovermode="x unified")
    return fig

tabs = st.tabs([":material/dashboard: Overview", ":material/storefront: Merchants", ":material/event_repeat: Recurring", ":material/monitoring: Patterns", ":material/troubleshoot: Anomalies", ":material/receipt_long: All transactions", ":material/savings: Save money"])
with tabs[0]:
    if spend_df.empty:
        st.info("No spending in this selection.")
    else:
        catsum = spend_df.groupby("Category", as_index=False).Spend.sum().sort_values("Spend")
        fig = px.bar(catsum, x="Spend", y="Category", orientation="h", title="Where your money went", template="pulse", labels={"Spend": "Spent (R)", "Category": ""})
        fig.update_layout(height=370, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")
        largest = catsum.iloc[-1]
        st.write(f"**{largest.Category}** is your largest spending category: R {largest.Spend:,.2f} ({largest.Spend / expenses:.0%} of spending).")
        ideas = savings_plan(filtered, ["Food delivery", "Restaurants", "Shopping"], 20)
        if not ideas.empty:
            target = ideas.iloc[0]
            st.write(f"**Try this:** spend 20% less at {target.Merchant} to save R {target['Target saving (R)']:,.2f} over a similar period.")
with tabs[1]:
    st.subheader("Merchant spending")
    if spend_df.empty: st.info("No debits in the selection.")
    else:
        merchant_summary = spend_df.groupby("Merchant").agg(Total_spent=("Spend","sum"), Transactions=("Spend","size"), Average=("Spend","mean"), First_seen=("Date","min"), Last_seen=("Date","max")).sort_values("Total_spent", ascending=False)
        st.dataframe(merchant_summary, width="stretch")
        selected = st.selectbox("Inspect merchant", merchant_summary.index.tolist())
        history = filtered[filtered.Merchant.eq(selected)].sort_values("Date")
        st.plotly_chart(line_fig(history.assign(Spend=history.Amount.abs()), "Date", "Spend", f"{selected} transaction amounts"), width="stretch")
        st.dataframe(history, width="stretch", hide_index=True, column_config=money_columns)
with tabs[2]:
    st.subheader("Likely recurring transactions")
    st.caption("Regular payments seen on at least three dates. Confirm what each payment covers.")
    rec = recurring_transactions(filtered)
    if rec.empty: st.info("No regular payment patterns found. More history may help.")
    else: st.dataframe(rec, width="stretch", hide_index=True, column_config=money_columns)
with tabs[3]:
    st.subheader("Spending patterns")
    if spend_df.empty: st.info("No spending data.")
    else:
        a,b = st.columns(2)
        with a:
            daily_spend = spend_df.groupby("Date", as_index=False).Spend.sum()
            st.plotly_chart(line_fig(daily_spend, "Date", "Spend", "Daily spending"), width="stretch")
        with b:
            week = spend_df.assign(Weekday=spend_df.Date.dt.day_name()).groupby("Weekday", as_index=False).Spend.sum()
            order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
            fig = px.bar(week, x="Weekday", y="Spend", category_orders={"Weekday":order}, title="Spending by weekday", template="pulse")
            fig.update_layout(height=370)
            st.plotly_chart(fig, width="stretch")
        spend_df["Month"] = spend_df.Date.dt.strftime("%Y-%m")
        pivot = spend_df.pivot_table(index="Month", columns="Category", values="Spend", aggfunc="sum", fill_value=0)
        fig = px.bar(pivot, barmode="stack", title="Category trends by month", template="pulse")
        st.plotly_chart(fig, width="stretch")
        st.caption("Partial months and inconsistent statement coverage can make comparisons misleading.")
    st.subheader("Cash flow")
    daily = filtered.groupby("Date", as_index=False).Amount.sum()
    daily["Cumulative net flow"] = daily.Amount.cumsum()
    st.plotly_chart(line_fig(daily, "Date", "Cumulative net flow", "Cumulative net cash flow (R)"), width="stretch")
    month = filtered.assign(Month=filtered.Date.dt.strftime("%Y-%m"), Received=filtered.Amount.clip(lower=0), Paid=-filtered.Amount.clip(upper=0))
    monthly = month.groupby("Month", as_index=False)[["Received", "Paid"]].sum()
    st.dataframe(monthly, hide_index=True, column_config=money_columns, alt="Monthly money in and out including transfers")
    for item in insights(filtered):
        st.caption(item)
with tabs[4]:
    st.subheader("Unusual spending")
    st.caption("Unusually large payments to review. These are not fraud findings.")
    flagged = anomalies(filtered)
    if flagged.empty: st.success("No unusual transactions identified with the current rules.")
    else: st.dataframe(flagged[["Date","Merchant","Description","Spend","Reason"]], width="stretch", hide_index=True, column_config=money_columns)
with tabs[5]:
    st.subheader("Transaction explorer")
    st.caption(f"{len(filtered):,} matching entries" + (f" · Latest listed balance R {last_balance.iloc[-1]:,.2f}" if len(last_balance) else ""))
    st.dataframe(filtered.sort_values("Date", ascending=False), width="stretch", hide_index=True, column_config=money_columns)
    st.download_button("Download filtered CSV", filtered.to_csv(index=False).encode("utf-8"), "filtered_transactions.csv", "text/csv")
    st.download_button("Download enriched full CSV", df.to_csv(index=False).encode("utf-8"), "enriched_transactions.csv", "text/csv")
    st.caption("Merchant categories are heuristic. Review classifications before using totals for financial decisions. Identical same-day transactions can be ambiguous without bank transaction IDs.")
with tabs[6]:
    st.subheader("Find ways to save money")
    st.caption("Targets cover the selected period, not a monthly forecast.")
    debit_history = filtered[(filtered.Amount < 0) & ~filtered.Category.eq("Transfers")]
    if debit_history.empty:
        st.info("No spending to review in this selection. Widen the sidebar filters or upload more statements.")
    else:
        st.write("Choose a category you can cut back on, such as deliveries, eating out or optional shopping.")
        available = sorted(debit_history.Category.unique())
        flexible = [category for category in ("Food delivery", "Restaurants", "Shopping") if category in available]
        chosen = st.multiselect("Categories to reduce", available, default=flexible, key="savings_categories")
        reduction = st.slider("Spending reduction target (%)", 0, 100, 20, step=5, key="savings_reduction")
        plan = savings_plan(filtered, chosen, reduction)
        if plan.empty:
            st.info("Choose a spending category above to build a savings target.")
        else:
            saving, budget = st.columns(2)
            saving.metric("Potential saving for this period", f"R {plan['Target saving (R)'].sum():,.2f}", border=True)
            budget.metric("Budget after the cut", f"R {plan['Budget after cut (R)'].sum():,.2f}", border=True)
            st.caption("Estimated cuts to debits before refunds. Review categories and statement coverage before setting a budget.")
            st.dataframe(plan, hide_index=True, column_config=money_columns, alt="Spending and savings targets by merchant and category")
            merchant = st.selectbox("Review transactions before making a cut", plan.Merchant.unique(), key="savings_merchant")
            st.dataframe(debit_history[debit_history.Merchant.eq(merchant) & debit_history.Category.isin(chosen)], hide_index=True, column_config=money_columns, alt="Transactions behind the selected savings target")
            st.download_button("Download savings plan CSV", plan.to_csv(index=False).encode("utf-8"), "savings_plan.csv", "text/csv")
        st.subheader("Review recurring payments")
        recurring = recurring_transactions(debit_history)
        if recurring.empty:
            st.info("No regular payment patterns found. More history may help identify them.")
        else:
            st.write("Cancel services you no longer use or check for a cheaper plan. Confirm what each payment covers.")
            st.dataframe(recurring, hide_index=True, column_config=money_columns, alt="Recurring debit patterns to review for possible savings")
        fees = debit_history[debit_history.Category.eq("Bank fees")]
        if not fees.empty:
            st.subheader("Review bank fees")
            st.write(f"You paid R {-fees.Amount.sum():,.2f} in identified bank fees across {len(fees)} transactions in this period. Check which charges repeat and whether your account's fee structure suits your usage.")
            st.dataframe(fees, hide_index=True, column_config=money_columns, alt="Bank fee transactions in the selected period")
        st.caption("Recurring payments and bank fees are review prompts; they are not added to the savings target above.")

st.subheader("Payments tracker · Full history")
st.caption("All uploaded dates, independent of sidebar filters. Whole-word matching: muma excludes mumandafhadzi.")
reference = st.text_input("Payment description reference", value="muma", key="payment_reference_full_history")
payments = payments_since(df, reference)
if payments.empty:
    st.info("No descriptions match this reference in the uploaded history.")
else:
    st.write(f"{len(payments):,} payments · Paid R {-payments.Amount.clip(upper=0).sum():,.2f} · Received R {payments.Amount.clip(lower=0).sum():,.2f}")
    monthly_payments = payments.assign(Month=payments.Date.dt.strftime("%Y-%m"), Paid=-payments.Amount.clip(upper=0), Received=payments.Amount.clip(lower=0)).groupby("Month", as_index=False).agg(Transactions=("Amount", "size"), Paid=("Paid", "sum"), Received=("Received", "sum"))
    st.dataframe(monthly_payments, hide_index=True, column_config=money_columns, alt="Monthly totals for matching payments across the full history")
    st.dataframe(payments.sort_values("Date", ascending=False), hide_index=True, column_config=money_columns, alt="Matching payment descriptions across the full history")
    st.download_button("Download payments CSV", payments.to_csv(index=False).encode("utf-8"), "payments_full_history.csv", "text/csv")

st.html(Path(__file__).with_name("assets").joinpath("chart_animation.html").read_text(), unsafe_allow_javascript=True)
