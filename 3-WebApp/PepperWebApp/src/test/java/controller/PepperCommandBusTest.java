package controller;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import java.util.concurrent.atomic.AtomicLong;

import org.junit.Before;
import org.junit.Test;

/** Stati, scadenze e "robot collegato" della coda dei comandi, con un orologio simulato. */
public class PepperCommandBusTest {

    private final AtomicLong now = new AtomicLong(1000000L);
    private PepperCommandBus bus;

    @Before
    public void setUp() {
        bus = new PepperCommandBus(now::get, 30000L, 60000L, 5000L);
    }

    private void advance(long ms) {
        now.addAndGet(ms);
    }

    @Test
    public void comandoEseguitoConEsito() {
        PepperCommand cmd = PepperCommand.gesture("Ciao");
        assertTrue(bus.enqueue(cmd));
        assertNotNull(cmd.getId());
        assertEquals(PepperCommand.STATUS_QUEUED, bus.find(cmd.getId()).getStatus());

        PepperCommand sent = bus.poll();
        assertEquals(cmd.getId(), sent.getId());
        assertEquals(PepperCommand.STATUS_SENT, bus.find(cmd.getId()).getStatus());

        assertTrue(bus.complete(cmd.getId(), true, "gesture eseguita"));
        PepperCommand done = bus.find(cmd.getId());
        assertEquals(PepperCommand.STATUS_DONE, done.getStatus());
        assertEquals("gesture eseguita", done.getResultMessage());
        assertTrue(done.isFinal());
    }

    @Test
    public void comandoFallito() {
        PepperCommand cmd = PepperCommand.gesture("assente");
        bus.enqueue(cmd);
        bus.poll();
        bus.complete(cmd.getId(), false, "gestureId non mappato: assente");
        assertEquals(PepperCommand.STATUS_FAILED, bus.find(cmd.getId()).getStatus());
    }

    @Test
    public void ordineFifo() {
        PepperCommand a = PepperCommand.say("uno");
        PepperCommand b = PepperCommand.say("due");
        bus.enqueue(a);
        bus.enqueue(b);
        assertEquals(a.getId(), bus.poll().getId());
        assertEquals(b.getId(), bus.poll().getId());
        assertNull(bus.poll());
    }

    @Test
    public void comandoVecchioScadeEnonVieneInviato() {
        PepperCommand old = PepperCommand.say("vecchio");
        bus.enqueue(old);
        advance(31000L);
        PepperCommand fresh = PepperCommand.say("nuovo");
        bus.enqueue(fresh);
        assertEquals(fresh.getId(), bus.poll().getId());
        assertEquals(PepperCommand.STATUS_EXPIRED, bus.find(old.getId()).getStatus());
        assertNull(bus.poll());
    }

    @Test
    public void scadenzaVistaAncheDalTablet() {
        PepperCommand cmd = PepperCommand.say("ciao");
        bus.enqueue(cmd);
        advance(30001L);
        assertEquals(PepperCommand.STATUS_EXPIRED, bus.find(cmd.getId()).getStatus());
        assertEquals(0, bus.size());
    }

    @Test
    public void inviatoSenzaEsitoDiventaNonConfermatoENonVieneRimandato() {
        PepperCommand cmd = PepperCommand.gesture("ciao");
        bus.enqueue(cmd);
        bus.poll();
        advance(60001L);
        assertEquals(PepperCommand.STATUS_UNCONFIRMED, bus.find(cmd.getId()).getStatus());
        assertNull(bus.poll());          // non viene rimandato
    }

    @Test
    public void esitoTardivoCorreggeNonConfermato() {
        PepperCommand cmd = PepperCommand.gesture("ciao");
        bus.enqueue(cmd);
        bus.poll();
        advance(61000L);
        bus.find(cmd.getId());
        assertTrue(bus.complete(cmd.getId(), true, "ok"));
        assertEquals(PepperCommand.STATUS_DONE, bus.find(cmd.getId()).getStatus());
    }

    @Test
    public void esitoDuplicatoNonCambiaLoStato() {
        PepperCommand cmd = PepperCommand.gesture("ciao");
        bus.enqueue(cmd);
        bus.poll();
        bus.complete(cmd.getId(), true, "primo");
        bus.complete(cmd.getId(), false, "secondo");
        assertEquals(PepperCommand.STATUS_DONE, bus.find(cmd.getId()).getStatus());
        assertEquals("primo", bus.find(cmd.getId()).getResultMessage());
    }

    @Test
    public void idSconosciuto() {
        assertFalse(bus.complete("nessuno", true, ""));
        assertNull(bus.find("nessuno"));
        assertNull(bus.find(null));
    }

    @Test
    public void robotCollegatoSeFaPolling() {
        assertFalse(bus.isControllerOnline());          // mai visto
        bus.poll();
        assertTrue(bus.isControllerOnline());
        advance(4000L);
        assertTrue(bus.isControllerOnline());
        advance(2000L);
        assertFalse(bus.isControllerOnline());          // nessun polling da 6 s
    }

    @Test
    public void robotCollegatoMentreEsegueUnComando() {
        PepperCommand cmd = PepperCommand.gesture("ciao");
        bus.poll();
        bus.enqueue(cmd);
        bus.poll();                       // inviato: durante il gesto Controll non fa polling
        advance(20000L);
        assertTrue(bus.isControllerOnline());
        bus.complete(cmd.getId(), true, "ok");
        assertFalse(bus.isControllerOnline());
    }

    @Test
    public void comandoVuotoNonVieneAccodato() {
        assertFalse(bus.enqueue(PepperCommand.none()));
        assertFalse(bus.enqueue(null));
    }

    @Test
    public void codaPiena() {
        for (int i = 0; i < PepperCommandBus.DEFAULT_QUEUE_CAPACITY; i++) {
            assertTrue(bus.enqueue(PepperCommand.say("n" + i)));
        }
        assertFalse(bus.enqueue(PepperCommand.say("troppo")));
    }

    @Test
    public void storicoLimitato() {
        for (int i = 0; i < PepperCommandBus.HISTORY_MAX + 50; i++) {
            PepperCommand c = PepperCommand.say("n" + i);
            bus.enqueue(c);
            bus.poll();
            bus.complete(c.getId(), true, "");
        }
        PepperCommand last = PepperCommand.say("ultimo");
        bus.enqueue(last);
        assertNotNull(bus.find(last.getId()));
    }
}
