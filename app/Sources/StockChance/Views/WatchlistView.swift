import SwiftUI

struct WatchlistView: View {
    @StateObject private var store = WatchlistStore.shared
    @StateObject private var viewModel = WatchlistViewModel()
    @StateObject private var alertStore = WatchlistAlertStore.shared
    @State private var showSearch = false
    @State private var alertSheetSymbol: AlertSheetSymbol?
    @EnvironmentObject private var apiConfig: APIConfig

    var body: some View {
        NavigationStack {
            List {
                if store.symbols.isEmpty {
                    EmptyStateView(
                        "No symbols yet",
                        systemImage: "chart.line.uptrend.xyaxis",
                        description: Text("Tap + to search and add any stock, ETF or crypto symbol.")
                    )
                    .listRowBackground(Color.clear)
                } else {
                    ForEach(store.symbols, id: \.self) { symbol in
                        NavigationLink(value: symbol) {
                            WatchlistRow(
                                symbol: symbol,
                                update: viewModel.liveData[symbol],
                                hasAlert: alertStore.alert(for: symbol)?.isActive ?? false
                            )
                        }
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                        .listRowInsets(EdgeInsets(top: 6, leading: 16, bottom: 6, trailing: 16))
                        .swipeActions(edge: .trailing) {
                            Button("Remove", role: .destructive) {
                                store.remove(symbol)
                            }
                        }
                        .swipeActions(edge: .leading) {
                            Button {
                                alertSheetSymbol = AlertSheetSymbol(symbol: symbol)
                            } label: {
                                Label("Alert", systemImage: "bell")
                            }
                            .tint(Theme.gold)
                        }
                    }
                }
            }
            .listStyle(.plain)
            .luxuryBackground()
            .navigationTitle("Watchlist")
            .navigationDestination(for: String.self) { symbol in
                StockDetailView(symbol: symbol)
            }
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        showSearch = true
                    } label: {
                        Label("Add Symbol", systemImage: "plus")
                    }
                }
                ToolbarItem(placement: .cancellationAction) {
                    if viewModel.isConnected {
                        Image(systemName: "dot.radiowaves.left.and.right")
                            .foregroundStyle(Theme.profit)
                            .help("Live updates connected")
                    }
                }
            }
            .sheet(isPresented: $showSearch) {
                SearchView(onSelect: { symbol in
                    store.add(symbol)
                    showSearch = false
                })
            }
            .sheet(item: $alertSheetSymbol) { item in
                WatchlistAlertSheet(
                    symbol: item.symbol,
                    currentPrice: viewModel.liveData[item.symbol]?.quote?.price,
                    alertStore: alertStore
                )
            }
            .onAppear {
                viewModel.start(symbols: store.symbols, baseURL: apiConfig.webSocketBaseURL)
            }
            .onChange(of: store.symbols) { newValue in
                viewModel.start(symbols: newValue, baseURL: apiConfig.webSocketBaseURL)
            }
            .onDisappear {
                viewModel.stop()
            }
        }
    }
}

/// Identifies which symbol's alert sheet to present.
private struct AlertSheetSymbol: Identifiable {
    let symbol: String
    var id: String { symbol }
}

/// Premium watchlist card: symbol + signal-tinted accent, live price/change,
/// signal badge, and a bell glyph when a price/signal alert is configured.
private struct WatchlistRow: View {
    let symbol: String
    let update: LiveUpdate?
    let hasAlert: Bool

    private var accentColor: Color {
        update?.signal?.action.color ?? Theme.cardBorder
    }

    var body: some View {
        HStack(spacing: 14) {
            RoundedRectangle(cornerRadius: 3, style: .continuous)
                .fill(accentColor)
                .frame(width: 4, height: 44)
                .opacity(update?.signal != nil ? 1 : 0.3)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(symbol)
                        .font(Theme.priceFont(20))
                        .foregroundStyle(Theme.textPrimary)
                    if hasAlert {
                        Image(systemName: "bell.fill")
                            .font(.caption2)
                            .foregroundStyle(Theme.gold)
                    }
                }

                if let error = update?.error {
                    Text(error)
                        .font(.caption2)
                        .foregroundStyle(Theme.loss)
                        .lineLimit(1)
                } else if let quote = update?.quote, let changePercent = quote.changePercent {
                    HStack(spacing: 4) {
                        Image(systemName: changePercent >= 0 ? "arrow.up.right" : "arrow.down.right")
                        Text(changePercent / 100, format: .percent.precision(.fractionLength(2)))
                    }
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(changePercent >= 0 ? Theme.profit : Theme.loss)
                } else {
                    Text("Connecting...")
                        .font(.caption2)
                        .foregroundStyle(Theme.textSecondary)
                }
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 6) {
                if let quote = update?.quote {
                    Text(quote.price, format: .currency(code: quote.currency ?? "USD"))
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Theme.textPrimary)
                        .monospacedDigit()
                } else {
                    ProgressView()
                }

                if let signal = update?.signal {
                    SignalBadge(action: signal.action, confidence: signal.confidence)
                }
            }
        }
        .padding(.vertical, 6)
        .luxuryCard()
    }
}

/// Sheet for configuring a price-threshold and/or signal-change alert for a
/// single watched symbol. Notifications are delivered locally via
/// `NotificationManager`.
private struct WatchlistAlertSheet: View {
    let symbol: String
    let currentPrice: Double?
    @ObservedObject var alertStore: WatchlistAlertStore
    @Environment(\.dismiss) private var dismiss

    @State private var priceAboveText = ""
    @State private var priceBelowText = ""
    @State private var notifyOnSignalChange = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    if let currentPrice {
                        LabeledContent("Current Price", value: currentPrice.formatted(.currency(code: "USD")))
                    }
                    LabeledContent("Notify if price rises above") {
                        TextField("e.g. 250", text: $priceAboveText)
                            .decimalKeyboard()
                            .multilineTextAlignment(.trailing)
                    }
                    LabeledContent("Notify if price falls below") {
                        TextField("e.g. 200", text: $priceBelowText)
                            .decimalKeyboard()
                            .multilineTextAlignment(.trailing)
                    }
                    Toggle("Notify on signal change", isOn: $notifyOnSignalChange)
                } footer: {
                    Text("We'll send a local notification when \(symbol) crosses a price threshold or its Buy/Sell signal changes. Leave price fields blank to disable.")
                }

                if alertStore.alert(for: symbol)?.isActive == true {
                    Button("Remove Alert", role: .destructive) {
                        alertStore.remove(symbol)
                        dismiss()
                    }
                }
            }
            .navigationTitle("\(symbol) Alerts")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        NotificationManager.shared.requestAuthorization()
                        alertStore.set(WatchlistAlert(
                            symbol: symbol,
                            priceAbove: Double(priceAboveText),
                            priceBelow: Double(priceBelowText),
                            notifyOnSignalChange: notifyOnSignalChange
                        ))
                        dismiss()
                    }
                }
            }
            .onAppear {
                if let existing = alertStore.alert(for: symbol) {
                    priceAboveText = existing.priceAbove.map { String($0) } ?? ""
                    priceBelowText = existing.priceBelow.map { String($0) } ?? ""
                    notifyOnSignalChange = existing.notifyOnSignalChange
                }
            }
        }
    }
}
