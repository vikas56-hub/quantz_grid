import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np


def grid_bot_strategy(df, start_date, end_date, initial_price, lower_limit, upper_limit, grid_levels, initial_capital):
    # Filteration
    df['date'] = pd.to_datetime(df['date'])
    df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
    df = df[(df['close'] >= lower_limit) & (df['close'] <= upper_limit)]
    df = df.iloc[::-1]

    # Calculate the grid range and initial buy/sell levels
    grid_range = (upper_limit - lower_limit) / grid_levels
    buy_level = initial_price - grid_range
    sell_level = initial_price + grid_range
    trade_log = []
    total_pnl = 0
    quantity = 0
    open_positions = {}  # To track open positions

    print(f"Initial Buy Level: {buy_level}, Initial Sell Level: {sell_level}")
    print(f"Grid Range: {grid_range}")

# ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

# In this part , we are calculating buy/sell_level and appending trade log and open_positions to be closed in next itereation

    for i, row in df.iterrows():
        price = row['close']
        date = row['date']
        quantity = ((initial_capital / price) / (grid_levels/2))

        if price <= buy_level:
            trade_log.append({
                'Date': date,
                'Price': price,
                'B/S': 'Buy',
                'Buy_Level': buy_level,
                'Sell_Level': sell_level
            })
            open_positions[date] = {
                'Price': price,
                'B/S': 'Buy'
            }
            # Update levels
            sell_level = buy_level + grid_range
            buy_level = buy_level - grid_range

        elif price >= sell_level:
            trade_log.append({
                'Date': date,
                'Price': price,
                'B/S': 'Sell',
                'Buy_Level': buy_level,
                'Sell_Level': sell_level
            })
            open_positions[date] = {
                'Price': price,
                'B/S': 'Sell'
            }

            buy_level = sell_level - grid_range
            sell_level = sell_level + grid_range

#  /////////////////////////////////////////////////////////////////////////////////////////////////////////

# In this part , Match and close trades

    closed_trades = {}
    for trade in trade_log:
        date = trade['Date']
        price = trade['Price']
        bs = trade['B/S']
        if bs == 'Buy':
            for other_date, other_trade in open_positions.items():
                if other_trade['B/S'] == 'Sell' and abs(other_trade['Price'] - price) <= grid_range:
                    pnl = (price - other_trade['Price']) * quantity
                    closed_trades[other_date] = {
                        'Date': other_date,
                        'Price': other_trade['Price'],
                        'B/S': 'Sell',
                        'PNL': pnl
                    }
                    closed_trades[date] = {
                        'Date': date,
                        'Price': price,
                        'B/S': 'Buy',
                        'PNL': pnl
                    }
                    total_pnl += pnl
                    del open_positions[other_date]
                    break
        elif bs == 'Sell':
            for other_date, other_trade in open_positions.items():
                if other_trade['B/S'] == 'Buy' and abs(other_trade['Price'] - price) <= grid_range:
                    pnl = (other_trade['Price'] - price) * quantity
                    closed_trades[other_date] = {
                        'Date': other_date,
                        'Price': other_trade['Price'],
                        'B/S': 'Buy',
                        'PNL': pnl
                    }
                    closed_trades[date] = {
                        'Date': date,
                        'Price': price,
                        'B/S': 'Sell',
                        'PNL': pnl
                    }
                    total_pnl += pnl
                    del open_positions[other_date]
                    break

    # Convert trade log to DataFrame and include PNL calculations
    trade_log_df = pd.DataFrame(trade_log, columns=[
        'Date', 'Price', 'B/S', 'Buy_Level', 'Sell_Level'
    ])

    closed_trades_df = pd.DataFrame(list(closed_trades.values()), columns=[
        'Date', 'Price', 'B/S', 'PNL'
    ])

    return trade_log_df, closed_trades_df, total_pnl


df = pd.read_csv('BTC-2017min.csv')

trade_log_df, closed_trades_df, total_pnl = grid_bot_strategy(
    df,
    start_date='2017-10-01',
    end_date='2017-11-01',
    initial_price=4500,
    lower_limit=3000,
    upper_limit=6000,
    grid_levels=15,
    initial_capital=1000
)


# //////////////////////////////////////////////////////////////////////////////////////////////////////////////
# Data Plotting


# Plotting with dark theme and custom date format
plt.style.use('fast')
fig, ax = plt.subplots(figsize=(15, 8))
df_filtered = df[(df['date'] >= '2017-10-01') & (df['date'] <= '2017-11-01')]
ax.plot(df_filtered['date'], df_filtered['close'], label='Price', alpha=0.5)

# Plot buy and sell signals
buy_signals = trade_log_df[trade_log_df['B/S'] == 'Buy']
sell_signals = trade_log_df[trade_log_df['B/S'] == 'Sell']

ax.plot(buy_signals['Date'], buy_signals['Price'], '^',
        markersize=10, color='g', label='Buy Signal')
ax.plot(sell_signals['Date'], sell_signals['Price'], 'v',
        markersize=10, color='r', label='Sell Signal')

# Calculate grid range and plot grid lines
grid_range = (6000 - 3000) / 15
grid_levels = np.arange(3000, 6000, grid_range)
for level in grid_levels:
    ax.axhline(level, color='b', linestyle='--', alpha=0.5)

# Set date format for x-axis
date_form = mdates.DateFormatter("%m-%d")
ax.xaxis.set_major_formatter(date_form)
fig.autofmt_xdate()  # Rotate date labels for better readability

# Display total PNL on the chart
ax.text(df_filtered['date'].min(), df_filtered['close'].max(), f'Total PNL: {
        total_pnl:.2f}', ha='left', va='top', fontsize=14)

# Connect closed trades with dotted lines
for i in range(len(closed_trades_df) - 1):
    if closed_trades_df.iloc[i]['B/S'] == 'Buy' and closed_trades_df.iloc[i+1]['B/S'] == 'Sell':
        ax.plot([closed_trades_df.iloc[i]['Date'], closed_trades_df.iloc[i+1]['Date']],
                [closed_trades_df.iloc[i]['Price'],
                    closed_trades_df.iloc[i+1]['Price']],
                linestyle=':', color='red', alpha=0.5)

ax.set_title('Grid Trading Strategy')
ax.set_xlabel('Date')
ax.set_ylabel('Price')
# Ensure y-axis limits are within specified range, Change this too , if your'e changing U_level, and L_level
ax.set_ylim(3000, 6000)
ax.legend()
ax.grid()
plt.show()

print("Trade Log:")
print(trade_log_df)
print(f"Total PNL: {total_pnl}")
