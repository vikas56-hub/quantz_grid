import pandas as pd
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from tkcalendar import DateEntry
import ccxt


def grid_bot_strategy(df, start_date, end_date, initial_price, lower_limit, upper_limit,
                      grid_levels, initial_capital, leverage, lower_stop_loss, upper_stop_loss,
                      stop_loss_enabled):
    df['Open time'] = pd.to_datetime(df['Open time'])
    df = df[(df['Open time'] >= pd.to_datetime(start_date))
            & (df['Open time'] <= pd.to_datetime(end_date))]
    df = df.sort_values(by='Open time')

    grid_range = (upper_limit - lower_limit) / grid_levels
    buy_levels = [initial_price - i *
                  grid_range for i in range(1, grid_levels + 1)]
    sell_levels = [initial_price + i *
                   grid_range for i in range(1, grid_levels + 1)]

    trade_log = []
    total_pnl = 0
    total_cost = 0
    working_capital = initial_capital * leverage

    open_positions = []
    stop_loss_triggered = False
    stop_loss_trigger_date = None
    stop_loss_trigger_price = None
    mtm_value = 0

    for _, row in df.iterrows():
        price = row['Close']
        date = row['Open time']

        # Monitor stop-loss triggers
        if stop_loss_enabled:
            if price >= upper_stop_loss:
                stop_loss_triggered = True
                stop_loss_trigger_date = date
                stop_loss_trigger_price = price
                break  # Stop trading if upper stop-loss is hit

            if price <= lower_stop_loss:
                stop_loss_triggered = True
                stop_loss_trigger_date = date
                stop_loss_trigger_price = price
                break  # Stop trading if lower stop-loss is hit

        # Manage existing positions
        for pos in open_positions[:]:
            if pos['type'] == 'Buy' and price >= pos['target_sell_level']:
                pnl_current = (price - pos['price']) * pos['quantity']
                transaction_cost = 0.0003 * price * pos['quantity']
                total_pnl += pnl_current
                total_cost += transaction_cost
                working_capital += pnl_current
                trade_log.append([date, price, 'Sell (Closing)', pos['price'], pos['target_sell_level'],
                                  round(pnl_current, 3), pos['quantity'], round(transaction_cost, 3)])
                open_positions.remove(pos)

            elif pos['type'] == 'Sell' and price <= pos['target_buy_level']:
                pnl_current = (pos['price'] - price) * pos['quantity']
                transaction_cost = 0.0003 * price * pos['quantity']
                total_pnl += pnl_current
                total_cost += transaction_cost
                working_capital += pnl_current
                trade_log.append([date, price, 'Buy (Closing)', pos['target_buy_level'], pos['price'],
                                  round(pnl_current, 3), pos['quantity'], round(transaction_cost, 3)])
                open_positions.remove(pos)

        # Grid strategy logic (Buy/Sell levels management)
        eligible_buy_levels = [level for level in buy_levels if price <= level]
        eligible_sell_levels = [
            level for level in sell_levels if price >= level]

        if price < initial_price and eligible_buy_levels:
            for buy_level in eligible_buy_levels:
                if not any(p['price'] == buy_level for p in open_positions):
                    quantity = working_capital / price / (grid_levels / 2)
                    target_sell_level = buy_level + grid_range
                    transaction_cost = 0.0003 * price * quantity
                    total_cost += transaction_cost
                    open_positions.append({'type': 'Buy', 'price': buy_level, 'target_sell_level': target_sell_level,
                                           'quantity': round(quantity, 8)})
                    trade_log.append([date, price, 'Buy (Opening)', buy_level, target_sell_level, 0,
                                      round(quantity, 8), round(transaction_cost, 3)])

        elif price > initial_price and eligible_sell_levels:
            for sell_level in eligible_sell_levels:
                if not any(p['price'] == sell_level for p in open_positions):
                    quantity = working_capital / price / (grid_levels / 2)
                    target_buy_level = sell_level - grid_range
                    transaction_cost = 0.0003 * price * quantity
                    total_cost += transaction_cost
                    open_positions.append({'type': 'Sell', 'price': sell_level, 'target_buy_level': target_buy_level,
                                           'quantity': round(quantity, 8)})
                    trade_log.append([date, price, 'Sell (Opening)', target_buy_level, sell_level, 0,
                                      round(quantity, 8), round(transaction_cost, 3)])

    # Calculate MTM value
    if stop_loss_triggered:
        mtm_price = stop_loss_trigger_price
    elif not df.empty:
        mtm_price = df.iloc[-1]['Close']
    else:
        mtm_price = initial_price

    for pos in open_positions:
        if pos['type'] == 'Buy':
            mtm_value += (mtm_price - pos['price']) * pos['quantity']
        elif pos['type'] == 'Sell':
            mtm_value += (pos['price'] - mtm_price) * pos['quantity']

    total_mtm = total_pnl + mtm_value - total_cost
    roi = (total_mtm) / initial_capital * 100

    # Create DataFrame for the trade log
    trade_log_df = pd.DataFrame(trade_log, columns=['Date', 'Price', 'B/S', 'Entry_Level', 'Target_Level',
                                                    'PNL_Current', 'Quantity', 'Transaction_Cost'])
    trade_log_df.insert(0, 'Seq', range(1, len(trade_log_df) + 1))
    trade_log_df['Cumulative_PNL'] = trade_log_df['PNL_Current'].cumsum()
    trade_log_df['Cumulative_Cost'] = trade_log_df['Transaction_Cost'].cumsum()
    trade_log_df['Net_PNL'] = trade_log_df['Cumulative_PNL'] - \
        trade_log_df['Cumulative_Cost']

    return trade_log_df, total_pnl, mtm_value, total_mtm, total_cost, roi, len(open_positions), \
        stop_loss_triggered, stop_loss_trigger_date, stop_loss_trigger_price


class GridBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Grid Bot Strategy")
        self.root.geometry("1200x800")
        self.root.configure(bg='#2c3e50')

        title_font = ("Arial", 14, "bold")
        label_font = ("Arial", 12)
        self.summary_font = ("Arial", 12, "bold")
        entry_bg = "#1e272e"
        entry_fg = "#ecf0f1"
        entry_width = 10

        # Main frames for layout
        self.top_frame = tk.Frame(root, bg='#2c3e50')
        self.top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        self.summary_frame = tk.Frame(
            self.top_frame, bg='#2c3e50', bd=2, relief='ridge')
        self.summary_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.optimized_summary_frame = tk.Frame(
            self.top_frame, bg='#34495e', bd=2, relief='ridge')
        self.optimized_summary_frame.pack(
            side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.params_frame = tk.Frame(root, bg='#34495e', bd=2, relief='ridge')
        self.params_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        # Parameters Frame
        tk.Label(self.params_frame, text="Parameters", font=title_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=0, column=0, columnspan=5, pady=10)

        tk.Label(self.params_frame, text="Exchange:", font=label_font, fg="#ecf0f1",
                 bg="#34495e").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.exchange_entry = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.exchange_entry.insert(0, 'binance')
        self.exchange_entry.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(self.params_frame, text="Symbol:", font=label_font, fg="#ecf0f1",
                 bg="#34495e").grid(row=2, column=0, sticky='e', padx=5, pady=5)
        self.symbol_entry = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.symbol_entry.insert(0, 'BTC/USDT')
        self.symbol_entry.grid(row=2, column=1, padx=5, pady=5)

        tk.Label(self.params_frame, text="Time Frame:", font=label_font, fg="#ecf0f1",
                 bg="#34495e").grid(row=3, column=0, sticky='e', padx=5, pady=5)
        self.timeframe_entry = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.timeframe_entry.insert(0, '1h')
        self.timeframe_entry.grid(row=3, column=1, padx=5, pady=5)

        tk.Label(self.params_frame, text="Start Date:", font=label_font, fg="#ecf0f1",
                 bg="#34495e").grid(row=4, column=0, sticky='e', padx=5, pady=5)
        self.start_date = DateEntry(self.params_frame, date_pattern='yyyy-mm-dd',
                                    background=entry_bg, foreground=entry_fg, width=entry_width)
        self.start_date.grid(row=4, column=1, padx=5, pady=5)
        self.start_date.bind("<<DateEntrySelected>>",
                             self.update_initial_price)

        tk.Label(self.params_frame, text="End Date:", font=label_font, fg="#ecf0f1",
                 bg="#34495e").grid(row=5, column=0, sticky='e', padx=5, pady=5)
        self.end_date = DateEntry(self.params_frame, date_pattern='yyyy-mm-dd',
                                  background=entry_bg, foreground=entry_fg, width=entry_width)
        self.end_date.grid(row=5, column=1, padx=5, pady=5)

        # Initial Price Selection
        tk.Label(self.params_frame, text="Initial Price:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=6, column=0, sticky='e', padx=5, pady=5)
        self.initial_price_mode = tk.StringVar(value="absolute")
        self.initial_price_absolute = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.initial_price_absolute.grid(row=6, column=1, padx=5, pady=5)
        tk.Radiobutton(self.params_frame, text="Absolute", variable=self.initial_price_mode,
                       value="absolute", bg="#34495e", fg="#ecf0f1").grid(row=6, column=2, padx=5, pady=5)
        tk.Radiobutton(self.params_frame, text="First Value", variable=self.initial_price_mode,
                       value="first_value", bg="#34495e", fg="#ecf0f1").grid(row=6, column=3, padx=5, pady=5)

        # Lower Limit
        tk.Label(self.params_frame, text="Lower Limit:", font=label_font, fg="#ecf0f1",
                 bg="#34495e").grid(row=7, column=0, sticky='e', padx=5, pady=5)
        self.lower_limit_mode = tk.StringVar(value="absolute")
        self.lower_limit_absolute = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.lower_limit_absolute.grid(row=7, column=1, padx=5, pady=5)
        self.lower_limit_percentage = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.lower_limit_percentage.grid(row=7, column=2, padx=5, pady=5)
        tk.Radiobutton(self.params_frame, text="Absolute", variable=self.lower_limit_mode, value="absolute",
                       bg="#34495e", fg="#ecf0f1", command=self.update_limits).grid(row=7, column=3, padx=5, pady=5)
        tk.Radiobutton(self.params_frame, text="Percentage", variable=self.lower_limit_mode, value="percentage",
                       bg="#34495e", fg="#ecf0f1", command=self.update_limits).grid(row=7, column=4, padx=5, pady=5)

        # Upper Limit
        tk.Label(self.params_frame, text="Upper Limit:", font=label_font, fg="#ecf0f1",
                 bg="#34495e").grid(row=8, column=0, sticky='e', padx=5, pady=5)
        self.upper_limit_mode = tk.StringVar(value="absolute")
        self.upper_limit_absolute = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.upper_limit_absolute.grid(row=8, column=1, padx=5, pady=5)
        self.upper_limit_percentage = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.upper_limit_percentage.grid(row=8, column=2, padx=5, pady=5)
        tk.Radiobutton(self.params_frame, text="Absolute", variable=self.upper_limit_mode, value="absolute",
                       bg="#34495e", fg="#ecf0f1", command=self.update_limits).grid(row=8, column=3, padx=5, pady=5)
        tk.Radiobutton(self.params_frame, text="Percentage", variable=self.upper_limit_mode, value="percentage",
                       bg="#34495e", fg="#ecf0f1", command=self.update_limits).grid(row=8, column=4, padx=5, pady=5)

        # Lower Stop Loss
        tk.Label(self.params_frame, text="Lower Stop Loss:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=9, column=0, sticky='e', padx=5, pady=5)
        self.lower_stop_loss_mode = tk.StringVar(value="absolute")
        self.lower_stop_loss_absolute = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.lower_stop_loss_absolute.grid(row=9, column=1, padx=5, pady=5)
        self.lower_stop_loss_percentage = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.lower_stop_loss_percentage.grid(row=9, column=2, padx=5, pady=5)
        tk.Radiobutton(self.params_frame, text="Absolute", variable=self.lower_stop_loss_mode, value="absolute",
                       bg="#34495e", fg="#ecf0f1", command=self.update_limits).grid(row=9, column=3, padx=5, pady=5)
        tk.Radiobutton(self.params_frame, text="Percentage", variable=self.lower_stop_loss_mode, value="percentage",
                       bg="#34495e", fg="#ecf0f1", command=self.update_limits).grid(row=9, column=4, padx=5, pady=5)

        # Upper Stop Loss
        tk.Label(self.params_frame, text="Upper Stop Loss:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=10, column=0, sticky='e', padx=5, pady=5)
        self.upper_stop_loss_mode = tk.StringVar(value="absolute")
        self.upper_stop_loss_absolute = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.upper_stop_loss_absolute.grid(row=10, column=1, padx=5, pady=5)
        self.upper_stop_loss_percentage = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.upper_stop_loss_percentage.grid(row=10, column=2, padx=5, pady=5)
        tk.Radiobutton(self.params_frame, text="Absolute", variable=self.upper_stop_loss_mode, value="absolute",
                       bg="#34495e", fg="#ecf0f1", command=self.update_limits).grid(row=10, column=3, padx=5, pady=5)
        tk.Radiobutton(self.params_frame, text="Percentage", variable=self.upper_stop_loss_mode, value="percentage",
                       bg="#34495e", fg="#ecf0f1", command=self.update_limits).grid(row=10, column=4, padx=5, pady=5)

        # Stop Loss Enable/Disable
        tk.Label(self.params_frame, text="Stop Loss Enabled:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=11, column=0, sticky='e', padx=5, pady=5)
        self.stop_loss_enabled = tk.BooleanVar(value=True)
        self.stop_loss_enabled_checkbox = tk.Checkbutton(
            self.params_frame, variable=self.stop_loss_enabled, bg="#34495e")
        self.stop_loss_enabled_checkbox.grid(row=11, column=1, padx=5, pady=5)

        # Grid Levels
        tk.Label(self.params_frame, text="Grid Levels:", font=label_font, fg="#ecf0f1",
                 bg="#34495e").grid(row=12, column=0, sticky='e', padx=5, pady=5)
        self.grid_levels_mode = tk.StringVar(value="absolute")
        self.grid_levels_absolute = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.grid_levels_absolute.insert(0, '20')
        self.grid_levels_absolute.grid(row=12, column=1, padx=5, pady=5)
        self.grid_levels_percentage = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.grid_levels_percentage.grid(row=12, column=2, padx=5, pady=5)
        tk.Radiobutton(self.params_frame, text="Absolute", variable=self.grid_levels_mode, value="absolute",
                       bg="#34495e", fg="#ecf0f1", command=self.update_grid_levels).grid(row=12, column=3, padx=5, pady=5)
        tk.Radiobutton(self.params_frame, text="Percentage", variable=self.grid_levels_mode, value="percentage",
                       bg="#34495e", fg="#ecf0f1", command=self.update_grid_levels).grid(row=12, column=4, padx=5, pady=5)

        # Initial Capital
        tk.Label(self.params_frame, text="Initial Capital:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=13, column=0, sticky='e', padx=5, pady=5)
        self.initial_capital = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.initial_capital.insert(0, '10000')
        self.initial_capital.grid(row=13, column=1, padx=5, pady=5)

        # Leverage
        tk.Label(self.params_frame, text="Leverage:", font=label_font, fg="#ecf0f1",
                 bg="#34495e").grid(row=14, column=0, sticky='e', padx=5, pady=5)
        self.leverage = tk.Entry(
            self.params_frame, bg=entry_bg, fg=entry_fg, width=entry_width)
        self.leverage.insert(0, '10')
        self.leverage.grid(row=14, column=1, padx=5, pady=5)

        # Status Label
        self.status_label = tk.Label(
            root, text="", font=label_font, fg="#ecf0f1", bg="#2c3e50")
        self.status_label.pack(side=tk.TOP, pady=5)

        # Progress Bar
        self.progress_bar = ttk.Progressbar(
            root, mode='indeterminate', length=400)
        self.progress_bar.pack(side=tk.TOP, pady=5)

        # Execution Buttons
        self.run_button = tk.Button(root, text="Run Strategy", command=self.run_strategy, bg="#27ae60", fg="#ecf0f1", font=(
            "Arial", 12, "bold"), bd=2, relief='raised', padx=10, pady=5)
        self.run_button.pack(side=tk.TOP, pady=20)

        self.optimize_button = tk.Button(root, text="Optimize", command=self.optimize_strategy, bg="#e74c3c", fg="#ecf0f1", font=(
            "Arial", 12, "bold"), bd=2, relief='raised', padx=10, pady=5)
        self.optimize_button.pack(side=tk.TOP, pady=20)

        # Summary Labels
        self.summary_label = tk.Label(self.summary_frame, text="Summary", font=(
            "Arial", 16, "bold"), fg="#ecf0f1", bg="#2c3e50")
        self.summary_label.grid(row=0, column=0, columnspan=2, pady=10)

        tk.Label(self.summary_frame, text="Total Current PNL:", font=label_font,
                 fg="#ecf0f1", bg="#2c3e50").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.total_pnl_label = tk.Label(
            self.summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#2c3e50")
        self.total_pnl_label.grid(row=1, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.summary_frame, text="MTM Value of Open Positions:", font=label_font,
                 fg="#ecf0f1", bg="#2c3e50").grid(row=2, column=0, sticky='e', padx=5, pady=5)
        self.mtm_value_label = tk.Label(
            self.summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#2c3e50")
        self.mtm_value_label.grid(row=2, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.summary_frame, text="Number of Total Trades:", font=label_font,
                 fg="#ecf0f1", bg="#2c3e50").grid(row=3, column=0, sticky='e', padx=5, pady=5)
        self.total_trades_label = tk.Label(
            self.summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#2c3e50")
        self.total_trades_label.grid(
            row=3, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.summary_frame, text="Open Trades:", font=label_font,
                 fg="#ecf0f1", bg="#2c3e50").grid(row=4, column=0, sticky='e', padx=5, pady=5)
        self.open_trades_label = tk.Label(
            self.summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#2c3e50")
        self.open_trades_label.grid(
            row=4, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.summary_frame, text="Total Transaction Costs:", font=label_font,
                 fg="#ecf0f1", bg="#2c3e50").grid(row=5, column=0, sticky='e', padx=5, pady=5)
        self.total_cost_label = tk.Label(
            self.summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#2c3e50")
        self.total_cost_label.grid(row=5, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.summary_frame, text="Net PNL After Costs:", font=label_font,
                 fg="#ecf0f1", bg="#2c3e50").grid(row=6, column=0, sticky='e', padx=5, pady=5)
        self.net_pnl_label = tk.Label(
            self.summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#2c3e50")
        self.net_pnl_label.grid(row=6, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.summary_frame, text="ROI:", font=label_font, fg="#ecf0f1",
                 bg="#2c3e50").grid(row=7, column=0, sticky='e', padx=5, pady=5)
        self.roi_label = tk.Label(
            self.summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#2c3e50")
        self.roi_label.grid(row=7, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.summary_frame, text="Stop Loss Triggered:", font=label_font,
                 fg="#ecf0f1", bg="#2c3e50").grid(row=8, column=0, sticky='e', padx=5, pady=5)
        self.stop_loss_triggered_label = tk.Label(
            self.summary_frame, text="No", font=self.summary_font, fg="#ecf0f1", bg="#2c3e50")
        self.stop_loss_triggered_label.grid(
            row=8, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.summary_frame, text="SL Trigger Date:", font=label_font,
                 fg="#ecf0f1", bg="#2c3e50").grid(row=9, column=0, sticky='e', padx=5, pady=5)
        self.stop_loss_trigger_date_label = tk.Label(
            self.summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#2c3e50")
        self.stop_loss_trigger_date_label.grid(
            row=9, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.summary_frame, text="SL Trigger Price:", font=label_font,
                 fg="#ecf0f1", bg="#2c3e50").grid(row=10, column=0, sticky='e', padx=5, pady=5)
        self.stop_loss_trigger_price_label = tk.Label(
            self.summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#2c3e50")
        self.stop_loss_trigger_price_label.grid(
            row=10, column=1, sticky='w', padx=5, pady=5)

        # Optimized Summary Labels
        self.optimized_summary_label = tk.Label(self.optimized_summary_frame, text="Optimized Summary", font=(
            "Arial", 16, "bold"), fg="#ecf0f1", bg="#34495e")
        self.optimized_summary_label.grid(
            row=0, column=0, columnspan=2, pady=10)

        tk.Label(self.optimized_summary_frame, text="Best Grid Levels:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.optimized_grid_levels_label = tk.Label(
            self.optimized_summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#34495e")
        self.optimized_grid_levels_label.grid(
            row=1, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.optimized_summary_frame, text="Total Current PNL:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=2, column=0, sticky='e', padx=5, pady=5)
        self.optimized_total_pnl_label = tk.Label(
            self.optimized_summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#34495e")
        self.optimized_total_pnl_label.grid(
            row=2, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.optimized_summary_frame, text="MTM Value of Open Positions:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=3, column=0, sticky='e', padx=5, pady=5)
        self.optimized_mtm_value_label = tk.Label(
            self.optimized_summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#34495e")
        self.optimized_mtm_value_label.grid(
            row=3, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.optimized_summary_frame, text="Number of Total Trades:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=4, column=0, sticky='e', padx=5, pady=5)
        self.optimized_total_trades_label = tk.Label(
            self.optimized_summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#34495e")
        self.optimized_total_trades_label.grid(
            row=4, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.optimized_summary_frame, text="Open Trades:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=5, column=0, sticky='e', padx=5, pady=5)
        self.optimized_open_trades_label = tk.Label(
            self.optimized_summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#34495e")
        self.optimized_open_trades_label.grid(
            row=5, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.optimized_summary_frame, text="Total Transaction Costs:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=6, column=0, sticky='e', padx=5, pady=5)
        self.optimized_total_cost_label = tk.Label(
            self.optimized_summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#34495e")
        self.optimized_total_cost_label.grid(
            row=6, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.optimized_summary_frame, text="Net PNL After Costs:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=7, column=0, sticky='e', padx=5, pady=5)
        self.optimized_net_pnl_label = tk.Label(
            self.optimized_summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#34495e")
        self.optimized_net_pnl_label.grid(
            row=7, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.optimized_summary_frame, text="ROI:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=8, column=0, sticky='e', padx=5, pady=5)
        self.optimized_roi_label = tk.Label(
            self.optimized_summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#34495e")
        self.optimized_roi_label.grid(
            row=8, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.optimized_summary_frame, text="Stop Loss Triggered:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=9, column=0, sticky='e', padx=5, pady=5)
        self.optimized_stop_loss_triggered_label = tk.Label(
            self.optimized_summary_frame, text="No", font=self.summary_font, fg="#ecf0f1", bg="#34495e")
        self.optimized_stop_loss_triggered_label.grid(
            row=9, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.optimized_summary_frame, text="SL Trigger Date:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=10, column=0, sticky='e', padx=5, pady=5)
        self.optimized_stop_loss_trigger_date_label = tk.Label(
            self.optimized_summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#34495e")
        self.optimized_stop_loss_trigger_date_label.grid(
            row=10, column=1, sticky='w', padx=5, pady=5)

        tk.Label(self.optimized_summary_frame, text="SL Trigger Price:", font=label_font,
                 fg="#ecf0f1", bg="#34495e").grid(row=11, column=0, sticky='e', padx=5, pady=5)
        self.optimized_stop_loss_trigger_price_label = tk.Label(
            self.optimized_summary_frame, text="", font=self.summary_font, fg="#ecf0f1", bg="#34495e")
        self.optimized_stop_loss_trigger_price_label.grid(
            row=11, column=1, sticky='w', padx=5, pady=5)

        # Add a Notebook widget to create tabs for trade logs
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH,
                           expand=True, padx=10, pady=10)

        # Create Frames for each tab
        self.default_log_frame = tk.Frame(
            self.notebook, bg='#34495e', bd=2, relief='ridge')
        self.optimized_log_frame = tk.Frame(
            self.notebook, bg='#34495e', bd=2, relief='ridge')

        # Add tabs to the notebook
        self.notebook.add(self.default_log_frame, text="Default Trade Logs")
        self.notebook.add(self.optimized_log_frame,
                          text="Optimized Trade Logs")

        # Default Trade Log Frame (ttk.Treeview)
        columns = ['Seq', 'Date', 'Price', 'B/S', 'Entry_Level', 'Target_Level',
                   'PNL_Current', 'Quantity', 'Transaction_Cost', 'Net_PNL']

        self.trade_log_tree_default = ttk.Treeview(
            self.default_log_frame, columns=columns, show='headings', height=15)
        self.trade_log_tree_default.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True)

        for col in columns:
            self.trade_log_tree_default.heading(col, text=col)
            self.trade_log_tree_default.column(col, anchor='center', width=90)

        self.scrollbar_default = tk.Scrollbar(
            self.default_log_frame, orient=tk.VERTICAL, command=self.trade_log_tree_default.yview)
        self.trade_log_tree_default.configure(
            yscrollcommand=self.scrollbar_default.set)
        self.scrollbar_default.pack(side=tk.RIGHT, fill=tk.Y)

        # Optimized Trade Log Frame (ttk.Treeview)
        self.trade_log_tree_optimized = ttk.Treeview(
            self.optimized_log_frame, columns=columns, show='headings', height=15)
        self.trade_log_tree_optimized.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True)

        for col in columns:
            self.trade_log_tree_optimized.heading(col, text=col)
            self.trade_log_tree_optimized.column(
                col, anchor='center', width=90)

        self.scrollbar_optimized = tk.Scrollbar(
            self.optimized_log_frame, orient=tk.VERTICAL, command=self.trade_log_tree_optimized.yview)
        self.trade_log_tree_optimized.configure(
            yscrollcommand=self.scrollbar_optimized.set)
        self.scrollbar_optimized.pack(side=tk.RIGHT, fill=tk.Y)

    def update_initial_price(self, event=None):
        try:
            exchange_name = self.exchange_entry.get()
            symbol = self.symbol_entry.get()
            timeframe = self.timeframe_entry.get()
            start_date = self.start_date.get()
            exchange_class = getattr(ccxt, exchange_name)()
            start_timestamp = int(pd.to_datetime(
                start_date).timestamp() * 1000)
            ohlcv = exchange_class.fetch_ohlcv(
                symbol, timeframe, since=start_timestamp, limit=1)
            if ohlcv:
                initial_price = ohlcv[0][4]  # Close price
                self.initial_price_absolute.delete(0, tk.END)
                self.initial_price_absolute.insert(0, f"{initial_price:.2f}")
                self.status_label.config(
                    text="Initial Price Fetched", fg="#2ecc71")
            else:
                self.initial_price_absolute.delete(0, tk.END)
                self.initial_price_absolute.insert(0, "N/A")
                self.status_label.config(
                    text="No data available for the selected start date", fg="#e74c3c")
        except Exception as e:
            self.status_label.config(text=str(e), fg="#e74c3c")

    def update_limits(self):
        try:
            initial_price = float(self.initial_price_absolute.get())

            if self.lower_limit_mode.get() == "absolute":
                lower_limit = float(self.lower_limit_absolute.get())
                percentage = (initial_price - lower_limit) / \
                    initial_price * 100
                self.lower_limit_percentage.delete(0, tk.END)
                self.lower_limit_percentage.insert(0, f"{percentage:.2f}%")
            else:
                percentage = float(
                    self.lower_limit_percentage.get().strip('%'))
                lower_limit = initial_price * (1 - percentage / 100)
                self.lower_limit_absolute.delete(0, tk.END)
                self.lower_limit_absolute.insert(0, f"{lower_limit:.2f}")

            if self.upper_limit_mode.get() == "absolute":
                upper_limit = float(self.upper_limit_absolute.get())
                percentage = (upper_limit - initial_price) / \
                    initial_price * 100
                self.upper_limit_percentage.delete(0, tk.END)
                self.upper_limit_percentage.insert(0, f"{percentage:.2f}%")
            else:
                percentage = float(
                    self.upper_limit_percentage.get().strip('%'))
                upper_limit = initial_price * (1 + percentage / 100)
                self.upper_limit_absolute.delete(0, tk.END)
                self.upper_limit_absolute.insert(0, f"{upper_limit:.2f}")

            if self.lower_stop_loss_mode.get() == "absolute":
                lower_stop_loss = float(self.lower_stop_loss_absolute.get())
                percentage = (initial_price - lower_stop_loss) / \
                    initial_price * 100
                self.lower_stop_loss_percentage.delete(0, tk.END)
                self.lower_stop_loss_percentage.insert(0, f"{percentage:.2f}%")
            else:
                percentage = float(
                    self.lower_stop_loss_percentage.get().strip('%'))
                lower_stop_loss = initial_price * (1 - percentage / 100)
                self.lower_stop_loss_absolute.delete(0, tk.END)
                self.lower_stop_loss_absolute.insert(
                    0, f"{lower_stop_loss:.2f}")

            if self.upper_stop_loss_mode.get() == "absolute":
                upper_stop_loss = float(self.upper_stop_loss_absolute.get())
                percentage = (upper_stop_loss - initial_price) / \
                    initial_price * 100
                self.upper_stop_loss_percentage.delete(0, tk.END)
                self.upper_stop_loss_percentage.insert(0, f"{percentage:.2f}%")
            else:
                percentage = float(
                    self.upper_stop_loss_percentage.get().strip('%'))
                upper_stop_loss = initial_price * (1 + percentage / 100)
                self.upper_stop_loss_absolute.delete(0, tk.END)
                self.upper_stop_loss_absolute.insert(
                    0, f"{upper_stop_loss:.2f}")

        except ValueError:
            pass

    def update_grid_levels(self):
        try:
            initial_price = float(self.initial_price_absolute.get())

            if self.grid_levels_mode.get() == "absolute":
                grid_levels = int(self.grid_levels_absolute.get())
                grid_range = (float(self.upper_limit_absolute.get()) -
                              float(self.lower_limit_absolute.get())) / grid_levels
                percentage = grid_range / initial_price * 100
                self.grid_levels_percentage.delete(0, tk.END)
                self.grid_levels_percentage.insert(0, f"{percentage:.2f}%")
            else:
                percentage = float(
                    self.grid_levels_percentage.get().strip('%'))
                grid_range = initial_price * (percentage / 100)
                grid_levels = int((float(self.upper_limit_absolute.get(
                )) - float(self.lower_limit_absolute.get())) / grid_range)
                self.grid_levels_absolute.delete(0, tk.END)
                self.grid_levels_absolute.insert(0, f"{grid_levels}")

        except ValueError:
            pass

    def fetch_data(self):
        exchange_name = self.exchange_entry.get()
        symbol = self.symbol_entry.get()
        timeframe = self.timeframe_entry.get()
        start_date = self.start_date.get()
        end_date = self.end_date.get()
        start_timestamp = int(pd.to_datetime(start_date).timestamp() * 1000)
        end_timestamp = int(pd.to_datetime(end_date).timestamp() * 1000)
        exchange_class = getattr(ccxt, exchange_name)()
        since = start_timestamp
        all_ohlcv = []
        while since < end_timestamp:
            try:
                ohlcv = exchange_class.fetch_ohlcv(
                    symbol, timeframe, since=since, limit=1000)
                if not ohlcv:
                    break
                last_timestamp = ohlcv[-1][0]
                if last_timestamp == since:
                    break
                since = last_timestamp + 1
                all_ohlcv.extend(ohlcv)
            except Exception as e:
                break  # Handle exceptions
        df = pd.DataFrame(all_ohlcv, columns=[
                          'Open time', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df['Open time'] = pd.to_datetime(df['Open time'], unit='ms')
        df = df[(df['Open time'] >= pd.to_datetime(start_date))
                & (df['Open time'] <= pd.to_datetime(end_date))]
        return df

    def run_strategy(self):
        self.status_label.config(text="Running Strategy...", fg="#f39c12")
        self.progress_bar.start()
        try:
            self.df = self.fetch_data()  # Store data in self.df for later use

            # Determine initial price
            if self.initial_price_mode.get() == "absolute":
                initial_price = float(self.initial_price_absolute.get())
            else:
                df_on_start_date = self.df[self.df['Open time'].dt.date == pd.to_datetime(
                    self.start_date.get()).date()]
                if df_on_start_date.empty:
                    raise ValueError(f"No data available for the selected start date: {
                                     self.start_date.get()}")
                initial_price = df_on_start_date['Close'].iloc[0]

            # Determine lower limit
            if self.lower_limit_mode.get() == "absolute":
                lower_limit = float(self.lower_limit_absolute.get())
            else:
                lower_limit = initial_price * \
                    (1 - float(self.lower_limit_percentage.get().strip('%')) / 100)

            # Determine upper limit
            if self.upper_limit_mode.get() == "absolute":
                upper_limit = float(self.upper_limit_absolute.get())
            else:
                upper_limit = initial_price * \
                    (1 + float(self.upper_limit_percentage.get().strip('%')) / 100)

            # Determine lower stop loss
            if self.lower_stop_loss_mode.get() == "absolute":
                lower_stop_loss = float(self.lower_stop_loss_absolute.get())
            else:
                lower_stop_loss = initial_price * \
                    (1 - float(self.lower_stop_loss_percentage.get().strip('%')) / 100)

            # Determine upper stop loss
            if self.upper_stop_loss_mode.get() == "absolute":
                upper_stop_loss = float(self.upper_stop_loss_absolute.get())
            else:
                upper_stop_loss = initial_price * \
                    (1 + float(self.upper_stop_loss_percentage.get().strip('%')) / 100)

            # Determine grid levels
            if self.grid_levels_mode.get() == "absolute":
                grid_levels = int(self.grid_levels_absolute.get())
            else:
                grid_levels = round((upper_limit - lower_limit) / (
                    initial_price * float(self.grid_levels_percentage.get().strip('%')) / 100))

            # Filter the data and run the strategy
            df = self.df[(self.df['Open time'] >= pd.to_datetime(self.start_date.get())) & (
                self.df['Open time'] <= pd.to_datetime(self.end_date.get()))]
            df = df[(df['Close'] >= lower_limit) &
                    (df['Close'] <= upper_limit)]

            if df.empty:
                raise ValueError(
                    "No data available for the given parameters after filtering. Adjust your limits or date range.")

            # Run the strategy
            self.trade_log_df_default, total_current_pnl, mtm_value, total_mtm, total_cost, roi, open_trades, \
                stop_loss_triggered, stop_loss_trigger_date, stop_loss_trigger_price = grid_bot_strategy(
                    df,
                    start_date=self.start_date.get(),
                    end_date=self.end_date.get(),
                    initial_price=initial_price,
                    lower_limit=lower_limit,
                    upper_limit=upper_limit,
                    grid_levels=grid_levels,
                    initial_capital=float(self.initial_capital.get()),
                    leverage=float(self.leverage.get()),
                    lower_stop_loss=lower_stop_loss,
                    upper_stop_loss=upper_stop_loss,
                    stop_loss_enabled=self.stop_loss_enabled.get()
                )

            # Store default results for comparison
            self.default_results = {
                'total_current_pnl': total_current_pnl,
                'mtm_value': mtm_value,
                'total_mtm': total_mtm,
                'total_cost': total_cost,
                'roi': roi,
                'open_trades': open_trades,
                'stop_loss_triggered': stop_loss_triggered,
                'stop_loss_trigger_date': stop_loss_trigger_date,
                'stop_loss_trigger_price': stop_loss_trigger_price,
                'trade_log_df': self.trade_log_df_default
            }

            # Update the summary
            self.total_pnl_label.config(text=f"{total_current_pnl:.3f}")
            self.mtm_value_label.config(text=f"{mtm_value:.3f}")
            self.total_trades_label.config(
                text=f"{len(self.trade_log_df_default)}")
            self.open_trades_label.config(text=f"{open_trades}")
            self.total_cost_label.config(text=f"{total_cost:.3f}")
            self.net_pnl_label.config(text=f"{total_mtm:.3f}")
            self.roi_label.config(text=f"{roi:.2f}%")

            if stop_loss_triggered:
                self.stop_loss_triggered_label.config(text="Yes", fg="#e74c3c")
                self.stop_loss_trigger_date_label.config(
                    text=stop_loss_trigger_date)
                self.stop_loss_trigger_price_label.config(
                    text=f"{stop_loss_trigger_price:.2f}")
            else:
                self.stop_loss_triggered_label.config(text="No", fg="#2ecc71")
                self.stop_loss_trigger_date_label.config(text="")
                self.stop_loss_trigger_price_label.config(text="")

            # Clear the Treeview before inserting new logs
            for item in self.trade_log_tree_default.get_children():
                self.trade_log_tree_default.delete(item)

            # Insert the trade log data into the Treeview
            for _, row in self.trade_log_df_default.iterrows():
                self.trade_log_tree_default.insert("", "end", values=list(row))

            self.status_label.config(text="Strategy Completed", fg="#2ecc71")

        except ValueError as ve:
            messagebox.showerror("Error", str(ve))
            self.status_label.config(
                text="Error running strategy", fg="#e74c3c")
        finally:
            self.progress_bar.stop()

    def optimize_strategy(self):
        self.status_label.config(text="Optimizing Strategy...", fg="#f39c12")
        self.progress_bar.start()

        try:
            # Ensure that the default data is available
            if not hasattr(self, 'df'):
                self.df = self.fetch_data()

            initial_price = float(self.initial_price_absolute.get())

            # Determine lower and upper limits
            if self.lower_limit_mode.get() == "absolute":
                lower_limit = float(self.lower_limit_absolute.get())
            else:
                lower_limit = initial_price * \
                    (1 - float(self.lower_limit_percentage.get().strip('%')) / 100)

            if self.upper_limit_mode.get() == "absolute":
                upper_limit = float(self.upper_limit_absolute.get())
            else:
                upper_limit = initial_price * \
                    (1 + float(self.upper_limit_percentage.get().strip('%')) / 100)

            # Fixed parameters for optimization
            initial_capital = float(self.initial_capital.get())
            leverage = float(self.leverage.get())
            lower_stop_loss = float(self.lower_stop_loss_absolute.get())
            upper_stop_loss = float(self.upper_stop_loss_absolute.get())
            stop_loss_enabled = self.stop_loss_enabled.get()

            # Variables to store the best results
            best_grid_levels = 0
            best_pnl = -float('inf')
            best_trade_log_df = None
            best_roi = 0
            best_total_current_pnl = 0
            best_mtm_value = 0
            best_total_cost = 0
            best_open_trades = 0
            best_stop_loss_triggered = False
            best_stop_loss_trigger_date = None
            best_stop_loss_trigger_price = None

            # Range of grid levels to test
            # Grid levels from 20 to 80 in intervals of 10
            grid_levels_list = [20, 30, 40, 50, 60, 70, 80]

            # Filter the data based on the date range and price limits
            df_filtered = self.df[(self.df['Open time'] >= pd.to_datetime(self.start_date.get())) & (
                self.df['Open time'] <= pd.to_datetime(self.end_date.get()))]
            df_filtered = df_filtered[(df_filtered['Close'] >= lower_limit) & (
                df_filtered['Close'] <= upper_limit)]

            if df_filtered.empty:
                raise ValueError(
                    "No data available for the given parameters after filtering. Adjust your limits or date range.")

            for grid_levels in grid_levels_list:
                # Run strategy with current grid levels
                trade_log_df, total_current_pnl, mtm_value, total_mtm, total_cost, roi, open_trades, \
                    stop_loss_triggered, stop_loss_trigger_date, stop_loss_trigger_price = grid_bot_strategy(
                        df_filtered,
                        start_date=self.start_date.get(),
                        end_date=self.end_date.get(),
                        initial_price=initial_price,
                        lower_limit=lower_limit,
                        upper_limit=upper_limit,
                        grid_levels=grid_levels,
                        initial_capital=initial_capital,
                        leverage=leverage,
                        lower_stop_loss=lower_stop_loss,
                        upper_stop_loss=upper_stop_loss,
                        stop_loss_enabled=stop_loss_enabled
                    )

                pnl = total_mtm

                # Check if this is the best result
                if pnl > best_pnl:
                    best_pnl = pnl
                    best_grid_levels = grid_levels
                    best_trade_log_df = trade_log_df.copy()
                    best_roi = roi
                    best_total_current_pnl = total_current_pnl
                    best_mtm_value = mtm_value
                    best_total_cost = total_cost
                    best_open_trades = open_trades
                    best_stop_loss_triggered = stop_loss_triggered
                    best_stop_loss_trigger_date = stop_loss_trigger_date
                    best_stop_loss_trigger_price = stop_loss_trigger_price

            # Ensure optimized result is better than or equal to default
            if not hasattr(self, 'default_results'):
                messagebox.showerror(
                    "Error", "Please run the default strategy first.")
                return

            if best_pnl < self.default_results['total_mtm']:
                # If optimized result is worse, use default
                best_pnl = self.default_results['total_mtm']
                best_grid_levels = int(self.grid_levels_absolute.get())
                best_trade_log_df = self.default_results['trade_log_df']
                best_roi = self.default_results['roi']
                best_total_current_pnl = self.default_results['total_current_pnl']
                best_mtm_value = self.default_results['mtm_value']
                best_total_cost = self.default_results['total_cost']
                best_open_trades = self.default_results['open_trades']
                best_stop_loss_triggered = self.default_results['stop_loss_triggered']
                best_stop_loss_trigger_date = self.default_results['stop_loss_trigger_date']
                best_stop_loss_trigger_price = self.default_results['stop_loss_trigger_price']

            # Update the optimized summary
            self.optimized_grid_levels_label.config(text=f"{best_grid_levels}")
            self.optimized_total_pnl_label.config(
                text=f"{best_total_current_pnl:.3f}")
            self.optimized_mtm_value_label.config(text=f"{best_mtm_value:.3f}")
            self.optimized_total_trades_label.config(
                text=f"{len(best_trade_log_df)}")
            self.optimized_open_trades_label.config(text=f"{best_open_trades}")
            self.optimized_total_cost_label.config(
                text=f"{best_total_cost:.3f}")
            self.optimized_net_pnl_label.config(text=f"{best_pnl:.3f}")
            self.optimized_roi_label.config(text=f"{best_roi:.2f}%")

            if best_stop_loss_triggered:
                self.optimized_stop_loss_triggered_label.config(
                    text="Yes", fg="#e74c3c")
                self.optimized_stop_loss_trigger_date_label.config(
                    text=best_stop_loss_trigger_date)
                self.optimized_stop_loss_trigger_price_label.config(
                    text=f"{best_stop_loss_trigger_price:.2f}")
            else:
                self.optimized_stop_loss_triggered_label.config(
                    text="No", fg="#2ecc71")
                self.optimized_stop_loss_trigger_date_label.config(text="")
                self.optimized_stop_loss_trigger_price_label.config(text="")

            # Clear the Treeview before inserting new logs for optimized strategy
            for item in self.trade_log_tree_optimized.get_children():
                self.trade_log_tree_optimized.delete(item)

            # Insert optimized trade logs
            for _, row in best_trade_log_df.iterrows():
                self.trade_log_tree_optimized.insert(
                    "", "end", values=list(row))

            self.status_label.config(text=f"Optimization Completed. Best Grid Levels: {
                                     best_grid_levels}", fg="#2ecc71")

        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.status_label.config(
                text="Error during optimization", fg="#e74c3c")
        finally:
            self.progress_bar.stop()


if __name__ == "__main__":
    root = tk.Tk()
    app = GridBotGUI(root)
    root.mainloop()
