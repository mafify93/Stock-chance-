import SwiftUI

/// A cool, focused "trading terminal" visual theme: deep navy backgrounds,
/// a teal/cyan accent and high-contrast text - tuned to read like a
/// professional FX desk while staying calm on the eye during long sessions.
enum Theme {
    // MARK: - Palette

    static let background = Color(red: 0.055, green: 0.075, blue: 0.114)        // deep navy
    static let backgroundElevated = Color(red: 0.094, green: 0.122, blue: 0.176)
    static let card = Color(red: 0.106, green: 0.137, blue: 0.196)             // slate card
    static let cardBorder = Color(red: 0.196, green: 0.243, blue: 0.314)

    static let accent = Color(red: 0.149, green: 0.733, blue: 0.706)           // teal
    static let accentBright = Color(red: 0.243, green: 0.851, blue: 0.808)

    static let profit = Color(red: 0.220, green: 0.804, blue: 0.490)           // green
    static let loss = Color(red: 0.937, green: 0.353, blue: 0.353)             // red
    static let neutral = Color(red: 0.612, green: 0.659, blue: 0.722)

    static let textPrimary = Color(red: 0.929, green: 0.945, blue: 0.969)
    static let textSecondary = Color(red: 0.612, green: 0.659, blue: 0.722)

    static let backgroundGradient = LinearGradient(
        colors: [
            Color(red: 0.063, green: 0.086, blue: 0.133),
            Color(red: 0.039, green: 0.055, blue: 0.090),
        ],
        startPoint: .top,
        endPoint: .bottom
    )

    static let accentGradient = LinearGradient(
        colors: [accentBright, accent],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    // MARK: - Typography

    static func priceFont(_ size: CGFloat = 28) -> Font {
        .system(size: size, weight: .semibold, design: .rounded).monospacedDigit()
    }

    static func sectionTitleFont() -> Font {
        .system(.headline, design: .rounded).weight(.semibold)
    }

    // MARK: - Action colors

    static func color(for action: TradeAction) -> Color {
        switch action {
        case .strongBuy, .buy: return profit
        case .hold: return neutral
        case .sell, .strongSell: return loss
        }
    }
}

// MARK: - View modifiers

private struct CardModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding()
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(Theme.card)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .strokeBorder(Theme.cardBorder.opacity(0.7), lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.25), radius: 10, x: 0, y: 4)
    }
}

private struct HeroCardModifier: ViewModifier {
    let tint: Color

    func body(content: Content) -> some View {
        content
            .padding(20)
            .background(
                ZStack {
                    RoundedRectangle(cornerRadius: 26, style: .continuous)
                        .fill(Theme.card)
                    RoundedRectangle(cornerRadius: 26, style: .continuous)
                        .fill(tint.opacity(0.12))
                }
            )
            .overlay(
                RoundedRectangle(cornerRadius: 26, style: .continuous)
                    .strokeBorder(tint.opacity(0.45), lineWidth: 1.5)
            )
            .shadow(color: tint.opacity(0.25), radius: 18, x: 0, y: 8)
    }
}

extension View {
    func cardStyle() -> some View { modifier(CardModifier()) }
    func heroCardStyle(tint: Color) -> some View { modifier(HeroCardModifier(tint: tint)) }
}
