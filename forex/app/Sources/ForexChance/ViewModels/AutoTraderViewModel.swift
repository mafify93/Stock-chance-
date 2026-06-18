import Foundation
import SwiftUI

@MainActor
final class AutoTraderViewModel: ObservableObject {
    @Published var status: AutoTraderStatus?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var actionMessage: String?

    // Config overrides exposed to the UI
    @Published var riskPct: Double = 1.0         // shown as percent
    @Published var rrRatio: Double = 2.0
    @Published var maxPositions: Int = 2
    @Published var maxTradesPerDay: Int = 5
    @Published var dailyLossLimitPct: Double = 3.0  // shown as percent
    @Published var minConfidence: Double = 60.0      // shown as percent
    @Published var maxSpreadPips: Double = 3.0
    @Published var sessionFilter: Bool = true

    private var refreshTask: Task<Void, Never>?
    private let client: APIClient
    private let brokerStore: BrokerStore

    init(client: APIClient, brokerStore: BrokerStore) {
        self.client = client
        self.brokerStore = brokerStore
    }

    // MARK: - Load status

    func loadStatus() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let s = try await client.autoTraderStatus()
            status = s
            // Sync UI sliders with current server config
            riskPct = s.config.riskPct * 100
            rrRatio = s.config.rrRatio
            maxPositions = s.config.maxPositions
            maxTradesPerDay = s.config.maxTradesPerDay
            dailyLossLimitPct = s.config.dailyLossLimitPct * 100
            minConfidence = s.config.minConfidence * 100
            maxSpreadPips = s.config.maxSpreadPips
            sessionFilter = s.config.sessionFilter
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Auto-refresh while running

    func startPolling() {
        stopPolling()
        refreshTask = Task {
            while !Task.isCancelled {
                await loadStatus()
                try? await Task.sleep(nanoseconds: 15_000_000_000) // 15 s
            }
        }
    }

    func stopPolling() {
        refreshTask?.cancel()
        refreshTask = nil
    }

    // MARK: - Bot control

    func startBot(environment: OandaEnvironment, liveTradingAcknowledged: Bool) async {
        guard let creds = brokerStore.credentials(for: environment) else {
            errorMessage = environment == .live
                ? "Enter your OANDA Live token and account ID in Settings > Broker first."
                : "Enter your OANDA Practice token and account ID in Settings > Broker first."
            return
        }

        isLoading = true
        defer { isLoading = false }

        let request = AutoTraderStartRequest(
            token: creds.token,
            accountId: creds.accountId,
            environment: environment.rawValue,
            liveTradingAcknowledged: liveTradingAcknowledged,
            riskPct: riskPct / 100,
            maxPositions: maxPositions,
            maxTradesPerDay: maxTradesPerDay,
            dailyLossLimitPct: dailyLossLimitPct / 100,
            rrRatio: rrRatio,
            maxSpreadPips: maxSpreadPips,
            minConfidence: minConfidence / 100,
            sessionFilter: sessionFilter,
            pairs: nil   // use server default
        )

        do {
            _ = try await client.startAutoTrader(request)
            actionMessage = "Auto-Trader started on \(environment == .live ? "LIVE" : "Practice") account."
            await loadStatus()
            startPolling()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func stopBot() async {
        isLoading = true
        defer { isLoading = false }
        do {
            _ = try await client.stopAutoTrader()
            actionMessage = "Auto-Trader stopped. Open OANDA positions remain until their SL/TP is hit."
            stopPolling()
            await loadStatus()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func emergencyClose() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let result = try await client.emergencyClose()
            let closed = result["closed"] ?? []
            let errors = result["errors"] ?? []
            if errors.isEmpty {
                actionMessage = "Emergency close: \(closed.isEmpty ? "no open positions" : closed.joined(separator: ", "))."
            } else {
                actionMessage = "Closed: \(closed.joined(separator: ", ")). Errors: \(errors.joined(separator: "; "))"
            }
            stopPolling()
            await loadStatus()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
