import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var apiConfig: APIConfig
    @EnvironmentObject private var brokerStore: BrokerStore

    @State private var baseURLString = ""
    @State private var savedConfirmation = false

    var body: some View {
        NavigationStack {
            ScreenBackground {
                Form {
                    backendSection
                    practiceSection
                    liveSection
                    aboutSection
                }
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("Settings")
        }
        .onAppear { baseURLString = apiConfig.baseURL.absoluteString }
    }

    // MARK: - Backend

    private var backendSection: some View {
        Section {
            TextField("https://your-backend.onrender.com", text: $baseURLString)
                #if os(iOS)
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)
                #endif
                .autocorrectionDisabled()
            Button("Save Backend URL") {
                if let url = URL(string: baseURLString.trimmingCharacters(in: .whitespaces)) {
                    apiConfig.baseURL = url
                    savedConfirmation = true
                }
            }
        } header: {
            Text("Backend")
        } footer: {
            Text("The Forex Chance API server. Defaults to a local dev server; deploy the backend (see /forex/backend) and paste its URL here.")
        }
        .listRowBackground(Theme.card)
        .alert("Saved", isPresented: $savedConfirmation) {
            Button("OK", role: .cancel) {}
        }
    }

    // MARK: - Practice (demo) credentials

    private var practiceSection: some View {
        Section {
            SecureField("API Token", text: $brokerStore.token)
                .autocorrectionDisabled()
            TextField("Account ID (e.g. 101-001-1234567-001)", text: $brokerStore.accountId)
                #if os(iOS)
                .textInputAutocapitalization(.never)
                #endif
                .autocorrectionDisabled()
            if brokerStore.isPracticeConfigured {
                Label("Practice account connected", systemImage: "checkmark.seal.fill")
                    .font(.caption)
                    .foregroundStyle(Theme.profit)
                Button("Disconnect", role: .destructive) { brokerStore.clearPractice() }
            }
        } header: {
            Text("OANDA Practice (Demo)")
        } footer: {
            Text("A fxPractice token trades virtual money — safe to use freely. Create one at OANDA → Manage API Access. Stored only in your device Keychain and sent directly to OANDA.")
        }
        .listRowBackground(Theme.card)
    }

    // MARK: - Live credentials (real money)

    private var liveSection: some View {
        Section {
            Toggle("I understand live trading uses REAL money", isOn: $brokerStore.liveTradingAcknowledged)
                .tint(Theme.loss)

            if brokerStore.liveTradingAcknowledged {
                SecureField("Live API Token", text: $brokerStore.liveToken)
                    .autocorrectionDisabled()
                TextField("Live Account ID", text: $brokerStore.liveAccountId)
                    #if os(iOS)
                    .textInputAutocapitalization(.never)
                    #endif
                    .autocorrectionDisabled()
                if brokerStore.isLiveConfigured {
                    Label("Live account connected", systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(Theme.loss)
                    Button("Disconnect Live", role: .destructive) { brokerStore.clearLive() }
                }
            }
        } header: {
            Text("OANDA Live (Real Money)")
        } footer: {
            Text("A fxTrade token places REAL orders with REAL money. Orders against the live account always require a per-order confirmation.")
        }
        .listRowBackground(Theme.card)
    }

    private var aboutSection: some View {
        Section {
            LabeledContent("Version", value: "1.0")
            Text("Educational technical analysis, not financial advice. Leveraged forex trading carries a high risk of losing money rapidly.")
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
        } header: {
            Text("About")
        }
        .listRowBackground(Theme.card)
    }
}
