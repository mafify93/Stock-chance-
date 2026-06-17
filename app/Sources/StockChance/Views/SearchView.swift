import SwiftUI

/// Search any stock, ETF, crypto or FX symbol available on Yahoo Finance.
///
/// - When `onSelect` is provided (e.g. presented as a sheet from the
///   watchlist's "+" button), tapping a result calls it and the caller is
///   expected to dismiss.
/// - When `onSelect` is nil (e.g. used as its own tab), tapping a result
///   pushes the stock detail screen.
struct SearchView: View {
    var onSelect: ((String) -> Void)? = nil

    @StateObject private var viewModel = SearchViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("Search")
                .searchable(text: $viewModel.query, placement: .automatic, prompt: "Symbol or company name")
                .toolbar {
                    if onSelect != nil {
                        ToolbarItem(placement: .cancellationAction) {
                            Button("Cancel") { dismiss() }
                        }
                    }
                }
                .luxuryBackground()
        }
    }

    @ViewBuilder
    private var content: some View {
        if viewModel.isLoading {
            ProgressView()
        } else if let error = viewModel.errorMessage {
            EmptyStateView("Search failed", systemImage: "exclamationmark.triangle", description: Text(error))
        } else if viewModel.query.isEmpty {
            EmptyStateView(
                "Search all stocks",
                systemImage: "magnifyingglass",
                description: Text("Find any stock, ETF, index, crypto or FX symbol, e.g. \"Apple\" or \"AAPL\".")
            )
        } else if viewModel.results.isEmpty {
            EmptyStateView.search
        } else {
            List(viewModel.results) { result in
                if let onSelect {
                    Button {
                        onSelect(result.symbol)
                    } label: {
                        SearchResultRow(result: result)
                    }
                    .buttonStyle(.plain)
                    .listRowBackground(Theme.card)
                } else {
                    NavigationLink(value: result.symbol) {
                        SearchResultRow(result: result)
                    }
                    .listRowBackground(Theme.card)
                }
            }
            .listStyle(.plain)
            .navigationDestination(for: String.self) { symbol in
                StockDetailView(symbol: symbol)
            }
        }
    }
}

private struct SearchResultRow: View {
    let result: SearchResult

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(result.symbol)
                    .font(.headline)
                    .foregroundStyle(Theme.textPrimary)
                if let type = result.type {
                    Text(type.capitalized)
                        .font(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Theme.gold.opacity(0.15))
                        .foregroundStyle(Theme.gold)
                        .clipShape(Capsule())
                }
            }
            if let name = result.name {
                Text(name)
                    .font(.subheadline)
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(1)
            }
            if let exchange = result.exchange {
                Text(exchange)
                    .font(.caption2)
                    .foregroundStyle(Theme.textSecondary.opacity(0.7))
            }
        }
    }
}
