import SwiftUI

/// Places a market order on a pair through OANDA. Lets the user pick the
/// environment (practice/live), the side (buy/sell), and a position size in
/// units, with a clear real-money confirmation for live orders.
struct OrderSheet: View {
    let pair: PairInfo
    var suggestedAction: TradeAction?

    @ObservedObject private var brokerStore = BrokerStore.shared
    @Environment(\.dismiss) private var dismiss

    @State private var environment: OandaEnvironment = .practice
    @State private var isBuy = true
    @State private var units: Double = 1000
    @State private var isSubmitting = false
    @State private var result: BrokerOrder?
    @State private var errorMessage: String?
    @State private var showLiveConfirm = false

    private var environments: [OandaEnvironment] { brokerStore.availableEnvironments }

    var body: some View {
        NavigationStack {
            ScreenBackground {
                Form {
                    Section {
                        if environments.count > 1 {
                            Picker("Account", selection: $environment) {
                                ForEach(environments) { env in
                                    Text(env.label).tag(env)
                                }
                            }
                        } else if let only = environments.first {
                            LabeledContent("Account", value: only.label)
                        }
                    }
                    .listRowBackground(Theme.card)

                    Section("Order") {
                        Picker("Side", selection: $isBuy) {
                            Text("Buy / Long").tag(true)
                            Text("Sell / Short").tag(false)
                        }
                        .pickerStyle(.segmented)

                        Stepper(value: $units, in: 1000...500000, step: 1000) {
                            VStack(alignment: .leading) {
                                Text("\(Int(units)) units")
                                    .font(.headline)
                                Text(lotLabel)
                                    .font(.caption)
                                    .foregroundStyle(Theme.textSecondary)
                            }
                        }
                    }
                    .listRowBackground(Theme.card)

                    if environment.isLive {
                        Section {
                            Label("This is a LIVE account — the order uses REAL money.", systemImage: "exclamationmark.triangle.fill")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(Theme.loss)
                        }
                        .listRowBackground(Theme.card)
                    }

                    if let result {
                        Section("Result") {
                            OrderResultView(order: result)
                        }
                        .listRowBackground(Theme.card)
                    }

                    if let errorMessage {
                        Section {
                            Text(errorMessage)
                                .font(.caption)
                                .foregroundStyle(Theme.loss)
                        }
                        .listRowBackground(Theme.card)
                    }
                }
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("Trade \(pair.display)")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
                ToolbarItem(placement: .primaryAction) {
                    Button(isBuy ? "Buy" : "Sell") {
                        if environment.isLive {
                            showLiveConfirm = true
                        } else {
                            Task { await submit() }
                        }
                    }
                    .disabled(isSubmitting)
                    .fontWeight(.semibold)
                }
            }
            .confirmationDialog(
                "Place a REAL-money \(isBuy ? "buy" : "sell") order for \(Int(units)) units of \(pair.display)?",
                isPresented: $showLiveConfirm,
                titleVisibility: .visible
            ) {
                Button("Place Live Order", role: .destructive) {
                    Task { await submit() }
                }
                Button("Cancel", role: .cancel) {}
            }
        }
        .onAppear {
            environment = environments.first ?? .practice
            if let suggestedAction { isBuy = suggestedAction.isBuy }
        }
    }

    private var lotLabel: String {
        switch units {
        case 100000...: return "\(String(format: "%.1f", units / 100000)) standard lot(s)"
        case 10000...: return "\(String(format: "%.1f", units / 10000)) mini lot(s)"
        default: return "\(String(format: "%.0f", units / 1000)) micro lot(s)"
        }
    }

    private func submit() async {
        isSubmitting = true
        errorMessage = nil
        result = nil
        defer { isSubmitting = false }

        let creds = brokerStore.credentials(for: environment)
        let signedUnits = isBuy ? units : -units
        let client = APIClient(baseURL: APIConfig.shared.baseURL)
        do {
            result = try await client.placeOrder(
                BrokerOrderRequest(pair: pair.pair, units: signedUnits, stopLossPrice: nil, takeProfitPrice: nil),
                creds: creds
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct OrderResultView: View {
    let order: BrokerOrder

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: order.wasFilled ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundStyle(order.wasFilled ? Theme.profit : Theme.loss)
                Text(order.wasFilled ? "Filled" : "Not filled")
                    .font(.headline)
                    .foregroundStyle(Theme.textPrimary)
            }
            if let price = order.fillPrice {
                Text("Fill price: \(String(format: "%.5f", price))")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
            }
            if let reason = order.reason {
                Text(reason)
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
            }
        }
    }
}
