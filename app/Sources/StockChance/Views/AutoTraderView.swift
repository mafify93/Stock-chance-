import SwiftUI

/// Configuration screen for the AI Auto-Trader: lets the user choose which
/// broker (Alpaca or Questrade) and symbols to watch, how confident the
/// combined AI signal must be before acting, position sizing limits, and -
/// with explicit double confirmation - whether it's allowed to place REAL
/// orders with REAL money.
///
/// Disabled by default. Real-money orders additionally require
/// `confirmedRealMoney`, mirroring the "Enable Live Trading" pattern in
/// Settings. Questrade has no paper-trading mode, so it always requires this
/// confirmation; Alpaca only requires it when `environment == "live"`.
struct AutoTraderView: View {
    @EnvironmentObject private var apiConfig: APIConfig
    @EnvironmentObject private var brokerStore: BrokerStore
    @StateObject private var viewModel = AutoTraderViewModel()

    @State private var enabled = false
    @State private var broker = "alpaca" // "alpaca" | "questrade"
    @State private var symbolsText = ""
    @State private var autoSelect = false
    @State private var autoSelectCount = 5
    @State private var maxOpenPositions = 5
    @State private var minConfidence: Double = 70
    @State private var maxPositionValueText = "100"
    @State private var maxDailyTrades = 3
    @State private var pollIntervalMinutes = 15
    @State private var environmentSelection = "paper"
    @State private var confirmedRealMoney = false
    @State private var alpacaApiKeyId = ""
    @State private var alpacaApiSecretKey = ""
    @State private var questradeRefreshToken = ""
    @State private var questradeAccountNumber = ""

    @State private var hasLoadedConfig = false
    @State private var showEnableConfirmation = false
    @State private var showRealMoneyConfirmation = false
    @State private var saveMessage: String?

    var body: some View {
        NavigationStack {
            Form {
                statusSection
                brokerSection
                symbolsSection
                strategySection
                environmentSection
                credentialsSection
                actionsSection
                decisionsSection
                disclaimerSection
            }
            .navigationTitle("AI Auto-Trader")
            .luxuryBackground()
            .task {
                await viewModel.load(baseURL: apiConfig.baseURL)
                if !hasLoadedConfig, let config = viewModel.status?.config {
                    apply(config)
                    hasLoadedConfig = true
                }
            }
        }
    }

    // MARK: - Sections

