import SwiftUI

struct StockDetailView: View {
    let symbol: String

    @StateObject private var viewModel: StockDetailViewModel
    @StateObject private var watchlist = WatchlistStore.shared
    @StateObject private var positions = PositionStore.shared
    @State private var showBuySheet = false
    @State private var orderSheetItem: OrderSheetItem?
    @EnvironmentObject private var apiConfig: APIConfig
    @EnvironmentObject private var brokerStore: BrokerStore

    init(symbol: String) {
        self.symbol = symbol
        _viewModel = StateObject(wrappedValue: StockDetailViewModel(symbol: symbol))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if viewModel.isLoading && viewModel.quote == nil {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                        .padding(.top, 40)
                } else if let error = viewModel.errorMessage, viewModel.quote == nil {
                    EmptyStateView("Couldn't load \(symbol)", systemImage: "exclamationmark.triangle", description: Text(error))
                } else {
                    header
                    positionSection
                    tradeSection
                    if !viewModel.candles.isEmpty {
                        PriceChartView(candles: viewModel.candles)
                            .luxuryCard()
                    }
                    if let signal = viewModel.signal {
                        signalCard(signal)
                        reasonsCard(signal)
                        levelsCard(signal)
                        if let analyst = signal.analyst {
                            analystCard(analyst)
                        }
                    }
                    dayTradeSection
                    if let signal = viewModel.signal {
                        disclaimer(signal.disclaimer)
                    }
                }
            }
            .padding()
        }
        .luxuryBackground()
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
            viewModel.startLive(baseURL: apiConfig.webSocketBaseURL)
        }
        .onDisappear {
            viewModel.stopLive()
        }
        .sheet(isPresented: $showBuySheet) {
            MarkAsBoughtSheet(symbol: symbol, suggestedPrice: viewModel.quote?.price) { price, quantity in
                positions.add(symbol: symbol, entryPrice: price, quantity: quantity)
                NotificationManager.shared.requestAuthorization()
            }
        }
        .sheet(item: $orderSheetItem) { item in
            BrokerOrderSheet(
                symbol: symbol,
                side: item.side,
                suggestedPrice: viewModel.quote?.price,
                credentials: brokerStore.credentials,
                baseURL: apiConfig.baseURL
            )
        }
    }

    // MARK: - Sections

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let quote = viewModel.quote {
                Text(quote.price, format: .currency(code: quote.currency ?? "USD"))
                    .font(Theme.priceFont(34))
                    .foregroundStyle(Theme.textPrimary)
                    .monospacedDigit()
                if let change = quote.change, let changePercent = quote.changePercent {
                    HStack(spacing: 4) {
                        Image(systemName: change >= 0 ? "arrow.up.right" : "arrow.down.right")
                        Text(change, format: .currency(code: quote.currency ?? "USD"))
                        Text("(\(changePercent / 100, format: .percent.precision(.fractionLength(2))))")
                    }
                    .font(.subheadline)
                    .foregroundStyle(change >= 0 ? Theme.profit : Theme.loss)
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

    /// "I Bought This" call to action, or a summary of the tracked position.
    @ViewBuilder
    private var positionSection: some View {
        if let position = positions.positions.first(where: { $0.symbol == symbol.uppercased() }) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Tracking Your Position")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Theme.gold)
                    Text("\(position.quantity.formatted()) sh @ \(position.entryPrice.formatted(.currency(code: "USD")))")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                    Text("We'll alert you here and in My Positions when it's time to sell.")
                        .font(.caption2)
                        .foregroundStyle(Theme.textSecondary)
                }
                Spacer()
                Button("Remove") {
                    positions.remove(position)
                }
                .buttonStyle(LuxuryButtonStyle(prominent: false))
            }
            .luxuryCard()
        } else {
            Button {
                showBuySheet = true
            } label: {
                Label("I Bought This", systemImage: "bag.badge.plus")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(LuxuryButtonStyle(prominent: true))
        }
    }

    /// Buy/Sell buttons for the Alpaca **paper trading** account.
    @ViewBuilder
    private var tradeSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Paper Trading")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                Text("SIMULATED")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(Theme.gold)
            }

            if brokerStore.isConfigured {
                HStack(spacing: 12) {
                    Button {
                        orderSheetItem = OrderSheetItem(side: "buy")
                    } label: {
                        Label("Buy", systemImage: "arrow.up.circle.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(LuxuryButtonStyle(prominent: true))

                    Button {
                        orderSheetItem = OrderSheetItem(side: "sell")
                    } label: {
                        Label("Sell", systemImage: "arrow.down.circle.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(LuxuryButtonStyle(prominent: false))
                }
            } else {
                Text("Connect a free Alpaca paper-trading account in Settings to place simulated Buy/Sell orders - no real money at risk.")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
            }
        }
        .luxuryCard()
    }

    private func signalCard(_ signal: SignalResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Signal")
                    .font(Theme.sectionTitleFont())
                    .foregroundStyle(Theme.textPrimary)
                InfoTooltip(title: TradingGlossary.confidence.0, text: TradingGlossary.confidence.1)
                Spacer()
                SignalBadge(action: signal.action, confidence: signal.confidence)
            }
            ProgressView(value: (signal.score + 1) / 2)
                .tint(signal.action.color)
            Text("Composite score: \(signal.score, specifier: "%.2f") (-1 strong sell ... +1 strong buy)")
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
        }
        .luxuryCard()
    }

    private func reasonsCard(_ signal: SignalResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Why")
                .font(Theme.sectionTitleFont())
                .foregroundStyle(Theme.textPrimary)
            ForEach(signal.reasons, id: \.self) { reason in
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "circle.fill")
                        .font(.system(size: 5))
                        .padding(.top, 6)
                        .foregroundStyle(Theme.textSecondary)
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(Theme.textPrimary)
                }
            }
        }
        .luxuryCard()
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
                    HStack {
                        Text("Suggested Levels (ATR-based)")
                            .font(Theme.sectionTitleFont())
                            .foregroundStyle(Theme.textPrimary)
                        InfoTooltip(title: TradingGlossary.stopLoss.0, text: "\(TradingGlossary.stopLoss.1)\n\n\(TradingGlossary.takeProfit.0): \(TradingGlossary.takeProfit.1)")
                    }
                    ForEach(pairs, id: \.0) { label, value in
                        HStack {
                            Text(label)
                                .font(.subheadline)
                                .foregroundStyle(Theme.textPrimary)
                            Spacer()
                            Text(formatted(value ?? 0))
                                .font(.subheadline.monospacedDigit())
                                .foregroundStyle(Theme.textSecondary)
                        }
                    }
                    if let rr = levels.riskReward {
                        HStack {
                            Text("Risk / Reward")
                                .foregroundStyle(Theme.textPrimary)
                            InfoTooltip(title: TradingGlossary.riskReward.0, text: TradingGlossary.riskReward.1)
                            Spacer()
                            Text("1 : \(rr, specifier: "%.1f")")
                                .foregroundStyle(Theme.textSecondary)
                        }
                        .font(.subheadline)
                    }
                    if let entry = levels.suggestedEntry, let stop = levels.stopLoss {
                        NavigationLink {
                            RiskCalculatorView(initialEntry: entry, initialStop: stop)
                        } label: {
                            Label("Position Size Calculator", systemImage: "function")
                                .font(.caption)
                        }
                    }
                }
                .luxuryCard()
            }
        }
    }

    private func analystCard(_ analyst: AnalystOutlook) -> some View {
        Group {
            if analyst.targetMeanPrice != nil || analyst.recommendationKey != nil {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Analyst Outlook")
                        .font(Theme.sectionTitleFont())
                        .foregroundStyle(Theme.textPrimary)
                    if let key = analyst.recommendationKey {
                        HStack {
                            Text("Consensus")
                                .foregroundStyle(Theme.textPrimary)
                            Spacer()
                            Text(key.capitalized)
                                .foregroundStyle(Theme.textSecondary)
                        }
                        .font(.subheadline)
                    }
                    if let mean = analyst.targetMeanPrice {
                        HStack {
                            Text("Avg. Price Target")
                                .foregroundStyle(Theme.textPrimary)
                            Spacer()
                            Text(formatted(mean))
                                .foregroundStyle(Theme.textSecondary)
                        }
                        .font(.subheadline)
                    }
                    if let low = analyst.targetLowPrice, let high = analyst.targetHighPrice {
                        HStack {
                            Text("Target Range")
                                .foregroundStyle(Theme.textPrimary)
                            Spacer()
                            Text("\(formatted(low)) - \(formatted(high))")
                                .foregroundStyle(Theme.textSecondary)
                        }
                        .font(.subheadline)
                    }
                    if let count = analyst.numberOfAnalystOpinions {
                        Text("Based on \(count) analyst opinions (Yahoo Finance)")
                            .font(.caption)
                            .foregroundStyle(Theme.textSecondary)
                    }
                }
                .luxuryCard()
            }
        }
    }

    // MARK: - Day Trade (same-day)

    @ViewBuilder
    private var dayTradeSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("SAME-DAY")
                .luxuryEyebrow()
            HStack {
                Text("Day Trade Signal")
                    .font(Theme.sectionTitleFont())
                    .foregroundStyle(Theme.textPrimary)
                InfoTooltip(title: TradingGlossary.vwap.0, text: "\(TradingGlossary.vwap.1)\n\n\(TradingGlossary.openingRange.0): \(TradingGlossary.openingRange.1)\n\n\(TradingGlossary.volumeSpike.0): \(TradingGlossary.volumeSpike.1)")
            }

            if let daySignal = viewModel.daySignal {
                MarketSessionBanner(session: daySignal.session)

                if let alert = daySignal.alert {
                    AlertBanner(alert: alert)
                }

                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("Action")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(Theme.textPrimary)
                        Spacer()
                        DayActionBadge(action: daySignal.action, confidence: daySignal.confidence)
                    }

                    if !viewModel.intradayCandles.isEmpty {
                        IntradayChartView(
                            candles: viewModel.intradayCandles,
                            vwap: daySignal.vwap,
                            entry: daySignal.entry,
                            target: daySignal.target,
                            stop: daySignal.stop
                        )
                    }

                    let stats: [(String, String)] = [
                        ("Session Open", formatted(daySignal.sessionOpen)),
                        ("Session High", formatted(daySignal.sessionHigh)),
                        ("Session Low", formatted(daySignal.sessionLow)),
                        ("Change From Open", "\(daySignal.changeFromOpenPct >= 0 ? "+" : "")\(String(format: "%.2f", daySignal.changeFromOpenPct))%"),
                    ]
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                        ForEach(stats, id: \.0) { label, value in
                            statPair(label, value)
                        }
                        if let vwap = daySignal.vwap {
                            statPair("VWAP", formatted(vwap))
                        }
                    }

                    if daySignal.entry != nil || daySignal.target != nil || daySignal.stop != nil {
                        Divider().overlay(Theme.cardBorder)
                        let levels: [(String, Double?)] = [
                            ("Entry", daySignal.entry),
                            ("Target", daySignal.target),
                            ("Stop", daySignal.stop),
                        ].filter { $0.1 != nil }
                        ForEach(levels, id: \.0) { label, value in
                            HStack {
                                Text(label)
                                    .font(.subheadline)
                                    .foregroundStyle(Theme.textPrimary)
                                Spacer()
                                Text(formatted(value ?? 0))
                                    .font(.subheadline.monospacedDigit())
                                    .foregroundStyle(Theme.textSecondary)
                            }
                        }
                        if let pct = daySignal.suspectedProfitPct, let amount = daySignal.suspectedProfitAmount {
                            HStack {
                                Text("Suspected Profit")
                                    .font(.subheadline)
                                    .foregroundStyle(Theme.textPrimary)
                                Spacer()
                                Text("\(pct, specifier: "%.1f")% (~\(amount.formatted(.currency(code: "USD"))))")
                                    .font(.subheadline.monospacedDigit())
                                    .foregroundStyle(Theme.profit)
                            }
                        }
                    }

                    Divider().overlay(Theme.cardBorder)
                    ForEach(daySignal.reasons, id: \.self) { reason in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "circle.fill")
                                .font(.system(size: 5))
                                .padding(.top, 6)
                                .foregroundStyle(Theme.textSecondary)
                            Text(reason)
                                .font(.subheadline)
                                .foregroundStyle(Theme.textPrimary)
                        }
                    }

                    disclaimer(daySignal.disclaimer)
                }
                .luxuryCard()
            } else if let error = viewModel.dayErrorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .luxuryCard()
            } else {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .padding()
            }
        }
    }

    // MARK: - Helpers

    private func disclaimer(_ text: String) -> some View {
        Text(text)
            .font(.caption2)
            .foregroundStyle(Theme.textSecondary.opacity(0.8))
            .padding(.top, 4)
    }

    private func statPair(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
            Text(value)
                .font(.caption.monospacedDigit())
                .foregroundStyle(Theme.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func formatted(_ value: Double) -> String {
        value.formatted(.currency(code: viewModel.quote?.currency ?? "USD"))
    }
}

/// Identifies which side of a paper-trading order sheet to present.
private struct OrderSheetItem: Identifiable {
    let side: String // "buy" | "sell"
    var id: String { side }
}

/// Sheet for recording entry price + quantity when the user taps
/// "I Bought This".
private struct MarkAsBoughtSheet: View {
    let symbol: String
    let suggestedPrice: Double?
    let onSave: (Double, Double) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var priceText: String = ""
    @State private var quantityText: String = "1"

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    LabeledContent("Entry Price") {
                        TextField("0.00", text: $priceText)
                            #if os(iOS)
                            .keyboardType(.decimalPad)
                            #endif
                            .multilineTextAlignment(.trailing)
                    }
                    LabeledContent("Quantity (shares)") {
                        TextField("1", text: $quantityText)
                            #if os(iOS)
                            .keyboardType(.decimalPad)
                            #endif
                            .multilineTextAlignment(.trailing)
                    }
                } header: {
                    Text("Position Details")
                } footer: {
                    Text("We'll track \(symbol) in My Positions and let you know when the same-day signal suggests it's time to sell.")
                }
            }
            .navigationTitle("I Bought \(symbol)")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        if let price = Double(priceText), let quantity = Double(quantityText), price > 0, quantity > 0 {
                            onSave(price, quantity)
                            dismiss()
                        }
                    }
                }
            }
            .onAppear {
                if priceText.isEmpty, let suggestedPrice {
                    priceText = String(format: "%.2f", suggestedPrice)
                }
            }
        }
    }
}
