import SwiftUI
import UserNotifications
#if os(iOS)
import UIKit
#elseif os(macOS)
import AppKit
#endif

struct SettingsView: View {
    @EnvironmentObject private var apiConfig: APIConfig
    @EnvironmentObject private var brokerStore: BrokerStore
    @Environment(\.dismiss) private var dismiss
    @State private var urlText: String = ""
    @State private var statusMessage: String?
    @State private var isChecking = false

    @State private var apiKeyIdText: String = ""
    @State private var apiSecretKeyText: String = ""
    @State private var brokerStatusMessage: String?
    @State private var isCheckingBroker = false

    @State private var showLiveTradingConfirmation = false
    @State private var liveApiKeyIdText: String = ""
    @State private var liveApiSecretKeyText: String = ""
    @State private var liveBrokerStatusMessage: String?
    @State private var isCheckingLiveBroker = false

    @State private var questradeRefreshTokenText: String = ""
    @State private var questradeStatusMessage: String?
    @State private var isConnectingQuestrade = false

    @State private var notificationStatus: UNAuthorizationStatus = .notDetermined

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
                    LabeledContent("Status") {
                        Text(notificationStatusLabel)
                            .foregroundStyle(notificationStatusColor)
                    }
                    if notificationStatus == .notDetermined {
                        Button("Enable Notifications") {
                            NotificationManager.shared.requestAuthorization()
                            Task { await refreshNotificationStatus() }
                        }
                    } else if notificationStatus == .denied {
                        Button("Open Notification Settings") {
                            openSystemNotificationSettings()
                        }
                    }
                } header: {
                    Text("Notifications")
                } footer: {
                    Text("Stock Chance uses local notifications for watchlist price/signal alerts and \"time to sell\" position alerts - checked live while the app is open, and periodically in the background. For background alerts to arrive, enable notifications here and Background App Refresh in iOS Settings > General > Background App Refresh.")
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
                    Text("Alpaca Paper Trading")
                } footer: {
                    Text("Connect a free Alpaca paper-trading account to place simulated Buy/Sell orders from Stock Chance with no real money at risk. Get keys at alpaca.markets (Paper Trading API Keys). Stored securely in this device's Keychain - never sent anywhere except directly to Alpaca.")
                }

                Section {
                    Toggle("Enable Live Trading", isOn: Binding(
                        get: { brokerStore.liveTradingAcknowledged },
                        set: { newValue in
                            if newValue {
                                showLiveTradingConfirmation = true
                            } else {
                                brokerStore.liveTradingAcknowledged = false
                            }
                        }
                    ))
                    .tint(Theme.loss)
                } header: {
                    Text("Live Trading (Real Money)")
                } footer: {
                    Text("Enable this to connect a real Alpaca or Questrade account and place orders with real money. Every live order requires a separate confirmation before it's sent.")
                }
                .alert("Enable Live Trading?", isPresented: $showLiveTradingConfirmation) {
                    Button("Cancel", role: .cancel) {}
                    Button("I Understand - Enable", role: .destructive) {
                        brokerStore.liveTradingAcknowledged = true
                    }
                } message: {
                    Text("Live trading places REAL orders with REAL money through your Alpaca or Questrade account. Stock Chance's signals are educational technical analysis, not financial advice, and are not guaranteed to be profitable. You are solely responsible for any trades you place. Only continue if you understand and accept this risk.")
                }

                if brokerStore.liveTradingAcknowledged {
                    Section {
                        SecureField("Alpaca LIVE API Key ID", text: $liveApiKeyIdText)
                            #if os(iOS)
                            .autocorrectionDisabled()
                            .textInputAutocapitalization(.never)
                            #endif
                        SecureField("Alpaca LIVE API Secret Key", text: $liveApiSecretKeyText)
                            #if os(iOS)
                            .autocorrectionDisabled()
                            .textInputAutocapitalization(.never)
                            #endif
                        Button("Save & Test Connection") {
                            Task { await saveLiveAlpaca() }
                        }
                        if isCheckingLiveBroker {
                            ProgressView()
                        } else if let liveBrokerStatusMessage {
                            Text(liveBrokerStatusMessage)
                                .font(.caption)
                                .foregroundStyle(liveBrokerStatusMessage.hasPrefix("✅") ? .green : .red)
                        }
                        if brokerStore.liveCredentials.isConfigured {
                            Button("Remove Live Credentials", role: .destructive) {
                                brokerStore.clearLiveAlpaca()
                                liveApiKeyIdText = ""
                                liveApiSecretKeyText = ""
                                liveBrokerStatusMessage = nil
                            }
                        }
                    } header: {
                        Text("Alpaca Live Trading")
                    } footer: {
                        Text("Uses your Alpaca LIVE account API keys - these are different from your paper keys. Orders placed here use real money in your real brokerage account.")
                    }

                    Section {
                        if brokerStore.isQuestradeConfigured {
                            LabeledContent("Connected Account", value: brokerStore.questradeAccountNumber)
                            Button("Disconnect Questrade", role: .destructive) {
                                brokerStore.clearQuestrade()
                                questradeRefreshTokenText = ""
                                questradeStatusMessage = nil
                            }
                        } else {
                            SecureField("Questrade Refresh Token", text: $questradeRefreshTokenText)
                                #if os(iOS)
                                .autocorrectionDisabled()
                                .textInputAutocapitalization(.never)
                                #endif
                            Button("Connect") {
                                Task { await connectQuestrade() }
                            }
                        }
                        if isConnectingQuestrade {
                            ProgressView()
                        } else if let questradeStatusMessage {
                            Text(questradeStatusMessage)
                                .font(.caption)
                                .foregroundStyle(questradeStatusMessage.hasPrefix("✅") ? .green : .red)
                        }
                    } header: {
                        Text("Questrade Live Trading")
                    } footer: {
                        Text("Generate a personal refresh token from Questrade's App Hub (questrade.com -> My Apps -> Personal apps), then paste it here once. Stock Chance exchanges it for an access token and refreshes it automatically. Orders placed here use real money in your real brokerage account.")
                    }
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
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .onAppear {
                urlText = apiConfig.baseURL.absoluteString
                apiKeyIdText = brokerStore.apiKeyId
                apiSecretKeyText = brokerStore.apiSecretKey
                liveApiKeyIdText = brokerStore.liveApiKeyId
                liveApiSecretKeyText = brokerStore.liveApiSecretKey
            }
            .task {
                await refreshNotificationStatus()
            }
        }
    }

    private var notificationStatusLabel: String {
        switch notificationStatus {
        case .authorized, .provisional, .ephemeral: return "Enabled"
        case .denied: return "Denied"
        case .notDetermined: return "Not Enabled"
        @unknown default: return "Unknown"
        }
    }

    private var notificationStatusColor: Color {
        switch notificationStatus {
        case .authorized, .provisional, .ephemeral: return Theme.profit
        case .denied: return Theme.loss
        default: return Theme.textSecondary
        }
    }

    @MainActor
    private func refreshNotificationStatus() async {
        notificationStatus = await NotificationManager.shared.authorizationStatus()
    }

    private func openSystemNotificationSettings() {
        #if os(iOS)
        if let url = URL(string: UIApplication.openSettingsURLString) {
            UIApplication.shared.open(url)
        }
        #elseif os(macOS)
        if let url = URL(string: "x-apple.systempreferences:com.apple.Notifications-Settings.extension") {
            NSWorkspace.shared.open(url)
        }
        #endif
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
            let account = try await client.brokerAccount(credentials: brokerStore.paperCredentials)
            let value = account.portfolioValue.map { $0.formatted(.currency(code: account.currency ?? "USD")) } ?? "n/a"
            brokerStatusMessage = "✅ Connected (paper account, portfolio value \(value))"
        } catch {
            brokerStatusMessage = "❌ \(error.localizedDescription)"
        }
    }

    @MainActor
    private func saveLiveAlpaca() async {
        let keyId = liveApiKeyIdText.trimmingCharacters(in: .whitespacesAndNewlines)
        let secretKey = liveApiSecretKeyText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !keyId.isEmpty, !secretKey.isEmpty else {
            liveBrokerStatusMessage = "❌ Enter both your live API Key ID and Secret Key"
            return
        }
        brokerStore.liveApiKeyId = keyId
        brokerStore.liveApiSecretKey = secretKey

        isCheckingLiveBroker = true
        liveBrokerStatusMessage = nil
        defer { isCheckingLiveBroker = false }

        let client = APIClient(baseURL: apiConfig.baseURL)
        do {
            let account = try await client.brokerAccount(credentials: brokerStore.liveCredentials)
            let value = account.portfolioValue.map { $0.formatted(.currency(code: account.currency ?? "USD")) } ?? "n/a"
            liveBrokerStatusMessage = "✅ Connected to LIVE account (portfolio value \(value)). Orders placed against this account use real money."
        } catch {
            liveBrokerStatusMessage = "❌ \(error.localizedDescription)"
        }
    }

    @MainActor
    private func connectQuestrade() async {
        let token = questradeRefreshTokenText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !token.isEmpty else {
            questradeStatusMessage = "❌ Enter your Questrade refresh token"
            return
        }

        isConnectingQuestrade = true
        questradeStatusMessage = nil
        defer { isConnectingQuestrade = false }

        brokerStore.questradeRefreshToken = token
        let client = APIClient(baseURL: apiConfig.baseURL)
        do {
            try await brokerStore.refreshQuestradeToken(client: client)
            let accounts = try await client.questradeAccounts(credentials: brokerStore.questradeCredentials)
            guard let first = accounts.first else {
                brokerStore.clearQuestrade()
                questradeStatusMessage = "❌ No Questrade accounts found on this login."
                return
            }
            brokerStore.questradeAccountNumber = first.accountNumber
            questradeRefreshTokenText = ""
            questradeStatusMessage = "✅ Connected to Questrade account \(first.accountNumber). Orders placed against this account use real money."
        } catch {
            brokerStore.clearQuestrade()
            questradeStatusMessage = "❌ \(error.localizedDescription)"
        }
    }
}
