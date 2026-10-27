# Trading bot

Promemoria di quello che c’è già e di quello che abbiamo deciso di costruire.
Siamo in debug: la pagina, il grafico e l’archivio devono raccontare la stessa cosa
prima di aggiungere funzioni nuove.

Il file sta in `web/` insieme al codice. Apache manda tutto a Flask, quindi questo
testo non è una pagina del sito.

## Già costruito

- Accesso con utente e password. La password è cifrata. Si esce solo con **Esci**. La pagina di accesso è una card di Bootstrap.
- Barra blu fissa: nome, poi Posizioni, Acquisto e Transazioni, poi aggiorna prezzi, solo controllo vendite, menu con Preferenze ed Esci. I pulsanti della barra sono alti 2rem. Icone Lucide in `icons/`.
- Due schede Bootstrap, Volume e Storico. Il cambio di scheda non ricarica la pagina. Posizioni, acquisto e transazioni sono tre pannelli della barra, aperti dal proprio pulsante.
- Volume: dimensione = volume dell’ultima seduta, colore = movimento del giorno (verde su, rosso giù, blu stabile). Sul riquadro c’è la sigla, oppure il nome della società se la sigla è di una o due lettere o se il riquadro è largo. Il `title` è sigla, società e percentuale, senza virgola: `ACN — Accenture -3.6%`.
- Storico: select dei titoli in archivio con il nome della società, periodi `1G` `1S` `1M` `3M` `6M` `YTD` `1A` `2A` (il `title` spiega Giorno, Settimana, Mese, Tre mesi, Sei mesi, Da inizio anno, Un anno, Due anni), linea o candele. Cambiare titolo, periodo o tipo sostituisce solo l’immagine.
- Il messaggio esce da sotto la barra, arrotondato e trasparente. Compare quando un aggiornamento parte e quando finisce, per i secondi della preferenza. Non compare a ogni apertura della pagina. Durante l’aggiornamento resta. `?anteprima=messaggi` lo tiene acceso e fa girare ogni 4 secondi i quattro stati, su tre righe: message, success, warning, alert. Serve a controllare testo, bordo, fondo e opacità.
- Preferenze in una finestra Bootstrap, dal menu.
- Acquisto manuale. Vendita automatica del lotto quando il profitto netto, tolte commissione e imposta, raggiunge la soglia.
- Prezzi da Massive, client ufficiale `massive`. Una chiamata REST è il riepilogo di un giorno intero del mercato USA; si tengono i 500 dell’elenco S&P 500. Il piano gratuito consente cinque chiamate al minuto, quindi fra una seduta e l’altra passano tredici secondi, e il giro prosegue finché ci sono sedute mancanti. Si parte dall’ultima seduta già chiusa a New York e si va indietro, fino a due anni. Una seduta senza barre, più vecchia di quella appena chiusa, non si richiede più. Le barre vecchie restano.
- Il giorno in corso non si chiede: il piano gratuito lo pubblica a fine seduta. I file S3 non si scaricano.
- Il grafico del volume, tra le barre in archivio con volume sopra zero, tiene i più redditizi sulle sedute della preferenza (20), fino al numero scelto (100, 200 o 500).
- `6M` chiede sempre 180 giorni. `YTD` chiede dal 1° gennaio dell’anno in corso. `1A` e `2A` chiedono 365 e 730 giorni. Si disegnano solo i giorni presenti. Cinque anni, dieci anni e «sempre» non compaiono finché l’archivio non arriva fin lì.
- Cron nei giorni feriali, dall’apertura americana.
- Bootstrap 5.3 è in `static/`, non da una rete esterna. Favicon: il robot nell’indirizzo `data:` della pagina.
- Ultimo scarico Yahoo che ha scritto barre: 27 ottobre 2026 alle 05:23. Da quel momento il giro usa Massive. Lo scarico del 27 ottobre 2026, chiuso alle 19:38, ha riempito l’archivio dal 28 ottobre 2024 al 26 ottobre 2026. Il 25 ottobre 2024 è fuori dai due anni del piano gratuito.

## Da costruire

1. Fatto. Due schede, una sola visibile: **Volume** e **Storico**. Il cambio non ricarica la pagina.
2. Fatto. Barra con titolo, icone e menu.
3. Fatto. Cinque icone Lucide in `icons/`, con la licenza accanto.
4. Fatto. Il messaggio del ciclo compare all’avvio e alla fine, per i secondi della preferenza. Non a ogni apertura. Durante un aggiornamento resta.
5. Fatto. Preferenze in una finestra, aperte dal menu.
6. Fatto. Posizioni aperte, registra un acquisto e ultime transazioni stanno nei pannelli della barra. L'esito dell'acquisto compare in cima al pannello Acquisto. Il messaggio del ciclo resta sotto la barra e il pannello parte sotto di lui.
7. Fatto. Nello Storico, l’elenco dei titoli che hanno barre in archivio, con il nome della società.
8. Fatto. Intervalli `1G` `1S` `1M` `3M` `6M` `YTD`, con il significato nel `title`. Linea o candele, nella stessa scheda.
9. Fatti `1A` e `2A`: l’archivio copre dal 28 ottobre 2024. Cinque anni, dieci anni e «sempre» restano fuori finché un piano non consegna quelle barre.
10. Fatto. Sigla o nome sul riquadro. Nel `title`, sigla, società e percentuale.

11. Visto il 26 ottobre 2026. Yahoo ha risposto «troppe richieste» per quasi tutta la sera. Distanziare ancora le chiamate non è la strada.
12. Fatto il collegamento REST del piano gratuito: una chiamata per il riepilogo di un giorno intero, filtrata sui 500. Resta Stocks Starter mensile, prima di giudicare la seduta aperta. I file S3 restano chiusi finché il piano non li include.

## Decisioni già prese

- L’ingresso resta manuale finché il comportamento non è affidabile.
- Massive (prima Polygon) è il fornitore dei prezzi. Account gratuito aperto il 27 ottobre 2026, e il giro lo chiama. Starter si prende mese per mese quando serve la seduta aperta; l'annuale e Advanced no, per ora.
- Il giro dei prezzi e la regola di vendita restano codice deterministico.
- Broker, rischio, calendario di borsa e controllo database-contro-conto vengono dopo, quando la simulazione regge. Sono il passo professionale, non questo riordino.
- Quattro o cinque icone nostre. Non si installano qui altri trading bot presi da GitHub per copiarne la pagina.
- Si scaricano tutti i 500, una seduta alla volta. Il grafico è ciò che riduce l’elenco. L’ordine alfabetico della tabella non è un criterio di scelta.
- I periodi sono `1G` `1S` `1M` `3M` `6M` `YTD` `1A` `2A`. Cinque anni, dieci anni e «sempre» si aggiungono quando l’archivio arriva fin lì.

## Backup e git

- Backup ISPConfig giornaliero, quattro copie. Si esclude solo `web/stats/*`. `private/` e il database restano nel backup: il git non li sostituisce.
- Repository git in `web/`, ramo `main`, remote privato `Stecnica/trading-bot`. Autore dei commit: Stecnica.
- Fuori dal repository: `private/`, `.htaccess` (contiene la password del database), `stats/`, `media/`, `__pycache__/`, i vecchi `index2.py` … `index6-OK.py` e le copie di `app.wsgi`, il file di specifiche in `private/` (contiene le credenziali).
- Il remote resta privato finché non si decide di aprirlo. Si può collaborare anche senza renderlo pubblico.
