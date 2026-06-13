import SwiftUI

/// Sheet for placing a market order via Alpaca **paper trading** - lets the
/// user practice the Buy/Sell flow with no real money at risk.
struct BrokerOrderSheet: View {
    let symbol: String
    let side: String // "buy" | "sell"
    let suggestedPrice: Double?
    let credentials: BrokerCredentials
    let baseURL: URL

    @Environment(\.dismiss) private var dismiss
    @State private var quantityText: String = "1"
    @State private var isSubmitting = false
    @State private var resultMessage: String?
    @State private var didSucceed = false

    private var sideLabel: String { side == "buy" ? "Buy" : "Sell" }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    LabeledContent("Symbol", value: symbol)
                    LabeledContent("Side", value: sideLabel)
                    if let suggestedPrice {
                        LabeledContent("Last Price", value: suggestedPrice.formatted(.currency(code: "USD")))
                    }
                    LabeledContent("Quantity (shares)") {
                        TextField("1", text: $quantityText)
                            .decimalKeyboard()
                            .multilineTextAlignment(.trailing)
                    }
                } header: {
                    Text("Paper Trade Order")
                } footer: {
                    Text("Submitted as a market order to your Alpaca PAPER TRADING account - this is simulated money, not real money.")
                }

                if let resultMessage {
                    Section {
                        Text(resultMessage)
                            .font(.subheadline)
                            .foregroundStyle(didSucceed ? Theme.profit : Theme.loss)
                    }
                }
            }
            .navigationTitle("\(sideLabel) \(symbol)")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    if isSubmitting {
                        ProgressView()
                    } else {
                        Button(didSucceed ? "Done" : "Submit") {
                            if didSucceed {
                                dismiss()
                            } else {
                                Task { await submit() }
                            }
                        }
                    }
                }
            }
        }
    }

    @MainActor
    private func submit() async {
        guard let quantity = Double(quantityText), quantity > 0 else {
            resultMessage = "Enter a valid quantity greater than 0."
            didSucceed = false
            return
        }

        isSubmitting = true
        resultMessage = nil
        defer { isSubmitting = false }

        let order = BrokerOrderRequest(symbol: symbol, quantity: quantity, side: side)
        let client = APIClient(baseURL: baseURL)
        do {
            let placed = try await client.placeBrokerOrder(order, credentials: credentials)
            didSucceed = true
            resultMessage = "✅ Order submitted (status: \(placed.status ?? "accepted")). View it in your Alpaca paper account."
        } catch {
            didSucceed = false
            resultMessage = "❌ \(error.localizedDescription)"
        }
    }
}
