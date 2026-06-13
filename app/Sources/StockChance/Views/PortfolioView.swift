import SwiftUI

/// "Portfolio" tab - everything the user has marked as bought (with live
/// P/L and same-day sell alerts), plus a summary of every connected
/// brokerage account (Alpaca paper/live, Questrade) and a link to the
/// trade journal.
struct PortfolioView: View {
    @StateObject private var store = PositionStore.shared
    @StateObject private var viewModel = PositionsViewModel()
    @StateObject private var portfolioViewModel = PortfolioViewModel()
    @EnvironmentObject private var apiConfig: APIConfig
    @EnvironmentObject private var brokerStore: BrokerStore
    @State private var sellSheetPosition: Position?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    NavigationLink {
                        JournalView()
                    } label: {
                        Label("Trade Journal", systemImage: "book.closed.fill")
                    }
                }
                .listRowBackground(Theme.card)

                if !brokerStore.availableTradeAccounts.isEmpty {
                    Section("Broker Accounts") {
                        if portfolioViewModel.isLoading && portfolioViewModel.summaries.isEmpty {
                            ProgressView()
                                .listRowBackground(Color.clear)
                        } else {
                            ForEach(portfolioViewModel.summaries) { summary in
                                BrokerAccountCard(summary: summary)
                                    .listRowBackground(Color.clear)
                                    .listRowSeparator(.hidden)
                                    .listRowInsets(EdgeInsets(top: 6, leading: 16, bottom: 6, trailing: 16))
                            }
                            if let error = portfolioViewModel.errorMessage {
                                Text(error)
                                    .font(.caption)
                                    .foregroundStyle(Theme.loss)
                                    .listRowBackground(Color.clear)
                            }
                        }
                    }
                }

                Section("My Positions") {
                    if store.positions.isEmpty {
                        EmptyStateView(
                            "No positions yet",
                            systemImage: "bag.badge.plus",
                            description: Text("Open any stock and tap \"I Bought This\" to track it here with live same-day sell alerts.")
                        )
                        .listRowBackground(Color.clear)
                    } else {
                        ForEach(store.positions) { position in
                            NavigationLink(value: position.symbol) {
                                PositionRow(position: position, signal: viewModel.liveSignals[position.symbol])
                            }
                            .swipeActions(edge: .trailing) {
                                Button("Sold") {
                                    sellSheetPosition = position
                                }
                                .tint(Theme.loss)
                                Button("Remove", role: .destructive) {
                                    store.remove(position)
                                }
                            }
                        }
                    }
                }
            }
            .listStyle(.plain)
            .navigationTitle("Portfolio")
            .luxuryBackground()
            .navigationDestination(for: String.self) { symbol in
                StockDetailView(symbol: symbol)
            }
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    if viewModel.isConnected {
                        Image(systemName: "dot.radiowaves.left.and.right")
                            .foregroundStyle(Theme.profit)
                            .help("Live updates connected")
                    }
                }
            }
            .task {
                NotificationManager.shared.requestAuthorization()
                viewModel.start(symbols: store.positions.map(\.symbol), baseURL: apiConfig.webSocketBaseURL)
                await refreshBrokerAccounts()
            }
            .onChange(of: store.positions) { newValue in
                viewModel.start(symbols: newValue.map(\.symbol), baseURL: apiConfig.webSocketBaseURL)
            }
            .onDisappear {
                viewModel.stop()
            }
            .refreshable {
                await refreshBrokerAccounts()
            }
            .sheet(item: $sellSheetPosition) { position in
                LogSaleSheet(
                    position: position,
                    suggestedPrice: viewModel.liveSignals[position.symbol]?.price
                ) { exitPrice in
                    let realizedPL = (exitPrice - position.entryPrice) * position.quantity
                    JournalStore.shared.log(
                        symbol: position.symbol,
                        side: "sell",
                        quantity: position.quantity,
                        price: exitPrice,
                        source: "manual",
                        realizedPL: realizedPL
                    )
                    store.remove(position)
                }
            }
        }
    }

    private func refreshBrokerAccounts() async {
        await portfolioViewModel.refresh(accounts: brokerStore.availableTradeAccounts, brokerStore: brokerStore, baseURL: apiConfig.baseURL)
    }
}

/// Summary card for one connected brokerage account: equity, cash, buying
/// power, and its open positions.
private struct BrokerAccountCard: View {
    let summary: PortfolioViewModel.AccountSummary

