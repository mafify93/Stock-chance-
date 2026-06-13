import SwiftUI

/// Position-size calculator: turns "how much am I willing to lose" into
/// "how many shares should I buy", given an entry and stop price. This is
/// the single most important habit for new day traders - risking a fixed,
/// small slice of the account on every trade instead of an arbitrary
/// number of shares.
struct RiskCalculatorView: View {
    var initialEntry: Double?
    var initialStop: Double?

    @State private var accountSizeText: String = "1000"
    @State private var riskPercentText: String = "1"
    @State private var entryText: String = ""
    @State private var stopText: String = ""

    private var accountSize: Double? { Double(accountSizeText) }
    private var riskPercent: Double? { Double(riskPercentText) }
    private var entry: Double? { Double(entryText) }
    private var stop: Double? { Double(stopText) }

    private var riskAmount: Double? {
        guard let accountSize, let riskPercent, accountSize > 0, riskPercent > 0 else { return nil }
        return accountSize * (riskPercent / 100)
    }

    private var riskPerShare: Double? {
        guard let entry, let stop, entry != stop else { return nil }
        return abs(entry - stop)
    }

    private var suggestedShares: Int? {
        guard let riskAmount, let riskPerShare, riskPerShare > 0 else { return nil }
        return Int(riskAmount / riskPerShare)
    }

    private var positionCost: Double? {
        guard let suggestedShares, let entry else { return nil }
        return Double(suggestedShares) * entry
    }

    private var positionPercentOfAccount: Double? {
        guard let positionCost, let accountSize, accountSize > 0 else { return nil }
        return positionCost / accountSize
    }

    var body: some View {
        Form {
            Section {
                LabeledContent("Account Size") {
                    TextField("1000", text: $accountSizeText)
                        .multilineTextAlignment(.trailing)
                        .decimalKeyboard()
                }
                HStack {
                    LabeledContent("Risk per Trade") {
                        TextField("1", text: $riskPercentText)
                            .multilineTextAlignment(.trailing)
                            .decimalKeyboard()
                    }
                    Text("%")
                        .foregroundStyle(Theme.textSecondary)
                }
            } header: {
                HStack {
                    Text("Your Account")
                    InfoTooltip(title: TradingGlossary.positionSizing.0, text: TradingGlossary.positionSizing.1)
                }
            } footer: {
                Text("Most experienced day traders risk 1-2% of their account on any single trade, so a string of losses doesn't wipe out the account.")
            }

            Section("This Trade") {
                LabeledContent("Entry Price") {
                    TextField("0.00", text: $entryText)
                        .multilineTextAlignment(.trailing)
                        .decimalKeyboard()
                }
                HStack {
                    LabeledContent("Stop Loss") {
                        TextField("0.00", text: $stopText)
                            .multilineTextAlignment(.trailing)
                            .decimalKeyboard()
                    }
                    InfoTooltip(title: TradingGlossary.stopLoss.0, text: TradingGlossary.stopLoss.1)
                }
            }

            Section("Suggested Position") {
                if let riskAmount {
                    LabeledContent("Max Dollar Risk", value: riskAmount.formatted(.currency(code: "USD")))
                }
                if let riskPerShare {
                    LabeledContent("Risk per Share", value: riskPerShare.formatted(.currency(code: "USD")))
                }
                if let suggestedShares {
                    LabeledContent("Suggested Shares") {
                        Text("\(suggestedShares)")
                            .font(.title3.weight(.semibold).monospacedDigit())
                            .foregroundStyle(Theme.gold)
                    }
                }
                if let positionCost {
                    LabeledContent("Position Cost", value: positionCost.formatted(.currency(code: "USD")))
                }
                if let positionPercentOfAccount {
                    LabeledContent("% of Account") {
                        Text(positionPercentOfAccount, format: .percent.precision(.fractionLength(1)))
                            .foregroundStyle(positionPercentOfAccount > 0.5 ? Theme.loss : Theme.textPrimary)
                    }
                }
                if suggestedShares == nil {
                    Text("Enter an entry price and a stop-loss price to see a suggested share count.")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                }
                if let suggestedShares, suggestedShares == 0 {
                    Text("Your stop is far from your entry relative to your risk budget - either widen your account size, increase risk %, or pick a tighter stop.")
                        .font(.caption)
                        .foregroundStyle(Theme.loss)
                }
            }
        }
        .navigationTitle("Position Size")
        .luxuryBackground()
        .onAppear {
            if let initialEntry { entryText = String(format: "%.2f", initialEntry) }
            if let initialStop { stopText = String(format: "%.2f", initialStop) }
        }
    }
}
