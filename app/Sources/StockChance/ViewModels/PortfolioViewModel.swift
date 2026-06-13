import Foundation

/// Fetches account summaries (cash, equity, buying power, open positions)
/// from every connected brokerage account - Alpaca paper/live and Questrade
/// - for the Portfolio tab's "Broker Accounts" section.
@MainActor
final class PortfolioViewModel: ObservableObject {
    struct AccountSummary: Identifiable {
        let account: TradeAccount
        var equity: Double?
        var cash: Double?
        var buyingPower: Double?
        var currency: String?
        var positions: [BrokerHolding]

        var id: String { account.id }
    }

    struct BrokerHolding: Identifiable {
        var symbol: String
        var quantity: Double
        var marketValue: Double?
        var unrealizedPL: Double?

        var id: String { symbol }
    }

    @Published private(set) var summaries: [AccountSummary] = []
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    func refresh(accounts: [TradeAccount], brokerStore: BrokerStore, baseURL: URL) async {
        guard !accounts.isEmpty else {
            summaries = []
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        let client = APIClient(baseURL: baseURL)
        var results: [AccountSummary] = []

        for account in accounts {
            do {
                switch account {
                case .alpacaPaper:
                    results.append(try await summary(for: account, credentials: brokerStore.paperCredentials, client: client))

                case .alpacaLive:
                    results.append(try await summary(for: account, credentials: brokerStore.liveCredentials, client: client))

                case .questrade(let accountNumber):
                    if brokerStore.isQuestradeAccessTokenExpired {
                        try await brokerStore.refreshQuestradeToken(client: client)
                    }
                    let credentials = brokerStore.questradeCredentials
                    let balances = try await client.questradeBalances(accountNumber: accountNumber, credentials: credentials)
                    let positions = try await client.questradePositions(accountNumber: accountNumber, credentials: credentials)
                    results.append(AccountSummary(
                        account: account,
                        equity: balances.totalEquity,
                        cash: balances.cash,
                        buyingPower: balances.buyingPower,
                        currency: balances.currency,
                        positions: positions.map {
                            BrokerHolding(symbol: $0.symbol, quantity: $0.quantity, marketValue: $0.marketValue, unrealizedPL: $0.unrealizedPl)
                        }
                    ))
                }
            } catch {
                errorMessage = error.localizedDescription
            }
        }

        summaries = results
    }

    private func summary(for account: TradeAccount, credentials: BrokerCredentials, client: APIClient) async throws -> AccountSummary {
        let info = try await client.brokerAccount(credentials: credentials)
        let positions = try await client.brokerPositions(credentials: credentials)
        return AccountSummary(
            account: account,
            equity: info.equity ?? info.portfolioValue,
            cash: info.cash,
            buyingPower: info.buyingPower,
            currency: info.currency,
            positions: positions.map {
                BrokerHolding(symbol: $0.symbol, quantity: $0.quantity, marketValue: $0.marketValue, unrealizedPL: $0.unrealizedPl)
            }
        )
    }
}
