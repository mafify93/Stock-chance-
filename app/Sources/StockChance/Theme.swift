import SwiftUI

/// A dark, "private trading terminal" visual theme: warm espresso-charcoal
/// backgrounds, muted amber-gold accents, and refined typography - tuned for
/// comfortable extended viewing (lower blue light, softer contrast) without
/// losing the premium feel. Applied consistently across the app via the
/// helpers below.
enum Theme {
    // MARK: - Palette

    static let background = Color(red: 0.071, green: 0.063, blue: 0.059)       // warm espresso charcoal
    static let backgroundElevated = Color(red: 0.098, green: 0.087, blue: 0.078)
    static let card = Color(red: 0.122, green: 0.110, blue: 0.098)
    static let cardBorder = Color(red: 0.231, green: 0.196, blue: 0.149)

    static let gold = Color(red: 0.776, green: 0.655, blue: 0.388)             // muted amber gold
    static let goldBright = Color(red: 0.898, green: 0.792, blue: 0.557)

    static let profit = Color(red: 0.345, green: 0.733, blue: 0.557)           // softened emerald
    static let loss = Color(red: 0.851, green: 0.392, blue: 0.380)             // softened crimson
    static let neutral = Color(red: 0.580, green: 0.565, blue: 0.541)

    static let textPrimary = Color(red: 0.925, green: 0.910, blue: 0.886)      // warm ivory
    static let textSecondary = Color(red: 0.643, green: 0.612, blue: 0.580)

    static let backgroundGradient = LinearGradient(
        colors: [
            Color(red: 0.082, green: 0.071, blue: 0.063),
            Color(red: 0.039, green: 0.035, blue: 0.031),
        ],
        startPoint: .top,
        endPoint: .bottom
    )

    static let goldGradient = LinearGradient(
        colors: [goldBright, gold],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    // MARK: - Typography

    static func priceFont(_ size: CGFloat = 28) -> Font {
        .system(size: size, weight: .semibold, design: .serif)
    }

    static func sectionTitleFont() -> Font {
        .system(.headline, design: .rounded).weight(.semibold)
    }
}

// MARK: - View modifiers

private struct LuxuryCardModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding()
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(Theme.card)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .strokeBorder(Theme.cardBorder.opacity(0.6), lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.35), radius: 12, x: 0, y: 6)
    }
}

/// A larger, glowing "hero" card used for the Top Pick recommendation - a
/// glass-morphism treatment with a soft tinted glow matching the action
/// (buy = green, hold = gold, sell/avoid = red).
private struct HeroGlassCardModifier: ViewModifier {
    let tint: Color

    func body(content: Content) -> some View {
        content
            .padding(20)
            .background(
                ZStack {
                    RoundedRectangle(cornerRadius: 28, style: .continuous)
                        .fill(.ultraThinMaterial)
                    RoundedRectangle(cornerRadius: 28, style: .continuous)
                        .fill(
                            LinearGradient(
                                colors: [tint.opacity(0.30), Color.clear],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                }
            )
            .overlay(
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .strokeBorder(tint.opacity(0.55), lineWidth: 1.5)
            )
            .shadow(color: tint.opacity(0.25), radius: 24, x: 0, y: 12)
    }
}

private struct LuxuryBackgroundModifier: ViewModifier {
    func body(content: Content) -> some View {
        ZStack {
            Theme.backgroundGradient.ignoresSafeArea()
            content
        }
        .scrollContentBackground(.hidden)
    }
}

extension View {
    /// Standard "premium card" container: rounded corners, subtle gold-tinted
    /// border, soft shadow, on the theme's card background color.
    func luxuryCard() -> some View {
        modifier(LuxuryCardModifier())
    }

    /// Applies the app's dark charcoal gradient background and makes
    /// List/ScrollView backgrounds transparent so it shows through.
    func luxuryBackground() -> some View {
        modifier(LuxuryBackgroundModifier())
    }

    /// Larger glowing "hero" card for the Top Pick recommendation.
    func heroGlassCard(tint: Color) -> some View {
        modifier(HeroGlassCardModifier(tint: tint))
    }

    /// Small gold label used for section eyebrows ("TODAY", "LIVE", etc).
    func luxuryEyebrow() -> some View {
        self
            .font(.caption2.weight(.bold))
            .tracking(1.5)
            .foregroundStyle(Theme.gold)
            .textCase(.uppercase)
    }
}

/// A pill-shaped gold-accented primary button style.
struct LuxuryButtonStyle: ButtonStyle {
    var prominent: Bool = true

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(
                Capsule().fill(prominent ? AnyShapeStyle(Theme.goldGradient) : AnyShapeStyle(Theme.backgroundElevated))
            )
            .foregroundStyle(prominent ? Color.black : Theme.gold)
            .overlay(
                Capsule().strokeBorder(Theme.gold.opacity(prominent ? 0 : 0.5), lineWidth: 1)
            )
            .opacity(configuration.isPressed ? 0.7 : 1.0)
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
    }
}
