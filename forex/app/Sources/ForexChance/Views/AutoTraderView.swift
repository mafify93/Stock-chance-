import SwiftUI

struct AutoTraderView: View {
    @StateObject private var vm: AutoTraderViewModel
    @State private var showStartSheet = false
    @State private var showEmergencyAlert = false
    @State private var showLiveWarning = false
    @State private var selectedEnv: OandaEnvironment = .practice
    @State private var showBacktest = false

    init(baseURL: URL, brokerStore: BrokerStore) {
        _vm = StateObject(wrappedValue: AutoTraderViewModel(
            client: APIClient(baseURL: baseURL),
            brokerStore: brokerStore
        ))
    }

    var body: some View {
        ScreenBackground {
            NavigationStack {
                ScrollView {
                    VStack(spacing: 16) {
                        statusCard
                        if let status = vm.status {
                            dailyStatsCard(status)
                            if !status.recentTrades.isEmpty {
                                recentTradesCard(status.recentTrades)
                            }
                            learnerStatsCard
                            configCard
                        }
                        emergencySection
                    }
                    .padding()
                }
                .navigationTitle("Auto-Trader")
                .toolbar { toolbar }
                .task {
                    await vm.loadStatus()
                    await vm.loadLearnerStats()
                }
                .onAppear { if vm.status?.running == true { vm.startPolling() } }
                .onDisappear { vm.stopPolling() }
                .navigationDestination(isPresented: $showBacktest) {
                    BacktestView(vm: vm)
                }
                .alert("Error", isPresented: Binding(
                    get: { vm.errorMessage != nil },
                    set: { if !$0 { vm.errorMessage = nil } }
                )) {
                    Button("OK") { vm.errorMessage = nil }
                } message: {
                    Text(vm.errorMessage ?? "")
                }
                .alert("Action", isPresented: Binding(
                    get: { vm.actionMessage != nil },
                    set: { if !$0 { vm.actionMessage = nil } }
                )) {
                    Button("OK") { vm.actionMessage = nil }
                } message: {
                    Text(vm.actionMessage ?? "")
                }
                .alert("Emergency Close", isPresented: $showEmergencyAlert) {
                    Button("Close All Positions", role: .destructive) {
                        Task { await vm.emergencyClose() }
                    }
                    Button("Cancel", role: .cancel) {}
                } message: {
                    Text("Stop the bot and close ALL open positions immediately? This cannot be undone.")
                }
                .alert("Live Trading Warning", isPresented: $showLiveWarning) {
                    Button("Start Live Trading", role: .destructive) {
                        Task { await vm.startBot(environment: .live, liveTradingAcknowledged: true) }
                    }
                    Button("Cancel", role: .cancel) {}
                } message: {
                    Text("This will place REAL orders using REAL money on your OANDA fxTrade account. Losses are possible and this is for educational purposes only.")
                }
                .sheet(isPresented: $showStartSheet) {
                    startSheet
                }
            }
        }
    }

    // MARK: - Status card

    private var statusCard: some View {
        VStack(spacing: 12) {
            HStack {
                statusIndicator
                Spacer()
                if vm.isLoading {
                    ProgressView().tint(Theme.accent)
                }
            }

            if let status = vm.status, status.halted {
                Text(status.haltReason)
                    .font(.caption)
                    .foregroundColor(Theme.loss)
                    .multilineTextAlignment(.leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            controlButtons
        }
        .cardStyle()
    }

    private var statusIndicator: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(statusColor)
                .frame(width: 12, height: 12)
            VStack(alignment: .leading, spacing: 2) {
                Text(vm.status?.statusLabel ?? "–")
                    .font(.headline)
                    .foregroundColor(.white)
                Text(vm.status?.environment == "live" ? "LIVE Account" : "Practice Account")
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
            }
        }
    }

    private var statusColor: Color {
        guard let s = vm.status else { return Theme.textSecondary }
        if s.halted { return Theme.loss }
        if s.running { return Theme.profit }
        return Theme.textSecondary
    }

    private var controlButtons: some View {
        HStack(spacing: 12) {
            if vm.status?.running == true {
                Button("Stop Bot") {
                    Task { await vm.stopBot() }
                }
                .buttonStyle(SecondaryButtonStyle())
            } else {
                Button("Start Bot") { showStartSheet = true }
                    .buttonStyle(AccentButtonStyle())
            }
        }
    }

    // MARK: - Daily stats

    private func dailyStatsCard(_ status: AutoTraderStatus) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Today")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
                .textCase(.uppercase)

            HStack(spacing: 0) {
                StatTile(
                    label: "Daily P&L",
                    value: Format.signedMoney(status.dailyPl),
                    valueColor: status.dailyPl >= 0 ? Theme.profit : Theme.loss
                )
                StatTile(
                    label: "Trades",
                    value: "\(status.tradesToday)/\(status.config.maxTradesPerDay)"
                )
                StatTile(
                    label: "Open",
                    value: "\(status.openPositions)/\(status.config.maxPositions)"
                )
                StatTile(
                    label: "Risk Scale",
                    value: "\(Int(status.riskScale * 100))%",
                    valueColor: status.riskScale < 1 ? Theme.loss : Theme.textSecondary
                )
            }