    private var statusSection: some View {
        Section {
            Toggle("Enable Auto-Trader", isOn: Binding(
                get: { enabled },
                set: { newValue in
                    if newValue {
                        showEnableConfirmation = true
                    } else {
                        enabled = false
                    }
                }
            ))
            .tint(Theme.gold)

            if let status = viewModel.status {
                LabeledContent("Trades Today", value: "\(status.tradesToday) / \(maxDailyTrades)")
                if let lastRunAt = status.lastRunAt {
                    LabeledContent("Last Run", value: relativeDate(lastRunAt))
                }
            } else if viewModel.isLoading {
                ProgressView()
            } else if let errorMessage = viewModel.errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(Theme.loss)
            }
        } header: {
            Text("AI Auto-Trader")
        } footer: {
            Text("When enabled, Stock Chance evaluates your symbols below on a schedule during market hours, combining the technical signal, ML model, and AI analyst into one decision - and can place orders through your selected broker automatically, with no per-trade confirmation.")
        }
        .alert("Enable AI Auto-Trader?", isPresented: $showEnableConfirmation) {
            Button("Cancel", role: .cancel) {}
            Button("I Understand - Enable", role: .destructive) {
                enabled = true
            }
        } message: {
            Text("The AI Auto-Trader will automatically evaluate your chosen symbols and place buy/sell orders based on its own analysis, with no further confirmation from you. Double-check your symbols, position size, and environment below before enabling.")
        }
    }

    private var brokerSection: some View {
        Section {
            Picker("Broker", selection: $broker) {
                Text("Alpaca").tag("alpaca")
                Text("Questrade").tag("questrade")
            }
            .pickerStyle(.segmented)
        } header: {
            Text("Broker")
        } footer: {
            if broker == "questrade" {
                Text("Questrade (Canadian brokerage) has no paper-trading mode - the auto-trader always acts on your real account, gated by Confirm Real-Money Trading below.")
            } else {
                Text("Alpaca supports a simulated paper account, so you can test the auto-trader risk-free before switching to live.")
            }
        }
    }

    private var symbolsSection: some View {
        Section {
            Toggle("Let the AI pick symbols", isOn: $autoSelect)
                .tint(Theme.gold)

            if autoSelect {
                Stepper("Trade top \(autoSelectCount) ideas", value: $autoSelectCount, in: 1...20)
            } else {
                TextField("AAPL, MSFT, TSLA", text: $symbolsText)
                    #if os(iOS)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.characters)
                    #endif
            }
        } header: {
            Text("Symbols")
        } footer: {
            if autoSelect {
                Text("The AI scans a broad universe of liquid US stocks & ETFs every cycle and trades only its highest-conviction ideas - you don't pick the symbols. It still respects every limit below (confidence, position size, daily trade cap, and max open positions).")
            } else {
                Text("Comma-separated list of symbols for the auto-trader to watch and trade.")
            }
        }
    }

    private var strategySection: some View {
        Section {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("Minimum Confidence")
                        .foregroundStyle(Theme.textPrimary)
                    InfoTooltip(title: TradingGlossary.confidence.0, text: TradingGlossary.confidence.1)
                    Spacer()
                    Text("\(Int(minConfidence))%")
                        .foregroundStyle(Theme.textSecondary)
                }
                Slider(value: $minConfidence, in: 0...100, step: 5)
            }
            LabeledContent("Max Position Value") {
                TextField("100", text: $maxPositionValueText)
                    .decimalKeyboard()
                    .multilineTextAlignment(.trailing)
            }
            Stepper("Max Trades / Day: \(maxDailyTrades)", value: $maxDailyTrades, in: 0...20)
            Stepper("Max Open Positions: \(maxOpenPositions)", value: $maxOpenPositions, in: 1...50)
            Stepper("Check Every \(pollIntervalMinutes) min", value: $pollIntervalMinutes, in: 5...120, step: 5)
        } header: {
            Text("Strategy")
        } footer: {
            Text("Only acts when the combined AI signal meets this confidence level. Max Position Value caps the dollar amount per buy order; Max Open Positions caps how many holdings it can run at once (your total risk ≈ Max Position Value × Max Open Positions). The auto-trader never adds to an existing position.")
        }
    }

    /// Whether the configured combination requires the real-money
    /// confirmation: Questrade always (no paper mode), Alpaca only when
    /// `environment == "live"`.
    private var isLiveSelection: Bool {
        broker == "questrade" || environmentSelection == "live"
    }

    private var environmentSection: some View {
        Section {
            if broker == "alpaca" {
                Picker("Environment", selection: $environmentSelection) {
                    Text("Paper (Simulated)").tag("paper")
                    Text("Live (Real Money)").tag("live")
                }
                .pickerStyle(.segmented)
            }

            if isLiveSelection {
                Toggle("Confirm Real-Money Trading", isOn: Binding(
                    get: { confirmedRealMoney },
                    set: { newValue in
                        if newValue {
                            showRealMoneyConfirmation = true
                        } else {
                            confirmedRealMoney = false
                        }
                    }
                ))
                .tint(Theme.loss)
            }
        } header: {
            Text("Environment")
        } footer: {
            if isLiveSelection && !confirmedRealMoney {
                Text("Live decisions will be logged as DRY RUN (not executed) until you confirm real-money trading.")
            } else if isLiveSelection {
                Text("REAL orders will be placed with REAL money in your \(broker == "questrade" ? "Questrade" : "Alpaca live") account.")
            } else {
                Text("Orders are placed in your Alpaca paper (simulated) account - no real money at risk.")
            }
        }
        .alert("Enable Real-Money Trading?", isPresented: $showRealMoneyConfirmation) {
            Button("Cancel", role: .cancel) {}
            Button("I Understand - Use Real Money", role: .destructive) {
                confirmedRealMoney = true
            }
        } message: {
            Text("The AI Auto-Trader will place REAL orders with REAL money in your \(broker == "questrade" ? "Questrade" : "Alpaca live") account, fully autonomously, with no per-trade confirmation. Stock Chance's signals - including the ML model and AI analyst - are educational technical analysis, not financial advice, and are not guaranteed to be profitable. You could lose money. Only continue if you understand and accept this risk.")
        }
    }

    @ViewBuilder
    private var credentialsSection: some View {
        if broker == "questrade" {
            Section {
                SecureField("Questrade Refresh Token", text: $questradeRefreshToken)
                    #if os(iOS)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    #endif
                TextField("Questrade Account Number", text: $questradeAccountNumber)
                    #if os(iOS)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .keyboardType(.numberPad)
                    #endif
                if viewModel.status?.config.questradeConfigured == true {
                    Text("✅ Questrade credentials are configured on the backend.")
                        .font(.caption)
                        .foregroundStyle(Theme.profit)
                }
            } header: {
                Text("Questrade Credentials")
            } footer: {
                Text("Generate a personal refresh token from Questrade's App Hub (questrade.com -> My Apps -> Personal apps) - this must be a fresh token, separate from the one used for manual trading in Settings, since Questrade tokens are single-use. Stock Chance refreshes and persists the rotated token on the backend automatically. Leave the token blank to keep the previously saved one unchanged.")
            }
        } else {
            Section {
                SecureField("Alpaca API Key ID", text: $alpacaApiKeyId)
                    #if os(iOS)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    #endif
                SecureField("Alpaca API Secret Key", text: $alpacaApiSecretKey)
                    #if os(iOS)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    #endif
                if viewModel.status?.config.alpacaConfigured == true {
                    Text("✅ Alpaca credentials are configured on the backend.")
                        .font(.caption)
                        .foregroundStyle(Theme.profit)
                }
            } header: {
                Text("Alpaca Credentials")
            } footer: {
                Text("Stored on the backend (not just this device) so the auto-trader can act while the app is closed. Leave blank to keep previously saved credentials. Use keys matching the environment selected above (paper or live).")
            }
        }
    }

    private var actionsSection: some View {
        Section {
            Button {
                Task { await save() }
            } label: {
                if viewModel.isSaving {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                } else {
                    Text("Save Configuration")
                        .frame(maxWidth: .infinity)
                }
            }
            .disabled(viewModel.isSaving)

            Button {
                Task { await viewModel.runNow(baseURL: apiConfig.baseURL) }
            } label: {
                if viewModel.isRunning {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                } else {
                    Label("Run Now", systemImage: "play.fill")
                        .frame(maxWidth: .infinity)
                }
            }
            .disabled(viewModel.isRunning)

            if let saveMessage {
                Text(saveMessage)
                    .font(.caption)
                    .foregroundStyle(saveMessage.hasPrefix("✅") ? Theme.profit : Theme.loss)
            }
        } footer: {
            Text("\"Run Now\" triggers one evaluation immediately (useful for testing) - it still only places orders while the US market is open.")
        }
    }

    @ViewBuilder
    private var decisionsSection: some View {
        if let decisions = viewModel.status?.decisions, !decisions.isEmpty {
            Section("Recent Decisions") {
                ForEach(decisions) { decision in
                    decisionRow(decision)
                }
            }
        }
    }

    @ViewBuilder
    private var disclaimerSection: some View {
        if let disclaimer = viewModel.status?.disclaimer {
            Section {
                Text(disclaimer)
                    .font(.caption2)
                    .foregroundStyle(Theme.textSecondary.opacity(0.8))
            }
        }
    }

    private func decisionRow(_ decision: AutoTraderDecision) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(decision.symbol)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.textPrimary)
                SignalBadge(action: TradeAction(rawValue: decision.action) ?? .hold, confidence: decision.combinedConfidence)
                Spacer()
                if decision.executed {
                    Text("EXECUTED")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(Theme.profit)
                }
            }
            Text(decision.reason)
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
            Text(decision.date.formatted(date: .abbreviated, time: .shortened))
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary.opacity(0.8))
        }
        .padding(.vertical, 2)
    }

    // MARK: - Helpers

    private func apply(_ config: AutoTraderConfig) {
        enabled = config.enabled
        broker = config.broker
        symbolsText = config.symbols.joined(separator: ", ")
        autoSelect = config.autoSelect
        autoSelectCount = config.autoSelectCount
        maxOpenPositions = config.maxOpenPositions
        minConfidence = config.minConfidence
        maxPositionValueText = String(format: "%.2f", config.maxPositionValue)
        maxDailyTrades = config.maxDailyTrades
        pollIntervalMinutes = config.pollIntervalMinutes
        environmentSelection = config.environment
        confirmedRealMoney = config.confirmedRealMoney
        if questradeAccountNumber.isEmpty && !brokerStore.questradeAccountNumber.isEmpty {
            questradeAccountNumber = brokerStore.questradeAccountNumber
        }
    }

    private func buildRequest() -> AutoTraderConfigRequest {
        let symbols = symbolsText
            .split(whereSeparator: { $0 == "," || $0.isWhitespace })
            .map { $0.uppercased() }
            .filter { !$0.isEmpty }

        return AutoTraderConfigRequest(
            enabled: enabled,
            broker: broker,
            symbols: symbols,
            autoSelect: autoSelect,
            autoSelectCount: autoSelectCount,
            maxOpenPositions: maxOpenPositions,
            minConfidence: minConfidence,
            maxPositionValue: Double(maxPositionValueText) ?? 100,
            maxDailyTrades: maxDailyTrades,
            pollIntervalMinutes: pollIntervalMinutes,
            environment: environmentSelection,
            confirmedRealMoney: confirmedRealMoney,
            alpacaApiKeyId: alpacaApiKeyId.isEmpty ? nil : alpacaApiKeyId,
            alpacaApiSecretKey: alpacaApiSecretKey.isEmpty ? nil : alpacaApiSecretKey,
            questradeRefreshToken: questradeRefreshToken.isEmpty ? nil : questradeRefreshToken,
            questradeAccountNumber: questradeAccountNumber.isEmpty ? nil : questradeAccountNumber
        )
    }

    @MainActor
    private func save() async {
        if let error = await viewModel.save(buildRequest(), baseURL: apiConfig.baseURL) {
            saveMessage = "❌ \(error)"
        } else {
            saveMessage = "✅ Saved"
            alpacaApiKeyId = ""
            alpacaApiSecretKey = ""
            questradeRefreshToken = ""
        }
    }

    private func relativeDate(_ isoString: String) -> String {
        let date = ISO8601DateFormatter.flexible.date(from: isoString) ?? Date()
        return date.formatted(date: .abbreviated, time: .shortened)
    }
}
