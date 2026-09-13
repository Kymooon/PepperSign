package controller;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * Command bus singleton usato per mettere in coda i comandi destinati a Pepper.
 * La coda è FIFO e thread-safe.
 */
public final class PepperCommandBus {

    /**
     * Capacità massima della coda.
     * Puoi aumentarla o ridurla in base al comportamento desiderato.
     */
    private static final int DEFAULT_QUEUE_CAPACITY = 100;

    private static final PepperCommandBus INSTANCE = new PepperCommandBus();

    private final BlockingQueue<PepperCommand> queue =
            new LinkedBlockingQueue<PepperCommand>(DEFAULT_QUEUE_CAPACITY);

    private PepperCommandBus() {
        // Singleton
    }

    public static PepperCommandBus getInstance() {
        return INSTANCE;
    }

    /**
     * Inserisce un comando in coda.
     *
     * @param cmd comando da accodare
     * @return true se inserito, false se nullo o se la coda è piena
     */
    public boolean enqueue(PepperCommand cmd) {
        if (cmd == null) {
            return false;
        }
        return queue.offer(cmd);
    }

    /**
     * Restituisce e rimuove il prossimo comando, oppure null se la coda è vuota.
     */
    public PepperCommand poll() {
        return queue.poll();
    }

    /**
     * Variante con timeout utile se vuoi attendere un po' prima di restituire null.
     */
    public PepperCommand poll(long timeout, TimeUnit unit) throws InterruptedException {
        return queue.poll(timeout, unit);
    }

    /**
     * Restituisce il numero attuale di elementi in coda.
     */
    public int size() {
        return queue.size();
    }

    /**
     * Indica se la coda è vuota.
     */
    public boolean isEmpty() {
        return queue.isEmpty();
    }

    /**
     * Svuota completamente la coda.
     */
    public void clear() {
        queue.clear();
    }
}
