# Trading bot

Strumento personale per seguire un listino, registrare gli acquisti a mano e vendere un lotto quando il profitto netto supera la soglia scelta. Non invia ordini a un broker: i prezzi si scaricano, le operazioni restano nel database.

La licenza è MIT. Il repository nasce privato. Si può rendere pubblico in seguito, oppure invitare qualcuno mentre resta privato: sono due scelte separate.

## L'idea di partenza

Il bot tiene lo storico dei prezzi e le transazioni. Le preferenze dicono la soglia di profitto, l'investimento massimo, le commissioni e l'imposta. Dato un acquisto già registrato, quando il prezzo sale abbastanza da coprire commissioni, imposta e soglia, il lotto si vende e la vendita si scrive insieme all'acquisto.

La pagina mostra due cose. A blocchi, il volume dell'ultima seduta: la dimensione è la massa scambiata, il colore è lo stato del giorno (blu stabile, verde in crescita, rosso in perdita). A parte, lo storico del titolo scelto, a linea o a candele, secondo la preferenza.

Le tabelle sono tre.

- `preferences`: nome e valore. Soglia di profitto, investimento massimo, e le altre impostazioni di pagina e di calcolo.
- `market_history`: titolo, data, prezzo. In seguito si sono aggiunti apertura, massimo, minimo e volume.
- `transactions`: acquisto o vendita, titolo, quantità, prezzo, data, commissioni, tasse. Le vendite non hanno una tabella a parte: si distinguono dal tipo.

Gli acquisti partono da un record inserito da chi usa il bot. La vendita è il gesto automatico.

## Scelte fatte dopo

I prezzi arrivano da Yahoo Finance, per uso personale, a blocchi. Se un blocco non risponde, il giro salva quello che ha e al passaggio successivo riprende i titoli rimasti indietro. Nel fine settimana una seduta di venerdì già in archivio non si riscarica.

L'universo è l'elenco S&P 500. In grafico restano i più mossi nel periodo scelto, tra quelli scaricati, fino al numero indicato nelle preferenze.

L'accesso alla pagina è una sessione. La password è cifrata. Si esce solo con Esci. I tentativi falliti li conta anche il filtro del server.

La pagina di adesso è ancora un banco di prova: le sezioni stanno nell'ordine in cui sono state scritte. Il riordino deciso, e quello che manca, è in `TODO.md`.

## Cosa non fa

Non compra da solo. Non parla con un broker. Non ha un tetto di perdita, un calendario di borsa, né un controllo fra le quantità nel database e quelle su un conto. Un fornitore di prezzi a pagamento si aggancia solo quando la simulazione è piena e la fonte gratuita non basta. La regola di vendita resta codice deterministico.

## Avvio

Le credenziali del database stanno in variabili d'ambiente, non nel codice: `DB_SERVER`, `DB_USERNAME`, `DB_PASSWORD`, `DB_NAME`, oppure le stesse con il suffisso del sito. L'applicazione è Flask, servita da un processo WSGI.

Dipendenze usate: Flask, mysql-connector, pandas, yfinance, matplotlib.
