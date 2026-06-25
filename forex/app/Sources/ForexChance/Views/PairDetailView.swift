import SwiftUI

struct PairDetailView: View {
    @StateObject private var viewModel: PairDetailViewModel
    @ObservedObject private var brokerStore = BrokerStore.shared
    @State private var showOrderSheet = false

    private let pair: PairInfo

    init(pair: PairInfo) {
        self.pair = pair
        _viewModel = StateObject(wrappedValue: PairDetailViewModel(pair: pair))
    }

    private var decimals: Int { pair.quote == "JPY" ? 3 : 5 }

    var body: some View {
        ScreenBackground {
            ScrollView {
                VStack(spacing: 16) {
                    quoteHeader

                    if !viewModel.candles.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Today (5-min)")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(Theme.textSecondary)
                            PriceChartView(candles: viewModel.candles, vwap: viewModel.daySignal?.vwap, decimals: decimals)
                        }
                        .cardStyle()
                    }

                    if let day = viewModel.daySignal {
                        DaySignalCard(day: day, decimals: decimals)
                    }

                    if let signal = viewModel.signal {
                        SwingSignalCard(signal: signal, decimals: decimals)
                    }

                    if viewModel.isLoading && viewModel.signal == nil {
                        ProgressView().tint(Theme.accent).padding(.top, 30)
                    }

                    if let error = viewModel.errorMessage, viewModel.signal == nil {
                        InfoState(icon: "exclamationmark.triangle.fill", title: "Couldn't load", message: error)
                    }

                    DisclaimerText()
                }
                .padding()
            }
        }
        .navigationTitle(pair.display)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showOrderSheet = true
                } label: {
                    Label("Trade", systemImage: "arrow.left.arrow.right")
                }
                .disabled(brokerStore.availableEnvironments.isEmpty)
            }
        }
        .sheet(isPresented: $showOrderSheet) {
            OrderSheet(pair: pair, suggestedAction: viewModel.signal?.tradeAction)
        }
        .refreshable { await viewModel.refresh() }
        .task { await viewModel.refresh() }
    }

    private var quoteHeader: some View {
        VStack(spacing: 10) {
            if let quote = viewModel.quote {
                Text(Format.price(quote.mid, decimals: decimals))
                    .font(Theme.priceFont(40))
                    .foregroundStyle(Theme.textPrimary)
                HStack(spacing: 20) {
                    StatTile(label: "Bid", value: Format.price(quote.bid, decimals: decimals))
                    StatTile(label: "Ask", value: Format.price(quote.ask, decimals: decimals))
                    StatTile(label: "Spread", value: quote.spreadPips.map { String(format: "%.1f pips", $0) } ?? "—")
                }
            } else {
                Text("—")
                    .font(Theme.priceFont(40))
                    .foregroundStyle(Theme.textSecondary)
            }
        }
        .frame(maxWidth: .infinity)
        .cardStyle()
    }
}

// MARK: - Day signal card

private struct DaySignalCard: View {
    let day: DaySignalResponse
    let decimals: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Same-Day Signal")
                    .font(Theme.sectionTitleFont())
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                DayActionBadge(action: day.dayAction)
            }

            HStack {
                StatTile(label: "From Open", value: Format.pips(day.changeFromOpenPips),
                         valueColor: day.changeFromOpenPips >= 0 ? Theme.profit : Theme.loss)
                StatTile(label: "VWAP", value: Format.price(day.vwap, decimals: decimals))
                StatTile(label: "Confidence", value: "\(Int(day.confidence))%")
            }

            if day.dayAction.isActionable {
                HStack {
                    StatTile(label: "Entry", value: Format.price(day.entry, decimals: decimals))
                    StatTile(label: "Target", value: Format.pips(day.targetPips), valueColor: Theme.profit)
                    StatTile(label: "Stop", value: Format.pips(day.stopPips.map { -$0 }), valueColor: Theme.loss)
                }
            }

            if let alert = day.alert {
                Label(alertText(alert), systemImage: "bell.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.accentBright)
            }

            ForEach(day.reasons, id: \.self) { reason in
                ReasonRow(text: reason)
            }
        }
        .cardStyle()
    }

    private func alertText(_ alert: String) -> String {
        switch alert {
        case "TAKE_PROFIT_ZONE": return "In a take-profit zone — consider locking in gains"
        case "STOP_LOSS_ZONE": return "In a stop-loss zone — consider cutting losses"
        default: return alert
        }
    }
}

// MARK: - Swing signal card

private struct SwingSignalCard: View {
    let signal: SignalResponse
    let decimals: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Trend Signal (H1)")
                    .font(Theme.sectionTitleFont())
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                SignalBadge(action: signal.tradeAction)
            }

            HStack {
                StatTile(label: "Confidence", value: "\(Int(signal.confidence))%")
                if let entry = signal.levels.suggestedEntry {
                    StatTile(label: "Entry", value: Format.price(entry, decimals: decimals))
                }
                StatTile(label: "Target", value: Format.pips(signal.levels.targetPips), valueColor: Theme.profit)
                StatTile(label: "Stop", value: Format.pips(signal.levels.stopPips.map { -$0 }), valueColor: Theme.loss)
            }

            ForEach(signal.reasons, id: \.self) { reason in
                ReasonRow(text: reason)
            }
        }
        .cardStyle()
    }
}

private struct ReasonRow: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "circle.fill")
                .font(.system(size: 5))
                .foregroundStyle(Theme.accent)
                .padding(.top, 6)
            Text(text)
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
