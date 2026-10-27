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

I prezzi arrivano ancora da Yahoo Finance, per uso personale, a blocchi. Se un blocco non risponde, il giro salva quello che ha e al passaggio successivo riprende i titoli rimasti indietro. Nel fine settimana una seduta di venerdì già in archivio non si riscarica. Il 26 ottobre 2026 quei blocchi sono stati rifiutati per quasi tutta la sera: una chiamata su sei ha scritto barre, e l'unica riuscita è arrivata a borsa chiusa. Spezzare le chiamate non aggira quel limite.

Il passo successivo è Massive (prima Polygon). L'account gratuito, Stocks Basic, è stato aperto il 27 ottobre 2026 con l'utenza GitHub. Le chiavi stanno in `private/massive_api.env`, fuori dal repository. Due accessi, due porte:

- REST, con la chiave dell'API. Il tetto del piano gratuito è di cinque richieste HTTP al minuto: conta la chiamata, non il titolo. Il riepilogo giornaliero `GET /v2/aggs/grouped/locale/us/market/stocks/{data}` restituisce apertura, massimo, minimo, chiusura e volume di tutte le azioni USA di un giorno in una sola risposta. Le barre di un singolo titolo restano una chiamata per simbolo. Sul gratuito i dati del giorno in corso non ci sono: arrivano a fine seduta, e lo storico delle barre è di due anni.
- File piatti su S3, un CSV compresso per giorno di borsa. Il piano gratuito non li include. Le coordinate sono già nel file delle chiavi, per quando si passerà a Stocks Starter.

Starter, pagato mese per mese, è il piano previsto per la seduta: chiamate senza quel tetto, barre con quindici minuti di ritardo, cinque anni e i file giornalieri. L'annuale si decide dopo che il bot disegna quelle barre. Advanced non serve a questo passo.

L'universo da scaricare è l'elenco S&P 500, tutti i 500, nell'ordine della tabella: è la coda di scarico, non una classifica. Ogni giro ne prende al massimo 100 fra quelli ancora senza storico aggiornato. In grafico restano i più redditizi sulle sedute scelte nelle preferenze, fra quelli già in archivio, fino al numero indicato.

La prima richiesta di un titolo è di circa sei mesi. Gli aggiornamenti aggiungono le sedute nuove e non cancellano le vecchie. `6M` mostra sempre gli ultimi 180 giorni. `YTD` mostra dal 1° gennaio, solo per i giorni presenti. I pulsanti di uno, due, cinque e dieci anni non compaiono da soli quando l'archivio si allunga.

L'accesso alla pagina è una sessione. La password è cifrata. Si esce solo con Esci. I tentativi falliti li conta anche il filtro del server.

La pagina è una barra e due schede, Volume e Storico, con Bootstrap tenuto in `static/`. Il cambio di scheda e dei controlli dello storico non ricarica la pagina. Siamo ancora in debug: messaggio, grafico e archivio devono coincidere. Il dettaglio di ciò che è fatto e di ciò che manca è in `TODO.md`.

## Cosa non fa

Non compra da solo. Non parla con un broker. Non ha un tetto di perdita, un calendario di borsa, né un controllo fra le quantità nel database e quelle su un conto. Yahoo resta il motore dei prezzi finché il collegamento a Massive non è nel codice. La regola di vendita resta codice deterministico.

## Avvio

Le credenziali del database stanno in variabili d'ambiente, non nel codice: `DB_SERVER`, `DB_USERNAME`, `DB_PASSWORD`, `DB_NAME`, oppure le stesse con il suffisso del sito. L'applicazione è Flask, servita da un processo WSGI.

Dipendenze usate: Flask, mysql-connector, pandas, yfinance, matplotlib.
