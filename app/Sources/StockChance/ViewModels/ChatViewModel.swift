import Foundation

/// Drives the "Ask the AI" chat: keeps the running conversation and sends
/// each new message to the backend along with live context (current
/// positions and watchlist) so Claude can ground its answers in the user's
/// actual data.
@MainActor
final class ChatViewModel: ObservableObject {
    @Published private(set) var messages: [ChatMessage] = []
    @Published private(set) var isAvailable: Bool?
    @Published private(set) var isSending = false
    @Published var errorMessage: String?

    func checkAvailability(baseURL: URL) async {
        let client = APIClient(baseURL: baseURL)
        do {
            let status = try await client.aiChatStatus()
            isAvailable = status.configured
        } catch {
            isAvailable = nil
        }
    }

    func send(_ text: String, baseURL: URL, positions: [Position], watchlist: [String]) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isSending else { return }

        errorMessage = nil
        messages.append(ChatMessage(role: "user", content: trimmed))
        isSending = true
        defer { isSending = false }

        let context = AIChatContext(
            positions: positions.map { ChatPosition(symbol: $0.symbol, quantity: $0.quantity, avgEntryPrice: $0.entryPrice) },
            watchlist: watchlist
        )
        let request = AIChatRequest(messages: messages, context: context)

        let client = APIClient(baseURL: baseURL)
        do {
            let response = try await client.sendChatMessage(request)
            messages.append(ChatMessage(role: "assistant", content: response.reply))
        } catch {
            errorMessage = AutoTraderViewModel.friendlyMessage(for: error)
        }
    }

    func clear() {
        messages = []
        errorMessage = nil
    }
}
