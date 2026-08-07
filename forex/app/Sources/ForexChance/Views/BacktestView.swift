import SwiftUI
import Charts

struct BacktestView: View {
    @ObservedObject var vm: AutoTraderViewModel
    @State private var selectedEnv: OandaEnvironment = .practice
    @State private var showError = false

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
                        if let wf = result.walkForward {
                            walkForwardCard(wf, fullMaxDrawdownPct: result.overall.maxDrawdownPct)
                        }
                        equityCurveCard(result)
                        if let strategies = result.perStrategy, !strategies.isEmpty {
                            perStrategyCard(strategies)
                        }
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
            .alert("Backtest Error", isPresented: $showError) {
                Button("OK", role: .cancel) { vm.errorMessage = nil }
            } message: {
                Text(vm.errorMessage ?? "")
            }
            .onChange(of: vm.errorMessage) { msg in
                showError = msg != nil
            }
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
                Stepper("\(vm.backtestBars)", value: $vm.backtestBars, in: 500...5000, step: 500)
                    .fixedSize()
                    .tint(Theme.accent)
            }

            backtestSlider(label: "Spread cost (pips)", value: $vm.backtestSpreadPips, range: 0.5...3.0, step: 0.25, format: "%.1f")
            backtestSlider(label: "Starting NAV ($)", value: $vm.backtestStartingNav, range: 200...100000, step: 1000, format: "%.0f")

            VStack(alignment: .leading, spacing: 8) {
                Text("Pairs")
                    .font(.subheadline)
                    .foregroundColor(.white)
                ForEach(AutoTraderViewModel.availableBacktestPairs, id: \.self) { pair in
                    let display = pair.replacingOccurrences(of: "_", with: "/")
                    let selected = vm.backtestPairs.contains(pair)
                    Button {
                        if selected {
                            vm.backtestPairs.remove(pair)
                        } else {
                            vm.backtestPairs.insert(pair)
                        }
                    } label: {
                        HStack {
                            Image(systemName: selected ? "checkmark.square.fill" : "square")
                                .foregroundColor(selected ? Theme.accent : Theme.textSecondary)
                            Text(display)
                                .foregroundColor(.white)
                                .font(.subheadline)
                            Spacer()
                        }
                    }
                }
            }

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
                    value: String(format: "%@%.1f%%", result.returnPct >= 0 ? "+" : "", result.returnPct),
                    valueColor: result.returnPct >= 0 ? Theme.profit : Theme.loss
                )
                StatTile(
                    label: "Win Rate",
                    value: String(format: "%.0f%%", o.winRatePct),
                    valueColor: o.winRatePct >= 50 ? Theme.profit : Theme.loss
                )
                StatTile(
                    label: "Trades",
                    value: "\(result.tradeCount)"
                )
                StatTile(
                    label: "PF",
                    value: o.profitFactor < 99 ? String(format: "%.2f", o.profitFactor) : "∞",
                    valueColor: o.profitFactor >= 1 ? Theme.profit : Theme.loss
                )
            }

            Divider().background(Theme.cardBorder)

            HStack(spacing: 0) {
                StatTile(
                    label: "Expectancy",
                    value: String(format: "%@%.1fp", o.expectancyPips >= 0 ? "+" : "", o.expectancyPips)
                )
                StatTile(
                    label: "Max DD",
                    value: String(format: "-%.1f%%", o.maxDrawdownPct),
                    valueColor: o.maxDrawdownPct > 5 ? Theme.loss : Theme.textSecondary
                )
                StatTile(
                    label: "Net P&L",
                    value: Format.signedMoney(o.netPnlUsd),
                    valueColor: o.netPnlUsd >= 0 ? Theme.profit : Theme.loss
                )
                StatTile(
                    label: "Calmar",
                    value: String(format: "%.2f", result.calmarRatio),
                    valueColor: result.calmarRatio >= 1.0 ? Theme.profit : (result.calmarRatio >= 0.5 ? Theme.accent : Theme.loss)
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

    // MARK: - Walk-forward (out-of-sample) validation

    private func walkForwardCard(_ wf: WalkForwardModel, fullMaxDrawdownPct: Double) -> some View {
        let o = wf.overall
        let ret = o.returnPct
        let dd = o.maxDrawdownPct
        // FTMO safety must use the WORST drawdown the challenge could face — the
        // full backtest period, not just the calm out-of-sample slice.
        let worstDD = max(dd, fullMaxDrawdownPct)
        let passed = ret > 0 && o.profitFactor >= 1.0 && wf.tradeCount >= 5
        return VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Walk-Forward Test")
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .textCase(.uppercase)
                Spacer()
                Text(passed ? "✓ EDGE HOLDS" : "⚠︎ WEAK OOS")
                    .font(.caption2.bold())
                    .foregroundColor(passed ? Theme.profit : Theme.loss)
            }

            Text("Trained on first \(wf.trainPct)% of data, tested on the last \(wf.testPct)% it never saw. If these stay positive, the edge is real — not curve-fit.")
                .font(.caption2)
                .foregroundColor(Theme.textSecondary)

            HStack(spacing: 0) {
                StatTile(
                    label: "OOS Return",
                    value: String(format: "%@%.1f%%", ret >= 0 ? "+" : "", ret),
                    valueColor: ret >= 0 ? Theme.profit : Theme.loss
                )
                StatTile(
                    label: "OOS Win",
                    value: String(format: "%.0f%%", o.winRatePct),
                    valueColor: o.winRatePct >= 50 ? Theme.profit : Theme.loss
                )
                StatTile(
                    label: "OOS Trades",
                    value: "\(wf.tradeCount)"
                )
                StatTile(
                    label: "OOS PF",
                    value: o.profitFactor < 99 ? String(format: "%.2f", o.profitFactor) : "∞",
                    valueColor: o.profitFactor >= 1 ? Theme.profit : Theme.loss
                )
            }

            HStack(spacing: 0) {
                StatTile(
                    label: "OOS Max DD",
                    value: String(format: "-%.1f%%", dd),
                    valueColor: dd > 8 ? Theme.loss : Theme.profit
                )
                StatTile(
                    label: "Calmar",
                    value: o.calmarRatio.map { String(format: "%.2f", $0) } ?? "—",
                    valueColor: (o.calmarRatio ?? 0) >= 1.0 ? Theme.profit : Theme.accent
                )
                StatTile(
                    label: "FTMO DD?",
                    value: worstDD < 8 ? "✓ Safe" : "✗ Risk",
                    valueColor: worstDD < 8 ? Theme.profit : Theme.loss
                )
                StatTile(
                    label: "Worst DD",
                    value: String(format: "-%.1f%%", worstDD),
                    valueColor: worstDD < 8 ? Theme.profit : Theme.loss
                )
            }
        }
        .cardStyle()
    }

    // MARK: - Equity curve

    private func equityCurveCard(_ result: BacktestResult) -> some View {
        let curve = equityCurve(from: result)
        let isPositive = result.endingNav >= result.startingNav

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
                let minY = (curve.map { $0.nav }.min() ?? 0) * 0.98
                let maxY = (curve.map { $0.nav }.max() ?? 0) * 1.02

                Chart {
                    ForEach(curve) { point in
                        LineMark(
                            x: .value("Trade", point.index),
                            y: .value("NAV", point.nav)
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

    private struct EquityPoint: Identifiable {
        let id = UUID()
        let index: Int
        let nav: Double
    }

    private func equityCurve(from result: BacktestResult) -> [EquityPoint] {
        var nav = result.startingNav
        var points = [EquityPoint(index: 0, nav: nav)]
        for (i, trade) in result.trades.enumerated() {
            nav += trade.pnlUsd
            points.append(EquityPoint(index: i + 1, nav: max(0, nav)))
        }
        return points
    }

    // MARK: - Per-strategy breakdown

    private func strategyDisplayName(_ key: String) -> String {
        switch key {
        case "london_breakout": return "London Breakout"
        case "orb":             return "Opening Range Breakout"
        case "order_block":     return "Order Block Reversal"
        default:                return "EMA / Intraday"
        }
    }

    private func perStrategyCard(_ strategies: [BacktestStatsModel]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("By Strategy")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
                .textCase(.uppercase)

            Text("Which strategy is making (or losing) money?")
                .font(.caption2)
                .foregroundColor(Theme.textSecondary)

            ForEach(strategies) { stat in
                VStack(spacing: 4) {
                    HStack {
                        Text(strategyDisplayName(stat.pair))
                            .font(.subheadline.bold())
                            .foregroundColor(.white)
                        Spacer()
                        Text(Format.signedMoney(stat.netPnlUsd))
                            .font(.subheadline.bold())
                            .foregroundColor(stat.netPnlUsd >= 0 ? Theme.profit : Theme.loss)
                    }
                    HStack {
                        Text("\(stat.trades) trades")
                            .font(.caption)
                            .foregroundColor(Theme.textSecondary)
                        Text("·")
                            .font(.caption)
                            .foregroundColor(Theme.textSecondary)
                        Text(String(format: "%.0f%% WR", stat.winRatePct))
                            .font(.caption)
                            .foregroundColor(stat.winRatePct >= 50 ? Theme.profit : Theme.loss)
                        Text("·")
                            .font(.caption)
                            .foregroundColor(Theme.textSecondary)
                        Text(String(format: "PF %.2f", stat.profitFactor))
                            .font(.caption)
                            .foregroundColor(stat.profitFactor >= 1.0 ? Theme.profit : Theme.loss)
                        Spacer()
                        if let calmar = stat.calmarRatio {
                            Text(String(format: "Calmar %.2f", calmar))
                                .font(.caption)
                                .foregroundColor(calmar >= 1.0 ? Theme.profit : (calmar >= 0.5 ? Theme.accent : Theme.loss))
                        }
                    }
                }
                if stat.id != (strategies.last?.id ?? "") {
                    Divider().background(Theme.cardBorder)
                }
            }
        }
        .cardStyle()
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
                        Text(String(format: "%.0f%% WR · %d trades", stat.winRatePct, stat.trades))
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
                    Text(trade.strategyLabel)
                        .font(.caption2.bold())
                        .foregroundColor(Theme.accent)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Theme.accent.opacity(0.15))
                        .cornerRadius(3)
                    Spacer()
                    Text(String(format: "%@%.0fp", trade.netPips >= 0 ? "+" : "", trade.netPips))
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
