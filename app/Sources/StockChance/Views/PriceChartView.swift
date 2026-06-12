import SwiftUI
import Charts

/// Line chart of closing prices with optional 50/200-day moving averages
/// overlaid (computed client-side from the candle data).
struct PriceChartView: View {
    let candles: [Candle]

    var body: some View {
        Chart {
            ForEach(candles) { candle in
                LineMark(
                    x: .value("Date", candle.dateValue),
                    y: .value("Close", candle.close)
                )
                .foregroundStyle(Theme.gold)
                .interpolationMethod(.catmullRom)
            }

            ForEach(movingAverage(period: 50)) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("SMA50", point.value)
                )
                .foregroundStyle(Theme.profit)
                .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading)
        }
        .frame(height: 220)
    }

    private struct MAPoint: Identifiable {
        let date: Date
        let value: Double
        var id: Date { date }
    }

    private func movingAverage(period: Int) -> [MAPoint] {
        guard candles.count > period else { return [] }
        var result: [MAPoint] = []
        var window: [Double] = []
        for candle in candles {
            window.append(candle.close)
            if window.count > period {
                window.removeFirst()
            }
            if window.count == period {
                let avg = window.reduce(0, +) / Double(period)
                result.append(MAPoint(date: candle.dateValue, value: avg))
            }
        }
        return result
    }
}

#Preview {
    PriceChartView(candles: [])
}

/// Intraday (5-minute) price line for the same-day trading view, with
/// optional reference lines for VWAP and the suggested entry/target/stop
/// levels.
struct IntradayChartView: View {
    let candles: [Candle]
    var vwap: Double? = nil
    var entry: Double? = nil
    var target: Double? = nil
    var stop: Double? = nil

    var body: some View {
        Chart {
            ForEach(candles) { candle in
                LineMark(
                    x: .value("Time", candle.dateValue),
                    y: .value("Price", candle.close)
                )
                .foregroundStyle(Theme.gold)
                .interpolationMethod(.catmullRom)
            }

            if let vwap {
                RuleMark(y: .value("VWAP", vwap))
                    .foregroundStyle(Theme.textSecondary)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
                    .annotation(position: .top, alignment: .leading) {
                        Text("VWAP")
                            .font(.caption2)
                            .foregroundStyle(Theme.textSecondary)
                    }
            }
            if let target {
                RuleMark(y: .value("Target", target))
                    .foregroundStyle(Theme.profit.opacity(0.6))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 2]))
                    .annotation(position: .top, alignment: .leading) {
                        Text("Target")
                            .font(.caption2)
                            .foregroundStyle(Theme.profit)
                    }
            }
            if let entry {
                RuleMark(y: .value("Entry", entry))
                    .foregroundStyle(Theme.gold.opacity(0.6))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 2]))
            }
            if let stop {
                RuleMark(y: .value("Stop", stop))
                    .foregroundStyle(Theme.loss.opacity(0.6))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 2]))
                    .annotation(position: .bottom, alignment: .leading) {
                        Text("Stop")
                            .font(.caption2)
                            .foregroundStyle(Theme.loss)
                    }
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading)
        }
        .frame(height: 180)
    }
}

#Preview {
    IntradayChartView(candles: [])
}
