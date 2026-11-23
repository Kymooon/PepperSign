package controller;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import org.junit.Test;

/** Validazione del corpo di POST /api/pepper/result. */
public class PepperResultServletTest {

    private static void rejected(String raw) {
        try {
            PepperResultServlet.parse(raw);
            fail("doveva essere rifiutato: " + raw);
        } catch (IllegalArgumentException expected) {
            // ok
        }
    }

    @Test
    public void esitoValido() {
        PepperResultServlet.Result r = PepperResultServlet.parse("{\"id\":\"c1-x\",\"ok\":true,\"message\":\"detto\"}");
        assertEquals("c1-x", r.id);
        assertTrue(r.ok);
        assertEquals("detto", r.message);
    }

    @Test
    public void esitoFallitoSenzaMessaggio() {
        PepperResultServlet.Result r = PepperResultServlet.parse("{\"id\":\"c2\",\"ok\":false}");
        assertFalse(r.ok);
        assertEquals("", r.message);
    }

    @Test
    public void messaggioTroppoLungoTroncato() {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 2 * PepperResultServlet.MAX_MESSAGE; i++) {
            sb.append('x');
        }
        PepperResultServlet.Result r = PepperResultServlet.parse("{\"id\":\"c3\",\"ok\":true,\"message\":\"" + sb + "\"}");
        assertEquals(PepperResultServlet.MAX_MESSAGE, r.message.length());
    }

    @Test
    public void datiNonValidiRifiutati() {
        rejected(null);
        rejected("");
        rejected("non json");
        rejected("[1,2]");
        rejected("{\"ok\":true}");                              // id mancante
        rejected("{\"id\":\"  \",\"ok\":true}");                // id vuoto
        rejected("{\"id\":5,\"ok\":true}");                     // id non testo
        rejected("{\"id\":\"c\",\"ok\":{\"a\":1}}");            // ok non booleano (prima: HTTP 500)
        rejected("{\"id\":\"c\",\"ok\":\"true\"}");             // ok come testo
        rejected("{\"id\":\"c\"}");                             // ok mancante
        rejected("{\"id\":\"c\",\"ok\":true,\"message\":[1]}"); // message non testo
    }
}
