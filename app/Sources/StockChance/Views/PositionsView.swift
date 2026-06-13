import SwiftUI

/// "My Positions" tab - everything the user has marked as bought, with a
/// live current price, unrealized P/L, and same-day sell alerts driven by
/// the `/ws/daytrade` stream + local notifications.
struct PositionsView: View {
    @StateObject private var store = PositionStore.shared
    @StateObject private var viewModel = PositionsViewModel()
    @EnvironmentObject private var apiConfig: APIConfig

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("My Positions")
                .luxuryBackground()
                .navigationDestination(for: String.self) { symbol in
                    StockDetailView(symbol: symbol)
                }
                .task {
                    NotificationManager.shared.requestAuthorization()
                    viewModel.start(symbols: store.positions.map(\.symbol), baseURL: apiConfig.webSocketBaseURL)
                }
                .onChange(of: store.positions) { newValue in
                    viewModel.start(symbols: newValue.map(\.symbol), baseURL: apiConfig.webSocketBaseURL)
                }
                .onDisappear {
                    viewModel.stop()
                }
        }
    }

    @ViewBuilder
    private var content: some View {
        if store.positions.isEmpty {
            EmptyStateView(
                "No positions yet",
                systemImage: "bag.badge.plus",
                description: Text("Open any stock and tap \"I Bought This\" to track it here with live same-day sell alerts.")
            )
        } else {
            List {
                ForEach(store.positions) { position in
                    NavigationLink(value: position.symbol) {
                        PositionRow(position: position, signal: viewModel.liveSignals[position.symbol])
                    }
                    .swipeActions(edge: .trailing) {
                        Button("Sold", role: .destructive) {
                            store.remove(position)
                        }
                    }
                }
            }
            .listStyle(.plain)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    if viewModel.isConnected {
                        Image(systemName: "dot.radiowaves.left.and.right")
                            .foregroundStyle(Theme.profit)
                            .help("Live updates connected")
                    }
                }
            }
        }
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
