import Foundation

final class SearchViewModel: ObservableObject {
    @Published var query: String = "" {
        didSet { scheduleSearch() }
    }
    @Published private(set) var results: [SearchResult] = []
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    private var searchTask: Task<Void, Never>?

    private func scheduleSearch() {
        searchTask?.cancel()
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            results = []
            errorMessage = nil
            isLoading = false
            return
        }

        searchTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled, let self else { return }
            await self.runSearch(trimmed)
        }
    }

    @MainActor
    private func runSearch(_ text: String) async {
        isLoading = true
        errorMessage = nil
        do {
            let client = APIClient(baseURL: APIConfig.shared.baseURL)
            results = try await client.search(text)
        } catch {
            errorMessage = error.localizedDescription
            results = []
        }
        isLoading = false
    }
}
