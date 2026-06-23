import SwiftUI
import Charts

struct BacktestView: View {
    @ObservedObject var vm: AutoTraderViewModel
    @State private var selectedEnv: OandaEnvironment = .practice
    @State private var showTradeList = false

    var body: some View {
        ScreenBackground {
            ScrollView {
                VStack(spacing: 16) {
                    settingsCard
                    if vm.isBacktesting {
                        ProgressView("Running backtest…")
                            .tint(Theme.accent)
                            .padding()
                    }
                    if let result = vm.backtestResult {
                        summaryCard(result)
                        equityCurveCard(result)
                        perPairCard(result)
                        if !result.trades.isEmpty {
                            tradeListCard(result.trades)
                        }
                        if !result.errors.isEmpty {
                            errorsCard(result.errors)
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Backtest")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    // MARK: - Settings card

    private var settingsCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Parameters")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
                .textCase(.uppercase)

            Picker("Environment", selection: $selectedEnv) {
                ForEach(OandaEnvironment.allCases, id: \.self) { env in
                    Text(env == .live ? "Live data" : "Practice data").tag(env)
                }
            }
            .pickerStyle(.segmented)

            HStack {
                Text("History (bars)")
                    .font(.subheadline)
                    .foregroundColor(.white)
                Spacer()
                Stepper("\(vm.backtestBars)", value: $vm.backtestBars, step: 500, in: 500...5000)
                    .fixedSize()
                    .tint(Theme.accent)
            }

            backtestSlider(label: "Spread cost (pips)", value: $vm.backtestSpreadPips, range: 0.5...3.0, step: 0.25, format: "%.1f")
            backtestSlider(label: "Starting NAV ($)", value: $vm.backtestStartingNav, range: 200...10000, step: 200, format: "%.0f")

            Button {
                Task { await vm.runBacktest(environment: selectedEnv) }
            } label: {
                if vm.isBacktesting {
                    ProgressView().tint(.black)
                } else {
                    Text("Run Backtest")
                        .fontWeight(.semibold)
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(Theme.accent)
            .foregroundColor(.black)
            .cornerRadius(10)
            .disabled(vm.isBacktesting)
        }
        .cardStyle()
    }

    // MARK: - Summary card

    private func summaryCard(_ result: BacktestResult) -> some View {
        let o = result.overall
        return VStack(alignment: .leading, spacing: 12) {
            Text("Summary")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
                .textCase(.uppercase)

            HStack(spacing: 0) {
                StatTile(
                    label: "Return",
                    value: "\(result.returnPct >= 0 ? "+" : "")\(result.returnPct, specifier: "%.1f")%",
                    valueColor: result.returnPct >= 0 ? Theme.profit : Theme.loss
                )
                StatTile(
                    label: "Win Rate",
                    value: "\(o.winRatePct, specifier: "%.0f")%",
                    valueColor: o.winRatePct >= 50 ? Theme.profit : Theme.loss
                )
                StatTile(
                    label: "Trades",
                    value: "\(result.tradeCount)"
                )
                StatTile(
                    label: "PF",
                    value: o.profitFactor < 99 ? "\(o.profitFactor, specifier: "%.2f")" : "∞",
                    valueColor: o.profitFactor >= 1 ? Theme.profit : Theme.loss
                )
            }

            Divider().background(Theme.cardBorder)

            HStack(spacing: 0) {
                StatTile(
                    label: "Expectancy",
                    value: "\(o.expectancyPips >= 0 ? "+" : "")\(o.expectancyPips, specifier: "%.1f")p"
                )
                StatTile(
                    label: "Max DD",
                    value: "-\(o.maxDrawdownPct, specifier: "%.1f")%",
                    valueColor: o.maxDrawdownPct > 5 ? Theme.loss : Theme.textSecondary
                )
                StatTile(
                    label: "Net P&L",
                    value: Format.signedMoney(o.netPnlUsd),
                    valueColor: o.netPnlUsd >= 0 ? Theme.profit : Theme.loss
                )
                StatTile(
                    label: "Net Pips",
                    value: "\(o.netPips >= 0 ? "+" : "")\(o.netPips, specifier: "%.0f")"
                )
            }

            HStack {
                Text("Starting NAV:")
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                Spacer()
                Text(Format.money(result.startingNav))
                    .font(.caption.monospacedDigit())
                    .foregroundColor(.white)
            }
            HStack {
                Text("Ending NAV:")
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                Spacer()
                Text(Format.money(result.endingNav))
                    .font(.caption.monospacedDigit())
                    .foregroundColor(result.endingNav >= result.startingNav ? Theme.profit : Theme.loss)
            }
        }
        .cardStyle()
    }

    // MARK: - Equity curve

    private func equityCurveCard(_ result: BacktestResult) -> some View {
        let curve = equityCurve(from: result)
        return VStack(alignment: .leading, spacing: 12) {
            Text("Equity Curve")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
                .textCase(.uppercase)

            if curve.count < 2 {
                Text("Not enough trades for a chart.")
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
            } else {
                let minY = (curve.map { $0.1 }.min() ?? 0) * 0.98
                let maxY = (curve.map { $0.1 }.max() ?? 0) * 1.02
                let isPositive = result.endingNav >= result.startingNav

                Chart {
                    ForEach(Array(curve.enumerated()), id: \.offset) { i, point in
                        LineMark(
                            x: .value("Trade", i),
                            y: .value("NAV", point.1)
                        )
                        .foregroundStyle(isPositive ? Theme.profit : Theme.loss)
                        .interpolationMethod(.monotone)
                    }
                }
                .chartYScale(domain: minY...maxY)
                .chartXAxis(.hidden)
                .frame(height: 160)
            }
        }
        .cardStyle()
    }

    private func equityCurve(from result: BacktestResult) -> [(String, Double)] {
        var nav = result.startingNav
        var points: [(String, Double)] = [("0", nav)]
        for (i, trade) in result.trades.enumerated() {
            nav += trade.pnlUsd
            points.append(("\(i + 1)", max(0, nav)))
        }
        return points
    }

    // MARK: - Per-pair breakdown

    private func perPairCard(_ result: BacktestResult) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("By Pair")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
                .textCase(.uppercase)

            ForEach(result.perPair) { stat in
                HStack {
                    Text(stat.pair.replacingOccurrences(of: "_", with: "/"))
                        .font(.subheadline.bold())
                        .foregroundColor(.white)
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("\(stat.winRatePct, specifier: "%.0f")% WR · \(stat.trades) trades")
                            .font(.caption)
                            .foregroundColor(Theme.textSecondary)
                        Text(Format.signedMoney(stat.netPnlUsd))
                            .font(.caption.bold())
                            .foregroundColor(stat.netPnlUsd >= 0 ? Theme.profit : Theme.loss)
                    }
                }
                if stat.id != (result.perPair.last?.id ?? "") {
                    Divider().background(Theme.cardBorder)
                }
            }
        }
        .cardStyle()
    }

    // MARK: - Trade list

    private func tradeListCard(_ trades: [BacktestTradeModel]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Trades (\(trades.count))")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
                .textCase(.uppercase)

            ForEach(trades.prefix(50)) { trade in
                HStack(spacing: 8) {
                    Circle()
                        .fill(trade.isWin ? Theme.profit : (trade.outcome == "scratch" ? Theme.accent : Theme.loss))
                        .frame(width: 8, height: 8)
                    Text(trade.pair.replacingOccurrences(of: "_", with: "/"))
                        .font(.caption.bold())
                        .foregroundColor(.white)
                    Text(trade.side.uppercased())
                        .font(.caption2)
                        .foregroundColor(trade.side == "long" ? Theme.profit : Theme.loss)
                    Spacer()
                    Text("\(trade.netPips >= 0 ? "+" : "")\(trade.netPips, specifier: "%.0f")p")
                        .font(.caption.monospacedDigit())
                        .foregroundColor(trade.netPips >= 0 ? Theme.profit : Theme.loss)
                    Text(Format.signedMoney(trade.pnlUsd))
                        .font(.caption.monospacedDigit())
                        .foregroundColor(trade.pnlUsd >= 0 ? Theme.profit : Theme.loss)
                }
            }

            if trades.count > 50 {
                Text("Showing 50 of \(trades.count) trades.")
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
            }
        }
        .cardStyle()
    }

    // MARK: - Errors

    private func errorsCard(_ errors: [String]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Warnings")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
                .textCase(.uppercase)
            ForEach(errors, id: \.self) { err in
                Text(err)
                    .font(.caption)
                    .foregroundColor(Theme.loss)
            }
        }
        .cardStyle()
    }

    // MARK: - Helpers

    private func backtestSlider(label: String, value: Binding<Double>, range: ClosedRange<Double>, step: Double, format: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label)
                    .font(.subheadline)
                    .foregroundColor(.white)
                Spacer()
                Text(String(format: format, value.wrappedValue))
                    .font(.subheadline.monospacedDigit())
                    .foregroundColor(Theme.accent)
            }
            Slider(value: value, in: range, step: step)
                .tint(Theme.accent)
        }
    }
}
