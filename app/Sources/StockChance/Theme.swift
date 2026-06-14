import SwiftUI

/// A light, warm "clean trading desk" visual theme: soft cream-ivory
/// backgrounds, rich bronze-gold accents, and high-contrast text - tuned for
/// comfortable, easy-on-the-eye reading in daylight while keeping the premium
/// feel. Applied consistently across the app via the helpers below.
enum Theme {
    // MARK: - Palette

    static let background = Color(red: 0.968, green: 0.953, blue: 0.929)       // warm cream
    static let backgroundElevated = Color(red: 1.0, green: 1.0, blue: 1.0)
    static let card = Color(red: 1.0, green: 1.0, blue: 1.0)                   // white cards
    static let cardBorder = Color(red: 0.882, green: 0.855, blue: 0.812)       // soft warm gray

    static let gold = Color(red: 0.604, green: 0.482, blue: 0.176)             // rich bronze-gold
    static let goldBright = Color(red: 0.761, green: 0.604, blue: 0.275)

    static let profit = Color(red: 0.106, green: 0.541, blue: 0.353)           // deep emerald
    static let loss = Color(red: 0.753, green: 0.227, blue: 0.169)             // deep crimson
    static let neutral = Color(red: 0.541, green: 0.518, blue: 0.482)

    static let textPrimary = Color(red: 0.110, green: 0.102, blue: 0.090)      // warm near-black
    static let textSecondary = Color(red: 0.361, green: 0.337, blue: 0.302)    // medium warm gray

    static let backgroundGradient = LinearGradient(
        colors: [
            Color(red: 0.984, green: 0.973, blue: 0.953),
            Color(red: 0.941, green: 0.922, blue: 0.890),
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
            .shadow(color: .black.opacity(0.07), radius: 10, x: 0, y: 4)
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
            .shadow(color: tint.opacity(0.18), radius: 20, x: 0, y: 10)
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

    /// Numeric decimal keyboard on iOS; no-op on macOS.
    @ViewBuilder
    func decimalKeyboard() -> some View {
        #if os(iOS)
        self.keyboardType(.decimalPad)
        #else
        self
        #endif
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
            .foregroundStyle(prominent ? Color.white : Theme.gold)
            .overlay(
                Capsule().strokeBorder(Theme.gold.opacity(prominent ? 0 : 0.5), lineWidth: 1)
            )
            .opacity(configuration.isPressed ? 0.7 : 1.0)
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
    }
}
