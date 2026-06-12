import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var apiConfig: APIConfig
    @State private var urlText: String = ""
    @State private var statusMessage: String?
    @State private var isChecking = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Backend Server") {
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
                } footer: {
                    Text("Point this at your deployed Stock Chance backend (see /backend in the repo). For the iOS Simulator and Mac you can use http://127.0.0.1:8000 while running it locally; a physical iPhone needs your computer's LAN IP or a public URL.")
                }

                Section("About") {
                    LabeledContent("Data Source", value: "Yahoo Finance (free)")
                    LabeledContent("Signal Engine", value: "Technical analysis (RSI, MACD, SMA/EMA, Bollinger Bands, Stochastic, ADX, ATR)")
                    Text("Signals are educational technical-analysis output, not financial advice. Markets are risky - never trade money you can't afford to lose.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            .onAppear {
                urlText = apiConfig.baseURL.absoluteString
            }
        }
    }

    @MainActor
    private func save() async {
        guard let url = URL(string: urlText), url.scheme != nil, url.host != nil else {
            statusMessage = "❌ Invalid URL"
            return
        }
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
}

#Preview {
    SettingsView()
        .environmentObject(APIConfig.shared)
}
