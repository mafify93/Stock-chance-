import SwiftUI

/// A small "?" button that pops over a plain-language explanation of a
/// trading term (RSI, VWAP, stop-loss, etc.) - aimed at first-time traders
/// who shouldn't have to leave the app to look things up.
struct InfoTooltip: View {
    let title: String
    let text: String
    @State private var isPresented = false

    var body: some View {
        Button {
            isPresented = true
        } label: {
            Image(systemName: "questionmark.circle")
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
        }
        .buttonStyle(.plain)
        .popover(isPresented: $isPresented) {
            VStack(alignment: .leading, spacing: 8) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.textPrimary)
                Text(text)
                    .font(.subheadline)
                    .foregroundStyle(Theme.textSecondary)
            }
            .padding()
            .frame(minWidth: 220, idealWidth: 280, maxWidth: 320)
            .background(Theme.card)
        }
    }
}

/// Centralized plain-language explanations for indicators and concepts
/// shown throughout the app, so first-time traders always have a "why"
/// available without leaving the screen.
enum TradingGlossary {
    static let rsi = (
        "RSI (Relative Strength Index)",
        "Measures whether a stock has been bought or sold too aggressively recently, on a scale of 0-100. "
        + "Below 30 often means it's 'oversold' (possible bounce); above 70 often means it's 'overbought' (possible pullback)."
    )

    static let macd = (
        "MACD",
        "Compares two moving averages to gauge momentum. When MACD crosses above its signal line, momentum is "
        + "turning positive (often a buy cue); crossing below suggests momentum is fading (often a sell cue)."
    )

    static let vwap = (
        "VWAP (Volume-Weighted Average Price)",
        "The average price paid for a stock today, weighted by how many shares traded at each price. "
        + "Price above VWAP suggests buyers are in control today; below VWAP suggests sellers are."
    )

    static let openingRange = (
        "Opening Range",
        "The high and low price set in the first 30 minutes of trading. Breaking above that high (or below "
        + "that low) afterward is often read as a sign the move for the day has started."
    )

    static let volumeSpike = (
        "Volume Spike",
        "A sudden jump in the number of shares trading compared to normal. Big spikes often mean something "
        + "important is happening - news, a large buyer/seller, or growing momentum."
    )

    static let confidence = (
        "Confidence",
        "How strongly the signals agree with each other, shown as a percentage. Higher confidence means more "
        + "indicators are pointing the same direction - it is not a guarantee of being right."
    )

    static let riskReward = (
        "Risk / Reward",
        "Compares how much you stand to gain (to the target price) versus how much you're risking (to the stop "
        + "price). A ratio of 1:2 means you're risking $1 to potentially make $2."
    )

    static let stopLoss = (
        "Stop Loss",
        "A price where, if the stock falls to it, you sell to limit your loss. Deciding this BEFORE you buy is "
        + "one of the most important habits in day trading."
    )

    static let takeProfit = (
        "Take Profit",
        "A target price where you plan to sell and lock in gains, decided in advance so you're not tempted to "
        + "hold too long out of greed (or sell too early out of fear)."
    )

    static let suspectedProfit = (
        "Suspected Profit",
        "A rough target based on how much this stock typically moves in a day (its average true range), "
        + "not a promise - actual moves can be smaller or much larger."
    )

    static let relativeVolume = (
        "Relative Volume",
        "Today's trading volume compared to this stock's average. A value of 2.0x means it's trading at twice "
        + "its normal volume - a sign of unusually high interest, for better or worse."
    )

    static let momentumScore = (
        "Momentum Score",
        "A ranking score combining the size of the price gap, how unusual the volume is, and whether the "
        + "longer-term trend agrees. Higher = more notable, not necessarily 'better'."
    )

    static let positionSizing = (
        "Position Sizing",
        "Deciding how many shares to buy based on how much you're willing to lose on the trade, not just how "
        + "much you can afford to buy. This keeps any single loss small and survivable."
    )

    static let aiInsight = (
        "AI Insight",
        "Combines the rule-based signal with a machine-learning model trained on years of price history, and "
        + "(if enabled) a plain-English take from an AI analyst, into one suggested action. It learns from past "
        + "trends, which don't always repeat - it's a tool to inform your decision, not a guarantee."
    )

    static let tonightsPicks = (
        "Tonight's Picks",
        "Every evening, an AI researches recent news - earnings, partnerships, FDA decisions, analyst calls and "
        + "more - across a curated list of stocks, looking for catalysts that could move a stock at the next "
        + "open. \"BUY\" means a recent bullish catalyst; \"WATCH\" means notable news that's less clear-cut. "
        + "This is speculative research, not a guarantee - always do your own research."
    )
}
