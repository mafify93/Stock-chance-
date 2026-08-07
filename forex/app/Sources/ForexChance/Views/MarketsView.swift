import SwiftUI

/// Browse and search the tradable currency-pair universe, grouped into
/// majors and crosses. Tapping a pair opens its detail screen.
struct MarketsView: View {
    @State private var pairs: [PairInfo] = []
    @State private var query = ""
    @State private var isLoading = false
    @State private var errorMessage: String?

    private var filtered: [PairInfo] {
        guard !query.isEmpty else { return pairs }
        let needle = query.uppercased().replacingOccurrences(of: "/", with: "").replacingOccurrences(of: "_", with: "")
        return pairs.filter { $0.pair.replacingOccurrences(of: "_", with: "").contains(needle) }
    }

    private var majors: [PairInfo] { filtered.filter { $0.category == "major" } }
    private var minors: [PairInfo] { filtered.filter { $0.category == "minor" } }

    var body: some View {
        NavigationStack {
            ScreenBackground {
                Group {
                    if isLoading && pairs.isEmpty {
                        ProgressView().tint(Theme.accent)
                    } else if let error = errorMessage, pairs.isEmpty {
                        InfoState(icon: "wifi.exclamationmark", title: "Couldn't load pairs", message: error)
                    } else {
                        ScrollView {
                            VStack(spacing: 16) {
                                if !majors.isEmpty {
                                    PairSection(title: "Majors", pairs: majors)
                                }
                                if !minors.isEmpty {
                                    PairSection(title: "Crosses", pairs: minors)
                                }
                            }
                            .padding()
                        }
                    }
                }
            }
            .navigationTitle("Markets")
            .searchable(text: $query, prompt: "Search pairs, e.g. EUR or JPY")
        }
        .task { await load() }
    }

    private func load() async {
        isLoading = true
        defer { isLoading = false }
        let client = APIClient(baseURL: APIConfig.shared.baseURL)
        do {
            pairs = try await client.pairs()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct PairSection: View {
    let title: String
    let pairs: [PairInfo]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(Theme.sectionTitleFont())
                .foregroundStyle(Theme.textPrimary)
                .frame(maxWidth: .infinity, alignment: .leading)

            ForEach(pairs) { pair in
                NavigationLink {
                    PairDetailView(pair: pair)
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(pair.display)
                                .font(.system(.headline, design: .rounded))
                                .foregroundStyle(Theme.textPrimary)
                            Text("\(pair.base) / \(pair.quote)")
                                .font(.caption)
                                .foregroundStyle(Theme.textSecondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Theme.textSecondary)
                    }
                    .cardStyle()
                }
                .buttonStyle(.plain)
            }
        }
    }
}
