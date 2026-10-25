# Trading bot

Promemoria di quello che c’è già e di quello che abbiamo deciso di costruire.
Siamo in debug: la pagina, il grafico e l’archivio devono raccontare la stessa cosa
prima di aggiungere funzioni nuove.

Il file sta in `web/` insieme al codice. Apache manda tutto a Flask, quindi questo
testo non è una pagina del sito.

## Già costruito

- Accesso con utente e password. La password è cifrata. Si esce solo con **Esci**. La pagina di accesso è una card di Bootstrap.
- Barra blu fissa: nome, aggiorna prezzi, solo controllo vendite, menu con Preferenze ed Esci. Icone Lucide in `icons/`.
- Due schede Bootstrap, Volume e Storico. Il cambio di scheda non ricarica la pagina. Sotto restano posizioni, acquisto e transazioni.
- Volume: dimensione = volume dell’ultima seduta, colore = movimento del giorno (verde su, rosso giù, blu stabile). Sul riquadro c’è la sigla, oppure il nome della società se la sigla è di una o due lettere o se il riquadro è largo. Il `title` è sigla, società e percentuale, senza virgola: `ACN — Accenture -3.6%`.
- Storico: select dei titoli in archivio con il nome della società, periodi `1G` `1S` `1M` `3M` `6M` `YTD` (il `title` spiega Giorno, Settimana, Mese, Tre mesi, Sei mesi, Da inizio anno), linea o candele. Cambiare titolo, periodo o tipo sostituisce solo l’immagine.
- Il messaggio esce da sotto la barra, arrotondato e trasparente. Compare quando un aggiornamento parte e quando finisce, per i secondi della preferenza. Non compare a ogni apertura della pagina. Durante l’aggiornamento resta.
- Preferenze in una finestra Bootstrap, dal menu.
- Acquisto manuale. Vendita automatica del lotto quando il profitto netto, tolte commissione e imposta, raggiunge la soglia.
- Prezzi da Yahoo, a blocchi da 10. L’elenco è tutti i 500 dell’S&P 500, nell’ordine della tabella Wikipedia: è un ordine, non una classifica. Ogni giro ne scarica al massimo 100, solo quelli ancora indietro. Prima passano gli acquisti aperti e il titolo delle preferenze. Se un blocco torna senza barre, si attende 45 secondi, si riprova una volta, poi si continua. Il giro dopo riprende i rimasti.
- La prima volta un titolo riceve circa sei mesi. Poi si chiedono solo le ultime cinque sedute e si aggiungono. Le barre vecchie restano: lo storico si allunga in avanti, non all’indietro.
- Nel fine settimana la seduta di venerdì già salvata non viene riscaricata.
- Il grafico del volume, tra le barre in archivio con volume sopra zero, tiene i più redditizi sulle sedute della preferenza (20), fino al numero scelto (100, 200 o 500).
- `6M` chiede sempre 180 giorni. `YTD` chiede dal 1° gennaio dell’anno in corso e disegna solo i giorni presenti. Un anno di archivio non fa comparire da solo il pulsante di un anno.
- Cron nei giorni feriali, dall’apertura americana.
- Bootstrap 5.3 è in `static/`, non da una rete esterna. Favicon: il robot nell’indirizzo `data:` della pagina.
- Ultimo scarico completo: sei mesi, seduta di venerdì 23 ottobre 2026, circa 100 titoli. La sera del 25 ottobre il giro successivo ha avuto da Yahoo «troppe richieste» e ha scritto 0 barre.

## Da costruire

1. Fatto. Due schede, una sola visibile: **Volume** e **Storico**. Il cambio non ricarica la pagina.
2. Fatto. Barra con titolo, icone e menu.
3. Fatto. Cinque icone Lucide in `icons/`, con la licenza accanto.
4. Fatto. Il messaggio del ciclo compare all’avvio e alla fine, per i secondi della preferenza. Non a ogni apertura. Durante un aggiornamento resta.
5. Fatto. Preferenze in una finestra, aperte dal menu.
6. Fatto. Sotto il grafico: posizioni aperte e registra acquisto.
7. Fatto. Nello Storico, l’elenco dei titoli che hanno barre in archivio, con il nome della società.
8. Fatto. Intervalli `1G` `1S` `1M` `3M` `6M` `YTD`, con il significato nel `title`. Linea o candele, nella stessa scheda.
9. Uno, due, cinque, dieci anni e «sempre»: i pulsanti non crescono da soli con l’archivio. Prima serve uno scarico più lungo, poi i pulsanti.
10. Fatto. Sigla o nome sul riquadro. Nel `title`, sigla, società e percentuale.

11. Da vedere il 26 ottobre 2026, nei log: se il giro dei 100 titoli ancora indietro passa, o se Yahoo risponde di nuovo «troppe richieste». Da lì si decide come distanziare le chiamate.

## Decisioni già prese

- L’ingresso resta manuale finché il comportamento non è affidabile.
- Polygon si aggancia solo quando lo chiediamo noi, perché la simulazione è piena e Yahoo non basta.
- Il giro dei prezzi e la regola di vendita restano codice deterministico.
- Broker, rischio, calendario di borsa e controllo database-contro-conto vengono dopo, quando la simulazione regge. Sono il passo professionale, non questo riordino.
- Quattro o cinque icone nostre. Non si installano qui altri trading bot presi da GitHub per copiarne la pagina.
- Si scaricano tutti i 500, a giri da 100. Il grafico è ciò che riduce l’elenco. L’ordine alfabetico della tabella non è un criterio di scelta.
- I periodi restano `1G` `1S` `1M` `3M` `6M` `YTD` finché non c’è uno scarico più lungo.

## Backup e git

- Backup ISPConfig giornaliero, quattro copie. Si esclude solo `web/stats/*`. `private/` e il database restano nel backup: il git non li sostituisce.
- Repository git in `web/`, ramo `main`, remote privato `Stecnica/trading-bot`. Autore dei commit: Stecnica.
- Fuori dal repository: `private/`, `.htaccess` (contiene la password del database), `stats/`, `media/`, `__pycache__/`, i vecchi `index2.py` … `index6-OK.py` e le copie di `app.wsgi`, il file di specifiche in `private/` (contiene le credenziali).
- Il remote resta privato finché non si decide di aprirlo. Si può collaborare anche senza renderlo pubblico.
