import SwiftUI

/// Shows how Stock Chance's own Buy/Sell signal rules would have performed
/// on this symbol's historical data, compared to simple buy-and-hold.
struct BacktestView: View {
    @StateObject private var viewModel: BacktestViewModel

    init(symbol: String, baseURL: URL) {
        _viewModel = StateObject(wrappedValue: BacktestViewModel(symbol: symbol, baseURL: baseURL))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                periodPicker

                if viewModel.isLoading && viewModel.result == nil {
                    ProgressView("Running backtest...")
                        .frame(maxWidth: .infinity)
                        .padding(.top, 40)
                } else if let error = viewModel.errorMessage, viewModel.result == nil {
                    EmptyStateView("Couldn't run backtest", systemImage: "exclamationmark.triangle", description: Text(error))
                } else if let result = viewModel.result {
                    summaryCard(result)
                    tradesSection(result)
                    Text(result.disclaimer)
                        .font(.caption2)
                        .foregroundStyle(Theme.textSecondary.opacity(0.8))
                }
            }
            .padding()
        }
        .luxuryBackground()
        .navigationTitle("\(viewModel.symbol) Backtest")
        .task {
            if viewModel.result == nil {
                await viewModel.load()
            }
        }
    }

    private var periodPicker: some View {
        Picker("Period", selection: $viewModel.period) {
            Text("1 Year").tag("1y")
            Text("2 Years").tag("2y")
            Text("5 Years").tag("5y")
        }
        .pickerStyle(.segmented)
    }

    private func summaryCard(_ result: BacktestResponse) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("STRATEGY VS BUY & HOLD")
                .luxuryEyebrow()
            HStack(spacing: 20) {
                statPair("Strategy Return", percentText(result.totalReturnPct), color: colorFor(result.totalReturnPct))
                statPair("Buy & Hold", percentText(result.buyHoldReturnPct), color: colorFor(result.buyHoldReturnPct))
            }
            HStack(spacing: 20) {
                statPair("Win Rate", "\(Int(result.winRatePct))%", color: Theme.textPrimary)
                statPair("Trades", "\(result.tradeCount)", color: Theme.textPrimary)
                statPair("Final Value", result.finalValue.formatted(.currency(code: "USD")), color: Theme.textPrimary)
            }
            Text("\(dateOnly(result.startDate)) – \(dateOnly(result.endDate)) • Starting capital \(result.initialCapital.formatted(.currency(code: "USD")))")
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
        }
        .luxuryCard()
    }

    private func tradesSection(_ result: BacktestResponse) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("SIMULATED TRADES")
                .luxuryEyebrow()
            if result.trades.isEmpty {
                Text("No buy/sell signals fired during this period - the strategy stayed in cash.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.textSecondary)
            } else {
                VStack(spacing: 10) {
                    ForEach(result.trades) { trade in
                        TradeRow(trade: trade)
                    }
                }
            }
        }
    }

    private func statPair(_ title: String, _ value: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
            Text(value)
                .font(.subheadline.weight(.semibold).monospacedDigit())
                .foregroundStyle(color)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func percentText(_ value: Double) -> String {
        "\(value >= 0 ? "+" : "")\(String(format: "%.2f", value))%"
    }

    private func colorFor(_ value: Double) -> Color {
        value >= 0 ? Theme.profit : Theme.loss
    }

    private func dateOnly(_ iso: String) -> String {
        String(iso.prefix(10))
    }
}

private struct TradeRow: View {
    let trade: BacktestTrade

    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 2) {
                Text("\(dateOnly(trade.entryDate)) \u{2192} \(dateOnly(trade.exitDate))")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text("\(trade.entryPrice.formatted(.currency(code: "USD"))) \u{2192} \(trade.exitPrice.formatted(.currency(code: "USD")))")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(Theme.textSecondary)
                Text(exitReasonLabel)
                    .font(.caption2)
                    .foregroundStyle(Theme.textSecondary)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                Text("\(trade.profitLoss >= 0 ? "+" : "")\(trade.profitLoss.formatted(.currency(code: "USD")))")
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                    .foregroundStyle(trade.profitLoss >= 0 ? Theme.profit : Theme.loss)
                Text("\(trade.profitLossPct >= 0 ? "+" : "")\(String(format: "%.2f", trade.profitLossPct))%")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(trade.profitLossPct >= 0 ? Theme.profit : Theme.loss)
            }
        }
        .luxuryCard()
    }

    private var exitReasonLabel: String {
        switch trade.exitReason {
        case "STRONG_SELL": return "Exited on Strong Sell signal"
        case "SELL": return "Exited on Sell signal"
        default: return "Position still open at end of period"
        }
    }

    private func dateOnly(_ iso: String) -> String {
        String(iso.prefix(10))
    }
}
