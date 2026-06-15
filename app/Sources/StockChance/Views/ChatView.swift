import SwiftUI

/// "Ask the AI" tab - a conversational chat grounded in the user's live
/// positions, watchlist, current signals, and the auto-trader's recent
/// activity (see `/api/ai/chat` on the backend).
struct ChatView: View {
    @EnvironmentObject private var apiConfig: APIConfig
    @StateObject private var viewModel = ChatViewModel()
    @ObservedObject private var positionStore = PositionStore.shared
    @ObservedObject private var watchlistStore = WatchlistStore.shared
    @State private var draft = ""
    @FocusState private var inputFocused: Bool

    private static let suggestions = [
        "How risky is my portfolio right now?",
        "What has the auto-trader done today?",
        "What's going on with my watchlist?",
        "Should I be worried about any of my positions?",
    ]

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("Ask the AI")
                .luxuryBackground()
                .toolbar {
                    ToolbarItem(placement: .primaryAction) {
                        Button {
                            viewModel.clear()
                        } label: {
                            Label("New Chat", systemImage: "square.and.pencil")
                        }
                        .disabled(viewModel.messages.isEmpty || viewModel.isSending)
                    }
                }
                .task {
                    await viewModel.checkAvailability(baseURL: apiConfig.baseURL)
                }
        }
    }

    @ViewBuilder
    private var content: some View {
        if viewModel.isAvailable == false {
            EmptyStateView(
                "Ask the AI Isn't Configured",
                systemImage: "sparkles",
                description: Text("This feature requires the backend's ANTHROPIC_API_KEY to be set - see the backend README.")
            )
        } else {
            VStack(spacing: 0) {
                conversation

                if let error = viewModel.errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(Theme.loss)
                        .padding(.horizontal)
                        .padding(.top, 6)
                }

                inputBar
            }
        }
    }

    @ViewBuilder
    private var conversation: some View {
        if viewModel.messages.isEmpty {
            emptyConversation
        } else {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        ForEach(viewModel.messages) { message in
                            ChatBubble(message: message)
                                .id(message.id)
                        }
                        if viewModel.isSending {
                            HStack {
                                ProgressView()
                                Text("Thinking...")
                                    .font(.subheadline)
                                    .foregroundStyle(Theme.textSecondary)
                            }
                            .padding(.leading, 4)
                            .id("thinking")
                        }
                    }
                    .padding()
                }
                .onChange(of: viewModel.messages.count) { _ in
                    scrollToBottom(proxy)
                }
                .onChange(of: viewModel.isSending) { _ in
                    scrollToBottom(proxy)
                }
            }
        }
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        withAnimation {
            if viewModel.isSending {
                proxy.scrollTo("thinking", anchor: .bottom)
            } else if let last = viewModel.messages.last {
                proxy.scrollTo(last.id, anchor: .bottom)
            }
        }
    }

    private var emptyConversation: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("ASK THE AI")
                        .luxuryEyebrow()
                    Text("Ask anything about your portfolio")
                        .font(Theme.sectionTitleFont())
                        .foregroundStyle(Theme.textPrimary)
                    Text("The AI can see your current positions, watchlist, recent signals, and what the auto-trader has been doing - ask it to explain what it sees.")
                        .font(.subheadline)
                        .foregroundStyle(Theme.textSecondary)
                }
                .luxuryCard()

                VStack(alignment: .leading, spacing: 10) {
                    Text("TRY ASKING")
                        .luxuryEyebrow()
                    ForEach(Self.suggestions, id: \.self) { suggestion in
                        Button {
                            Task { await send(suggestion) }
                        } label: {
                            HStack {
                                Text(suggestion)
                                    .font(.subheadline)
                                    .foregroundStyle(Theme.textPrimary)
                                    .multilineTextAlignment(.leading)
                                Spacer()
                                Image(systemName: "arrow.up.right")
                                    .foregroundStyle(Theme.gold)
                            }
                            .padding(12)
                            .background(Theme.card)
                            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .strokeBorder(Theme.cardBorder.opacity(0.6), lineWidth: 1)
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding()
        }
    }

    private var inputBar: some View {
        HStack(spacing: 10) {
            TextField("Ask about your portfolio...", text: $draft, axis: .vertical)
                .lineLimit(1...4)
                .focused($inputFocused)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Theme.card)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(Theme.cardBorder.opacity(0.6), lineWidth: 1)
                )

            Button {
                Task { await send(draft) }
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 30))
                    .foregroundStyle(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? Theme.textSecondary.opacity(0.5) : Theme.gold)
            }
            .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isSending)
        }
        .padding()
    }

    private func send(_ text: String) async {
        let message = text
        draft = ""
        inputFocused = false
        await viewModel.send(
            message,
            baseURL: apiConfig.baseURL,
            positions: positionStore.positions,
            watchlist: watchlistStore.symbols
        )
    }
}

/// A single chat message bubble - right-aligned gold for the user, left-
/// aligned card for the AI.
private struct ChatBubble: View {
    let message: ChatMessage

    private var isUser: Bool { message.role == "user" }

    var body: some View {
        HStack {
            if isUser { Spacer(minLength: 40) }

            Text(message.content)
                .font(.subheadline)
                .foregroundStyle(isUser ? Color.white : Theme.textPrimary)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                    Group {
                        if isUser {
                            Capsule().fill(Theme.goldGradient)
                        } else {
                            RoundedRectangle(cornerRadius: 16, style: .continuous)
                                .fill(Theme.card)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                                        .strokeBorder(Theme.cardBorder.opacity(0.6), lineWidth: 1)
                                )
                        }
                    }
                )

            if !isUser { Spacer(minLength: 40) }
        }
    }
}