            if status.consecutiveLosses > 0 {
                HStack {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(Theme.loss)
                    Text("\(status.consecutiveLosses) consecutive loss\(status.consecutiveLosses > 1 ? "es" : "") — risk scaled to \(Int(status.riskScale * 100))%")
                        .font(.caption)
                        .foregroundColor(Theme.loss)
                }
            }
        }
        .cardStyle()
    }

    // MARK: - Recent trades

    private func recentTradesCard(_ trades: [AutoTradeRecord]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Recent Trades")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
                .textCase(.uppercase)

            ForEach(trades.prefix(10)) { trade in
                AutoTradeRow(trade: trade)
                if trade.id != (trades.prefix(10).last?.id ?? "") {
                    Divider().background(Theme.cardBorder)
                }
            }
        }
        .cardStyle()
    }

    // MARK: - AI Learner stats card

    private var learnerStatsCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("AI Learner")
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .textCase(.uppercase)
                Spacer()
                if vm.isLoadingLearner {
                    ProgressView().scaleEffect(0.7).tint(Theme.accent)
                }
            }

            if let stats = vm.learnerStats {
                HStack(spacing: 0) {
                    StatTile(
                        label: "Win Rate",
                        value: stats.modelActive ? "\(stats.winRatePct, specifier: "%.0f")%" : "–",
                        valueColor: stats.modelActive ? (stats.winRatePct >= 50 ? Theme.profit : Theme.loss) : Theme.textSecondary
                    )
                    StatTile(
                        label: "Trades",
                        value: "\(stats.totalTradesObserved)"
                    )
                    StatTile(
                        label: "Status",
                        value: stats.modelActive ? "Active" : "Training",
                        valueColor: stats.modelActive ? Theme.profit : Theme.accent
                    )
                }

                if !stats.modelActive {
                    Text("\(stats.tradesUntilActive) more trade\(stats.tradesUntilActive == 1 ? "" : "s") until the model activates")
                        .font(.caption)
                        .foregroundColor(Theme.textSecondary)
                }

                if let importances = stats.featureImportances, !importances.isEmpty {
                    let sorted = importances.sorted { $0.value > $1.value }.prefix(3)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Top signals")
                            .font(.caption2)
                            .foregroundColor(Theme.textSecondary)
                        ForEach(sorted, id: \.key) { key, value in
                            HStack {
                                Text(key.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(.caption2)
                                    .foregroundColor(.white)
                                Spacer()
                                Text("\(value * 100, specifier: "%.0f")%")
                                    .font(.caption2.monospacedDigit())
                                    .foregroundColor(Theme.accent)
                            }
                        }
                    }
                }
            } else {
                Text("No data yet — start the bot to begin collecting trade history.")
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
            }
        }
        .cardStyle()
    }

    // MARK: - Config card

    private var configCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Configuration")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
                .textCase(.uppercase)

            configSlider(label: "Risk per trade", value: $vm.riskPct, range: 0.5...3, step: 0.25, format: "%.2f%%")
            configSlider(label: "Reward/Risk ratio", value: $vm.rrRatio, range: 1.0...3.0, step: 0.25, format: "%.2fx")
            configSlider(label: "Daily loss limit", value: $vm.dailyLossLimitPct, range: 1...6, step: 0.5, format: "%.1f%%")
            configSlider(label: "Min confidence", value: $vm.minConfidence, range: 35...80, step: 5, format: "%.0f%%")
            configSlider(label: "Max spread (pips)", value: $vm.maxSpreadPips, range: 1...8, step: 0.5, format: "%.1f")
            configStepper(label: "Max positions", value: $vm.maxPositions, range: 1...4)
            configStepper(label: "Max trades/day", value: $vm.maxTradesPerDay, range: 1...20)

            Divider().background(Theme.cardBorder)

            Toggle("Session filter (London/NY only)", isOn: $vm.sessionFilter)
                .tint(Theme.accent)
                .font(.subheadline)
                .foregroundColor(.white)

            Toggle("London Open Breakout", isOn: $vm.londonBreakout)
                .tint(Theme.accent)
                .font(.subheadline)
                .foregroundColor(.white)

            Toggle("AI Self-Learning", isOn: $vm.useAiLearner)
                .tint(Theme.accent)
                .font(.subheadline)
                .foregroundColor(.white)

            if vm.status?.running == true {
                Text("Changes apply to the running bot immediately.")
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
            }
        }
        .cardStyle()
        .onChange(of: vm.riskPct) { _ in applyConfig() }
        .onChange(of: vm.rrRatio) { _ in applyConfig() }
        .onChange(of: vm.dailyLossLimitPct) { _ in applyConfig() }
        .onChange(of: vm.minConfidence) { _ in applyConfig() }
        .onChange(of: vm.maxSpreadPips) { _ in applyConfig() }
        .onChange(of: vm.maxPositions) { _ in applyConfig() }
        .onChange(of: vm.maxTradesPerDay) { _ in applyConfig() }
        .onChange(of: vm.sessionFilter) { _ in applyConfig() }
        .onChange(of: vm.londonBreakout) { _ in applyConfig() }
        .onChange(of: vm.useAiLearner) { _ in applyConfig() }
    }

    private func applyConfig() {
        Task { await vm.applyConfigIfRunning() }
    }

    // MARK: - Emergency section

    private var emergencySection: some View {
        Button {
            showEmergencyAlert = true
        } label: {
            Label("Emergency Close All", systemImage: "xmark.octagon.fill")
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(Theme.loss.opacity(0.15))
                .foregroundColor(Theme.loss)
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .strokeBorder(Theme.loss.opacity(0.4), lineWidth: 1)
                )
        }
    }

    // MARK: - Start sheet

    private var startSheet: some View {
        NavigationStack {
            Form {
                Section("Account") {
                    Picker("Environment", selection: $selectedEnv) {
                        ForEach(OandaEnvironment.allCases, id: \.self) { env in
                            Text(env == .live ? "Live (Real Money)" : "Practice (Demo)").tag(env)
                        }
                    }
                }

                Section("Risk Settings") {
                    LabeledContent("Risk per trade") {
                        Text("\(vm.riskPct, specifier: "%.2f")%")
                            .foregroundColor(Theme.accent)
                    }
                    Slider(value: $vm.riskPct, in: 0.5...3, step: 0.25)
                        .tint(Theme.accent)

                    LabeledContent("R/R ratio") {
                        Text("\(vm.rrRatio, specifier: "%.1f"):1")
                            .foregroundColor(Theme.accent)
                    }
                    Slider(value: $vm.rrRatio, in: 1.5...4, step: 0.5)
                        .tint(Theme.accent)
                }

                if selectedEnv == .live {
                    Section {
                        Text("LIVE trading places REAL orders with REAL money. You can lose your entire account balance. This is for educational purposes only.")
                            .foregroundColor(Theme.loss)
                            .font(.footnote)
                    } header: {
                        Text("LIVE TRADING WARNING")
                            .foregroundColor(Theme.loss)
                    }
                }

                Section {
                    Button(selectedEnv == .live ? "Start Live Trading…" : "Start Practice Bot") {
                        showStartSheet = false
                        if selectedEnv == .live {
                            showLiveWarning = true
                        } else {
                            Task { await vm.startBot(environment: .practice, liveTradingAcknowledged: false) }
                        }
                    }
                    .foregroundColor(selectedEnv == .live ? Theme.loss : Theme.accent)
                }
            }
            .navigationTitle("Start Auto-Trader")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showStartSheet = false }
                }
            }
        }
    }

    // MARK: - Toolbar

    private var toolbar: some ToolbarContent {
        Group {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    Task { await vm.loadStatus() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .tint(Theme.accent)
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    showBacktest = true
                } label: {
                    Image(systemName: "chart.xyaxis.line")
                }
                .tint(Theme.accent)
            }
        }
    }

    // MARK: - Helpers

    private func configSlider(label: String, value: Binding<Double>, range: ClosedRange<Double>, step: Double, format: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label)
                    .font(.subheadline)
                    .foregroundColor(.white)
                Spacer()
                Text(String(format: format, value.wrappedValue))
                    .font(.subheadline.monospacedDigit())
                    .foregroundColor(Theme.accent)
            }
            Slider(value: value, in: range, step: step)
                .tint(Theme.accent)
        }
    }

    private func configStepper(label: String, value: Binding<Int>, range: ClosedRange<Int>) -> some View {
        HStack {
            Text(label)
                .font(.subheadline)
                .foregroundColor(.white)
            Spacer()
            Stepper("\(value.wrappedValue)", value: value, in: range)
                .fixedSize()
                .tint(Theme.accent)
        }
    }
}

