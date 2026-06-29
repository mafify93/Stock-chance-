import SwiftUI

/// A luxury "private wealth desk" visual theme: deep obsidian-black backgrounds,
/// a champagne-gold accent and warm ivory text - designed to read as premium
/// and high-trust, the kind of finish you'd want a funding evaluator to see.
enum Theme {
    // MARK: - Palette

    static let background = Color(red: 0.039, green: 0.043, blue: 0.051)        // obsidian black
    static let backgroundElevated = Color(red: 0.071, green: 0.078, blue: 0.090)
    static let card = Color(red: 0.094, green: 0.102, blue: 0.118)             // graphite card
    static let cardBorder = Color(red: 0.290, green: 0.255, blue: 0.180)        // faint bronze edge

    static let accent = Color(red: 0.792, green: 0.655, blue: 0.396)           // champagne gold
    static let accentBright = Color(red: 0.925, green: 0.812, blue: 0.576)      // bright gold

    static let profit = Color(red: 0.298, green: 0.776, blue: 0.553)           // refined emerald
    static let loss = Color(red: 0.851, green: 0.337, blue: 0.353)             // muted crimson
    static let neutral = Color(red: 0.639, green: 0.620, blue: 0.580)          // warm gray

    static let textPrimary = Color(red: 0.961, green: 0.949, blue: 0.922)       // warm ivory
    static let textSecondary = Color(red: 0.643, green: 0.624, blue: 0.584)     // muted champagne-gray

    static let backgroundGradient = LinearGradient(
        colors: [
            Color(red: 0.063, green: 0.067, blue: 0.078),
            Color(red: 0.027, green: 0.029, blue: 0.035),
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
                // Subtle top-lit gold edge for a brushed-metal, premium feel.
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .strokeBorder(
                        LinearGradient(
                            colors: [
                                Theme.accent.opacity(0.35),
                                Theme.cardBorder.opacity(0.35),
                            ],
                            startPoint: .top,
                            endPoint: .bottom
                        ),
                        lineWidth: 1
                    )
            )
            .shadow(color: .black.opacity(0.45), radius: 14, x: 0, y: 6)
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
