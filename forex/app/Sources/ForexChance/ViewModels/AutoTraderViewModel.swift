import Foundation
import SwiftUI

@MainActor
final class AutoTraderViewModel: ObservableObject {
    @Published var status: AutoTraderStatus?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var actionMessage: String?

    // Config overrides exposed to the UI
    @Published var riskPct: Double = 1.0           // shown as percent
    @Published var rrRatio: Double = 2.0
    @Published var maxPositions: Int = 2
    @Published var maxTradesPerDay: Int = 5
    @Published var minConfidence: Double = 65.0     // shown as percent
    @Published var maxSpreadPips: Double = 2.0
    @Published var sessionFilter: Bool = true
    @Published var londonBreakout: Bool = true
    @Published var useAiLearner: Bool = true
    @Published var useIctSweep: Bool = true
    @Published var useOrb: Bool = true
    @Published var useSilverBullet: Bool = true
    @Published var useOrderBlocks: Bool = true
    @Published var dailyLossHaltPct: Double = 3.0  // percent; 0 = disabled
    @Published var useAtrExpansionFilter: Bool = false

    // AI Learner stats
    @Published var learnerStats: LearnerStats?
    @Published var isLoadingLearner = false

    // Backtest
    @Published var backtestResult: BacktestResult?
    @Published var isBacktesting = false
    @Published var backtestBars: Int = 2000
    @Published var backtestSpreadPips: Double = 1.0
    @Published var backtestStartingNav: Double = 1000.0

    private var refreshTask: Task<Void, Never>?
    private let client: APIClient
    let brokerStore: BrokerStore

    /// We sync the config sliders/toggles from the server only on the first
    /// load. After that they're owned by the user - otherwise the 15s status
    /// poll would overwrite an edit in progress.
    private var hasSyncedConfig = false

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
            if !hasSyncedConfig {
                syncControls(from: s.config)
                hasSyncedConfig = true
            }
        } catch {
            if !isCancellation(error) {
                errorMessage = error.localizedDescription
            }
        }
    }

    private func syncControls(from config: AutoTraderConfig) {
        riskPct = config.riskPct * 100
        rrRatio = config.rrRatio
        maxPositions = config.maxPositions
        maxTradesPerDay = config.maxTradesPerDay
        minConfidence = config.minConfidence * 100
        maxSpreadPips = config.maxSpreadPips
        sessionFilter = config.sessionFilter
        londonBreakout = config.useLondonBreakout ?? true
        useAiLearner = config.useAiLearner ?? true
        useIctSweep = config.useIctSweep ?? true
        useOrb = config.useOrb ?? true
        useSilverBullet = config.useSilverBullet ?? true
        useOrderBlocks = config.useOrderBlocks ?? true
        dailyLossHaltPct = (config.dailyLossHaltPct ?? 0.03) * 100
        useAtrExpansionFilter = config.useAtrExpansionFilter ?? false
    }

    // MARK: - Learner stats

    func loadLearnerStats() async {
        isLoadingLearner = true
        defer { isLoadingLearner = false }
        do {
            learnerStats = try await client.learnerStats()
        } catch {
            if !isCancellation(error) {
                errorMessage = error.localizedDescription
            }
        }
    }

    // MARK: - Backtest

    func runBacktest(environment: OandaEnvironment) async {
        let creds = brokerStore.credentials(for: environment)
        guard creds.isConfigured else {
            errorMessage = "Configure your OANDA credentials in Settings > Broker first."
            return
        }
        isBacktesting = true
        defer { isBacktesting = false }
        let request = BacktestRequest(
            token: creds.token,
            accountId: creds.accountId,
            environment: environment.rawValue,
            pairs: nil,
            bars: backtestBars,
            spreadPips: backtestSpreadPips,
            startingNav: backtestStartingNav,
            riskPct: riskPct / 100,
            rrRatio: rrRatio,
            minConfidence: minConfidence / 100,
            sessionFilter: sessionFilter,
            maxTradesPerDay: maxTradesPerDay,
            minStopPips: nil,
            maxStopPips: nil
        )
        do {
            backtestResult = try await client.backtest(request)
        } catch {
            if !isCancellation(error) {
                errorMessage = error.localizedDescription
            }
        }
    }

    // MARK: - Config push

    /// Push the current control values to a *running* bot. No-op when the bot
    /// is stopped - those values are sent in full when it's next started.
    func applyConfigIfRunning() async {
        guard status?.running == true else { return }
        let patch = AutoTraderConfigPatch(
            riskPct: riskPct / 100,
            maxPositions: maxPositions,
            maxTradesPerDay: maxTradesPerDay,
            rrRatio: rrRatio,
            maxSpreadPips: maxSpreadPips,
            minConfidence: minConfidence / 100,
            sessionFilter: sessionFilter,
            useLondonBreakout: londonBreakout,
            useAiLearner: useAiLearner,
            aiMinWinProb: nil,
            useIctSweep: useIctSweep,
            useOrb: useOrb,
            useSilverBullet: useSilverBullet,
            useOrderBlocks: useOrderBlocks,
            dailyLossHaltPct: dailyLossHaltPct / 100,
            useAtrExpansionFilter: useAtrExpansionFilter
        )
        do {
            try await client.updateAutoTraderConfig(patch)
        } catch {
            if !isCancellation(error) {
                errorMessage = error.localizedDescription
            }
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
        let creds = brokerStore.credentials(for: environment)
        guard creds.isConfigured else {
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
            rrRatio: rrRatio,
            maxSpreadPips: maxSpreadPips,
            minConfidence: minConfidence / 100,
            sessionFilter: sessionFilter,
            pairs: nil
        )

        do {
            _ = try await client.startAutoTrader(request)
            actionMessage = "Auto-Trader started on \(environment == .live ? "LIVE" : "Practice") account."
            await loadStatus()
            startPolling()
        } catch {
            if !isCancellation(error) {
                errorMessage = error.localizedDescription
            }
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
            if !isCancellation(error) {
                errorMessage = error.localizedDescription
            }
        }
    }

    func resetDay() async {
        isLoading = true
        defer { isLoading = false }
        do {
            try await client.resetDay()
            actionMessage = "Day reset — trades today and risk scale cleared. Bot can take new entries."
            await loadStatus()
        } catch {
            if !isCancellation(error) {
                errorMessage = error.localizedDescription
            }
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
            if !isCancellation(error) {
                errorMessage = error.localizedDescription
            }
        }
    }
}
