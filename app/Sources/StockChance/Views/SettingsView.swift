import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var apiConfig: APIConfig
    @EnvironmentObject private var brokerStore: BrokerStore
    @State private var urlText: String = ""
    @State private var statusMessage: String?
    @State private var isChecking = false

    @State private var apiKeyIdText: String = ""
    @State private var apiSecretKeyText: String = ""
    @State private var brokerStatusMessage: String?
    @State private var isCheckingBroker = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("http://127.0.0.1:8000", text: $urlText)
                        #if os(iOS)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        #endif
                    Button("Save & Test Connection") {
                        Task { await save() }
                    }
                    if isChecking {
                        ProgressView()
                    } else if let statusMessage {
                        Text(statusMessage)
                            .font(.caption)
                            .foregroundStyle(statusMessage.hasPrefix("✅") ? .green : .red)
                    }
                } header: {
                    Text("Backend Server")
                } footer: {
                    Text("Point this at your deployed Stock Chance backend (see /backend in the repo). For the iOS Simulator and Mac you can use http://127.0.0.1:8000 while running it locally; a physical iPhone needs your computer's LAN IP or a public URL.")
                }

                Section {
                    NavigationLink {
                        RiskCalculatorView()
                    } label: {
                        Label("Position Size Calculator", systemImage: "function")
                    }
                } header: {
                    Text("Risk Tools")
                } footer: {
                    Text("Figure out how many shares to buy based on your account size, how much you're willing to risk, and your stop-loss.")
                }

                Section {
                    SecureField("Alpaca API Key ID", text: $apiKeyIdText)
                        #if os(iOS)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        #endif
                    SecureField("Alpaca API Secret Key", text: $apiSecretKeyText)
                        #if os(iOS)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        #endif
                    Button("Save & Test Connection") {
                        Task { await saveBroker() }
                    }
                    if isCheckingBroker {
                        ProgressView()
                    } else if let brokerStatusMessage {
                        Text(brokerStatusMessage)
                            .font(.caption)
                            .foregroundStyle(brokerStatusMessage.hasPrefix("✅") ? .green : .red)
                    }
                    if brokerStore.isConfigured {
                        Button("Remove Credentials", role: .destructive) {
                            brokerStore.clear()
                            apiKeyIdText = ""
                            apiSecretKeyText = ""
                            brokerStatusMessage = nil
                        }
                    }
                } header: {
                    Text("Broker (Paper Trading)")
                } footer: {
                    Text("Connect a free Alpaca paper-trading account to place simulated Buy/Sell orders from Stock Chance with no real money at risk. Get keys at alpaca.markets (Paper Trading API Keys). Stored securely in this device's Keychain - never sent anywhere except directly to Alpaca.")
                }

                Section("About") {
                    LabeledContent("Data Source", value: "Yahoo Finance (free)")
                    LabeledContent("Signal Engine", value: "Technical analysis (RSI, MACD, SMA/EMA, Bollinger Bands, Stochastic, ADX, ATR)")
                    LabeledContent("Day Trading", value: "Same-day VWAP, opening range, momentum & volume signals")
                    Text("Signals are educational technical-analysis output, not financial advice. Markets are risky - never trade money you can't afford to lose.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            .luxuryBackground()
            .onAppear {
                urlText = apiConfig.baseURL.absoluteString
                apiKeyIdText = brokerStore.apiKeyId
                apiSecretKeyText = brokerStore.apiSecretKey
            }
        }
    }

    @MainActor
    private func save() async {
        var trimmed = urlText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.lowercased().hasPrefix("http://") && !trimmed.lowercased().hasPrefix("https://") {
            trimmed = "http://" + trimmed
        }
        guard let url = URL(string: trimmed),
              let scheme = url.scheme, !scheme.isEmpty,
              let host = url.host, !host.isEmpty else {
            statusMessage = "❌ Invalid URL - example: http://10.0.0.221:8000"
            return
        }
        urlText = trimmed
        apiConfig.baseURL = url
        isChecking = true
        statusMessage = nil
        defer { isChecking = false }

        do {
            let (_, response) = try await URLSession.shared.data(from: url.appendingPathComponent("/health"))
            if let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) {
                statusMessage = "✅ Connected"
            } else {
                statusMessage = "❌ Server responded with an error"
            }
        } catch {
            statusMessage = "❌ \(error.localizedDescription)"
        }
    }

    @MainActor
    private func saveBroker() async {
        let keyId = apiKeyIdText.trimmingCharacters(in: .whitespacesAndNewlines)
        let secretKey = apiSecretKeyText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !keyId.isEmpty, !secretKey.isEmpty else {
            brokerStatusMessage = "❌ Enter both your API Key ID and Secret Key"
            return
        }
        brokerStore.apiKeyId = keyId
        brokerStore.apiSecretKey = secretKey

        isCheckingBroker = true
        brokerStatusMessage = nil
        defer { isCheckingBroker = false }

        let client = APIClient(baseURL: apiConfig.baseURL)
        do {
            let account = try await client.brokerAccount(credentials: brokerStore.credentials)
            let value = account.portfolioValue.map { $0.formatted(.currency(code: account.currency ?? "USD")) } ?? "n/a"
            brokerStatusMessage = "✅ Connected (paper account, portfolio value \(value))"
        } catch {
            brokerStatusMessage = "❌ \(error.localizedDescription)"
        }
    }
}