    private var currency: String { summary.currency ?? "USD" }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(summary.account.label)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                if summary.account.isLive {
                    Text("REAL MONEY")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(Theme.loss)
                }
            }

            HStack(spacing: 20) {
                if let equity = summary.equity {
                    statPair("Equity", equity.formatted(.currency(code: currency)))
                }
                if let cash = summary.cash {
                    statPair("Cash", cash.formatted(.currency(code: currency)))
                }
                if let buyingPower = summary.buyingPower {
                    statPair("Buying Power", buyingPower.formatted(.currency(code: currency)))
                }
            }

            if !summary.positions.isEmpty {
                Divider().overlay(Theme.cardBorder)
                ForEach(summary.positions) { holding in
                    HStack {
                        Text(holding.symbol)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Theme.textPrimary)
                        Text("\(holding.quantity.formatted()) sh")
                            .font(.caption2)
                            .foregroundStyle(Theme.textSecondary)
                        Spacer()
                        if let marketValue = holding.marketValue {
                            Text(marketValue.formatted(.currency(code: currency)))
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(Theme.textSecondary)
                        }
                        if let pl = holding.unrealizedPL {
                            Text("\(pl >= 0 ? "+" : "")\(pl.formatted(.currency(code: currency)))")
                                .font(.caption.weight(.semibold).monospacedDigit())
                                .foregroundStyle(pl >= 0 ? Theme.profit : Theme.loss)
                        }
                    }
                }
            }
        }
        .luxuryCard()
    }

    private func statPair(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
            Text(value)
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(Theme.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct PositionRow: View {
    let position: Position
    let signal: DaySignalResponse?

    private var currentPrice: Double? { signal?.price }

    private var profitLoss: Double? {
        guard let currentPrice else { return nil }
        return (currentPrice - position.entryPrice) * position.quantity
    }

    private var profitLossPercent: Double? {
        guard position.entryPrice != 0, let currentPrice else { return nil }
        return (currentPrice - position.entryPrice) / position.entryPrice
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(position.symbol)
                        .font(Theme.priceFont(20))
                        .foregroundStyle(Theme.textPrimary)
                    Text("\(position.quantity.formatted()) sh @ \(position.entryPrice.formatted(.currency(code: "USD")))")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                }

                Spacer()

                if let signal {
                    DayActionBadge(action: signal.action, confidence: signal.confidence)
                } else {
                    ProgressView()
                }
            }

            if let currentPrice, let pl = profitLoss, let plPercent = profitLossPercent {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Current Price")
                            .font(.caption2)
                            .foregroundStyle(Theme.textSecondary)
                        Text(currentPrice, format: .currency(code: "USD"))
                            .font(.subheadline.monospacedDigit())
                            .foregroundStyle(Theme.textPrimary)
                    }

                    Spacer()

                    VStack(alignment: .trailing, spacing: 2) {
                        Text("Unrealized P/L")
                            .font(.caption2)
                            .foregroundStyle(Theme.textSecondary)
                        Text("\(pl >= 0 ? "+" : "")\(pl.formatted(.currency(code: "USD"))) (\(plPercent, format: .percent.precision(.fractionLength(2))))")
                            .font(.subheadline.monospacedDigit())
                            .foregroundStyle(pl >= 0 ? Theme.profit : Theme.loss)
                    }
                }
            }

            if let alert = signal?.alert {
                AlertBanner(alert: alert)
            }

            if let signal {
                PositionCoachView(coach: PositionCoach.evaluate(position: position, signal: signal))
            }
        }
        .padding(.vertical, 6)
        .listRowBackground(Theme.card)
    }
}

/// "Sell/Hold Position Coach" - a plain-language Hold / Take Profit / Cut
/// Loss recommendation with a confidence percentage, based on the user's
/// real entry price vs. the live same-day signal.
private struct PositionCoachView: View {
    let coach: PositionCoachResult

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Image(systemName: coach.action.systemImage)
                Text("Coach: \(coach.action.label)")
                    .fontWeight(.semibold)
                Text("\(Int(coach.confidence))%")
                    .opacity(0.7)
                Spacer()
            }
            .font(.caption)
            .foregroundStyle(coach.action.color)

            Text(coach.message)
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
        }
        .padding(8)
        .background(coach.action.color.opacity(0.10))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

/// Sheet for recording the exit price when the user swipes "Sold" on a
/// tracked position, so realized P/L can be logged to the trade journal.
private struct LogSaleSheet: View {
    let position: Position
    let suggestedPrice: Double?
    let onSave: (Double) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var priceText: String = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    LabeledContent("Symbol", value: position.symbol)
                    LabeledContent("Entry Price", value: position.entryPrice.formatted(.currency(code: "USD")))
                    LabeledContent("Quantity", value: position.quantity.formatted())
                    LabeledContent("Exit Price") {
                        TextField("0.00", text: $priceText)
                            .decimalKeyboard()
                            .multilineTextAlignment(.trailing)
                    }
                } header: {
                    Text("Log Sale")
                } footer: {
                    Text("We'll record the realized profit or loss in your Trade Journal and stop tracking this position.")
                }
            }
            .navigationTitle("Sold \(position.symbol)")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        if let price = Double(priceText), price > 0 {
                            onSave(price)
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
