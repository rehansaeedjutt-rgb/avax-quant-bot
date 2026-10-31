import pandas as pd

df = pd.read_csv("reports/final_decision_29_coins.csv")
df = df.sort_values("Return", ascending=False)

# 3-Tier structure
tier1 = ["MATIC","NEAR","LINK","LTC","ADA","AVAX","ETH","BNB","SOL","BTC"]
tier2 = ["DOT","HYPE","OP","APT","SUI","INJ","FET","GRT"]
tier3 = ["STX","RNDR","IMX","FIL","ICP"]
drop  = ["ATOM","ARB","SHIB","DOGE","XRP","BCH"]

portfolio = []
for i, coin in enumerate(tier1, 1):
    portfolio.append({"Coin":coin, "Tier":"Tier 1 (Core - Free)", "Rank":i})
for i, coin in enumerate(tier2, 1):
    portfolio.append({"Coin":coin, "Tier":"Tier 2 (VIP - Paid)", "Rank":i})
for i, coin in enumerate(tier3, 1):
    portfolio.append({"Coin":coin, "Tier":"Tier 3 (Watchlist)", "Rank":i})
for coin in drop:
    portfolio.append({"Coin":coin, "Tier":"DROP", "Rank":"-"})

pf = pd.DataFrame(portfolio)
pf.to_csv("reports/portfolio_structure_29_coins.csv", index=False)
print("Portfolio structure saved:")
print(pf.to_string(index=False))

# Attach tier to full results
df["Tier"] = df["Coin"].apply(lambda c: "Tier 1" if c in tier1 else "Tier 2" if c in tier2 else "Tier 3" if c in tier3 else "DROP")
df.to_csv("reports/final_decision_29_coins_with_tiers.csv", index=False)
print("\nFinal CSV saved with tiers.")
