import pandas as pd
df = pd.read_csv("reports/all_trades_detail.csv", parse_dates=["entry_date"])
df["year"] = df["entry_date"].dt.year
df["month"] = df["entry_date"].dt.month
# Per trade, if TP2 hit: profit_pct = 5% (but actual weighted: TP1 +2.5% and TP2 +5%, so total +7.5%? 
# Original backtest counts profit_pct as tp2_pct*100 = 5.0 only, not combined. So use profit_pct as-is.
pivot = df.pivot_table(index="year", columns="month", values="profit_pct", aggfunc="sum", fill_value=0)
pivot.columns = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
pivot["Year Total"] = pivot.sum(axis=1)
pivot["Trades"] = df.groupby("year").size()
print(pivot.round(2).to_string())
