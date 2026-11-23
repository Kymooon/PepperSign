package controller;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;

/**
 * Coda dei comandi destinati a Pepper (singleton, FIFO, thread-safe) e registro
 * del loro stato.
 *
 * <ul>
 *   <li>{@link #enqueue}: il comando entra in coda (stato "queued") e riceve un id;</li>
 *   <li>{@link #poll}: Controll preleva il prossimo comando (stato "sent"); i comandi
 *       rimasti in coda oltre {@link #queueTtlMs} vengono scartati come "expired",
 *       cosi' il robot non esegue richieste vecchie dopo essere stato spento;</li>
 *   <li>{@link #complete}: Controll riporta l'esito ("done" / "failed");</li>
 *   <li>{@link #find}: lo stato di un comando per il tablet; un comando inviato e senza
 *       esito oltre {@link #confirmTimeoutMs} diventa "unconfirmed" e NON viene rimandato.</li>
 * </ul>
 *
 * Controll e' considerato collegato se ha fatto polling negli ultimi
 * {@link #onlineWindowMs} oppure sta eseguendo un comando (durante un gesto non fa polling).
 */
public final class PepperCommandBus {

    /** Capacita' massima della coda. */
    static final int DEFAULT_QUEUE_CAPACITY = 100;
    /** Un comando non prelevato entro questo tempo viene scartato. */
    static final long DEFAULT_QUEUE_TTL_MS = 30000L;
    /** Un comando inviato senza esito entro questo tempo diventa "non confermato". */
    static final long DEFAULT_CONFIRM_TIMEOUT_MS = 60000L;
    /** Controll e' collegato se ha fatto polling entro questo tempo. */
    static final long DEFAULT_ONLINE_WINDOW_MS = 5000L;
    /** I comandi conclusi restano consultabili per questo tempo. */
    static final long HISTORY_MS = 10L * 60L * 1000L;
    static final int HISTORY_MAX = 500;

    private static final PepperCommandBus INSTANCE = new PepperCommandBus(
            System::currentTimeMillis, DEFAULT_QUEUE_TTL_MS, DEFAULT_CONFIRM_TIMEOUT_MS, DEFAULT_ONLINE_WINDOW_MS);

    private final LongSupplier clock;
    private final long queueTtlMs;
    private final long confirmTimeoutMs;
    private final long onlineWindowMs;

    private final Deque<PepperCommand> queue = new ArrayDeque<PepperCommand>();
    private final Map<String, PepperCommand> registry = new LinkedHashMap<String, PepperCommand>();
    private long lastPollAt;

    PepperCommandBus(LongSupplier clock, long queueTtlMs, long confirmTimeoutMs, long onlineWindowMs) {
        this.clock = clock;
        this.queueTtlMs = queueTtlMs;
        this.confirmTimeoutMs = confirmTimeoutMs;
        this.onlineWindowMs = onlineWindowMs;
    }

    public static PepperCommandBus getInstance() {
        return INSTANCE;
    }

    /**
     * Inserisce un comando in coda.
     *
     * @return true se inserito, false se nullo, senza id o se la coda e' piena
     */
    public synchronized boolean enqueue(PepperCommand cmd) {
        if (cmd == null || cmd.getId() == null) {
            return false;
        }
        long now = clock.getAsLong();
        expireQueued(now);
        if (queue.size() >= DEFAULT_QUEUE_CAPACITY) {
            return false;
        }
        cmd.markQueued(now);
        queue.addLast(cmd);
        registry.put(cmd.getId(), cmd);
        trimHistory(now);
        notifyAll();
        return true;
    }

    /**
     * Restituisce il prossimo comando da eseguire (e lo segna come inviato),
     * oppure null se la coda e' vuota. Registra anche che Controll e' collegato.
     */
    public synchronized PepperCommand poll() {
        long now = clock.getAsLong();
        lastPollAt = now;
        expireQueued(now);
        PepperCommand cmd = queue.pollFirst();
        if (cmd != null) {
            cmd.markSent(now);
        }
        return cmd;
    }

