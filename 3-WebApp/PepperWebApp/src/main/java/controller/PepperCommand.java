package controller;

import java.util.Locale;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Comando da inviare a Pepper (SAY, ANIMATED_SAY, PLAY_GESTURE...).
 * Non esegue nessuna azione sul robot: e' un oggetto con i dati del comando
 * (tipo, testo, gesto) e il suo stato, che il {@link PepperCommandBus} aggiorna:
 *
 * <pre>
 *   queued --(Controll lo preleva da /api/pepper/next)--> sent --(esito da /api/pepper/result)--> done | failed
 *   queued --(non prelevato entro la scadenza)--> expired
 *   sent   --(nessun esito entro il tempo massimo)--> unconfirmed
 * </pre>
 */
public class PepperCommand {

    public static final String ACTION_SAY = "SAY";
    public static final String ACTION_ANIMATED_SAY = "ANIMATED_SAY";
    public static final String ACTION_PLAY_GESTURE = "PLAY_GESTURE";
    public static final String ACTION_NONE = "NONE";

    public static final String STATUS_QUEUED = "queued";
    public static final String STATUS_SENT = "sent";
    public static final String STATUS_DONE = "done";
    public static final String STATUS_FAILED = "failed";
    public static final String STATUS_EXPIRED = "expired";
    public static final String STATUS_UNCONFIRMED = "unconfirmed";

    private static final AtomicLong SEQUENCE = new AtomicLong();

    private String id;
    private String action;
    private String text;
    private String gestureId;
    private long ts;

    // Stato, scritto solo dal PepperCommandBus (sotto il suo lock) ma letto anche da
    // altri thread (risposte al tablet): volatile per vedere sempre il valore aggiornato.
    private volatile String status = STATUS_QUEUED;
    private volatile long sentAt;
    private volatile long finishedAt;
    private volatile String resultMessage;

    public PepperCommand() {
        // Costruttore vuoto utile per framework JSON Serializzazione e Deseralizzazione
    }

    public String getId() {
        return id;
    }

    public String getAction() {
        return action;
    }

    public String getText() {
        return text;
    }

    public String getGestureId() {
        return gestureId;
    }

    public long getTs() {
        return ts;
    }

    public String getStatus() {
        return status;
    }

    public long getSentAt() {
        return sentAt;
    }

    public long getFinishedAt() {
        return finishedAt;
    }

    public String getResultMessage() {
        return resultMessage;
    }

    /** True se lo stato non cambiera' piu' (eseguito, fallito, scaduto, non confermato). */
    public boolean isFinal() {
        return STATUS_DONE.equals(status) || STATUS_FAILED.equals(status)
                || STATUS_EXPIRED.equals(status) || STATUS_UNCONFIRMED.equals(status);
    }

    public boolean isSay() {
        return ACTION_SAY.equals(action);
    }

    public boolean isAnimatedSay() {return ACTION_ANIMATED_SAY.equals(action);}

    public boolean isGesture() {
        return ACTION_PLAY_GESTURE.equals(action);
    }

    public boolean isNone() {
        return ACTION_NONE.equals(action);
    }

    // ---- aggiornamenti di stato (usati dal PepperCommandBus) ----

    void markQueued(long now) {
        this.status = STATUS_QUEUED;
        this.ts = now;
    }

    void markSent(long now) {
        this.status = STATUS_SENT;
        this.sentAt = now;
    }

    void markFinished(String finalStatus, String message, long now) {
        this.status = finalStatus;
        this.resultMessage = message;
        this.finishedAt = now;
    }

    //Comando Say Semplice
    public static PepperCommand say(String text) {
        PepperCommand c = create(ACTION_SAY);
        c.text = normalizeText(text);
        return c;
    }

    // Comando Animated Say
    public static PepperCommand animatedSay(String text) {
        PepperCommand c = create(ACTION_ANIMATED_SAY);
        c.text = normalizeText(text);
        return c;
    }

    //Comando per inviare una gesture da riprodurrre
    public static PepperCommand gesture(String gestureId) {
        PepperCommand c = create(ACTION_PLAY_GESTURE);
        c.gestureId = normalizeGestureId(gestureId);
        return c;
    }

    //Comando vuoto (nessun comando in coda): non ha id e non viene registrato
    public static PepperCommand none() {
        PepperCommand c = new PepperCommand();
        c.action = ACTION_NONE;
        c.ts = System.currentTimeMillis();
        return c;
    }

    private static PepperCommand create(String action) {
        PepperCommand c = new PepperCommand();
        c.id = "c" + SEQUENCE.incrementAndGet() + "-" + Long.toString(System.currentTimeMillis(), 36);
        c.action = action;
        c.ts = System.currentTimeMillis();
        return c;
    }

    //Utility:
    private static String normalizeText(String value) {
        if (value == null) {
            return "";
        }
        return value.trim();
    }

    private static String normalizeGestureId(String value) {
        if (value == null) {
            return "";
        }
        return value.trim().toLowerCase(Locale.ROOT);
    }
}