// MARK: - Trade Row

private struct AutoTradeRow: View {
    let trade: AutoTradeRecord

    var body: some View {
        HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text(trade.display)
                    .font(.subheadline.bold())
                    .foregroundColor(.white)
                Text(trade.side.capitalized + " · \(trade.units) units")
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                HStack(spacing: 4) {
                    Text(trade.isOpen ? "OPEN" : "CLOSED")
                        .font(.caption.bold())
                        .foregroundColor(trade.isOpen ? Theme.profit : Theme.textSecondary)
                    if let pl = trade.realizedPl {
                        Text(Format.signedMoney(pl))
                            .font(.caption.bold())
                            .foregroundColor(pl >= 0 ? Theme.profit : Theme.loss)
                    }
                }
                Text("\(trade.stopPips, specifier: "%.0f")p SL · \(trade.targetPips, specifier: "%.0f")p TP")
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
            }
        }
        .padding(.vertical, 2)
    }
}

// MARK: - Button styles

private struct AccentButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(Theme.accent)
            .foregroundColor(.black)
            .fontWeight(.semibold)
            .cornerRadius(10)
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

private struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(Theme.card)
            .foregroundColor(Theme.textSecondary)
            .fontWeight(.semibold)
            .cornerRadius(10)
            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Theme.cardBorder, lineWidth: 1))
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}
