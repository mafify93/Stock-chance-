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
                .foregroundStyle(.blue)
                .interpolationMethod(.catmullRom)
            }

            ForEach(movingAverage(period: 50)) { point in
                LineMark(
                    x: .value("Date", point.date),
                    y: .value("SMA50", point.value)
                )
                .foregroundStyle(.orange)
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
