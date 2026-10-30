# Trading bot

Strumento personale per seguire un listino, registrare gli acquisti a mano e vendere un lotto quando il profitto netto supera la soglia scelta. Non invia ordini a un broker: i prezzi si scaricano, le operazioni restano nel database.

La licenza è MIT. Il repository nasce privato. Si può rendere pubblico in seguito, oppure invitare qualcuno mentre resta privato: sono due scelte separate.

## L'idea di partenza

Il bot tiene lo storico dei prezzi e le transazioni. Le preferenze dicono la soglia di profitto, l'investimento massimo, le commissioni e l'imposta. Dato un acquisto già registrato, quando il prezzo sale abbastanza da coprire commissioni, imposta e soglia, il lotto si vende e la vendita si scrive insieme all'acquisto.

La pagina mostra due cose. A blocchi, il volume dell'ultima seduta: la dimensione è la massa scambiata, il colore è lo stato del giorno (blu stabile, verde in crescita, rosso in perdita). A parte, lo storico del titolo scelto, a linea o a candele, secondo la preferenza. Sotto le date di quello storico stanno le barre del volume in azioni. Il passaggio del mouse legge data, chiusura e importo della seduta: l'importo non arriva già calcolato, è il numero di azioni per il prezzo medio, oppure per la chiusura se il prezzo medio manca.

Le tabelle sono cinque.

- `preferences`: nome e valore. Soglia di profitto, investimento massimo, e le altre impostazioni di pagina e di calcolo.
- `market_history`: titolo, data, prezzo, apertura, massimo, minimo, volume, prezzo medio ponderato, numero di scambi, istante della barra in millisecondi e flag OTC.
- `transactions`: acquisto o vendita, titolo, quantità, prezzo, data, commissioni, tasse. Le vendite non hanno una tabella a parte: si distinguono dal tipo.
- `classification`: classe GICS. Il settore ha il codice uguale al nome e nessun padre. La sotto-industria ha per codice settore e nome separati da un tab, e punta al settore.
- `asset_class`: simbolo verso la sua sotto-industria. Il simbolo è lo stesso `asset_name` di prezzi e transazioni. Da lì si risale al settore.

Gli acquisti partono da un record inserito da chi usa il bot. La vendita è il gesto automatico.

## Scelte fatte dopo

I prezzi arrivano da Massive (prima Polygon), con il client ufficiale `massive`. Yahoo è stato lasciato perché il 26 ottobre 2026 ha rifiutato le chiamate per quasi tutta la sera: spezzarle non aggira quel limite. L'account gratuito, Stocks Basic, è stato aperto il 27 ottobre 2026 con l'utenza GitHub. Le chiavi stanno in `private/massive_api.env`, fuori dal repository. Due accessi, due porte:

- REST, con la chiave dell'API. Il tetto del piano gratuito è di cinque richieste HTTP al minuto: conta la chiamata, non il titolo. Il riepilogo giornaliero `GET /v2/aggs/grouped/locale/us/market/stocks/{data}` restituisce, per tutte le azioni USA di un giorno e in una sola risposta, apertura, massimo, minimo, chiusura, volume, prezzo medio ponderato, numero di scambi, istante in millisecondi e flag OTC. Si tiene tutto. La data della seduta resta la mezzanotte del giorno chiesto: l'istante di Massive sta accanto, non la sostituisce. Il giro ne chiede una per seduta, filtra i 500 dell'elenco e lascia passare tredici secondi fra una chiamata e l'altra, fino a esaurire le sedute ancora mancanti. Sul gratuito i dati del giorno in corso non ci sono: si chiede l'ultima seduta già chiusa a New York, e lo storico delle barre è di due anni. I prezzi non sono aggiustati per gli split, come le barre già in archivio.
- File piatti su S3, un CSV compresso per giorno di borsa. Il piano gratuito non li include. Le coordinate sono già nel file delle chiavi, per quando si passerà a Stocks Starter. Il client Python non li scarica: non è il suo compito.

Starter, pagato mese per mese, è il piano previsto per la seduta aperta: chiamate senza quel tetto, barre con quindici minuti di ritardo, cinque anni e i file giornalieri. L'annuale si decide dopo che il bot disegna quelle barre. Advanced non serve a questo passo.

L'universo è l'elenco S&P 500, tutti i 500. Non è più una coda di titoli: una seduta porta il mercato intero e si tengono solo quelli dell'elenco. In grafico restano i più redditizi sulle sedute scelte nelle preferenze, fra quelli già in archivio, fino al numero indicato. Sul grafico del volume si sceglie prima il settore e poi il gruppo dentro quel settore: il filtro entra prima della classifica.

Le sedute nuove si aggiungono e non cancellano le vecchie. Lo storico arriva al 28 ottobre 2024. `6M` mostra sempre gli ultimi 180 giorni. `YTD` mostra dal 1° gennaio, solo per i giorni presenti. `1A` e `2A` mostrano gli ultimi 365 e 730 giorni, solo per i giorni presenti. Cinque anni, dieci anni e «sempre» non hanno un pulsante: quelle barre non sono nel piano gratuito.

L'accesso alla pagina è una sessione. La password è cifrata. Si esce solo con Esci. I tentativi falliti li conta anche il filtro del server.

La pagina è una barra e due schede, Volume e Storico, con Bootstrap tenuto in `static/`. Dalla barra si aprono posizioni, acquisto e transazioni. Il cambio di scheda e dei controlli dello storico non ricarica la pagina. Siamo ancora in debug: messaggio, grafico e archivio devono coincidere. Il dettaglio di ciò che è fatto e di ciò che manca è in `TODO.md`.

`?anteprima=messaggi` accende il riquadro sotto la barra e fa girare ogni 4 secondi quattro stati su tre righe: message, success, warning e alert. Serve a controllare testo, bordo, fondo e opacità. Senza quel parametro il riquadro compare solo all’avvio e alla fine di un aggiornamento.

## Cosa non fa

Non compra da solo. Non parla con un broker. Non ha un tetto di perdita, un calendario di borsa, né un controllo fra le quantità nel database e quelle su un conto. Il piano gratuito non segue la seduta mentre è aperta. I file S3 non si scaricano. La regola di vendita resta codice deterministico.

## Avvio

Le credenziali del database stanno in variabili d'ambiente, non nel codice: `DB_SERVER`, `DB_USERNAME`, `DB_PASSWORD`, `DB_NAME`, oppure le stesse con il suffisso del sito. L'applicazione è Flask, servita da un processo WSGI.

Dipendenze usate: Flask, mysql-connector, pandas, massive, matplotlib. yfinance resta installato, il giro non lo chiama più.
