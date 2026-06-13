import SwiftUI

/// Sheet for placing a market order via Alpaca (paper or live) or Questrade
/// (live). Paper trading lets the user practice the Buy/Sell flow with no
/// real money at risk; live accounts (Alpaca live, Questrade) place REAL
/// orders with REAL money and require an extra confirmation before submit.
struct BrokerOrderSheet: View {
    let symbol: String
    let side: String // "buy" | "sell"
    let suggestedPrice: Double?
    let baseURL: URL

    @EnvironmentObject private var brokerStore: BrokerStore
    @Environment(\.dismiss) private var dismiss

    @State private var quantityText: String = "1"
    @State private var selectedAccount: TradeAccount?
    @State private var isSubmitting = false
    @State private var resultMessage: String?
    @State private var didSucceed = false
    @State private var showLiveConfirmation = false

    private var sideLabel: String { side == "buy" ? "Buy" : "Sell" }
    private var accounts: [TradeAccount] { brokerStore.availableTradeAccounts }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    LabeledContent("Symbol", value: symbol)
                    LabeledContent("Side", value: sideLabel)
                    if let suggestedPrice {
                        LabeledContent("Last Price", value: suggestedPrice.formatted(.currency(code: "USD")))
                    }
                    if accounts.count > 1 {
                        Picker("Account", selection: $selectedAccount) {
                            ForEach(accounts) { account in
                                Text(account.label).tag(Optional(account))
                            }
                        }
                    } else if let only = accounts.first {
                        LabeledContent("Account", value: only.label)
                    }
                    LabeledContent("Quantity (shares)") {
                        TextField("1", text: $quantityText)
                            .decimalKeyboard()
                            .multilineTextAlignment(.trailing)
                    }
                } header: {
                    Text("Order")
                } footer: {
                    if selectedAccount?.isLive == true {
                        Text("⚠️ LIVE TRADING - this submits a REAL market order with REAL money to \(selectedAccount?.label ?? "your live account").")
                    } else {
                        Text("Submitted as a market order to your Alpaca PAPER TRADING account - this is simulated money, not real money.")
                    }
                }

                if selectedAccount?.isLive == true {
                    Section {
                        Label("This order uses real money and cannot be undone once submitted.", systemImage: "exclamationmark.triangle.fill")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(Theme.loss)
                    }
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
                    } else if didSucceed {
                        Button("Done") { dismiss() }
                    } else {
                        Button(selectedAccount?.isLive == true ? "Review Order" : "Submit") {
                            if selectedAccount?.isLive == true {
                                showLiveConfirmation = true
                            } else {
                                Task { await submit() }
                            }
                        }
                        .disabled(selectedAccount == nil)
                    }
                }
            }
            .onAppear {
                if selectedAccount == nil {
                    selectedAccount = accounts.first
                }
            }
            .alert("Confirm LIVE Order", isPresented: $showLiveConfirmation) {
                Button("Cancel", role: .cancel) {}
                Button("Place Real Order", role: .destructive) {
                    Task { await submit() }
                }
            } message: {
                Text("This will \(sideLabel.lowercased()) \(quantityText) share(s) of \(symbol) using REAL money in \(selectedAccount?.label ?? "your live account"). This cannot be undone. Are you sure?")
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
        guard let account = selectedAccount else {
            resultMessage = "Select an account first."
            didSucceed = false
            return
        }

        isSubmitting = true
        resultMessage = nil
        defer { isSubmitting = false }

        let client = APIClient(baseURL: baseURL)

        do {
            switch account {
            case .alpacaPaper:
                let order = BrokerOrderRequest(symbol: symbol, quantity: quantity, side: side)
                let placed = try await client.placeBrokerOrder(order, credentials: brokerStore.paperCredentials)
                didSucceed = true
                resultMessage = "✅ Order submitted (status: \(placed.status ?? "accepted")). View it in your Alpaca paper account."

            case .alpacaLive:
                let order = BrokerOrderRequest(symbol: symbol, quantity: quantity, side: side)
                let placed = try await client.placeBrokerOrder(order, credentials: brokerStore.liveCredentials)
                didSucceed = true
                resultMessage = "✅ LIVE order submitted (status: \(placed.status ?? "accepted")). View it in your Alpaca account."

            case .questrade(let accountNumber):
                if brokerStore.isQuestradeAccessTokenExpired {
                    try await brokerStore.refreshQuestradeToken(client: client)
                }
                let matches = try await client.questradeSymbols(symbol, credentials: brokerStore.questradeCredentials)
                guard let match = matches.first(where: { $0.symbol.uppercased() == symbol.uppercased() }) else {
                    didSucceed = false
                    resultMessage = "❌ Couldn't find \(symbol) on Questrade."
                    return
                }
                let order = QuestradeOrderRequest(
                    accountNumber: accountNumber,
                    symbolId: match.symbolId,
                    symbol: symbol,
                    quantity: quantity,
                    side: side == "buy" ? "Buy" : "Sell"
                )
                let placed = try await client.placeQuestradeOrder(order, credentials: brokerStore.questradeCredentials)
                didSucceed = true
                resultMessage = "✅ LIVE order submitted (status: \(placed.state ?? "accepted")). View it in your Questrade account."
            }
        } catch {
            didSucceed = false
            resultMessage = "❌ \(error.localizedDescription)"
        }
    }
}
