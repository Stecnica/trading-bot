# Not built yet

The interface, the price archive, and the sell rule are in place. The items below are out of scope until the stored history and the price plan support them.

- The open US session. Stocks Basic publishes a session after it has closed. Same-evening requests are refused. A paid plan is what adds the delayed or real-time session. The application does not change plan by itself.
- History past the Basic window. Buttons stop at 2Y. Five years, ten years, and the full archive wait until the stored bars cover them. On 1 November 2026 those windows are Starter, Developer, and Advanced. See the sources in `README.md`.
- Flat files. Basic does not include them. `private/massive_api.env` is read only for `MASSIVE_API_KEY`.
- A broker. Buys and sales are rows written through the HTTP interface. Nothing here submits an order.
- A loss limit, an exchange holiday calendar, and a reconciliation of database quantities with an account.

A buy is a `POST /buy` from a person, from a schedule, or from an agent. A sale is recorded when `cycle.py` or `POST /cycle` finds a lot at or above the net threshold.
