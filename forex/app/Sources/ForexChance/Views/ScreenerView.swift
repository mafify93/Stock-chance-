import SwiftUI

struct ScreenerView: View {
    @StateObject private var viewModel = ScreenerViewModel()

    var body: some View {
        NavigationStack {
            ScreenBackground {
                Group {
                    if viewModel.isLoading && viewModel.response == nil {
                        ProgressView("Scanning pairs…").tint(Theme.accent)
                    } else if let error = viewModel.errorMessage, viewModel.response == nil {
                        InfoState(icon: "chart.bar.xaxis", title: "Couldn't run screener", message: error)
                    } else if let response = viewModel.response {
                        ScrollView {
                            VStack(spacing: 16) {
                                ScreenerBucket(title: "Buy", systemImage: "arrow.up.right", color: Theme.profit, items: response.buy)
                                ScreenerBucket(title: "Sell", systemImage: "arrow.down.right", color: Theme.loss, items: response.sell)
                                ScreenerBucket(title: "Hold", systemImage: "minus", color: Theme.neutral, items: response.hold)
                                DisclaimerText()
                            }
                            .padding()
                        }
                    } else {
                        InfoState(icon: "chart.bar.fill", title: "Forex Screener", message: "Pull to scan the major and cross pairs into Buy / Sell / Hold buckets.")
                    }
                }
            }
            .navigationTitle("Screener")
            .navigationDestination(for: PairInfo.self) { pair in
                PairDetailView(pair: pair)
            }
            .refreshable { await viewModel.refresh() }
        }
        .task { await viewModel.refresh() }
    }
}

private struct ScreenerBucket: View {
    let title: String
    let systemImage: String
    let color: Color
    let items: [ScreenerItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: systemImage).foregroundStyle(color)
                Text(title).font(Theme.sectionTitleFont()).foregroundStyle(Theme.textPrimary)
                Text("\(items.count)").font(.caption).foregroundStyle(Theme.textSecondary)
            }

            if items.isEmpty {
                Text("No \(title.lowercased()) signals right now.")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .padding(.bottom, 4)
            } else {
                ForEach(items) { item in
                    NavigationLink(value: PairInfo.from(code: item.pair)) {
                        ScreenerRow(item: item)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

private struct ScreenerRow: View {
    let item: ScreenerItem

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 3) {
                Text(item.display)
                    .font(.system(.headline, design: .rounded))
                    .foregroundStyle(Theme.textPrimary)
                Text(Format.price(item.price))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(Theme.textSecondary)
            }
            Spacer()
            if let change = item.changeFromOpenPips {
                Text(Format.pips(change))
                    .font(.caption.weight(.semibold).monospacedDigit())
                    .foregroundStyle(change >= 0 ? Theme.profit : Theme.loss)
            }
            SignalBadge(action: item.tradeAction, compact: true)
        }
        .cardStyle()
    }
}
