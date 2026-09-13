<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PepperSign</title>
    <link rel="stylesheet" href="<%= request.getContextPath() %>/css/style_main.css">
    <link rel="stylesheet" href="<%= request.getContextPath() %>/css/header.css">
    <link rel="stylesheet" href="<%= request.getContextPath() %>/css/footer.css">
    <link rel="stylesheet" href="<%= request.getContextPath() %>/css/welcome.css">
</head>
<body>
<div class="app-shell">

    <%@ include file="includes/header.jspf" %>

    <section class="pepper-interaction" aria-label="Interazione con Pepper">
        <div class="pepper-interaction-header">
            <div class="title-with-info">
                <h2 class="pepper-interaction-title">Interazione con Pepper</h2>
                <button class="info-btn" type="button" data-info="interazione" aria-label="Informazioni sezione Interazione con Pepper">i</button>
            </div>
        </div>

        <div class="pepper-interaction-body">
            <div class="pepper-status-box">
                <p class="pepper-status-note">
                    Premi per chiedere a Pepper un gesto.
                </p>
            </div>

            <div class="pepper-actions">
                <button id="speakButton" class="pepper-speak-btn" type="button">
                    <span class="speak-icon" aria-hidden="true">🎤</span>
                    <span class="speak-text">Parla con Pepper</span>
                </button>
            </div>
        </div>
    </section>

    <main class="page" role="main">
        <section class="gestures-section" aria-label="Archivio gesti">
            <div class="section-header">
                <div class="section-title-wrap">
                    <div class="title-with-info">
                        <h2>Gesti</h2>
                        <button class="info-btn" type="button" data-info="gesti" aria-label="Informazioni sezione Gesti">i</button>
                    </div>
                    <p class="section-subtitle">Seleziona un contenuto, riproducilo o prova ad eseguirlo.</p>
                </div>

                <div class="section-actions">
                    <button id="addButton" class="section-add-btn" type="button" title="Aggiungi nuovo gesto" aria-label="Aggiungi nuovo gesto">+</button>
                </div>
            </div>

            <div id="mediaGrid" class="media-grid" aria-live="polite">
                <p class="loading-state">Caricamento degli elementi...</p>
            </div>
        </section>
    </main>

    <div id="videoModal" class="modal" role="dialog" aria-modal="true" aria-label="Riproduzione video">
        <button class="close-btn" type="button" aria-label="Chiudi video">&times;</button>
        <video id="videoPlayer" controls autoplay playsinline></video>
    </div>

    <%@ include file="includes/welcome-modal.jspf" %>
    <%@ include file="includes/footer.jspf" %>

</div>

<noscript>
    <div class="page">
        <p class="empty-state">Per usare PepperSign è necessario abilitare JavaScript.</p>
    </div>
</noscript>

<script src="<%= request.getContextPath() %>/gestureTry.js"></script>
<script src="<%= request.getContextPath() %>/js/ps-core.js"></script>
<script src="<%= request.getContextPath() %>/js/ps-config.js"></script>
<script src="<%= request.getContextPath() %>/js/ps-state.js"></script>
<script src="<%= request.getContextPath() %>/js/ps-modal.js"></script>
<script src="<%= request.getContextPath() %>/js/ps-lesson.js"></script>
<script src="<%= request.getContextPath() %>/js/ps-media.js"></script>
<script src="<%= request.getContextPath() %>/js/ps-audio-pc.js"></script>
<script src="<%= request.getContextPath() %>/js/ps-pepper.js"></script>
<script src="<%= request.getContextPath() %>/js/ps-cards.js"></script>
<script src="<%= request.getContextPath() %>/js/ps-app.js"></script>
<script src="<%= request.getContextPath() %>/js/ps-welcome.js"></script>
<script src="<%= request.getContextPath() %>/js/ps-info-modal.js"></script>
<script src="<%= request.getContextPath() %>/js/ps-info.js"></script>

<script>
    (function () {
        var HOME_URL = "<%= request.getContextPath() %>/";
        var historyGuardActive = false;

        function getVideoModal() {
            return document.getElementById("videoModal");
        }

        function getVideoPlayer() {
            return document.getElementById("videoPlayer");
        }

        function isVideoModalOpen() {
            var modal = getVideoModal();

            if (!modal) {
                return false;
            }

            var style = window.getComputedStyle ? window.getComputedStyle(modal) : modal.currentStyle;

            if (!style) {
                return false;
            }

            return style.display !== "none" &&
                style.visibility !== "hidden" &&
                style.opacity !== "0";
        }

        function closeVideoModal() {
            var modal = getVideoModal();
            var video = getVideoPlayer();

            if (video) {
                try {
                    video.pause();
                    video.removeAttribute("src");
                    video.load();
                } catch (e) {}
            }

            if (modal) {
                modal.style.display = "none";
                modal.className = modal.className.replace(/\bis-open\b/g, "");
                modal.className = modal.className.replace(/\bopen\b/g, "");
                modal.className = modal.className.replace(/\bactive\b/g, "");
            }
        }

        function activateHistoryGuard() {
            if (!window.history || !window.history.pushState) {
                return;
            }

            if (!historyGuardActive) {
                history.replaceState({ page: "home" }, document.title, window.location.href);
                history.pushState({ page: "home-guard" }, document.title, window.location.href);
                historyGuardActive = true;
            }
        }

        activateHistoryGuard();

        window.addEventListener("popstate", function () {
            if (isVideoModalOpen()) {
                closeVideoModal();

                historyGuardActive = false;
                activateHistoryGuard();

                return;
            }

            window.location.replace(HOME_URL);
        });
    })();
</script>

</body>
</html>
