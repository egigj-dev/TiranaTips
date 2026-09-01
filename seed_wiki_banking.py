"""Create or refresh the practical banking knowledge-base pages in Wiki.js.

Run with:
    set -a; . ./.env; set +a
    python3 seed_wiki_banking.py

The script reads WIKI_URL and WIKI_TOKEN from the environment. It intentionally
only creates or updates the /banks pages declared below.
"""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


WIKI_URL = os.environ.get("WIKI_URL")
WIKI_TOKEN = os.environ.get("WIKI_TOKEN")


PAGES = [
    {
        "path": "banks",
        "title": "Banks in Tirana",
        "description": "A practical guide to banks, ATMs and banking safely in Tirana.",
        "content": """# Banks in Tirana

This guide helps residents and visitors find official information about banks, ATMs, accounts and digital banking in Tirana. It is not financial advice or a recommendation of any bank.

## Start here

- Albania's currency is the Albanian lek (**ALL**). Check the amount, currency and any charge shown on an ATM or payment terminal before approving a transaction.
- If an ATM offers to charge your foreign card in your home currency, it is offering **dynamic currency conversion (DCC)**. Read the exchange rate and fee shown on screen before choosing.
- Use an ATM attached to, or immediately outside, a bank branch when possible. Cover the keypad when entering your PIN and do not share PINs, passwords, one-time codes or card details.
- For a lost card or an unexpected transaction, contact the card issuer immediately using the number on the back of the card or its official app.

## Banks and useful pages

| Institution | What this page covers |
| --- | --- |
| [Bank of Albania (BoA)](/banks/boa) | Central bank and regulator — not a retail bank |
| [BKT](/banks/bkt) | Banka Kombëtare Tregtare |
| [Credins Bank](/banks/credins) | Retail and online-banking starting points |
| [Raiffeisen Bank Albania](/banks/raiffeisen) | Branch and ATM guidance |
| [Intesa Sanpaolo Bank Albania](/banks/intesa-sanpaolo) | Branch/ATM locator and digital support |
| [OTP Bank Albania](/banks/otp) | Accounts, eBanking and locations |
| [Tirana Bank](/banks/tirana-bank) | Retail-bank starting points |
| [ProCredit Bank Albania](/banks/procredit) | Retail and digital-banking starting points |
| [Union Bank](/banks/union-bank) | Retail-bank starting points |

## Choosing a bank or ATM

The best option depends on the service you need: opening an account, receiving a transfer, using a local debit card, or withdrawing cash with a foreign card. Before opening an account or sending money, compare the bank's current tariff, account terms, card limits, identity requirements and branch hours directly with that bank.

For foreign-card withdrawals, both the ATM owner and your own card issuer may charge a fee. The final amount and exchange rate can vary by card, currency and transaction, so confirm the information displayed by the ATM before continuing.

## Trusted sources

- [Bank of Albania — Annual Supervision Report 2025](https://www.bankofalbania.org/rc/doc/RV_I_MBIKEQYRJES_2025_shqip_34382.pdf)
- [Albanian Deposit Insurance Agency — member banks](https://asd.gov.al/en/home/deposit-insurance/banks-and-sca-members/)
""",
    },
    {
        "path": "banks/boa",
        "title": "Bank of Albania (BoA)",
        "description": "The central bank and banking supervisor of Albania.",
        "content": """# Bank of Albania (BoA)

The **Bank of Albania** is Albania's central bank. It is the institution responsible for monetary policy, the exchange-rate framework, bank licensing and supervision, and payment-system oversight.

## Important distinction

The Bank of Albania is **not** a commercial retail bank. It does not provide everyday personal accounts, debit cards, cash withdrawals or customer service for a visitor's bank card. For those services, use a licensed commercial bank such as BKT, Credins, Raiffeisen, Intesa Sanpaolo or OTP Bank Albania.

## When BoA information is useful

- Understanding the Albanian lek (ALL) and the country's banking system.
- Checking official information about regulated banks and financial-sector supervision.
- Reading official information about monetary policy and the exchange-rate framework.

## Official sources

- [Bank of Albania website](https://www.bankofalbania.org/)
- [Annual Report 2024](https://www.bankofalbania.org/rc/doc/RV_2024_anglisht_31880.pdf)
- [Annual Supervision Report 2025](https://www.bankofalbania.org/rc/doc/RV_I_MBIKEQYRJES_2025_shqip_34382.pdf)
""",
    },
    {
        "path": "banks/bkt",
        "title": "BKT (Banka Kombëtare Tregtare)",
        "description": "Practical information for using BKT's official banking and ATM services.",
        "content": """# BKT (Banka Kombëtare Tregtare)

**BKT**, short for *Banka Kombëtare Tregtare*, is a commercial bank operating in Albania. This page is a practical starting point for finding its official branches, ATM services and customer information.

## Useful for

- Finding a BKT branch or ATM.
- Checking the bank's current card, account and transfer terms.
- Using a BKT ATM: the bank describes cardless transactions at supported ATMs, including code- and QR-based options for its customers.

## Before making an ATM withdrawal

- Read the ATM screen carefully for any fees and the currency used for the transaction.
- When using a foreign card, confirm the amount and exchange rate before approval.
- Do not accept help from strangers at the machine; use official support if a card is retained or a transaction fails.

## Official sources

- [BKT website](https://bkt.com.al/en)
- [BKT cardless ATM transactions](https://bkt.com.al/en/cardless-transactions)
- [Bank of Albania — Annual Supervision Report 2025](https://www.bankofalbania.org/rc/doc/RV_I_MBIKEQYRJES_2025_shqip_34382.pdf)
""",
    },
    {
        "path": "banks/credins",
        "title": "Credins Bank",
        "description": "Practical information for Credins Bank branches, accounts and online banking.",
        "content": """# Credins Bank

**Credins Bank** is a commercial bank operating in Albania. Use its official channels to check current account terms, cards, branch availability, ATM services and digital-banking access.

## Useful for

- Everyday personal banking, accounts and cards.
- Finding a branch or ATM.
- Accessing Credins Online for account information and transfers, if you are an eligible customer.

## Before opening an account or requesting a card

Ask the branch to confirm the required identification, currencies supported, monthly charges, card-delivery timing, transfer charges and current transaction limits. These details can change and depend on the product.

## Security reminder

Use the official website or app rather than a link in an unexpected message. Never disclose a card PIN, online-banking password or one-time authorization code to anyone claiming to be from a bank.

## Official sources

- [Credins Bank website](https://www.bankacredins.com/)
- [Credins Online](https://www.bankacredins.com/personal/everyday-banking/online-banking)
- [Bank of Albania — Annual Supervision Report 2025](https://www.bankofalbania.org/rc/doc/RV_I_MBIKEQYRJES_2025_shqip_34382.pdf)
""",
    },
    {
        "path": "banks/raiffeisen",
        "title": "Raiffeisen Bank Albania",
        "description": "Practical information for Raiffeisen Bank Albania branches, ATMs and cards.",
        "content": """# Raiffeisen Bank Albania

**Raiffeisen Bank Albania** is a commercial bank with branches and ATMs in Tirana and elsewhere in Albania.

## Useful for

- Finding a branch, ATM or supported self-service device.
- Opening or managing eligible accounts and debit cards.
- Checking the bank's official guidance for foreign-card ATM use.

## Foreign-card ATM tip

Raiffeisen's official ATM guidance notes that an ATM may offer **dynamic currency conversion (DCC)** to international cardholders. You can accept or decline it; if you decline, the transaction is processed in the local currency and the card issuer determines the conversion rate. An acceptance fee may also apply to a foreign-issued card. Always read the machine's current disclosure before confirming.

## Official sources

- [Raiffeisen branches and ATMs](https://www.raiffeisen.al/en/individuals/ways-to-bank/branches-atms.html)
- [Raiffeisen debit cards](https://www.raiffeisen.al/en/individuals/products/cards/debit-cards.html)
- [Bank of Albania — Annual Supervision Report 2025](https://www.bankofalbania.org/rc/doc/RV_I_MBIKEQYRJES_2025_shqip_34382.pdf)
""",
    },
    {
        "path": "banks/intesa-sanpaolo",
        "title": "Intesa Sanpaolo Bank Albania",
        "description": "Practical information for Intesa Sanpaolo Bank Albania branches, ATMs and support.",
        "content": """# Intesa Sanpaolo Bank Albania

**Intesa Sanpaolo Bank Albania** is a commercial bank operating in Albania. Its official locator can be used to find branches and ATMs, while its digital channels provide current customer support and banking information.

## Useful for

- Locating a branch or ATM in Tirana.
- Checking account, card and transfer information directly with the bank.
- Finding official support if a card is lost, stolen or retained by an ATM.

## Before you go to a branch

Check the branch's current opening hours and the documents required for your request. For card or ATM problems, use the bank's official contact channel rather than relying on third-party social-media posts.

## Official sources

- [Intesa Sanpaolo Bank Albania branch and ATM locator](https://www.intesasanpaolobank.al/en/retail/branch-locator.html)
- [Intesa Sanpaolo Bank Albania website](https://www.intesasanpaolobank.al/)
- [Bank of Albania — Annual Supervision Report 2025](https://www.bankofalbania.org/rc/doc/RV_I_MBIKEQYRJES_2025_shqip_34382.pdf)
""",
    },
    {
        "path": "banks/otp",
        "title": "OTP Bank Albania",
        "description": "Practical information for OTP Bank Albania accounts, eBanking and locations.",
        "content": """# OTP Bank Albania

**OTP Bank Albania** is a commercial bank operating in Albania. Its individual-banking section provides official entry points for accounts, cards, eBanking and branch/ATM locations.

## Useful for

- Finding current personal account and card information.
- Using or applying for eligible digital-banking services.
- Locating official branches and ATMs.

## Check before using a service

Product fees, ATM availability, card limits and identity requirements depend on the service and can change. Confirm the current terms directly with OTP Bank Albania before opening an account, sending a transfer or using a card abroad.

## Official sources

- [OTP Bank Albania — individual banking](https://otpbank.al/en/individual/)
- [OTP Bank Albania website](https://otpbank.al/en/)
- [Bank of Albania — Annual Supervision Report 2025](https://www.bankofalbania.org/rc/doc/RV_I_MBIKEQYRJES_2025_shqip_34382.pdf)
""",
    },
    {
        "path": "banks/tirana-bank",
        "title": "Tirana Bank",
        "description": "Practical information for Tirana Bank's official retail banking channels.",
        "content": """# Tirana Bank

**Tirana Bank** is a commercial bank operating in Albania. Use the bank's official website and branch channels to verify current information for personal accounts, cards, transfers and ATM services.

## Useful for

- Finding a branch or ATM.
- Checking account and card services.
- Asking about current requirements for opening an account or receiving a transfer.

## Good practice

Before committing to a product, ask for the current tariff and terms in writing. For any foreign-card withdrawal, verify the fee, currency and conversion choice on the ATM screen before you approve the transaction.

## Official sources

- [Tirana Bank website](https://www.tiranabank.al/)
- [Bank of Albania — Annual Supervision Report 2025](https://www.bankofalbania.org/rc/doc/RV_I_MBIKEQYRJES_2025_shqip_34382.pdf)
""",
    },
    {
        "path": "banks/procredit",
        "title": "ProCredit Bank Albania",
        "description": "Practical information for ProCredit Bank Albania's official banking channels.",
        "content": """# ProCredit Bank Albania

**ProCredit Bank Albania** is a commercial bank operating in Albania. Its official channels are the right place to verify current information about accounts, cards, payments, digital services and branch access.

## Useful for

- Checking personal and business banking information.
- Finding the bank's current digital-banking and self-service options.
- Confirming account-opening requirements and transfer procedures.

## Before you choose a service

Compare the current account terms, card charges, cash-withdrawal fees, transfer charges and limits that apply to your situation. Do not send money based solely on payment instructions received by email or a message; verify a changed beneficiary account through an independent contact method.

## Official sources

- [ProCredit Bank Albania website](https://www.procreditbank.com.al/)
- [Bank of Albania — Annual Supervision Report 2025](https://www.bankofalbania.org/rc/doc/RV_I_MBIKEQYRJES_2025_shqip_34382.pdf)
""",
    },
    {
        "path": "banks/union-bank",
        "title": "Union Bank",
        "description": "Practical information for Union Bank's official retail banking channels.",
        "content": """# Union Bank

**Union Bank** is a commercial bank operating in Albania. For up-to-date details on its accounts, cards, digital services, ATMs and branches, consult the bank directly through its official website or branch network.

## Useful for

- Finding official account, card and transfer information.
- Locating a branch or ATM.
- Confirming the documents and current terms required for a banking service.

## Safety and verification

Use official bank contacts when you need help. A legitimate bank will not ask for your PIN, password or one-time authorization code by phone, email or social media.

## Official sources

- [Union Bank website](https://www.unionbank.al/)
- [Bank of Albania — Annual Supervision Report 2025](https://www.bankofalbania.org/rc/doc/RV_I_MBIKEQYRJES_2025_shqip_34382.pdf)
""",
    },
]


