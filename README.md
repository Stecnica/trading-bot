# Trading bot

A paper-trading application for one US equity list. It stores daily prices, records buys, and records a sale when the net profit of an open lot reaches the configured threshold. Prices come from [Massive](https://massive.com/stocks). Orders are not sent to a broker: a buy or a sale is a row in the database.

The same HTTP interface is used by a person in the browser, by a scheduled run of `cycle.py`, and by a digital agent (OpenClaw or anything else that can hold a cookie and post a form). Each client has its own session. A price update takes a lock, so two updates do not write the same session twice. Other requests keep their own sessions and wait their turn on the WSGI process.

English is the default language. Every other language is a file in `lang/`.

## What you see

The page is a bar and two tabs. The icon links home. The title is the words Trading bot followed by the selected list, `S&P500`. Opening that word shows the entry and a disabled line, `next idea...`. The pictures below are the light theme.

![All](static/screenshot/Volume%20All.png)

**All** draws the names in the archive as blocks. The first control is the switch All | Sector. Beside it, on All and on Sector, is the flat band: the same value as in preferences. A block’s size is the volume of the latest stored session. Its colour and the percentage on it are that session against the one before: green up, red down, blue inside the flat band from preferences. The company name sits on the block. The sector name sits on the blocks of that sector. A block that would come out as a strip is left out and the space goes to the blocks that remain. In this picture: 77 blocks.

![Sector](static/screenshot/Volume%20Sector.png)

**Sector** is the other side of the same switch. The controls after it are Rank | Volume, Sessions, Names, the sector list, the group list, and the flat band. Rank places the rectangles in return order. Volume places the largest first. Sessions is how many sessions that return uses. Names is how many of those names are drawn. The sector list and the group list are the GICS names stored for this database. Choosing a sector limits the groups to that sector. The first entry of each list, All, clears that level. In this picture Rank is selected, Sessions is 240, Names is 40, and both lists are on All: the 40 names with the highest return over those sessions. The tile also shows the score. The same colour rule as All. `POST /volume` saves sessions, names, the sector or group, and the flat band. The switch and Rank | Volume are not saved.

![History](static/screenshot/History%20Line.png)

**History** is one symbol, as a line of daily closes or as candles, with the volume of each session underneath. Periods are built from `period.abbr.*` in the active language. Beside the chart: change, last, low, high, and the number of sessions in the window. This picture is MRNA, the line, six months: the change is +356.62%, the last close is 241.46, the low is 43.9, the high is 261, and the window has 125 sessions. Hover reads the session date, the close, and the traded value (shares times VWAP, or times the close when VWAP is missing). The drawing is either a generated image or an SVG in the page. The volume treemap stays HTML. The chart title follows the language, for example `TSLA — daily closes` or `TSLA — candles`. The same view as candles is `static/screenshot/History Candles.png`. The open sector list is `static/screenshot/Volume Sector - Sector Menu.png` and the open group list is `static/screenshot/Volume Sector - Group Menu.png`.

![Positions](static/screenshot/Positions.png)

**Positions** lists each open lot, its cost, the latest price, the net profit, and whether it is ready to sell. A row is marked when the net profit is at or above the threshold and the price is recent enough. This picture is the open lot IDXX, bought on 02/11/2026: quantity 1.48889285, cost 671.64, latest price 670.71 on 05/11/2026, net profit −0.34%, under the threshold of 5.00%.

Net profit subtracts the sale commission and the tax on the gain from the proceeds, then compares that with the cost of the buy (price plus the commissions and taxes already stored). The threshold, the commission, the tax, and the maximum age of a price are preferences.

![Buy](static/screenshot/Buy.png)

**Buy** records a lot with `POST /buy`. The fields are symbol, quantity, price, commissions, and taxes. An empty price uses the latest stored close. Empty commissions use the preference. Empty taxes stay zero: the tax on the gain is applied when the lot is sold. The amount cannot exceed the maximum investment. In this picture the panel is open over the IDXX candle chart. The symbol field contains MRNA. Quantity, price, and commissions are empty, and taxes are 0.

![Transactions](static/screenshot/Transactions.png)

**Transactions** lists the latest buys and sales. A sale is the same table with type `sell`. This picture is the one stored buy, over the IDXX line: 02/11/2026, IDXX, quantity 1.48889285, price 671.64, commissions 1, taxes 0.

The update button is `POST /update`. It starts `cycle.py`: download missing closed sessions, then apply the sell rule. The checklist button is `POST /cycle`. It runs only the sell rule. **Preferences** and **Sign out** are in the main menu, shown open in `static/screenshot/Menu.png`. The language menu is the flag button just before it, shown open in `static/screenshot/Languages.png`: English, Español, Français, Italiano, Latina.

![Preferences](static/screenshot/Preferences.png)

Preferences are three groups. Operations: threshold, investment, commission, tax, and the maximum price age. Page: flat band, how many names the volume chart keeps, history days, return sessions, the history symbol, and how long a message stays. Appearance: typeface, size, weight, theme, chart type, and drawing. Short labels sit on the fields. The full sentence is the `title` of the label and of the field. Saving is `POST /prefs` and closes the dialog first. A spinner covers the page until it reloads. This picture: threshold 0.05, investment 1000, commission 0.001, tax 0.26, price age 120 hours, flat band 0.005, 50 volume names, 730 history days, 240 return sessions, history symbol MRNA, messages stay 8 seconds, typeface Outfit, size 100, weight regular, theme Light, chart Line, drawing Vector.

Theme **Automatic** follows the browser’s local time: light from 07:00 to 19:00, dark otherwise. Light and Dark stay fixed. The first paint uses the server clock; the page then follows the browser.

A message slides out under the bar when an update starts and when it finishes. It does not appear on an ordinary page load. While an update is running the page refreshes every 20 seconds. `?preview=messages` holds the message open and cycles four styles, for checking text, border, fill, and opacity.

## Operators

A person uses the buttons. A schedule runs `cycle.py` on its own, on weekdays after the US cash session, because the free price plan publishes a session only once it is closed. An agent uses the same routes as the form. There is no separate agent API and no broker plugin.

Sign in with `POST /login` (`username`, `password`, `csrf`). The username is `bot`. The password is the file `private/ui_password`: the first successful check replaces the plaintext with a scrypt hash. The session cookie lasts about a year and is refreshed on each request. Sign out is `POST /exit`. Five failed attempts lock the application for 15 minutes.

Every POST carries the `csrf` value from the page. After sign-in the routes are:

| Route | Role |
| --- | --- |
| `POST /buy` | Record a buy. Fields: `asset`, `amount`, `price`, `fees`, `taxes`, `csrf`. |
| `POST /cycle` | Apply the sell rule to lots that are ready. |
| `POST /update` | Start one price update, which then applies the sell rule. |
| `POST /prefs` | Save preferences. Field names match the inputs in the dialog. |
| `POST /volume` | Save the volume filter: `return_days` (1–240), `names` (10–500, step 10), `volume_class`, `stable_band` (0–0.2), `csrf`. `order` (`rank` or `volume`) and `scope` (`all` or `sector`) are sent with the picture and are not saved. |
| `POST /exit` | End this session. |

`volume_class` is empty for the whole archive, `s:` plus a sector name, or `u:` plus a sector, a pipe, and a group name.

Two agents can be signed in at the same time. They do not share a session. The price update is the exception: `cycle.lock` admits one update. A second start is told that an update is already running.

## Languages

Each valid JSON file in `lang/` is one language, and the language menu lists it. A file that does not parse, or whose name is not a language code, is left out. The file name is the code, for example `en.json`. `language.name` in the file is the name shown beside the flag, written in that language. The default is English. The application does not follow `Accept-Language`. `?lang=` followed by a code that has a file selects it and stores the `lang` cookie for one year. The same menu is the flag at the top right of the sign-in card. Status written by a running update is a catalog key, so the same status file is shown in the language of the reader. An older status that is already a sentence is shown as stored.

Period buttons are built from five abbreviations in the active language file: `period.abbr.day`, `period.abbr.week`, `period.abbr.month`, `period.abbr.year`, and `period.abbr.start`. The buttons are one day, one week, one month, three months, six months, the start-of-year abbreviation, one year, and two years. The values posted with the chart stay `1`, `7`, `30`, `90`, `180`, `ytd`, `365`, `730`.

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

The selected list is the S&P 500. A session stores every name on that list that the response contains. The volume chart then keeps the strongest trailing returns inside the chosen sector or group. The ranking reads only the sessions it needs, not the whole archive.

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

Requirements: Python 3.10, MariaDB, and the packages in `requirements.txt`. `yfinance` is imported when the application starts. The price update does not call it.

1. `pip install -r requirements.txt`
2. Create an empty database and a user that can create tables in it.
3. Apply `deploy/schema.sql`, or start the application once and let `ensure_schema` create the tables.
4. Copy `deploy/database.env.example` into the process environment. Fill `DB_SERVER`, `DB_USERNAME`, `DB_PASSWORD`, and `DB_NAME`. A suffixed form of the same name is used first.
5. With those variables set, `python deploy/sample_archive.py` loads six invented sessions for eight names, one sector, and one buy. It refuses to write when `market_history` already has rows. The rows are not market prices and not a Massive download. The page can be opened before any price update.
6. Copy `deploy/massive.env.example` to `private/massive_api.env` and set `MASSIVE_API_KEY`. A real update uses that key and the caller's own plan.
7. Put the interface password in `private/ui_password`. The first successful sign-in hashes it.
8. `ROOT` is the parent of the directory that contains the application, and `private/` sits next to `web/`. `SITE_PACKAGES` is the `SITE_PACKAGES` environment variable, or the process user’s own site-packages. The WSGI entry is `app.wsgi`. A generated session secret is written to `private/flask_secret` on first use.
9. Serve `app.wsgi`. Static files, including Bootstrap and the fonts, are under `static/` and are not loaded from a third party.

Nothing in those example files is a live credential. Do not commit a filled copy. `private/` stays outside the repository.

## Not in this version

`TODO.md` lists what is deliberately not built yet: the open session on Basic, history longer than the stored archive, flat-file download, a broker connection, a loss limit, an exchange calendar, and a check of database quantities against an account. The sell rule stays the deterministic threshold in `cycle.py` and in the sell check.

## Licence

[MIT](LICENSE). Copyright (c) 2026 Stefano Monti (Stecnica), <https://www.itecnica.it>.
