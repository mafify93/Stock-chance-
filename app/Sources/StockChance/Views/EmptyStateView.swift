import SwiftUI

/// A simple "nothing to show" placeholder, used in place of
/// `ContentUnavailableView` (iOS 17+) so the app can target iOS 16.
struct EmptyStateView: View {
    let title: String
    let systemImage: String
    var description: Text?

    init(_ title: String, systemImage: String, description: Text? = nil) {
        self.title = title
        self.systemImage = systemImage
        self.description = description
    }

    static let search = EmptyStateView("No Results", systemImage: "magnifyingglass")

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.system(size: 40))
                .foregroundStyle(Theme.textSecondary)
            Text(title)
                .font(.headline)
                .foregroundStyle(Theme.textPrimary)
            if let description {
                description
                    .font(.subheadline)
                    .foregroundStyle(Theme.textSecondary)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}
