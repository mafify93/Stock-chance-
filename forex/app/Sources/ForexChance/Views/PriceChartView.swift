import SwiftUI
import Charts

/// A simple intraday close-price line chart with an optional VWAP reference
/// line. Uses Swift Charts (iOS 16+ / macOS 13+).
struct PriceChartView: View {
    let candles: [Candle]
    var vwap: Double?
    var decimals: Int = 5

    private var lineColor: Color {
        guard let first = candles.first?.close, let last = candles.last?.close else {
            return Theme.accent
        }
        return last >= first ? Theme.profit : Theme.loss
    }

    var body: some View {
        Chart {
            ForEach(candles) { candle in
                LineMark(
                    x: .value("Time", candle.dateValue),
                    y: .value("Price", candle.close)
                )
                .foregroundStyle(lineColor)
                .interpolationMethod(.catmullRom)

                AreaMark(
                    x: .value("Time", candle.dateValue),
                    y: .value("Price", candle.close)
                )
                .foregroundStyle(
                    LinearGradient(
                        colors: [lineColor.opacity(0.25), lineColor.opacity(0.0)],
                        startPoint: .top, endPoint: .bottom
                    )
                )
                .interpolationMethod(.catmullRom)
            }

            if let vwap {
                RuleMark(y: .value("VWAP", vwap))
                    .foregroundStyle(Theme.accentBright.opacity(0.8))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
                    .annotation(position: .top, alignment: .leading) {
                        Text("VWAP")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(Theme.accentBright)
                    }
            }
        }
        .chartYScale(domain: .automatic(includesZero: false))
        .chartYAxis {
            AxisMarks(position: .trailing) { value in
                AxisGridLine().foregroundStyle(Theme.cardBorder.opacity(0.4))
                AxisValueLabel {
                    if let price = value.as(Double.self) {
                        Text(String(format: "%.\(decimals)f", price))
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(Theme.textSecondary)
                    }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 4)) { _ in
                AxisGridLine().foregroundStyle(Theme.cardBorder.opacity(0.3))
                AxisValueLabel(format: .dateTime.hour().minute())
                    .foregroundStyle(Theme.textSecondary)
            }
        }
        .frame(height: 200)
    }
}
