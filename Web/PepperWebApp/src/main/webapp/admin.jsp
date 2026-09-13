<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PepperSign - Impostazioni e test</title>

    <link rel="stylesheet" href="<%= request.getContextPath() %>/css/style_main.css">
    <link rel="stylesheet" href="<%= request.getContextPath() %>/css/header.css">
    <link rel="stylesheet" href="<%= request.getContextPath() %>/css/footer.css">
    <link rel="stylesheet" href="<%= request.getContextPath() %>/css/admin.css">
</head>
<body class="admin-page" data-context-path="<%= request.getContextPath() %>">
<div class="app-shell">

    <%@ include file="includes/header.jspf" %>

    <main class="page admin-main" role="main">
        <section class="admin-hero">
            <div class="admin-hero-text">
                <h1>Impostazioni e test rapidi</h1>
                <p>
                    Da questa pagina puoi verificare rapidamente se i servizi principali di PepperSign
                    sono raggiungibili, capire a cosa serve ogni modulo e inviare comandi di prova a Pepper.
                </p>
            </div>
            <div class="admin-hero-actions">
                <button id="runPassiveChecksBtn" class="admin-primary-btn" type="button">Verifica endpoint rapidi</button>
            </div>
        </section>

        <section class="admin-card admin-services-card" aria-label="Descrizione dei servizi">
            <div class="admin-card-header">
                <h2>Che cosa fa ogni servizio</h2>
                <p>
                    Questa sezione ti aiuta a riconoscere i servizi anche se non conosci il loro nome tecnico.
                    Così puoi capire subito quale test usare.
                </p>
            </div>

            <div class="admin-services-grid">
                <div class="admin-service-box">
                    <h3>ASR</h3>
                    <p><strong>Serve per:</strong> trascrivere l'audio dell'utente in testo.</p>
                    <p><strong>Quando usarlo:</strong> se vuoi verificare il riconoscimento vocale o i comandi parlati.</p>
                    <p class="admin-service-endpoint">Endpoint collegato: <span>/api/asr</span></p>
                </div>

                <div class="admin-service-box">
                    <h3>Media</h3>
                    <p><strong>Serve per:</strong> mostrare il catalogo di immagini e video disponibili nel sistema.</p>
                    <p><strong>Quando usarlo:</strong> se vuoi controllare se i contenuti sono stati caricati correttamente.</p>
                    <p class="admin-service-endpoint">Endpoint collegati: <span>/api/media</span> e <span>/media/*</span></p>
                </div>

                <div class="admin-service-box">
                    <h3>Lesson / Generation</h3>
                    <p><strong>Serve per:</strong> capire se un contenuto esiste già oppure se deve essere generato dal backend.</p>
                    <p><strong>Quando usarlo:</strong> se vuoi testare la ricerca o la generazione di un gesto/video.</p>
                    <p class="admin-service-endpoint">Endpoint collegato: <span>/api/lesson</span></p>
                </div>

                <div class="admin-service-box">
                    <h3>Pepper SAY</h3>
                    <p><strong>Serve per:</strong> far pronunciare a Pepper una frase di prova.</p>
                    <p><strong>Quando usarlo:</strong> se vuoi testare rapidamente il collegamento con la parte vocale del robot.</p>
                    <p class="admin-service-endpoint">Endpoint collegato: <span>/api/pepper/say</span></p>
                </div>

                <div class="admin-service-box">
                    <h3>Pepper GESTURE</h3>
                    <p><strong>Serve per:</strong> chiedere a Pepper di eseguire un gesto o un'animazione.</p>
                    <p><strong>Quando usarlo:</strong> se vuoi verificare che il robot o il servizio Pepper ricevano correttamente il comando.</p>
                    <p class="admin-service-endpoint">Endpoint collegati: <span>/api/pepper/gesture</span> e <span>/api/pepper/animatable</span></p>
                </div>

                <div class="admin-service-box">
                    <h3>TRY</h3>
                    <p><strong>Serve per:</strong> inviare un tentativo dell'utente, controllarne lo stato e recuperare lo skeleton video.</p>
                    <p><strong>Quando usarlo:</strong> se vuoi verificare il flusso di prova gesto e confronto col template.</p>
                    <p class="admin-service-endpoint">Endpoint collegato: <span>/api/try/*</span></p>
                </div>
            </div>
        </section>

        <section class="admin-card admin-status-card" aria-label="Stato servizi principali">
            <div class="admin-card-header">
                <h2>Stato servizi</h2>
                <p>Controllo veloce degli endpoint che si possono verificare senza far eseguire azioni al robot.</p>
            </div>

            <div class="admin-status-list">
                <div class="admin-status-row">
                    <div class="admin-status-info">
                        <strong>Catalogo media</strong>
                        <span class="admin-status-text">Controlla se il catalogo dei contenuti viene restituito correttamente.</span>
                        <span class="admin-status-path">GET /api/media</span>
                    </div>
                    <span id="statusMedia" class="admin-badge admin-badge-neutral">Non verificato</span>
                </div>

                <div class="admin-status-row">
                    <div class="admin-status-info">
                        <strong>Gesti animabili</strong>
                        <span class="admin-status-text">Controlla la lista dei gesti che Pepper può eseguire realmente.</span>
                        <span class="admin-status-path">GET /api/pepper/animatable</span>
                    </div>
                    <span id="statusAnimatable" class="admin-badge admin-badge-neutral">Non verificato</span>
                </div>

                <div class="admin-status-row">
                    <div class="admin-status-info">
                        <strong>Lesson / generation</strong>
                        <span class="admin-status-text">Test manuale del servizio che trova o genera un contenuto.</span>
                        <span class="admin-status-path">POST /api/lesson</span>
                    </div>
                    <span id="statusLesson" class="admin-badge admin-badge-neutral">Test manuale</span>
                </div>

                <div class="admin-status-row">
                    <div class="admin-status-info">
                        <strong>Pepper SAY</strong>
                        <span class="admin-status-text">Test manuale per accodare una frase da pronunciare.</span>
                        <span class="admin-status-path">POST /api/pepper/say</span>
                    </div>
                    <span id="statusSay" class="admin-badge admin-badge-neutral">Test manuale</span>
                </div>

                <div class="admin-status-row">
                    <div class="admin-status-info">
                        <strong>Pepper GESTURE</strong>
                        <span class="admin-status-text">Test manuale per inviare un gesto o un'animazione.</span>
                        <span class="admin-status-path">POST /api/pepper/gesture</span>
                    </div>
                    <span id="statusGesture" class="admin-badge admin-badge-neutral">Test manuale</span>
                </div>
            </div>

            <div class="admin-output-wrap">
                <pre id="passiveChecksOutput" class="admin-output">Premi “Verifica endpoint rapidi” per controllare media e gesti animabili.</pre>
            </div>
        </section>

        <div class="admin-tools-grid">
            <div class="admin-tools-row">
                <section class="admin-card admin-tool-card" aria-label="Test parlato Pepper">
                    <div class="admin-card-header">
                        <h2>Fai parlare Pepper</h2>
                        <p>Invia un comando rapido al bus di Pepper per verificare che il collegamento funzioni.</p>
                    </div>

                    <label class="admin-label" for="sayText">Testo da pronunciare</label>
                    <textarea id="sayText" class="admin-textarea" rows="4" placeholder="Scrivi qui il testo da far dire a Pepper...">Ciao, questo è un test rapido di PepperSign.</textarea>

                    <div class="admin-actions">
                        <button id="sendSayBtn" class="admin-primary-btn" type="button">Invia comando SAY</button>
                    </div>

                    <div class="admin-output-wrap">
                        <pre id="sayOutput" class="admin-output">Nessun comando inviato.</pre>
                    </div>
                </section>

                <section class="admin-card admin-tool-card" aria-label="Test gesto Pepper">
                    <div class="admin-card-header">
                        <h2>Fai eseguire un gesto</h2>
                        <p>Puoi scegliere un gesto dalla lista dei gesti animabili oppure scriverne uno manualmente.</p>
                    </div>

                    <label class="admin-label" for="gestureSelect">Gesto disponibile</label>
                    <select id="gestureSelect" class="admin-select">
                        <option value="">Caricamento lista gesti...</option>
                    </select>

                    <label class="admin-label" for="gestureCustom">Oppure scrivi un gestureId</label>
                    <input id="gestureCustom" class="admin-input" type="text" placeholder="Esempio: ciao">

                    <div class="admin-actions">
                        <button id="reloadGesturesBtn" class="admin-primary-btn" type="button">Ricarica lista</button>
                        <button id="sendGestureBtn" class="admin-primary-btn" type="button">Invia comando GESTURE</button>
                    </div>

                    <div class="admin-output-wrap">
                        <pre id="gestureOutput" class="admin-output">Nessun gesto inviato.</pre>
                    </div>
                </section>
            </div>

            <div class="admin-tools-row">
                <section class="admin-card admin-tool-card" aria-label="Test lesson e generazione">
                    <div class="admin-card-header">
                        <h2>Test lesson / generation</h2>
                        <p>Verifica se un contenuto è già disponibile oppure se il backend prova ad avviarne la generazione.</p>
                    </div>

                    <label class="admin-label" for="lessonTarget">Target da cercare/generare</label>
                    <input id="lessonTarget" class="admin-input" type="text" placeholder="Esempio: ciao">

                    <div class="admin-actions">
                        <button id="sendLessonBtn" class="admin-primary-btn" type="button">Invia test lesson</button>
                    </div>

                    <div class="admin-output-wrap">
                        <pre id="lessonOutput" class="admin-output">Nessun test eseguito.</pre>
                    </div>
                </section>

                <section class="admin-card admin-tool-card" aria-label="Test catalogo media">
                    <div class="admin-card-header">
                        <h2>Controllo media disponibili</h2>
                        <p>Recupera il catalogo dei media e mostra un riepilogo rapido utile per il debug.</p>
                    </div>

                    <div class="admin-actions">
                        <button id="loadMediaBtn" class="admin-primary-btn" type="button">Carica catalogo media</button>
                    </div>

                    <div class="admin-output-wrap">
                        <pre id="mediaOutput" class="admin-output">Catalogo non ancora caricato.</pre>
                    </div>
                </section>
            </div>

            <div class="admin-tools-row">
                <section class="admin-card admin-tool-card" aria-label="Modalità testing locale">
                    <div class="admin-card-header">
                        <h2>Modalità testing locale</h2>
                        <p>
                            Disabilita solo su questo browser i pulsanti “Prova gesto” ed “Esegui gesto”.
                            Utile se vuoi testare la web app dal PC senza inviare comandi al robot usato dal tablet.
                        </p>
                    </div>

                    <div class="admin-status-list">
                        <div class="admin-status-row">
                            <div class="admin-status-info">
                                <strong>Pulsanti utente</strong>
                                <span id="localGestureButtonsStatus" class="admin-status-text">
                                    Stato su questo dispositivo: caricamento...
                                </span>
                                <span class="admin-status-path">
                                    Impostazione salvata solo nel localStorage del browser corrente.
                                </span>
                            </div>
                            <span id="localGestureButtonsBadge" class="admin-badge admin-badge-neutral">Caricamento</span>
                        </div>
                    </div>

                    <div class="admin-actions">
                        <button id="toggleLocalGestureButtonsBtn" class="admin-primary-btn" type="button">
                            Caricamento...
                        </button>
                    </div>

                    <div class="admin-output-wrap">
                        <pre id="localGestureButtonsOutput" class="admin-output">Nessuna modifica eseguita.</pre>
                    </div>
                </section>

                <section class="admin-card admin-tool-card admin-reset-card" aria-label="Reset primo ingresso">
                    <div class="admin-card-header">
                        <h2>Reset primo ingresso</h2>
                        <p>
                            Cancella il flag del primo accesso usato dal popup di benvenuto, così puoi testarlo di nuovo senza dover svuotare manualmente i dati del browser.
                        </p>
                    </div>

                    <div class="admin-actions">
                        <button id="resetWelcomeBtn" class="admin-primary-btn" type="button">Reset popup primo ingresso</button>
                    </div>

                    <div class="admin-output-wrap">
                        <pre id="resetWelcomeOutput" class="admin-output">Nessun reset eseguito.</pre>
                    </div>
                </section>
            </div>
        </div>

        <section class="admin-card admin-notes-card" aria-label="Note operative">
            <div class="admin-card-header">
                <h2>Note utili</h2>
            </div>
            <ul class="admin-note-list">
                <li>I test “SAY” e “GESTURE” hanno effetto reale su Pepper o sul relativo servizio di backend.</li>
                <li>Il test lesson può restituire <strong>FOUND</strong> se il video esiste già oppure <strong>GENERATING</strong> se il backend avvia la generazione.</li>
                <li>Il reset del primo ingresso cancella sia il valore in <strong>localStorage</strong> sia il cookie di fallback usato dalla funzione di benvenuto.</li>
                <li>Questa pagina usa JavaScript ES5 e richieste XHR per restare compatibile con browser vecchi e tablet Android 5.</li>
                <li>La modalità testing locale non modifica il server: vale solo per il browser in cui viene attivata.</li>
            </ul>
        </section>
    </main>

    <%@ include file="includes/footer.jspf" %>
</div>

<script>
    window.PEPPERSIGN_CONTEXT_PATH = "<%= request.getContextPath() %>";
</script>

<script>
    (function () {
        "use strict";

        var STORAGE_KEY = "peppersign_disable_gesture_buttons";

        var statusText = document.getElementById("localGestureButtonsStatus");
        var badge = document.getElementById("localGestureButtonsBadge");
        var toggleBtn = document.getElementById("toggleLocalGestureButtonsBtn");
        var output = document.getElementById("localGestureButtonsOutput");

        function areButtonsDisabled() {
            try {
                return window.localStorage.getItem(STORAGE_KEY) === "1";
            } catch (e) {
                return false;
            }
        }

        function setButtonsDisabled(disabled) {
            try {
                window.localStorage.setItem(STORAGE_KEY, disabled ? "1" : "0");
                return true;
            } catch (e) {
                return false;
            }
        }

        function setBadge(enabled) {
            if (!badge) {
                return;
            }

            badge.className = "admin-badge " + (enabled ? "admin-badge-ok" : "admin-badge-warn");
            badge.textContent = enabled ? "Abilitati" : "Disabilitati";
        }

        function updateUI() {
            var disabled = areButtonsDisabled();

            if (!statusText || !toggleBtn) {
                return;
            }

            if (disabled) {
                statusText.textContent = "Stato su questo dispositivo: pulsanti disabilitati.";
                toggleBtn.textContent = "Riabilita Prova gesto ed Esegui gesto";
                setBadge(false);
            } else {
                statusText.textContent = "Stato su questo dispositivo: pulsanti abilitati.";
                toggleBtn.textContent = "Disabilita Prova gesto ed Esegui gesto";
                setBadge(true);
            }
        }

        if (toggleBtn) {
            toggleBtn.addEventListener("click", function () {
                var currentlyDisabled = areButtonsDisabled();
                var nextDisabled = !currentlyDisabled;
                var saved = setButtonsDisabled(nextDisabled);

                updateUI();

                if (output) {
                    if (!saved) {
                        output.textContent = "Errore: non è stato possibile salvare la preferenza nel localStorage.";
                        return;
                    }

                    output.textContent = nextDisabled
                        ? "Pulsanti disabilitati solo su questo dispositivo. Ricarica la home per vedere subito i tasti disabled."
                        : "Pulsanti riabilitati solo su questo dispositivo. Ricarica la home per vedere subito i tasti attivi.";
                }
            });
        }

        updateUI();
    })();
</script>

<script src="<%= request.getContextPath() %>/js/admin.js"></script>
</body>
</html>