def graphql(query: str, variables: dict | None = None) -> dict:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    request = Request(
        WIKI_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {WIKI_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
    except (HTTPError, URLError) as error:
        raise RuntimeError(f"Wiki.js request failed: {error}") from error

    if data.get("errors"):
        raise RuntimeError(f"Wiki.js GraphQL error: {data['errors']}")
    return data["data"]


def main() -> int:
    if not WIKI_URL or not WIKI_TOKEN:
        print("WIKI_URL and WIKI_TOKEN must be set.", file=sys.stderr)
        return 1

    pages = graphql("{ pages { list { id path locale } } }")["pages"]["list"]
    existing = {(page["path"], page["locale"]): page["id"] for page in pages}

    create_mutation = """
      mutation CreatePage($content: String!, $description: String!, $editor: String!,
        $isPublished: Boolean!, $isPrivate: Boolean!, $locale: String!, $path: String!,
        $tags: [String]!, $title: String!) {
        pages {
          create(content: $content, description: $description, editor: $editor,
            isPublished: $isPublished, isPrivate: $isPrivate, locale: $locale,
            path: $path, tags: $tags, title: $title) {
            responseResult { succeeded message }
            page { id path title }
          }
        }
      }
    """
    update_mutation = """
      mutation UpdatePage($id: Int!, $content: String!, $description: String!,
        $title: String!, $tags: [String]!) {
        pages {
          update(id: $id, content: $content, description: $description,
            title: $title, tags: $tags) {
            responseResult { succeeded message }
            page { id path title }
          }
        }
      }
    """

    for item in PAGES:
        values = {
            "content": item["content"],
            "description": item["description"],
            "title": item["title"],
            "tags": ["banks", "tirana", "financial-services"],
        }
        page_id = existing.get((item["path"], "en"))
        if page_id is None:
            values.update(
                {
                    "editor": "markdown",
                    "isPublished": True,
                    "isPrivate": False,
                    "locale": "en",
                    "path": item["path"],
                }
            )
            result = graphql(create_mutation, values)["pages"]["create"]
            action = "Created"
        else:
            values["id"] = page_id
            result = graphql(update_mutation, values)["pages"]["update"]
            action = "Updated"

        response = result["responseResult"]
        if not response["succeeded"]:
            raise RuntimeError(f"{action} {item['path']} failed: {response['message']}")
        print(f"{action}: /{result['page']['path']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
