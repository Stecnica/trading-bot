# Trading bot

A paper-trading application for one US equity list. It stores daily prices, records buys, and records a sale when the net profit of an open lot reaches the configured threshold. Prices come from [Massive](https://massive.com/stocks). Orders are not sent to a broker: a buy or a sale is a row in the database.

The same HTTP interface is used by a person in the browser, by a scheduled run of `cycle.py`, and by a digital agent (OpenClaw or anything else that can hold a cookie and post a form). Each client has its own session. A price update takes a lock, so two updates do not write the same session twice. Other requests keep their own sessions and wait their turn on the WSGI process.

English is the default language. Italian is included.

## What you see

The page is a bar and two tabs.

**Volume** is a treemap of the names with the highest trailing return. The tile size is the volume of the latest stored session. Green is up, red is down, and blue is inside the flat band from preferences. Sector and group filters apply before the ranking. Sessions and the number of names can be typed or stepped. The caption under the legend states the filter, the count, and how many tiles were drawn.

The sector list and the group list are the GICS names stored for the universe. Choosing a sector limits the groups to that sector. **All** clears that level. A filtered board is the same picture as an unfiltered one: fewer tiles, the same colour rule, and a caption that names the sector or the group.

**History** is one symbol, as a line of daily closes or as candles, with the volume of each session underneath. Periods are 1D, 1W, 1M, 3M, 6M, YTD, 1Y, and 2Y. Beside the chart: change, last, low, high, and the number of sessions in the window. Hover reads the session date, the close, and the traded value (shares times VWAP, or times the close when VWAP is missing). The drawing is either a generated image or an SVG in the page. The volume treemap stays HTML. The chart title follows the language, for example `TSLA — daily closes` or `TSLA — candles`.

From the bar:

- **Positions** lists each open lot, its cost, the latest price, the net profit, and whether it is ready to sell. A row is marked when the net profit is at or above the threshold and the price is recent enough.
- **Buy** records a lot. The fields are symbol, quantity, price, commissions, and taxes. An empty price uses the latest stored close. Empty commissions use the preference. Empty taxes stay zero: the tax on the gain is applied when the lot is sold. The amount cannot exceed the maximum investment.
- **Transactions** lists the latest buys and sales. A sale is the same table with type `sell`.
- The refresh button starts `cycle.py`: download missing closed sessions, then apply the sell rule.
- The checklist button runs only the sell rule.
- **Preferences** and **Sign out** are in the main menu. The language menu is the flag button just before it.

Net profit subtracts the sale commission and the tax on the gain from the proceeds, then compares that with the cost of the buy (price plus the commissions and taxes already stored). The threshold, the commission, the tax, and the maximum age of a price are preferences.

Preferences are two groups. Operations: threshold, investment, commission, tax, flat band, how many names the volume chart keeps, history days, return sessions, the history symbol, the maximum price age, and how long a message stays. Appearance: typeface, size, weight, theme, chart type, and drawing. Short labels sit on the fields. The full sentence is the `title` of the label and of the field. Saving closes the dialog first. A spinner covers the page until it reloads.

Theme **Automatic** follows the browser’s local time: light from 07:00 to 19:00, dark otherwise. Light and Dark stay fixed. The first paint uses the server clock; the page then follows the browser.

A message slides out under the bar when an update starts and when it finishes. It does not appear on an ordinary page load. While an update is running the page refreshes every 20 seconds. `?anteprima=messaggi` holds the message open and cycles four styles, for checking text, border, fill, and opacity.

## Operators

A person uses the buttons. A schedule runs `cycle.py` on its own, on weekdays after the US cash session, because the free price plan publishes a session only once it is closed. An agent uses the same routes as the form. There is no separate agent API and no broker plugin.

Sign in with `POST /login` (`username`, `password`, `csrf`). The username is `bot`. The password is the file `private/ui_password`: the first successful check replaces the plaintext with a scrypt hash. The session cookie lasts about a year and is refreshed on each request. Sign out is `POST /logout`. Five failed attempts lock the application for 15 minutes.

Every POST carries the `csrf` value from the page. After sign-in the routes are:

| Route | Role |
| --- | --- |
| `POST /buy` | Record a buy. Fields: `asset`, `amount`, `price`, `fees`, `taxes`, `csrf`. |
| `POST /sells` | Apply the sell rule to lots that are ready. |
| `POST /refresh` | Start one price update, which then applies the sell rule. |
| `POST /preferences` | Save preferences. Field names match the inputs in the dialog. |
| `POST /volume` | Save the volume filter: `return_days` (1–120), `universe_size` (10–500, step 10), `volume_class`, `csrf`. |
| `POST /logout` | End this session. |

`volume_class` is empty for the whole archive, `s:` plus a sector name, or `u:` plus a sector, a pipe, and a group name.

Two agents can be signed in at the same time. They do not share a session. The price update is the exception: `cycle.lock` admits one update. A second start is told that an update is already running.

## Languages

Each valid JSON file in `lang/` is one language, and the language menu lists it. A file that does not parse, or whose name is not a language code, is left out. The file name is the code (`en.json`, `it.json`). `language.name` in the file is the name shown beside the flag, written in that language. The default is English. The application does not follow `Accept-Language`. `?lang=` followed by a code that has a file selects it and stores the `lang` cookie for one year. The same list is on the sign-in card. Status written by a running update is a catalog key, so the same status file is shown in the language of the reader. An older status that is already a sentence is shown as stored.

Visible period labels are 1D, 1W, 1M, 3M, 6M, YTD, 1Y, 2Y in English and 1G, 1S, 1M, 3M, 6M, YTD, 1A, 2A in Italian. The values posted with the chart stay `1`, `7`, `30`, `90`, `180`, `ytd`, `365`, `730`.

## Prices

The client is the official `massive` package. One call is the grouped daily aggregate for the US stock market:

`GET /v2/aggs/grouped/locale/us/market/stocks/{date}`

The call asks for unadjusted bars and does not ask for OTC, so the OTC flag stays null. Each stored bar keeps the symbol, the session date, open, high, low, close, volume, VWAP, trade count, and the bar timestamp in milliseconds.

This copy is written for Stocks Basic. On that plan a session that is still open is not requested. A session the plan refuses as outside its history window is not requested again. Five calls per minute is the Basic cap, so the update waits between sessions. Paid plans remove that cap. The code does not switch plans by itself: it uses the key it is given.

Plan windows, read from Massive on 1 November 2026. Check the sources before relying on a price or a window. The history window is counted back from the request, not from a fixed start date.

| Plan | Price | Bars | Calls | Delivery |
| --- | --- | --- | --- | --- |
| Stocks Basic | Free | 2 years, end of day | 5 per minute | REST |
| Stocks Starter | $29 per month | 5 years, 15-minute delayed | Unlimited on paid plans | REST, WebSocket, flat files |
| Stocks Developer | $79 per month | 10 years, 15-minute delayed | Unlimited on paid plans | REST, WebSocket, flat files |
| Stocks Advanced | See the pricing page | All history back to 2003-09-10, real time | Unlimited on paid plans | REST, WebSocket, flat files |
| Stocks Business | $2,499 per month | All history, commercial licence | Unlimited on paid plans | REST, WebSocket, flat files |

Sources:

- [Massive stocks](https://massive.com/stocks), including the plan cards and the note that paid plans are listed with unlimited API calls
- [Pricing](https://massive.com/pricing)
- [How much historical stock data does Massive have?](https://massive.com/knowledge-base/article/how-much-historical-stock-data-does-massive-have) — Basic 2 years of bars, Starter 5, Developer 10, Advanced and Business everything back to 10 September 2003. Basic has no flat files. The pricing page’s “20+ years” is that same archive.

Individual plans are licensed for personal, non-professional use. Display or redistribution needs Business.

The history buttons stop at two years, which is the Basic window. Longer ranges are not offered until the stored bars cover them. Flat files are not downloaded. The key file can hold extra lines for a later S3 setup; the application reads only `MASSIVE_API_KEY`.

The universe is the S&P 500 list. A session stores every name on that list that the response contains. The volume chart then keeps the strongest trailing returns inside the chosen sector or group. The ranking reads only the sessions it needs, not the whole archive.

## Database

Five tables. `deploy/schema.sql` creates them. On startup `ensure_schema` creates any that are missing and adds missing price columns to an older `market_history`. It does not drop indexes that a live database already has.

| Table | Contents |
| --- | --- |
| `preferences` | One row per setting: name and value. |
| `market_history` | One bar per symbol and session. |
| `transactions` | Buys and sales. `type` is `buy` or `sell`. |
| `classification` | GICS sector and group. A sector has no parent. A group points at its sector. |
| `asset_class` | Symbol to its group. The symbol is the same `asset_name` used by prices and transactions. |

## Deploy

Requirements: Python 3.10, MariaDB, and the packages imported by the application (Flask, mysql-connector, pandas, matplotlib, massive). `yfinance` may be installed. The price update does not call it.

1. Create an empty database and a user that can create tables in it.
2. Apply `deploy/schema.sql`, or start the application once and let `ensure_schema` create the tables.
3. Copy `deploy/database.env.example` into the process environment. Fill `DB_SERVER`, `DB_USERNAME`, `DB_PASSWORD`, and `DB_NAME`. When both forms are set, `DB_SERVER_web5`, `DB_USERNAME_web5`, `DB_PASSWORD_web5`, and `DB_NAME_web5` win.
4. Copy `deploy/massive.env.example` to `private/massive_api.env` and set `MASSIVE_API_KEY`.
5. Put the interface password in `private/ui_password`. The first successful sign-in hashes it.
6. Point `ROOT`, `PRIVATE`, and `SITE_PACKAGES` in `bot_config.py` at this install. `ROOT` is the directory that contains `web/` and `private/`. The WSGI entry is `app.wsgi`. A generated session secret is written to `private/flask_secret` on first use.
7. Serve `app.wsgi`. Static files, including Bootstrap and the fonts, are under `static/` and are not loaded from a third party.

Nothing in those example files is a live credential. Do not commit a filled copy. `private/` stays outside the repository.

## Not in this version

`TODO.md` lists what is deliberately not built yet: the open session on Basic, history longer than the stored archive, flat-file download, a broker connection, a loss limit, an exchange calendar, and a check of database quantities against an account. The sell rule stays the deterministic threshold in `cycle.py` and in the sell check.

## Licence

[MIT](LICENSE). Copyright (c) 2026 Stefano Monti (Stecnica), <https://www.itecnica.it>.