    /** Come {@link #poll()}, ma attende fino a `timeout` se la coda e' vuota (per un futuro long-polling). */
    public synchronized PepperCommand poll(long timeout, TimeUnit unit) throws InterruptedException {
        long deadline = System.currentTimeMillis() + unit.toMillis(timeout);
        PepperCommand cmd = poll();
        while (cmd == null) {
            long left = deadline - System.currentTimeMillis();
            if (left <= 0) {
                return null;
            }
            wait(left);
            cmd = poll();
        }
        return cmd;
    }

    /**
     * Esito di un comando riportato da Controll.
     *
     * @return false se l'id non e' conosciuto
     */
    public synchronized boolean complete(String id, boolean ok, String message) {
        PepperCommand cmd = id == null ? null : registry.get(id);
        if (cmd == null) {
            return false;
        }
        // un esito arrivato tardi corregge anche un "non confermato"
        if (!cmd.isFinal() || PepperCommand.STATUS_UNCONFIRMED.equals(cmd.getStatus())) {
            cmd.markFinished(ok ? PepperCommand.STATUS_DONE : PepperCommand.STATUS_FAILED,
                    message, clock.getAsLong());
        }
        return true;
    }

    /** Comando con quell'id (con lo stato aggiornato alle scadenze), o null se sconosciuto. */
    public synchronized PepperCommand find(String id) {
        PepperCommand cmd = id == null ? null : registry.get(id);
        if (cmd != null) {
            refresh(cmd, clock.getAsLong());
        }
        return cmd;
    }

    /** True se Controll ha fatto polling di recente o sta eseguendo un comando. */
    public synchronized boolean isControllerOnline() {
        long now = clock.getAsLong();
        if (lastPollAt > 0 && now - lastPollAt <= onlineWindowMs) {
            return true;
        }
        for (PepperCommand cmd : registry.values()) {
            refresh(cmd, now);
            if (PepperCommand.STATUS_SENT.equals(cmd.getStatus())) {
                return true;
            }
        }
        return false;
    }

    /** Millisecondi dall'ultimo polling di Controll, -1 se non ha mai fatto polling. */
    public synchronized long millisSinceLastPoll() {
        return lastPollAt > 0 ? clock.getAsLong() - lastPollAt : -1L;
    }

    /** Numero di comandi in coda (non ancora prelevati). */
    public synchronized int size() {
        expireQueued(clock.getAsLong());
        return queue.size();
    }

    public synchronized boolean isEmpty() {
        return size() == 0;
    }

    /** Svuota la coda e il registro. */
    public synchronized void clear() {
        queue.clear();
        registry.clear();
        lastPollAt = 0;
    }

    // ------------------------------------------------------------ interni

    private void refresh(PepperCommand cmd, long now) {
        if (PepperCommand.STATUS_QUEUED.equals(cmd.getStatus()) && now - cmd.getTs() > queueTtlMs) {
            cmd.markFinished(PepperCommand.STATUS_EXPIRED,
                    "Il robot non ha prelevato il comando entro " + (queueTtlMs / 1000) + " s", now);
            queue.remove(cmd);
        } else if (PepperCommand.STATUS_SENT.equals(cmd.getStatus()) && now - cmd.getSentAt() > confirmTimeoutMs) {
            cmd.markFinished(PepperCommand.STATUS_UNCONFIRMED,
                    "Nessun esito dal robot entro " + (confirmTimeoutMs / 1000) + " s", now);
        }
    }

    private void expireQueued(long now) {
        Iterator<PepperCommand> it = queue.iterator();
        while (it.hasNext()) {
            PepperCommand cmd = it.next();
            if (now - cmd.getTs() > queueTtlMs) {
                cmd.markFinished(PepperCommand.STATUS_EXPIRED,
                        "Il robot non ha prelevato il comando entro " + (queueTtlMs / 1000) + " s", now);
                it.remove();
            }
        }
    }

    private void trimHistory(long now) {
        Iterator<PepperCommand> it = registry.values().iterator();
        while (it.hasNext() && registry.size() > 0) {
            PepperCommand cmd = it.next();
            refresh(cmd, now);
            boolean old = cmd.isFinal() && now - cmd.getFinishedAt() > HISTORY_MS;
            if (old || (registry.size() > HISTORY_MAX && cmd.isFinal())) {
                it.remove();
            }
        }
    }
}
