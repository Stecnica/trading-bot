# Trading bot

Promemoria di quello che c’è già e di quello che abbiamo deciso di costruire.
Siamo in debug: la pagina, il grafico e l’archivio devono raccontare la stessa cosa
prima di aggiungere funzioni nuove.

Il file sta in `web/` insieme al codice. Apache manda tutto a Flask, quindi questo
testo non è una pagina del sito.

## Già costruito

- Accesso con utente e password. La password è cifrata. Si esce solo con **Esci**.
- Pagina: messaggio di stato, due pulsanti, grafico Volume e stato, storico, posizioni, acquisto, transazioni, preferenze.
- Volume e stato: dimensione = volume dell’ultima seduta, colore = movimento del giorno (verde su, rosso giù, blu stabile).
- Storico a linea del titolo scelto. Il disegno a candele c’è nel codice e si attiva dalla preferenza, non ha ancora una vista sua.
- Acquisto manuale. Vendita automatica del lotto quando il profitto netto, tolte commissione e imposta, raggiunge la soglia.
- Prezzi da Yahoo, a blocchi. Se un blocco non risponde, il giro continua e al giro dopo riprende i titoli rimasti indietro.
- Nel fine settimana la seduta di venerdì già salvata non viene riscaricata.
- Cron nei giorni feriali, dall’apertura americana.
- Ultimo scarico utile: storico di sei mesi, ultima seduta venerdì 23 ottobre 2026, 100 titoli nel grafico.

## Da costruire, in quest’ordine

La landing di adesso è un banco di prova: le sezioni stanno nell’ordine in cui sono state scritte. Si riordina così.

1. Due schede, una sola visibile: **Volume** e **Storico**. Il grafico occupa la pagina intera. Niente affiancamento: stretto, i nomi diventano illeggibili.
2. Barra in alto. A sinistra il titolo **Trading bot**. A destra due icone, aggiorna prezzi e controlla vendite, poi il menu con Preferenze e, in fondo, Esci. La frase lunga sta nel titolo del pulsante, quello che compare al passaggio del mouse.
3. Icone sul server, poche, non un catalogo esterno. La pagina rifiuta gli stili che arrivano da fuori.
4. Il messaggio di stato fa capolino e resta per i secondi indicati nelle preferenze, poi se ne va.
5. Preferenze in una finestra, aperte dal menu.
6. Sotto il grafico, sulla stessa pagina: posizioni aperte e registra acquisto. Restano visibili, non in una finestra.
7. Nello Storico, un elenco dei titoli che hanno barre in archivio (oggi un centinaio, non i cinquecento dell’elenco S&P 500).
8. Intervalli che i dati reggono già: settimana, mese, tre mesi, sei mesi, da inizio anno. Con barre giornaliere il giorno è un punto solo.
9. Uno, due, cinque, dieci anni e «sempre»: prima serve uno scarico più lungo, poi i pulsanti.
10. Le fettine sottili di Volume restano senza nome anche a piena pagina, perché il nome si omette se il rettangolo è troppo piccolo. Dopo: nome al passaggio del mouse o al clic.
11. Candele dentro la scheda Storico, come altro disegno dello stesso titolo.

## Decisioni già prese

- L’ingresso resta manuale finché il comportamento non è affidabile.
- Polygon si aggancia solo quando lo chiediamo noi, perché la simulazione è piena e Yahoo non basta.
- Il giro dei prezzi e la regola di vendita restano codice deterministico.
- Broker, rischio, calendario di borsa e controllo database-contro-conto vengono dopo, quando la simulazione regge. Sono il passo professionale, non questo riordino.
- Quattro o cinque icone nostre. Non si installano qui altri trading bot presi da GitHub per copiarne la pagina.

## Backup e git

- Backup ISPConfig giornaliero, quattro copie. Si esclude solo `web/stats/*`. `private/` e il database restano nel backup: il git non li sostituisce.
- Repository git in `web/`, ramo `main`, remote privato `Stecnica/trading-bot`. Autore dei commit: Stecnica.
- Fuori dal repository: `private/`, `.htaccess` (contiene la password del database), `stats/`, `media/`, `__pycache__/`, i vecchi `index2.py` … `index6-OK.py` e le copie di `app.wsgi`, il file di specifiche in `private/` (contiene le credenziali).
- Il remote resta privato finché non si decide di aprirlo. Si può collaborare anche senza renderlo pubblico.
