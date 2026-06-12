import SwiftUI

/// "What to buy / what to sell right now" - scans either a curated universe
/// of popular stocks/ETFs or the user's watchlist and ranks them.
struct ScreenerView: View {
    @State private var viewModel = ScreenerViewModel()
    @State private var watchlist = WatchlistStore.shared

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("Screener")
                .toolbar {
                    ToolbarItem(placement: .primaryAction) {
                        Button {
                            Task { await viewModel.refresh(watchlistSymbols: watchlist.symbols) }
                        } label: {
                            Label("Refresh", systemImage: "arrow.clockwise")
                        }
                        .disabled(viewModel.isLoading)
                    }
                }
                .safeAreaInset(edge: .top) {
                    Picker("Universe", selection: $viewModel.useWatchlist) {
                        Text("Popular Stocks").tag(false)
                        Text("My Watchlist").tag(true)
                    }
                    .pickerStyle(.segmented)
                    .padding(.horizontal)
                    .padding(.top, 8)
                }
                .onChange(of: viewModel.useWatchlist) { _, _ in
                    Task { await viewModel.refresh(watchlistSymbols: watchlist.symbols) }
                }
                .task {
                    if viewModel.response == nil {
                        await viewModel.refresh(watchlistSymbols: watchlist.symbols)
                    }
                }
        }
    }

    @ViewBuilder
    private var content: some View {
        if viewModel.isLoading && viewModel.response == nil {
            ProgressView("Scanning the market...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = viewModel.errorMessage, viewModel.response == nil {
            ContentUnavailableView("Couldn't load screener", systemImage: "exclamationmark.triangle", description: Text(error))
        } else if let response = viewModel.response {
            List {
                section(title: "Buy Candidates", items: response.buy, emptyText: "No strong buy signals right now.")
                section(title: "Sell Candidates", items: response.sell, emptyText: "No strong sell signals right now.")
                section(title: "Hold / Neutral", items: response.hold, emptyText: "Nothing neutral right now.")
            }
            .navigationDestination(for: String.self) { symbol in
                StockDetailView(symbol: symbol)
            }
        }
    }

    private func section(title: String, items: [ScreenerItem], emptyText: String) -> some View {
        Section(title) {
            if items.isEmpty {
                Text(emptyText)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(items) { item in
                    NavigationLink(value: item.symbol) {
                        ScreenerRow(item: item)
                    }
                }
            }
        }
    }
}

private struct ScreenerRow: View {
    let item: ScreenerItem

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.symbol)
                    .font(.headline)
                Text(item.price, format: .currency(code: "USD"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let change = item.changePercent {
                Text(change / 100, format: .percent.precision(.fractionLength(2)))
                    .font(.caption)
                    .foregroundStyle(change >= 0 ? .green : .red)
                    .frame(width: 70, alignment: .trailing)
            }
            SignalBadge(action: item.action, confidence: item.confidence)
        }
    }
}

#Preview {
    ScreenerView()
        .environmentObject(APIConfig.shared)
}
