import SwiftUI

struct StockDetailView: View {
    let symbol: String

    @State private var viewModel: StockDetailViewModel
    @State private var watchlist = WatchlistStore.shared
    @EnvironmentObject private var apiConfig: APIConfig

    init(symbol: String) {
        self.symbol = symbol
        _viewModel = State(wrappedValue: StockDetailViewModel(symbol: symbol))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if viewModel.isLoading && viewModel.quote == nil {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                        .padding(.top, 40)
                } else if let error = viewModel.errorMessage, viewModel.quote == nil {
                    ContentUnavailableView("Couldn't load \(symbol)", systemImage: "exclamationmark.triangle", description: Text(error))
                } else {
                    header
                    if !viewModel.candles.isEmpty {
                        PriceChartView(candles: viewModel.candles)
                    }
                    if let signal = viewModel.signal {
                        signalCard(signal)
                        reasonsCard(signal)
                        levelsCard(signal)
                        if let analyst = signal.analyst {
                            analystCard(analyst)
                        }
                        disclaimer(signal)
                    }
                }
            }
            .padding()
        }
        .navigationTitle(symbol)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    watchlist.toggle(symbol)
                } label: {
                    Image(systemName: watchlist.contains(symbol) ? "star.fill" : "star")
                }
            }
        }
        .task {
            await viewModel.load()
            viewModel.startLive(baseURL: apiConfig.baseURL)
        }
        .onDisappear {
            viewModel.stopLive()
        }
    }

    // MARK: - Sections

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let quote = viewModel.quote {
                Text(quote.price, format: .currency(code: quote.currency ?? "USD"))
                    .font(.largeTitle.bold())
                    .monospacedDigit()
                if let change = quote.change, let changePercent = quote.changePercent {
                    HStack(spacing: 4) {
                        Image(systemName: change >= 0 ? "arrow.up.right" : "arrow.down.right")
                        Text(change, format: .currency(code: quote.currency ?? "USD"))
                        Text("(\(changePercent / 100, format: .percent.precision(.fractionLength(2))))")
                    }
                    .font(.subheadline)
                    .foregroundStyle(change >= 0 ? .green : .red)
                }
                HStack(spacing: 16) {
                    if let dayLow = quote.dayLow, let dayHigh = quote.dayHigh {
                        statPair("Day Range", "\(formatted(dayLow)) - \(formatted(dayHigh))")
                    }
                    if let yearLow = quote.yearLow, let yearHigh = quote.yearHigh {
                        statPair("52wk Range", "\(formatted(yearLow)) - \(formatted(yearHigh))")
                    }
                }
                .padding(.top, 4)
            }
        }
    }

    private func signalCard(_ signal: SignalResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Signal")
                    .font(.headline)
                Spacer()
                SignalBadge(action: signal.action, confidence: signal.confidence)
            }
            ProgressView(value: (signal.score + 1) / 2)
                .tint(signal.action.color)
            Text("Composite score: \(signal.score, specifier: "%.2f") (-1 strong sell ... +1 strong buy)")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .background(.quaternary.opacity(0.3))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func reasonsCard(_ signal: SignalResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Why")
                .font(.headline)
            ForEach(signal.reasons, id: \.self) { reason in
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "circle.fill")
                        .font(.system(size: 5))
                        .padding(.top, 6)
                        .foregroundStyle(.secondary)
                    Text(reason)
                        .font(.subheadline)
                }
            }
        }
        .padding()
        .background(.quaternary.opacity(0.3))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func levelsCard(_ signal: SignalResponse) -> some View {
        let levels = signal.levels
        let pairs: [(String, Double?)] = [
            ("Suggested Entry", levels.suggestedEntry),
            ("Stop Loss", levels.stopLoss),
            ("Take Profit", levels.takeProfit),
            ("Suggested Exit (Short)", levels.suggestedExit),
            ("Stop Loss (Short)", levels.stopLossShort),
            ("Take Profit (Short)", levels.takeProfitShort),
        ].filter { $0.1 != nil }

        return Group {
            if !pairs.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Suggested Levels (ATR-based)")
                        .font(.headline)
                    ForEach(pairs, id: \.0) { label, value in
                        HStack {
                            Text(label)
                                .font(.subheadline)
                            Spacer()
                            Text(formatted(value ?? 0))
                                .font(.subheadline.monospacedDigit())
                        }
                    }
                    if let rr = levels.riskReward {
                        HStack {
                            Text("Risk / Reward")
                            Spacer()
                            Text("1 : \(rr, specifier: "%.1f")")
                        }
                        .font(.subheadline)
                    }
                }
                .padding()
                .background(.quaternary.opacity(0.3))
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
        }
    }

    private func analystCard(_ analyst: AnalystOutlook) -> some View {
        Group {
            if analyst.targetMeanPrice != nil || analyst.recommendationKey != nil {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Analyst Outlook")
                        .font(.headline)
                    if let key = analyst.recommendationKey {
                        HStack {
                            Text("Consensus")
                            Spacer()
                            Text(key.capitalized)
                        }
                        .font(.subheadline)
                    }
                    if let mean = analyst.targetMeanPrice {
                        HStack {
                            Text("Avg. Price Target")
                            Spacer()
                            Text(formatted(mean))
                        }
                        .font(.subheadline)
                    }
                    if let low = analyst.targetLowPrice, let high = analyst.targetHighPrice {
                        HStack {
                            Text("Target Range")
                            Spacer()
                            Text("\(formatted(low)) - \(formatted(high))")
                        }
                        .font(.subheadline)
                    }
                    if let count = analyst.numberOfAnalystOpinions {
                        Text("Based on \(count) analyst opinions (Yahoo Finance)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding()
                .background(.quaternary.opacity(0.3))
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
        }
    }

    private func disclaimer(_ signal: SignalResponse) -> some View {
        Text(signal.disclaimer)
            .font(.caption2)
            .foregroundStyle(.tertiary)
            .padding(.top, 4)
    }

    private func statPair(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption.monospacedDigit())
        }
    }

    private func formatted(_ value: Double) -> String {
        value.formatted(.currency(code: viewModel.quote?.currency ?? "USD"))
    }
}

#Preview {
    NavigationStack {
        StockDetailView(symbol: "AAPL")
    }
    .environmentObject(APIConfig.shared)
}
