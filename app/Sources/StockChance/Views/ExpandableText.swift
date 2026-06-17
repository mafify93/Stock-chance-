import SwiftUI

/// Text collapsed to a few lines by default, with a "Read more" / "Show less"
/// toggle - keeps cards scannable while still letting the full detail be read
/// on demand.
struct ExpandableText: View {
    let text: String
    var lineLimit: Int = 2
    var font: Font = .subheadline
    var color: Color = Theme.textPrimary

    @State private var expanded = false

    /// Rough heuristic: only show the toggle if the text is long enough that
    /// it's likely to be truncated at `lineLimit` on a phone-width card.
    private var isLong: Bool {
        text.count > lineLimit * 50
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(text)
                .font(font)
                .foregroundStyle(color)
                .lineLimit(expanded ? nil : lineLimit)

            if isLong {
                Button(expanded ? "Show less" : "Read more") {
                    withAnimation { expanded.toggle() }
                }
                .font(.caption2.weight(.semibold))
                .foregroundStyle(Theme.gold)
            }
        }
    }
}
