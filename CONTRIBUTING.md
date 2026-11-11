# Contributing

The licence is MIT. From a fresh clone, the Start section gets the page open: install the packages, run `python deploy/prepare.py`, and sign in as `bot` with the password the command prints. The sample sessions are enough to read the page and try a change.

A language, a bug fix, or a small change needs no issue first: open a pull request. Anything larger — a new price plan, the broker, a change to the sell rule — open an issue first and wait for an answer, so the work is not done twice. `TODO.md` is the order of the work, not a wish list: the items there wait for the history and the plan to support them.

## A language

The menu lists every valid file in `lang/`. English, Italian, Spanish, French, and Latin are already there. A new language is a new file beside them.

Copy `lang/en.json` to `lang/` plus the language code plus `.json`, for example `lang/de.json`. The file name is the code. Set `language.name` to the name of the language, written in that language. Translate the values. Keep the keys, and keep the placeholders as they are: `{threshold}`, `{minutes}`, `{name}`, and the rest. A key you leave out shows the English text. A file that does not parse stays out of the menu.

Open the page and choose the new flag. Read Positions, Buy, the volume gear, and a price update. The status line of an update is a catalog key, so the same run is shown in the language of the reader.

## The price plan

Continuing is the path. The key in `private/massive_api.env` selects the plan. To let a richer plan through, work in `bot_massive.py`: `update_from_massive` asks for the bars, and `last_completed_session` decides which day that is.

Run `python cycle.py` with that key. The new bars belong in `market_history`, and the threshold sale and the score follow them. When the archive holds the longer history, add the matching period values next to `730`.

## The broker

`POST /buy`, `sell_ready_lots`, and `bot_decide.apply_once` finish in `insert_transaction`. The broker call belongs on that write: the same symbol, quantity, price, and side go to the broker, and the row is stored when the broker accepts the order. Credentials stay in `private/`, beside the Massive key.

Exercise it on the broker's paper account. That account uses the same API, a separate endpoint, and simulated money. `python cycle.py`, or an agent signed in and posting `/update`, should show the order on the paper account and the matching row in `transactions`.

## A change to the calculation

`bot_logic.py` is the net profit and the lots. `bot_decide.py` turns a score into one buy or a sale. `cycle.py` runs the prices, the threshold sale, and that decision, in that order. In the pull request, show the numbers: a lot at the threshold sells, a lot under it stays, and a score buy stays within the maximum investment.

Money stays `Decimal`.

## A bug

Say the page, the route, the language, and the plan of your key. Say what you expected and what happened instead. The sample archive is invented data: a bug that needs real bars needs your numbers, not the database.

## The pull request

One change. The commit subject is in English and names the change. `private/` and a filled environment file stay out of the commit. The sample archive is invented data. Real bars stay on your machine.
