import SwiftUI

struct PositionsView: View {
    @StateObject private var viewModel = PositionsViewModel()
    @EnvironmentObject private var brokerStore: BrokerStore

    var body: some View {
        NavigationStack {
            ScreenBackground {
                Group {
                    if brokerStore.availableEnvironments.isEmpty {
                        InfoState(
                            icon: "key.fill",
                            title: "Connect OANDA",
                            message: "Add your OANDA API token and account ID in Settings to see your account and positions."
                        )
                    } else {
                        ScrollView {
                            VStack(spacing: 16) {
                                if brokerStore.availableEnvironments.count > 1 {
                                    Picker("Environment", selection: $viewModel.environment) {
                                        ForEach(brokerStore.availableEnvironments) { env in
                                            Text(env.label).tag(env)
                                        }
                                    }
                                    .pickerStyle(.segmented)
                                    .onChange(of: viewModel.environment) { _ in
                                        Task { await viewModel.refresh() }
                                    }
                                }

                                if let account = viewModel.account {
                                    AccountCard(account: account)
                                }

                                if viewModel.isLoading && viewModel.account == nil {
                                    ProgressView().tint(Theme.accent).padding(.top, 30)
                                }

                                if let error = viewModel.errorMessage {
                                    InfoState(icon: "exclamationmark.triangle.fill", title: "Couldn't load", message: error)
                                }

                                if viewModel.positions.isEmpty && viewModel.account != nil {
                                    Text("No open positions.")
                                        .font(.subheadline)
                                        .foregroundStyle(Theme.textSecondary)
                                        .padding(.top, 8)
                                } else {
                                    ForEach(viewModel.positions) { position in
                                        PositionCard(position: position) {
                                            Task { await viewModel.close(position) }
                                        }
                                    }
                                }
                            }
                            .padding()
                        }
                    }
                }
            }
            .navigationTitle("Positions")
            .refreshable { await viewModel.refresh() }
            .alert("OANDA", isPresented: Binding(
                get: { viewModel.actionMessage != nil },
                set: { if !$0 { viewModel.actionMessage = nil } }
            )) {
                Button("OK", role: .cancel) { viewModel.actionMessage = nil }
            } message: {
                Text(viewModel.actionMessage ?? "")
            }
        }
        .task { await viewModel.refresh() }
    }
}

private struct AccountCard: View {
    let account: BrokerAccount

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(account.alias ?? "Account")
                    .font(Theme.sectionTitleFont())
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                if let currency = account.currency {
                    Text(currency)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Theme.accentBright)
                }
            }

            Text(Format.money(account.nav, currency: account.currency))
                .font(Theme.priceFont(32))
                .foregroundStyle(Theme.textPrimary)
            Text("Net Asset Value")
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)

            Divider().overlay(Theme.cardBorder)

            HStack {
                StatTile(label: "Balance", value: Format.money(account.balance))
                StatTile(label: "Unrealized P/L", value: Format.signedMoney(account.unrealizedPl),
                         valueColor: (account.unrealizedPl ?? 0) >= 0 ? Theme.profit : Theme.loss)
                StatTile(label: "Margin Avail.", value: Format.money(account.marginAvailable))
            }
        }
        .cardStyle()
    }
}

private struct PositionCard: View {
    let position: BrokerPosition
    let onClose: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text(position.display)
                        .font(.system(.headline, design: .rounded))
                        .foregroundStyle(Theme.textPrimary)
                    Text("\(position.isLong ? "Long" : "Short") · \(Int(position.units)) units @ \(Format.price(position.avgPrice))")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                }
                Spacer()
                Text(position.isLong ? "LONG" : "SHORT")
                    .font(.system(.caption, design: .rounded).weight(.bold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(Capsule().fill(position.isLong ? Theme.profit : Theme.loss))
            }

            HStack {
                StatTile(label: "Unrealized P/L", value: Format.signedMoney(position.unrealizedPl),
                         valueColor: (position.unrealizedPl ?? 0) >= 0 ? Theme.profit : Theme.loss)
                Spacer()
                Button(role: .destructive) {
                    onClose()
                } label: {
                    Text("Close")
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 16).padding(.vertical, 8)
                        .background(Capsule().fill(Theme.loss.opacity(0.18)))
                        .foregroundStyle(Theme.loss)
                }
                .buttonStyle(.plain)
            }
        }
        .cardStyle()
    }
}
