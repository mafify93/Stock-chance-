import SwiftUI

/// "What to buy / what to sell right now" - scans either a curated universe
/// of popular stocks/ETFs or the user's watchlist and ranks them.
struct ScreenerView: View {
    @StateObject private var viewModel = ScreenerViewModel()
    @StateObject private var watchlist = WatchlistStore.shared

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
                .onChange(of: viewModel.useWatchlist) { _ in
                    Task { await viewModel.refresh(watchlistSymbols: watchlist.symbols) }
                }
                .task {
                    if viewModel.response == nil {
                        await viewModel.refresh(watchlistSymbols: watchlist.symbols)
                    }
                }
                .luxuryBackground()
        }
    }

    @ViewBuilder
    private var content: some View {
        if viewModel.isLoading && viewModel.response == nil {
            ProgressView("Scanning the market...\nThis can take up to a minute.")
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = viewModel.errorMessage, viewModel.response == nil {
            VStack(spacing: 16) {
                EmptyStateView("Couldn't load screener", systemImage: "exclamationmark.triangle", description: Text(error))
                Button("Try Again") {
                    Task { await viewModel.refresh(watchlistSymbols: watchlist.symbols) }
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.gold)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let response = viewModel.response {
            List {
                if response.buy.isEmpty && response.sell.isEmpty && response.hold.isEmpty {
                    Section {
                        Text("No results came back this time - the data provider may be busy. Pull down to refresh.")
                            .font(.subheadline)
                            .foregroundStyle(Theme.textSecondary)
                            .listRowBackground(Color.clear)
                    }
                }
                section(title: "Buy Candidates", items: response.buy, emptyText: "No strong buy signals right now.")
                section(title: "Sell Candidates", items: response.sell, emptyText: "No strong sell signals right now.")
                section(title: "Hold / Neutral", items: response.hold, emptyText: "Nothing neutral right now.")
            }
            .listStyle(.plain)
            .refreshable { await viewModel.refresh(watchlistSymbols: watchlist.symbols) }
            .navigationDestination(for: String.self) { symbol in
                StockDetailView(symbol: symbol)
            }
        } else {
            VStack(spacing: 16) {
                EmptyStateView(
                    "Ready to scan",
                    systemImage: "chart.bar",
                    description: Text("Tap below to rank stocks into Buy / Sell / Hold.")
                )
                Button("Scan Now") {
                    Task { await viewModel.refresh(watchlistSymbols: watchlist.symbols) }
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.gold)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func section(title: String, items: [ScreenerItem], emptyText: String) -> some View {
        Section {
            if items.isEmpty {
                Text(emptyText)
                    .font(.subheadline)
                    .foregroundStyle(Theme.textSecondary)
                    .listRowBackground(Color.clear)
            } else {
                ForEach(items) { item in
                    NavigationLink(value: item.symbol) {
                        ScreenerRow(item: item)
                    }
                    .listRowBackground(Theme.card)
                }
            }
        } header: {
            Text(title)
                .luxuryEyebrow()
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
                    .foregroundStyle(Theme.textPrimary)
                Text(item.price, format: .currency(code: "USD"))
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
            }
            Spacer()
            if let change = item.changePercent {
                Text(change / 100, format: .percent.precision(.fractionLength(2)))
                    .font(.caption)
                    .foregroundStyle(change >= 0 ? Theme.profit : Theme.loss)
                    .frame(width: 70, alignment: .trailing)
            }
            SignalBadge(action: item.action, confidence: item.confidence)
        }
    }
}
