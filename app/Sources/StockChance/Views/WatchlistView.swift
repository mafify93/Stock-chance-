import SwiftUI

struct WatchlistView: View {
    @StateObject private var store = WatchlistStore.shared
    @StateObject private var viewModel = WatchlistViewModel()
    @State private var showSearch = false
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
                            WatchlistRow(symbol: symbol, update: viewModel.liveData[symbol])
                        }
                    }
                    .onDelete { offsets in
                        for index in offsets {
                            store.remove(store.symbols[index])
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

private struct WatchlistRow: View {
    let symbol: String
    let update: LiveUpdate?

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(symbol)
                    .font(.headline)
                    .foregroundStyle(Theme.textPrimary)
                if let error = update?.error {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(Theme.loss)
                        .lineLimit(1)
                }
            }

            Spacer()

            if let quote = update?.quote {
                VStack(alignment: .trailing, spacing: 4) {
                    Text(quote.price, format: .currency(code: quote.currency ?? "USD"))
                        .font(.subheadline)
                        .foregroundStyle(Theme.textPrimary)
                        .monospacedDigit()
                    if let changePercent = quote.changePercent {
                        Text(changePercent / 100, format: .percent.precision(.fractionLength(2)))
                            .font(.caption)
                            .foregroundStyle(changePercent >= 0 ? Theme.profit : Theme.loss)
                            .monospacedDigit()
                    }
                }
            } else {
                ProgressView()
            }

            if let signal = update?.signal {
                SignalBadge(action: signal.action, confidence: signal.confidence)
                    .frame(width: 90)
            }
        }
        .padding(.vertical, 4)
        .listRowBackground(Theme.card)
    }
}
